# 목적: model_download_queue 테이블 관리 — 다운로드 큐 추가, 진행률 조회, 상태 업데이트
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Optional

import aiosqlite


def _row_to_dict(row: aiosqlite.Row) -> dict:
    """aiosqlite.Row를 dict로 변환한다."""
    return dict(row)


class DownloadService:
    """model_download_queue 테이블 CRUD를 담당하는 서비스 클래스."""

    async def enqueue(
        self,
        db: aiosqlite.Connection,
        source: str,
        model_type: str,
        source_id: str,
        target_path: str,
    ) -> int:
        """다운로드 항목을 큐에 추가하고 생성된 ID를 반환한다."""
        cursor = await db.execute(
            "INSERT INTO model_download_queue (source, model_type, source_id, target_path, status) VALUES (?,?,?,?,'QUEUED')",
            (source, model_type, source_id, target_path),
        )
        await db.commit()
        return cursor.lastrowid

    async def list_active_downloads(self, db: aiosqlite.Connection) -> list[dict]:
        """QUEUED 또는 DOWNLOADING 상태인 다운로드 목록을 반환한다."""
        cursor = await db.execute(
            "SELECT * FROM model_download_queue WHERE status IN ('QUEUED', 'DOWNLOADING') ORDER BY id DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def list_downloads(self, db: aiosqlite.Connection, limit: int = 50) -> list[dict]:
        """전체 다운로드 이력을 최신 순으로 반환한다."""
        cursor = await db.execute(
            "SELECT * FROM model_download_queue ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]

    async def get_download(self, db: aiosqlite.Connection, queue_id: int) -> Optional[dict]:
        """ID로 다운로드 항목 단건 조회."""
        cursor = await db.execute(
            "SELECT * FROM model_download_queue WHERE id = ?", (queue_id,)
        )
        row = await cursor.fetchone()
        return _row_to_dict(row) if row else None

    async def update_progress(
        self,
        db: aiosqlite.Connection,
        queue_id: int,
        progress_pct: float,
    ) -> None:
        """다운로드 진행률을 업데이트하고 상태를 DOWNLOADING으로 전환한다."""
        await db.execute(
            "UPDATE model_download_queue SET progress_pct = ?, status = 'DOWNLOADING' WHERE id = ?",
            (round(progress_pct, 1), queue_id),
        )
        await db.commit()

    async def mark_done(self, db: aiosqlite.Connection, queue_id: int) -> None:
        """다운로드 완료 상태(DONE, progress 100%)로 업데이트한다."""
        await db.execute(
            "UPDATE model_download_queue SET status = 'DONE', progress_pct = 100.0, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (queue_id,),
        )
        await db.commit()

    async def mark_failed(
        self,
        db: aiosqlite.Connection,
        queue_id: int,
        error_message: str,
    ) -> None:
        """다운로드 실패 상태(FAILED)로 업데이트한다. 오류 메시지는 500자로 자른다."""
        await db.execute(
            "UPDATE model_download_queue SET status = 'FAILED', error_message = ?, finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (error_message[:500], queue_id),
        )
        await db.commit()


# 싱글턴 인스턴스 — 라우터에서 import하여 사용
download_service = DownloadService()
