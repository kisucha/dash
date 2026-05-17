# 목적: F006 스테이지 유효성 검증 및 반송(reject) 메커니즘.
# 오케스트레이터가 스테이지 출력을 검증한 뒤 실패 시 이 클래스를 통해 반송 처리한다.

import sys
import logging

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StageValidator:
    """F006 스테이지 유효성 검증 및 반송 메커니즘."""

    @staticmethod
    def handle_rejection(db_conn, job_id: int, current_stage_id: str, rejected_stage_id: str, reason: str) -> None:
        now: str = datetime.now(timezone.utc).isoformat()
        logger.warning(f"[job_id={job_id}] 스테이지 반송 처리 시작 - 현재: {current_stage_id} -> 반송 대상: {rejected_stage_id}, 사유: {reason}")
        try:
            db_conn.execute(
                """UPDATE stages SET status = 'REJECTED', rejection_reason = ?, rejection_target = ?, finished_at = ? WHERE job_id = ? AND stage_id = ?""",
                (reason, rejected_stage_id, now, job_id, current_stage_id),
            )
            db_conn.execute(
                """UPDATE stages SET status = 'PENDING', output_data = NULL, rejection_reason = NULL, started_at = NULL, finished_at = NULL, retry_count = retry_count + 1 WHERE job_id = ? AND stage_id = ?""",
                (job_id, rejected_stage_id),
            )
            db_conn.execute("UPDATE content_jobs SET current_stage = ? WHERE id = ?", (rejected_stage_id, job_id))
            db_conn.commit()
        except Exception as e:
            try:
                db_conn.rollback()
            except Exception:
                pass
            logger.error(f"[job_id={job_id}] 반송 처리 DB 오류 - {e}")
            raise
