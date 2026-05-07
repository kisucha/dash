# 목적: /api/schedules 엔드포인트 라우터 — 스케줄 CRUD 및 APScheduler 연동
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
from typing import Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException, Request

from core.config import DB_PATH
from core.database import get_db
from models.task import row_to_dict
from schemas.task import (
    ScheduleCreateRequest,
    ScheduleResponse,
    ScheduleUpdateRequest,
    TaskCreateRequest,
)
from services.task_service import task_service

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


def _get_scheduler(request: Request) -> AsyncIOScheduler:
    """app.state에서 APScheduler 인스턴스를 꺼내는 의존성 함수."""
    return request.app.state.scheduler


def _make_job_id(schedule_id: int) -> str:
    return f"schedule_{schedule_id}"


async def _register_job(scheduler: AsyncIOScheduler, schedule: dict) -> None:
    """APScheduler에 스케줄 job을 등록한다. 기존 job이 있으면 교체한다."""
    job_id = _make_job_id(schedule["id"])

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if not schedule["is_active"]:
        return

    try:
        trigger = CronTrigger.from_crontab(schedule["cron_expr"])
    except Exception as exc:
        raise ValueError(f"잘못된 cron 표현식: {schedule['cron_expr']} — {exc}") from exc

    _feature_id: str = schedule["feature_id"]
    _schedule_id: int = schedule["id"]
    _params_json: Optional[str] = schedule["default_params"]

    async def run_scheduled_task() -> None:
        """스케줄 트리거 시 Task를 생성하고 파이프라인을 실행하는 콜백."""
        from datetime import datetime
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            try:
                params: dict = json.loads(_params_json) if _params_json else {}
                req = TaskCreateRequest(feature_id=_feature_id, params=params)
                await task_service.create_task(conn, req, triggered_by="schedule")
                await conn.execute(
                    "UPDATE schedules SET last_run_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), _schedule_id),
                )
                await conn.commit()
            except Exception as exc:
                print(
                    f"[Schedule] 실행 오류 schedule_id={_schedule_id}: {exc}",
                    file=sys.stderr,
                )

    scheduler.add_job(run_scheduled_task, trigger=trigger, id=job_id, replace_existing=True)


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    db: aiosqlite.Connection = Depends(get_db),
) -> list[ScheduleResponse]:
    """등록된 모든 스케줄 목록을 반환한다."""
    cursor = await db.execute("SELECT * FROM schedules ORDER BY id")
    rows = await cursor.fetchall()
    return [ScheduleResponse.model_validate(row_to_dict(r)) for r in rows]


@router.post("", response_model=ScheduleResponse, status_code=201)
async def create_schedule(
    request: ScheduleCreateRequest,
    req: Request,
    db: aiosqlite.Connection = Depends(get_db),
) -> ScheduleResponse:
    """새 스케줄을 등록하고 APScheduler에 job을 추가한다."""
    params_json: Optional[str] = (
        json.dumps(request.default_params, ensure_ascii=False)
        if request.default_params else None
    )
    cursor = await db.execute(
        "INSERT INTO schedules (feature_id, cron_expr, default_params, is_active) VALUES (?, ?, ?, ?)",
        (request.feature_id, request.cron_expr, params_json, int(request.is_active)),
    )
    await db.commit()
    schedule_id: int = cursor.lastrowid

    cursor = await db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
    schedule = row_to_dict(await cursor.fetchone())

    scheduler = _get_scheduler(req)
    try:
        await _register_job(scheduler, schedule)
    except ValueError as exc:
        await db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
        await db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ScheduleResponse.model_validate(schedule)


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: int,
    request: ScheduleUpdateRequest,
    req: Request,
    db: aiosqlite.Connection = Depends(get_db),
) -> ScheduleResponse:
    """스케줄 정보를 수정하고 APScheduler job을 갱신한다."""
    cursor = await db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} 를 찾을 수 없습니다.")

    schedule = row_to_dict(row)
    updates = {}
    if request.cron_expr is not None:
        updates["cron_expr"] = request.cron_expr
    if request.default_params is not None:
        updates["default_params"] = json.dumps(request.default_params, ensure_ascii=False)
    if request.is_active is not None:
        updates["is_active"] = int(request.is_active)

    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        await db.execute(
            f"UPDATE schedules SET {set_clause} WHERE id = ?",
            (*updates.values(), schedule_id),
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
        schedule = row_to_dict(await cursor.fetchone())

    scheduler = _get_scheduler(req)
    try:
        await _register_job(scheduler, schedule)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ScheduleResponse.model_validate(schedule)


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int,
    req: Request,
    db: aiosqlite.Connection = Depends(get_db),
) -> None:
    """스케줄을 삭제하고 APScheduler에서 job을 제거한다."""
    cursor = await db.execute("SELECT id FROM schedules WHERE id = ?", (schedule_id,))
    if await cursor.fetchone() is None:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} 를 찾을 수 없습니다.")

    scheduler = _get_scheduler(req)
    job_id = _make_job_id(schedule_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    await db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    await db.commit()
