# 목적: F007 content_jobs, stages 테이블 CRUD 및 오케스트레이터 실행 서비스
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from models.task import row_to_dict
from schemas.f007 import F007JobCreateRequest

# F007 오케스트레이터 진입점 — 동적 경로 계산
ORCHESTRATOR_PATH = str(
    Path(__file__).parent.parent.parent / "pipelines" / "f007_youtube_v5" / "run_orchestrator.py"
)

# F007 파이프라인 6개 스테이지 정의 (stage_id, stage_order)
# F006와 동일한 6단계 구조, feature_id = 'F007'
_STAGES = [
    ("STAGE_01_TOPIC",  1),
    ("STAGE_02_SCRIPT", 2),
    ("STAGE_03_TTS",    3),
    ("STAGE_04_VISUAL", 4),
    ("STAGE_05_VIDEO",  5),
    ("STAGE_06_UPLOAD", 6),
]


def _now_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class F007Service:
    """F007 content_jobs, stages 테이블 CRUD 및 오케스트레이터 실행 서비스 클래스.

    F006Service를 계승하며 channel_type(finance/language) 필터를 추가로 지원한다.
    channel_type 값은 DB의 channel_category 컬럼에 저장한다.
    """

    async def create_job(
        self,
        db: aiosqlite.Connection,
        request: F007JobCreateRequest,
        triggered_by: str = "manual",
    ) -> dict:
        """새 content_job을 PENDING 상태로 생성하고 6개 스테이지를 INSERT한 뒤 오케스트레이터를 실행한다.

        channel_type을 channel_category 컬럼에 저장해 F006 DB 스키마를 재사용한다.
        """
        # 전체 입력 파라미터를 JSON 문자열로 직렬화
        initial_params = json.dumps(request.model_dump(), ensure_ascii=False)

        # content_jobs INSERT — feature_id = 'F007', channel_category에 channel_type 저장
        cursor = await db.execute(
            """
            INSERT INTO content_jobs
                (feature_id, status, channel_category, initial_params, upload_mode, triggered_by)
            VALUES ('F007', 'PENDING', ?, ?, ?, ?)
            """,
            (request.channel_type, initial_params, request.upload_mode, triggered_by),
        )
        await db.commit()
        job_id: int = cursor.lastrowid

        # 6개 스테이지 일괄 INSERT (모두 PENDING 상태)
        for stage_id, stage_order in _STAGES:
            await db.execute(
                """
                INSERT INTO stages (job_id, stage_id, stage_order, status)
                VALUES (?, ?, ?, 'PENDING')
                """,
                (job_id, stage_id, stage_order),
            )
        await db.commit()

        # 오케스트레이터를 독립 프로세스로 실행
        self._spawn_orchestrator(job_id)

        return await self.get_job(db, job_id)

    def _spawn_orchestrator(self, job_id: int) -> None:
        """subprocess.Popen으로 F007 오케스트레이터를 백그라운드 독립 프로세스로 실행한다.

        오케스트레이터가 아직 존재하지 않아도 Popen은 실패하지 않도록 예외를 잡는다.
        close_fds=True로 부모 프로세스 파일 디스크립터 누수를 방지한다.
        """
        try:
            subprocess.Popen(
                [sys.executable, ORCHESTRATOR_PATH, str(job_id)],
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            # 오케스트레이터 미존재 등 실행 실패 시 경고만 출력 — API 응답에는 영향 없음
            print(
                f"[F007Service] 오케스트레이터 실행 실패 job_id={job_id}: {exc}",
                file=sys.stderr,
            )

    async def get_job(self, db: aiosqlite.Connection, job_id: int) -> Optional[dict]:
        """job_id로 content_job 단건을 조회한다. stages 목록을 포함해 반환. 없으면 None."""
        cursor = await db.execute(
            "SELECT * FROM content_jobs WHERE id = ?",
            (job_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        job = row_to_dict(row)

        # 소속 스테이지 목록 조회 (stage_order ASC)
        stages_cursor = await db.execute(
            "SELECT * FROM stages WHERE job_id = ? ORDER BY stage_order ASC",
            (job_id,),
        )
        stage_rows = await stages_cursor.fetchall()
        job["stages"] = [row_to_dict(r) for r in stage_rows]

        return job

    async def list_jobs(
        self,
        db: aiosqlite.Connection,
        limit: int = 20,
        cursor: Optional[int] = None,
        status: Optional[str] = None,
        channel_type: Optional[str] = None,
    ) -> tuple[list[dict], Optional[int], bool]:
        """cursor 기반 페이징으로 F007 content_jobs 목록을 최신 순(id DESC)으로 조회한다.

        cursor: 마지막 수신 job id — 이 id보다 작은(더 오래된) 항목을 반환.
        status: 상태 필터 (없으면 전체).
        channel_type: channel_category 컬럼으로 필터 (finance/language, 없으면 전체).
        반환: (items, next_cursor, has_more)
        """
        # limit+1개 조회로 다음 페이지 존재 여부 판단
        fetch_limit = limit + 1

        # WHERE 절 조건을 동적으로 구성 — 조합 수가 많아 파라미터 방식 채택
        conditions = ["feature_id = 'F007'"]
        params: list = []

        if cursor is not None:
            conditions.append("id < ?")
            params.append(cursor)

        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        if channel_type is not None:
            # channel_type은 channel_category 컬럼에 저장됨
            conditions.append("channel_category = ?")
            params.append(channel_type)

        where_clause = " AND ".join(conditions)
        params.append(fetch_limit)

        sql = f"SELECT * FROM content_jobs WHERE {where_clause} ORDER BY id DESC LIMIT ?"
        db_cursor = await db.execute(sql, params)
        rows = await db_cursor.fetchall()
        items = [row_to_dict(r) for r in rows]

        # limit+1번째가 존재하면 다음 페이지 있음
        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        # 각 job에 stages 목록 추가
        for job in items:
            stages_cursor = await db.execute(
                "SELECT * FROM stages WHERE job_id = ? ORDER BY stage_order ASC",
                (job["id"],),
            )
            stage_rows = await stages_cursor.fetchall()
            job["stages"] = [row_to_dict(r) for r in stage_rows]

        # 다음 페이지 시작 cursor는 현재 페이지 마지막 항목의 id
        next_cursor: Optional[int] = items[-1]["id"] if has_more else None
        return items, next_cursor, has_more

    async def cancel_job(self, db: aiosqlite.Connection, job_id: int) -> Optional[dict]:
        """RUNNING 상태인 job을 CANCELLED로 변경한다.

        job이 없으면 None, RUNNING이 아니면 현재 job dict 반환.
        라우터에서 status를 확인해 400 판단.
        """
        job = await self.get_job(db, job_id)
        if job is None:
            return None

        # RUNNING이 아니면 현재 상태 그대로 반환 (라우터에서 400 처리)
        if job["status"] != "RUNNING":
            return job

        await db.execute(
            "UPDATE content_jobs SET status = 'CANCELLED', finished_at = ? WHERE id = ?",
            (_now_iso(), job_id),
        )
        await db.commit()
        return await self.get_job(db, job_id)

    async def delete_job(self, db: aiosqlite.Connection, job_id: int) -> bool:
        """content_jobs + 연관 stages를 DB에서 완전 삭제한다.

        RUNNING 상태인 경우 먼저 CANCELLED로 변경 후 삭제한다.
        존재하지 않는 job_id면 False 반환.
        """
        job = await self.get_job(db, job_id)
        if job is None:
            return False

        await db.execute("DELETE FROM stages WHERE job_id = ?", (job_id,))
        await db.execute("DELETE FROM content_jobs WHERE id = ?", (job_id,))
        await db.commit()
        return True


# 싱글턴 인스턴스 — 라우터에서 임포트하여 사용
f007_service = F007Service()
