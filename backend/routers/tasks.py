# 목적: /api/tasks 엔드포인트 라우터 — Task CRUD API 처리
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import get_db
from schemas.task import TaskCreateRequest, TaskListResponse, TaskResponse
from services.task_service import task_service

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    request: TaskCreateRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskResponse:
    """새 작업을 생성하고 파이프라인을 독립 프로세스로 실행한다."""
    task = await task_service.create_task(db, request)
    return TaskResponse.model_validate(task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    feature_id: str | None = Query(default=None, description="업무 ID 필터"),
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskListResponse:
    """작업 목록을 최신 순으로 반환한다. feature_id 지정 시 해당 업무만 필터링."""
    total, items = await task_service.list_tasks(db, limit=limit, offset=offset, feature_id=feature_id)
    return TaskListResponse(
        total=total,
        items=[TaskResponse.model_validate(item) for item in items],
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskResponse:
    """ID로 작업 상태와 결과를 조회한다."""
    task = await task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} 를 찾을 수 없습니다.")
    return TaskResponse.model_validate(task)


@router.delete("/{task_id}/history", status_code=204)
async def delete_task_history(
    task_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """완료된 작업 이력을 DB에서 삭제한다. RUNNING 상태는 삭제 불가."""
    result = await task_service.delete_task_record(db, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} 를 찾을 수 없습니다.")
    if result == "RUNNING":
        raise HTTPException(status_code=400, detail="실행 중인 작업은 삭제할 수 없습니다.")


@router.delete("/{task_id}", response_model=TaskResponse)
async def cancel_task(
    task_id: int,
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskResponse:
    """RUNNING 상태인 작업을 CANCELLED로 변경한다."""
    task = await task_service.cancel_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} 를 찾을 수 없습니다.")
    if task["status"] != "CANCELLED":
        raise HTTPException(
            status_code=400,
            detail=f"RUNNING 상태인 작업만 취소할 수 있습니다. 현재 상태: {task['status']}",
        )
    return TaskResponse.model_validate(task)
