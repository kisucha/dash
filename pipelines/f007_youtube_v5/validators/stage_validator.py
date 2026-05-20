# pipelines/f007_youtube_v5/validators/stage_validator.py
# 목적: F007 스테이지 반송 처리 (F006 독립 복사 - F006 삭제 시 영향 없음)

import sys
import logging

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class StageValidator:
    """F007 스테이지 유효성 검증 및 반송 메커니즘."""

    @staticmethod
    def handle_rejection(
        db_conn,
        job_id: int,
        current_stage_id: str,
        val_result,
        reason: str = None,
    ) -> None:
        """스테이지 반송 처리 - stages 레코드를 REJECTED/PENDING으로 업데이트한다.

        Args:
            db_conn: sqlite3 커넥션
            job_id: content_jobs.id
            current_stage_id: 현재 실행 중이던 스테이지 ID
            val_result: ValidationResult 객체 (rejection_reason, rejection_target 포함)
            reason: 반송 사유 문자열 (val_result가 없을 때 직접 전달)
        """
        # ValidationResult 객체에서 사유/대상 추출
        if hasattr(val_result, 'rejection_reason'):
            rejection_reason = val_result.rejection_reason or reason or ""
            rejected_stage_id = val_result.rejection_target or current_stage_id
        else:
            # 문자열로 직접 전달된 경우
            rejection_reason = reason or str(val_result)
            rejected_stage_id = current_stage_id

        now: str = datetime.now(timezone.utc).isoformat()
        logger.warning(
            f"[job_id={job_id}] F007 스테이지 반송 처리 - "
            f"현재: {current_stage_id} -> 반송 대상: {rejected_stage_id}, "
            f"사유: {rejection_reason}"
        )
        try:
            # 현재 스테이지를 REJECTED로 마킹
            db_conn.execute(
                """UPDATE stages
                   SET status = 'REJECTED',
                       rejection_reason = ?,
                       rejection_target = ?,
                       finished_at = ?
                   WHERE job_id = ? AND stage_id = ?""",
                (rejection_reason, rejected_stage_id, now, job_id, current_stage_id),
            )
            # 반송 대상 스테이지를 PENDING으로 리셋 (재실행 대기)
            db_conn.execute(
                """UPDATE stages
                   SET status = 'PENDING',
                       output_data = NULL,
                       rejection_reason = NULL,
                       started_at = NULL,
                       finished_at = NULL,
                       retry_count = retry_count + 1
                   WHERE job_id = ? AND stage_id = ?""",
                (job_id, rejected_stage_id),
            )
            # content_jobs의 current_stage를 반송 대상으로 업데이트
            db_conn.execute(
                "UPDATE content_jobs SET current_stage = ? WHERE id = ?",
                (rejected_stage_id, job_id),
            )
            db_conn.commit()
        except Exception as e:
            try:
                db_conn.rollback()
            except Exception:
                pass
            logger.error(f"[job_id={job_id}] F007 반송 처리 DB 오류 - {e}")
            raise
