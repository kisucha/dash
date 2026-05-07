# 목적: Task CRUD 및 파이프라인 subprocess 실행 로직 담당 서비스 레이어
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import subprocess
from typing import Optional

import aiosqlite

from core.config import PIPELINE_RUNNER_PATH
from models.task import row_to_dict
from schemas.task import TaskCreateRequest


class TaskService:
    """Task 생성, 조회, 취소 및 파이프라인 실행을 담당하는 서비스 클래스."""

    async def create_task(
        self,
        db: aiosqlite.Connection,
        request: TaskCreateRequest,
        triggered_by: str = "manual",
    ) -> dict:
        """새 Task를 PENDING 상태로 DB에 저장하고 파이프라인을 독립 프로세스로 실행한다."""
        params_json: str = json.dumps(request.params, ensure_ascii=False)

        cursor = await db.execute(
            """
            INSERT INTO tasks (feature_id, status, params, triggered_by)
            VALUES (?, 'PENDING', ?, ?)
            """,
            (request.feature_id, params_json, triggered_by),
        )
        await db.commit()
        task_id: int = cursor.lastrowid

        # 생성된 Task 조회
        task = await self.get_task(db, task_id)

        # 파이프라인 독립 프로세스 실행
        self._spawn_pipeline(task_id, request.feature_id)

        return task

    def _spawn_pipeline(self, task_id: int, feature_id: str) -> None:
        """subprocess.Popen으로 파이프라인 runner를 백그라운드 실행한다."""
        try:
            subprocess.Popen(
                [sys.executable, PIPELINE_RUNNER_PATH, str(task_id), feature_id],
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            print(
                f"[TaskService] 파이프라인 실행 실패 task_id={task_id}: {exc}",
                file=sys.stderr,
            )

    async def get_task(self, db: aiosqlite.Connection, task_id: int) -> Optional[dict]:
        """ID로 Task 단건을 조회한다. 없으면 None 반환."""
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return row_to_dict(row) if row else None

    async def list_tasks(
        self,
        db: aiosqlite.Connection,
        limit: int = 20,
        cursor: Optional[int] = None,
        feature_id: Optional[str] = None,
    ) -> tuple[list[dict], Optional[int], bool]:
        """cursor 기반 페이징으로 task 목록 조회. limit+1개 조회로 has_more 판단.

        cursor: 마지막 수신 task id — 이 id보다 작은(더 오래된) 항목을 반환.
        feature_id가 주어지면 해당 업무의 작업만 필터링한다.
        반환: (items, next_cursor, has_more)
        """
        # limit+1개를 조회해 다음 페이지 존재 여부를 판단
        fetch_limit = limit + 1

        if cursor is not None and feature_id:
            db_cursor = await db.execute(
                "SELECT * FROM tasks WHERE id < ? AND feature_id = ? ORDER BY id DESC LIMIT ?",
                (cursor, feature_id, fetch_limit),
            )
        elif cursor is not None:
            db_cursor = await db.execute(
                "SELECT * FROM tasks WHERE id < ? ORDER BY id DESC LIMIT ?",
                (cursor, fetch_limit),
            )
        elif feature_id:
            db_cursor = await db.execute(
                "SELECT * FROM tasks WHERE feature_id = ? ORDER BY id DESC LIMIT ?",
                (feature_id, fetch_limit),
            )
        else:
            db_cursor = await db.execute(
                "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
                (fetch_limit,),
            )

        rows = await db_cursor.fetchall()
        items = [row_to_dict(r) for r in rows]

        # limit+1번째 항목이 존재하면 다음 페이지가 있음
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        # 다음 페이지 시작 cursor는 현재 페이지 마지막 항목의 id
        next_cursor: Optional[int] = items[-1]["id"] if has_more else None
        return items, next_cursor, has_more

    async def cancel_task(
        self, db: aiosqlite.Connection, task_id: int
    ) -> Optional[dict]:
        """RUNNING 상태인 Task를 CANCELLED로 변경한다.

        Task가 없으면 None, RUNNING이 아니면 현재 task dict를 반환.
        라우터에서 status를 보고 400 판단.
        """
        task = await self.get_task(db, task_id)
        if task is None:
            return None

        if task["status"] != "RUNNING":
            return task

        await db.execute(
            "UPDATE tasks SET status = 'CANCELLED' WHERE id = ?", (task_id,)
        )
        await db.commit()
        return await self.get_task(db, task_id)

    async def delete_task_record(
        self, db: aiosqlite.Connection, task_id: int
    ) -> Optional[str]:
        """Task 레코드를 DB에서 완전히 삭제한다.

        Task가 없으면 None, RUNNING이면 'RUNNING' 반환.
        삭제 성공이면 'DELETED' 반환.
        """
        task = await self.get_task(db, task_id)
        if task is None:
            return None
        if task["status"] == "RUNNING":
            return "RUNNING"

        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()
        return "DELETED"


# 싱글턴 인스턴스 — 라우터에서 임포트하여 사용
task_service = TaskService()
