# 목적: /api/f006 엔드포인트 라우터 — F006 채팅 기반 콘텐츠 작업 CRUD API
# F004와 달리 topic_select 엔드포인트 없음 (STAGE_01_INPUT이 자동 확정)
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import get_db
from schemas.f006 import (
    F006ApproveRequest,
    F006ContentJobListResponse,
    F006ContentJobResponse,
    F006JobCreateRequest,
    F006ScriptRerunRequest,
    F006StageRejectRequest,
    F006StageResponse,
    F006StageRetryRequest,
)
from services.f006_service import f006_service
from services.youtube_uploader import get_access_token, load_youtube_credentials, upload_video

router = APIRouter(prefix="/api/f006", tags=["f006"])


# ── content_jobs CRUD ─────────────────────────────────────────────

@router.post("/jobs", response_model=F006ContentJobResponse, status_code=201)
async def create_job(
    request: F006JobCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> F006ContentJobResponse:
    """새 F006 콘텐츠 작업을 생성하고 오케스트레이터를 독립 프로세스로 실행한다."""
    job = await f006_service.create_job(db, request)
    return F006ContentJobResponse.model_validate(job)


@router.get("/jobs", response_model=F006ContentJobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    cursor: Optional[int] = Query(default=None, description="마지막 수신 job id (첫 페이지는 생략)"),
    status: Optional[str] = Query(default=None, description="상태 필터 (PENDING/RUNNING/DONE/FAILED/CANCELLED/PENDING_APPROVAL)"),
    db: aiosqlite.Connection = Depends(get_db),
) -> F006ContentJobListResponse:
    """F006 content_jobs 목록을 최신 순(id DESC)으로 반환한다. cursor 기반 페이징."""
    items, next_cursor, has_more = await f006_service.list_jobs(
        db, limit=limit, cursor=cursor, status=status
    )
    return F006ContentJobListResponse(
        items=[F006ContentJobResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/jobs/{job_id}", response_model=F006ContentJobResponse)
async def get_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> F006ContentJobResponse:
    """ID로 F006 content_job 단건을 조회한다. 스테이지 목록 포함."""
    job = await f006_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    return F006ContentJobResponse.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """F006 content_job과 연관 stages를 DB에서 완전 삭제한다."""
    deleted = await f006_service.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")


# ── stages 조회 및 제어 ──────────────────────────────────────────

@router.get("/jobs/{job_id}/stages", response_model=list[F006StageResponse])
async def list_stages(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> list[F006StageResponse]:
    """job_id에 속한 모든 F006 스테이지를 stage_order ASC로 반환한다."""
    # job 존재 여부 확인
    job = await f006_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    stages = await f006_service.list_stages(db, job_id)
    return [F006StageResponse.model_validate(s) for s in stages]


@router.get("/jobs/{job_id}/stages/{stage_id}", response_model=F006StageResponse)
async def get_stage(
    job_id: int,
    stage_id: str,
    db: aiosqlite.Connection = Depends(get_db),
) -> F006StageResponse:
    """job_id + stage_id로 F006 스테이지 단건을 조회한다."""
    stage = await f006_service.get_stage(db, job_id, stage_id)
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id}의 Stage {stage_id} 를 찾을 수 없습니다.",
        )
    return F006StageResponse.model_validate(stage)


@router.post("/jobs/{job_id}/stages/{stage_id}/retry", status_code=202)
async def retry_stage(
    job_id: int,
    stage_id: str,
    request: F006StageRetryRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """F006 스테이지를 PENDING 상태로 리셋하고 override_params를 input_data에 반영한다."""
    stage = await f006_service.get_stage(db, job_id, stage_id)
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
    # job 상태를 RUNNING으로 복구 (FAILED -> RUNNING)
    await db.execute(
        "UPDATE content_jobs SET status = 'RUNNING', finished_at = NULL WHERE id = ?",
        (job_id,),
    )
    await db.commit()

    # 오케스트레이터 재기동 — DONE 스테이지는 건너뛰고 PENDING 스테이지부터 실행
    f006_service._spawn_orchestrator(job_id)

    return {"message": f"Stage {stage_id} 재시도가 시작되었습니다.", "job_id": job_id}


@router.post("/jobs/{job_id}/stages/{stage_id}/reject", status_code=202)
async def reject_stage(
    job_id: int,
    stage_id: str,
    request: F006StageRejectRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """현재 F006 스테이지를 REJECTED로 표시하고 rejection_target 스테이지를 PENDING으로 리셋한다."""
    stage = await f006_service.get_stage(db, job_id, stage_id)
    if stage is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id}의 Stage {stage_id} 를 찾을 수 없습니다.",
        )

    # 현재 스테이지를 REJECTED로 업데이트
    await f006_service.update_stage_status(
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
        target_stage = await f006_service.get_stage(db, job_id, target_id)
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
    request: F006ApproveRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """PENDING_APPROVAL 상태인 F006 job을 YouTube에 직접 업로드하고 DONE 처리한다.

    처리 흐름:
      1. STAGE_05 output에서 video_file_path 획득
      2. STAGE_06 output에서 seo_metadata 획득 (final_* 파라미터로 오버라이드 가능)
      3. config.json 또는 환경변수에서 YouTube 인증 정보 로드
      4. access_token 갱신
      5. YouTube API로 영상 업로드
      6. STAGE_06 output_data 갱신 (youtube_video_id, youtube_url, upload_status)
      7. content_jobs.youtube_video_id 갱신, status = 'DONE'
    """
    from datetime import datetime, timezone

    job = await f006_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    if job["status"] != "PENDING_APPROVAL":
        raise HTTPException(
            status_code=400,
            detail=f"PENDING_APPROVAL 상태인 작업만 승인할 수 있습니다. 현재 상태: {job['status']}",
        )

    # ── STAGE_05 output -> video_file_path ──
    stage_05 = await f006_service.get_stage(db, job_id, "STAGE_05_EDIT")
    if not stage_05 or not stage_05.get("output_data"):
        raise HTTPException(status_code=400, detail="STAGE_05_EDIT 출력이 없습니다. 편집 스테이지가 완료됐는지 확인하세요.")
    try:
        s05_out: dict = json.loads(stage_05["output_data"])
    except json.JSONDecodeError:
        s05_out = {}
    video_file_path: Optional[str] = s05_out.get("video_file_path")
    if not video_file_path:
        raise HTTPException(status_code=400, detail="STAGE_05 출력에 video_file_path가 없습니다.")

    # ── STAGE_06 output -> seo_metadata ──
    stage_06 = await f006_service.get_stage(db, job_id, "STAGE_06_UPLOAD")
    if not stage_06 or not stage_06.get("output_data"):
        raise HTTPException(status_code=400, detail="STAGE_06_UPLOAD 출력이 없습니다.")
    try:
        s06_out: dict = json.loads(stage_06["output_data"])
    except json.JSONDecodeError:
        s06_out = {}

    seo: dict = s06_out.get("seo_metadata", {})
    # 사용자 오버라이드 적용 (final_title 등)
    title: str = request.final_title or seo.get("title", "유튜브 영상")
    description: str = request.final_description or seo.get("description", "")
    tags: list[str] = request.final_tags or seo.get("tags", [])
    category: str = seo.get("category", "28")
    # privacy: initial_params -> stage06 output -> 기본값 "private" 순으로 탐색
    _initial: dict = {}
    if isinstance(job, dict) and job.get("initial_params"):
        try:
            _initial = json.loads(job["initial_params"])
        except Exception:
            pass
    privacy: str = s06_out.get("privacy") or _initial.get("privacy", "private")

    # ── YouTube 인증 정보 로드 ──
    try:
        creds = load_youtube_credentials()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # ── access_token 갱신 ──
    try:
        access_token = await get_access_token(
            creds["client_id"], creds["client_secret"], creds["refresh_token"]
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"YouTube 인증 실패: {e}")

    # ── YouTube 업로드 ──
    try:
        youtube_video_id = await upload_video(
            video_path=video_file_path,
            title=title,
            description=description,
            tags=tags,
            category=category,
            privacy=privacy,
            access_token=access_token,
            job_id=job_id,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"YouTube 업로드 실패: {e}")

    youtube_url = f"https://youtu.be/{youtube_video_id}"
    now = datetime.now(timezone.utc).isoformat()

    # ── STAGE_06 output_data 갱신 ──
    s06_out.update({
        "upload_status": "UPLOADED",
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
        "approved_at": now,
        "final_title": title,
    })
    if request.final_title:
        s06_out["seo_metadata"] = {**seo, "title": title, "description": description, "tags": tags}

    await db.execute(
        "UPDATE stages SET output_data = ?, status = 'DONE', finished_at = ? "
        "WHERE job_id = ? AND stage_id = 'STAGE_06_UPLOAD'",
        (json.dumps(s06_out, ensure_ascii=False), now, job_id),
    )

    # ── content_jobs 갱신 ──
    await db.execute(
        "UPDATE content_jobs SET status = 'DONE', youtube_video_id = ?, finished_at = ? WHERE id = ?",
        (youtube_video_id, now, job_id),
    )
    await db.commit()

    return {
        "message": f"Job {job_id} YouTube 업로드 완료.",
        "job_id": job_id,
        "youtube_video_id": youtube_video_id,
        "youtube_url": youtube_url,
    }


# ── 스크립트 수정 후 TTS부터 재생성 ──────────────────────────────────

@router.post("/jobs/{job_id}/rerun-from-tts", status_code=202)
async def rerun_from_tts(
    job_id: int,
    request: F006ScriptRerunRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """STAGE_02 스크립트를 수정하고 STAGE_03_TTS부터 재실행한다.

    처리 흐름:
      1. STAGE_02 output_data의 script_text (+ 선택적 slides) 업데이트
      2. STAGE_03~STAGE_06을 PENDING으로 리셋
      3. content_jobs.status = RUNNING
      4. 오케스트레이터 재기동 (STAGE_01/02는 DONE이므로 자동 스킵)
    """
    from datetime import datetime, timezone

    job = await f006_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id}를 찾을 수 없습니다.")

    # STAGE_02 output_data 로드
    stage_02 = await f006_service.get_stage(db, job_id, "STAGE_02_SCRIPT")
    if not stage_02 or not stage_02.get("output_data"):
        raise HTTPException(status_code=400, detail="STAGE_02_SCRIPT 출력이 없습니다. 스크립트 생성 완료 후 수정 가능합니다.")

    try:
        s02_out: dict = json.loads(stage_02["output_data"])
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="STAGE_02 output_data JSON 파싱 실패")

    # script_text 업데이트 (slides는 전달 시에만 갱신)
    s02_out["script_text"] = request.script_text
    if request.slides is not None:
        s02_out["slides"] = request.slides

    now = datetime.now(timezone.utc).isoformat()

    # STAGE_02 output_data 저장
    await db.execute(
        "UPDATE stages SET output_data = ? WHERE job_id = ? AND stage_id = 'STAGE_02_SCRIPT'",
        (json.dumps(s02_out, ensure_ascii=False), job_id),
    )

    # STAGE_03~06 PENDING 리셋
    for sid in ("STAGE_03_TTS", "STAGE_04_VIDEO_GEN", "STAGE_05_EDIT", "STAGE_06_UPLOAD"):
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
            (job_id, sid),
        )

    # content_jobs RUNNING 전환
    await db.execute(
        "UPDATE content_jobs SET status = 'RUNNING', finished_at = NULL, current_stage = 'STAGE_03_TTS' WHERE id = ?",
        (job_id,),
    )
    await db.commit()

    # 오케스트레이터 재기동 — STAGE_01/02는 DONE이므로 자동 스킵
    f006_service._spawn_orchestrator(job_id)

    return {"message": "STAGE_03_TTS부터 재생성이 시작되었습니다.", "job_id": job_id}


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
