# 목적: /api/f007 엔드포인트 라우터 — F007 YouTube 자동화 파이프라인 CRUD API
# channel_type(finance/language) 쿼리 필터 지원
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import get_db
from schemas.f007 import (
    F007ContentJobListResponse,
    F007ContentJobResponse,
    F007JobCreateRequest,
)
from services.f007_service import f007_service

router = APIRouter(prefix="/api/f007", tags=["f007"])


# ── content_jobs CRUD ─────────────────────────────────────────────

@router.post("/jobs", response_model=F007ContentJobResponse, status_code=201)
async def create_job(
    request: F007JobCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> F007ContentJobResponse:
    """새 F007 콘텐츠 작업을 생성하고 오케스트레이터를 독립 프로세스로 실행한다.

    channel_type(finance/language)에 따라 파이프라인 분기가 결정된다.
    """
    job = await f007_service.create_job(db, request)
    return F007ContentJobResponse.model_validate(job)


@router.get("/jobs", response_model=F007ContentJobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    cursor: Optional[int] = Query(
        default=None,
        description="마지막 수신 job id (첫 페이지는 생략)",
    ),
    status: Optional[str] = Query(
        default=None,
        description="상태 필터 (PENDING/RUNNING/DONE/FAILED/CANCELLED/PENDING_APPROVAL)",
    ),
    channel_type: Optional[str] = Query(
        default=None,
        description="채널 유형 필터 (finance/language, 없으면 전체)",
    ),
    db: aiosqlite.Connection = Depends(get_db),
) -> F007ContentJobListResponse:
    """F007 content_jobs 목록을 최신 순(id DESC)으로 반환한다. cursor 기반 페이징.

    channel_type 필터를 추가로 지원한다 (channel_category 컬럼 사용).
    """
    items, next_cursor, has_more = await f007_service.list_jobs(
        db,
        limit=limit,
        cursor=cursor,
        status=status,
        channel_type=channel_type,
    )
    return F007ContentJobListResponse(
        items=[F007ContentJobResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/jobs/{job_id}", response_model=F007ContentJobResponse)
async def get_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> F007ContentJobResponse:
    """ID로 F007 content_job 단건을 조회한다. 스테이지 목록 포함."""
    job = await f007_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
    return F007ContentJobResponse.model_validate(job)


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(
    job_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """F007 content_job과 연관 stages를 DB에서 완전 삭제한다."""
    deleted = await f007_service.delete_job(db, job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Job {job_id} 를 찾을 수 없습니다.")
