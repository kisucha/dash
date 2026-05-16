# 목적: F004 스테이지 유효성 검증 및 반송(reject) 메커니즘.
# 오케스트레이터가 스테이지 출력을 검증한 뒤 실패 시 이 클래스를 통해 반송 처리한다.

import sys
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class StageValidator:
    """F004 스테이지 유효성 검증 및 반송 메커니즘.

    오케스트레이터(F004Orchestrator)에서 validate_output() 결과가
    is_valid=False일 때 이 클래스의 handle_rejection()을 호출한다.

    반송 규칙:
      - current_stage_id == rejected_stage_id: 현재 스테이지 자기 재시도
      - current_stage_id != rejected_stage_id: 이전 스테이지로 반송
        (출력 초기화 + retry_count 증가)
    """

    @staticmethod
    def handle_rejection(
        db_conn,
        job_id: int,
        current_stage_id: str,
        rejected_stage_id: str,
        reason: str,
    ) -> None:
        """스테이지를 REJECTED로 전환하고 반송 대상 스테이지를 PENDING으로 리셋.

        Args:
            db_conn: sqlite3.Connection (동기 커넥션)
            job_id: content_jobs.id — 어느 작업의 스테이지인지 식별
            current_stage_id: 현재 REJECTED 처리할 스테이지 ID
                              (예: "STAGE_02_SCRIPT")
            rejected_stage_id: 반송 대상 스테이지 ID
                               (예: "STAGE_01_RESEARCH" — 주제 재선택)
            reason: 반송 사유 텍스트 (UI와 DB에 기록)

        Side effects:
            1. stages WHERE job_id=? AND stage_id=current_stage_id
               → status='REJECTED', rejection_reason=reason, rejection_target, finished_at 설정
            2. stages WHERE job_id=? AND stage_id=rejected_stage_id
               → status='PENDING', output_data=NULL, started_at=NULL, finished_at=NULL,
                  rejection_reason=NULL, retry_count 증가
            3. content_jobs WHERE id=job_id
               → current_stage=rejected_stage_id (UI에서 어느 스테이지로 돌아갔는지 표시)
            4. db_conn.commit()
        """
        # 현재 시각 UTC ISO 형식
        now: str = datetime.now(timezone.utc).isoformat()

        logger.warning(
            f"[job_id={job_id}] 스테이지 반송 처리 시작 — "
            f"현재: {current_stage_id} → 반송 대상: {rejected_stage_id}, "
            f"사유: {reason}"
        )

        try:
            # 1. 현재 스테이지를 REJECTED 상태로 전환
            db_conn.execute(
                """UPDATE stages
                   SET status = 'REJECTED',
                       rejection_reason = ?,
                       rejection_target = ?,
                       finished_at = ?
                   WHERE job_id = ? AND stage_id = ?""",
                (reason, rejected_stage_id, now, job_id, current_stage_id),
            )
            logger.info(
                f"[job_id={job_id}] STAGE '{current_stage_id}' → REJECTED 처리 완료"
            )

            # 2. 반송 대상 스테이지를 PENDING으로 리셋
            #    output_data 초기화 — 재실행 시 새 출력으로 덮어씀
            #    retry_count 증가 — 무한 재시도 방지용 추적
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
            logger.info(
                f"[job_id={job_id}] STAGE '{rejected_stage_id}' → PENDING 리셋 완료 "
                f"(retry_count 증가)"
            )

            # 3. content_jobs current_stage 업데이트 — UI 현재 위치 표시용
            db_conn.execute(
                "UPDATE content_jobs SET current_stage = ? WHERE id = ?",
                (rejected_stage_id, job_id),
            )
            logger.info(
                f"[job_id={job_id}] content_jobs.current_stage → '{rejected_stage_id}' 업데이트"
            )

            # 4. 트랜잭션 커밋 — 위 3개 업데이트를 원자적으로 반영
            db_conn.commit()
            logger.info(
                f"[job_id={job_id}] 반송 처리 DB 커밋 완료 — "
                f"사용자가 '{rejected_stage_id}' 재시도 버튼을 눌러야 파이프라인이 재개됨"
            )

        except Exception as e:
            # DB 오류 발생 시 롤백 시도 후 예외 재발생
            try:
                db_conn.rollback()
            except Exception:
                pass
            logger.error(
                f"[job_id={job_id}] 반송 처리 DB 오류 — {e}"
            )
            raise
