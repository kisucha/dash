# 목적: /api/f001 엔드포인트 라우터 — F001 콘텐츠 작업 CRUD API
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import get_db
from schemas.f001 import (
    ApproveRequest,
    ContentJobListResponse,
    ContentJobResponse,
    F001JobCreateRequest,
    StageRejectRequest,
    StageResponse,
    StageRetryRequest,
    TopicSelectRequest,
)
from schemas.task import TaskListResponse, TaskResponse
from services.f001_service import f001_service
from services.task_service import task_service

router = APIRouter(prefix="/api/f001", tags=["f001"])


# ── content_jobs CRUD ─────────────────────────────────────────────

@router.post("/jobs", response_model=ContentJobResponse, status_code=201)
async def create_job(
    request: F001JobCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ContentJobResponse:
    """새 F001 콘텐츠 작업을 생성하고 오케스트레이터를 독립 프로세스로 실행한다."""
    job = await f001_service.create_job(db, request)
    return ContentJobResponse.model_validate(job)


@router.get("/jobs", response_model=ContentJobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    cursor: Optional[int] = Query(default=None, description="마지막 수신 job id (첫 페이지는 생략)"),
    status: Optional[str] = Query(default=None, description="상태 필터 (PENDING/RUNNING/DONE/FAILED/CANCELLED/PENDING_APPROVAL)"),
    db: aiosqlite.Connection = Depends(get_db),
) -> ContentJobListResponse:
    """content_jobs 목록을 최신 순(id DESC)으로 반환한다. cursor 기반 페이징."""
    items, next_cursor, has_more = await f001_service.list_jobs(
        db, limit=limit, cursor=cursor, status=status
    )
    return ContentJobListResponse(
        items=[ContentJobResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/jobs/{job_id}", response_model=ContentJobResponse)
async def get_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> ContentJobResponse:
    """ID로 content_job 단건을 조회한다. 스테이지 목록 포함."""
    job = await f001_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    return ContentJobResponse.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """content_job과 연관 stages를 DB에서 완전 삭제한다."""
    deleted = await f001_service.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")


# ── stages 조회 및 제어 ──────────────────────────────────────────

@router.get("/jobs/{job_id}/stages", response_model=list[StageResponse])
async def list_stages(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> list[StageResponse]:
    """job_id에 속한 모든 스테이지를 stage_order ASC로 반환한다."""
    # job 존재 여부 확인
    job = await f001_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    stages = await f001_service.list_stages(db, job_id)
    return [StageResponse.model_validate(s) for s in stages]


@router.get("/jobs/{job_id}/stages/{stage_id}", response_model=StageResponse)
async def get_stage(
    job_id: int,
    stage_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> StageResponse:
    """job_id + stage_id로 스테이지 단건을 조회한다."""
    stage = await f001_service.get_stage(db, job_id, stage_id)
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id}의 Stage {stage_id} 를 찾을 수 없습니다.",
        )
    return StageResponse.model_validate(stage)


@router.post("/jobs/{job_id}/stages/{stage_id}/retry", status_code=202)
async def retry_stage(
    job_id: int,
    stage_id: str,
    request: StageRetryRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """스테이지를 PENDING 상태로 리셋하고 override_params를 input_data에 반영한다."""
    stage = await f001_service.get_stage(db, job_id, stage_id)
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id}의 Stage {stage_id} 를 찾을 수 없습니다.",
        )

    # override_params가 있으면 기존 input_data에 병합
    input_data: Optional[str] = stage.get("input_data")
    if request.override_params:
        existing: dict = {}
        if input_data:
            try:
                existing = json.loads(input_data)
            except json.JSONDecodeError:
                existing = {}
        existing.update(request.override_params)
        input_data = json.dumps(existing, ensure_ascii=False)

    # retry_count 증가
    await db.execute(
        """
        UPDATE stages
        SET status = 'PENDING',
            retry_count = retry_count + 1,
            output_data = NULL,
            rejection_reason = NULL,
            started_at = NULL,
            finished_at = NULL,
            input_data = COALESCE(?, input_data)
        WHERE job_id = ? AND stage_id = ?
        """,
        (input_data, job_id, stage_id),
    )
    # job 상태를 RUNNING으로 복구 (FAILED → RUNNING)
    await db.execute(
        "UPDATE content_jobs SET status = 'RUNNING', finished_at = NULL WHERE id = ?",
        (job_id,),
    )
    await db.commit()

    # 오케스트레이터 재기동 — DONE 스테이지는 건너뛰고 PENDING 스테이지부터 실행
    f001_service._spawn_orchestrator(job_id)

    return {"message": f"Stage {stage_id} 재시도가 시작되었습니다.", "job_id": job_id}


@router.post("/jobs/{job_id}/stages/{stage_id}/reject", status_code=202)
async def reject_stage(
    job_id: int,
    stage_id: str,
    request: StageRejectRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """현재 스테이지를 REJECTED로 표시하고 rejection_target 스테이지를 PENDING으로 리셋한다."""
    stage = await f001_service.get_stage(db, job_id, stage_id)
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id}의 Stage {stage_id} 를 찾을 수 없습니다.",
        )

    # 현재 스테이지를 REJECTED로 업데이트
    await f001_service.update_stage_status(
        db,
        job_id,
        stage_id,
        status="REJECTED",
        rejection_reason=request.rejection_reason,
        rejection_target=request.rejection_target,
    )

    # rejection_target 스테이지가 있으면 PENDING으로 리셋
    target_id = request.rejection_target
    if target_id:
        target_stage = await f001_service.get_stage(db, job_id, target_id)
        if target_stage:
            await db.execute(
                """
                UPDATE stages
                SET status = 'PENDING',
                    output_data = NULL,
                    rejection_reason = NULL,
                    started_at = NULL,
                    finished_at = NULL
                WHERE job_id = ? AND stage_id = ?
                """,
                (job_id, target_id),
            )
            await db.commit()

    return {
        "message": f"Stage {stage_id} 반송 처리 완료.",
        "job_id": job_id,
        "rejection_target": target_id,
    }


# ── 업로드 승인 ───────────────────────────────────────────────────

@router.post("/jobs/{job_id}/approve", status_code=202)
async def approve_job(
    job_id: int,
    request: ApproveRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """PENDING_APPROVAL 상태인 job을 RUNNING으로 전환해 업로드를 트리거한다."""
    job = await f001_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    if job["status"] != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"PENDING_APPROVAL 상태인 작업만 승인할 수 있습니다. 현재 상태: {job['status']}",
        )

    # 승인 정보를 STAGE_06 input_data에 병합
    approve_data = {}
    if request.final_title:
        approve_data["final_title"] = request.final_title
    if request.final_description:
        approve_data["final_description"] = request.final_description
    if request.final_tags:
        approve_data["final_tags"] = request.final_tags

    if approve_data:
        stage_06 = await f001_service.get_stage(db, job_id, "STAGE_06_UPLOAD")
        if stage_06:
            existing: dict = {}
            if stage_06.get("input_data"):
                try:
                    existing = json.loads(stage_06["input_data"])
                except json.JSONDecodeError:
                    existing = {}
            existing.update(approve_data)
            await db.execute(
                "UPDATE stages SET input_data = ? WHERE job_id = ? AND stage_id = 'STAGE_06_UPLOAD'",
                (json.dumps(existing, ensure_ascii=False), job_id),
            )

    # job 상태를 RUNNING으로 전환
    await db.execute(
        "UPDATE content_jobs SET status = 'RUNNING' WHERE id = ?",
        (job_id,),
    )
    await db.commit()

    return {"message": f"Job {job_id} 업로드 승인 완료.", "job_id": job_id}


# ── 주제 선택 ─────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/topics")
async def get_topics(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """STAGE_01_RESEARCH output_data에서 topics 배열을 반환한다."""
    job = await f001_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")

    stage = await f001_service.get_stage(db, job_id, "STAGE_01_RESEARCH")
    if stage is None or not stage.get("output_data"):
        return {"job_id": job_id, "topics": [], "message": "STAGE_01_RESEARCH 결과가 아직 없습니다."}

    try:
        output = json.loads(stage["output_data"])
        topics = output.get("topics", [])
    except json.JSONDecodeError:
        topics = []

    return {"job_id": job_id, "topics": topics}


@router.post("/jobs/{job_id}/topics/{topic_rank}/select")
async def select_topic(
    job_id: int,
    topic_rank: int,
    request: TopicSelectRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """STAGE_01 output_data에 selected_topic을 기록하고 STAGE_02를 PENDING으로 트리거한다."""
    job = await f001_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")

    stage_01 = await f001_service.get_stage(db, job_id, "STAGE_01_RESEARCH")
    if stage_01 is None:
        raise HTTPException(status_code=404, detail="STAGE_01_RESEARCH 를 찾을 수 없습니다.")

    # STAGE_01 output_data에 selected_topic 기록
    output: dict = {}
    if stage_01.get("output_data"):
        try:
            output = json.loads(stage_01["output_data"])
        except json.JSONDecodeError:
            output = {}

    # selected_topic은 문자열로 저장 — 스테이지 프롬프트에서 직접 삽입되므로 단순 title 사용
    output["selected_topic"] = request.selected_topic_title
    output["selected_topic_rank"] = topic_rank
    await db.execute(
        "UPDATE stages SET output_data = ? WHERE job_id = ? AND stage_id = 'STAGE_01_RESEARCH'",
        (json.dumps(output, ensure_ascii=False), job_id),
    )

    # STAGE_02를 PENDING으로 리셋
    await db.execute(
        """
        UPDATE stages
        SET status = 'PENDING', started_at = NULL, finished_at = NULL
        WHERE job_id = ? AND stage_id = 'STAGE_02_SCRIPT'
        """,
        (job_id,),
    )
    # job을 RUNNING으로 복구 (WAITING → RUNNING)
    await db.execute(
        "UPDATE content_jobs SET status = 'RUNNING' WHERE id = ?",
        (job_id,),
    )
    await db.commit()

    # 오케스트레이터 재기동 — STAGE_01은 DONE이므로 건너뛰고 STAGE_02부터 실행
    f001_service._spawn_orchestrator(job_id)

    return {
        "message": f"주제 선택 완료. 오케스트레이터가 STAGE_02부터 재시작됩니다.",
        "job_id": job_id,
        "selected_topic": output["selected_topic"],
    }


# ── YouTube 쿼터 조회 ─────────────────────────────────────────────

@router.get("/youtube/quota")
async def get_youtube_quota(
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """settings 테이블의 youtube_quota_used_today 값을 반환한다."""
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'youtube_quota_used_today'",
    )
    row = await cursor.fetchone()
    quota_used = int(row["value"]) if row and row["value"] else 0
    return {"quota_used_today": quota_used, "quota_limit": 10000}


# ── 레거시 F001 이력 조회 ─────────────────────────────────────────

@router.get("/legacy", response_model=TaskListResponse)
async def list_legacy_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: Optional[int] = Query(default=None, description="마지막 수신 task id"),
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskListResponse:
    """기존 tasks 테이블에서 F001 이력을 cursor 페이징으로 반환한다."""
    items, next_cursor, has_more = await task_service.list_tasks(
        db, limit=limit, cursor=cursor, feature_id="F001"
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# ── 레거시 마이그레이션 ───────────────────────────────────────────

@router.post("/migrate-legacy", status_code=202)
async def migrate_legacy() -> dict:
    """레거시 tasks → content_jobs 마이그레이션 (Phase 5 구현 예정)."""
    return {"message": "마이그레이션 기능은 Phase 5에서 구현됩니다."}
