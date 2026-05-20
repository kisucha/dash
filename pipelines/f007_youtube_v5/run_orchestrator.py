# pipelines/f007_youtube_v5/run_orchestrator.py
# 목적: F007 오케스트레이터 subprocess 진입점
# backend에서 subprocess로 호출되며 argv[1]=job_id를 받아 F007Orchestrator를 실행한다.

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import sqlite3
from pathlib import Path

# 로깅 설정 - stdout으로 출력 (backend가 subprocess 로그를 캡처)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# DB 경로 - run_orchestrator.py 기준 세 단계 상위가 프로젝트 루트
DB_PATH = str(Path(__file__).parent.parent.parent / "storage" / "dash.db")


def _mark_job_failed(job_id: int, reason: str) -> None:
    """오케스트레이터 시작 실패 시 content_jobs를 FAILED로 마킹한다."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE content_jobs SET status='FAILED', notes=? WHERE id=?",
            (reason[:500], job_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[F007][run_orchestrator] FAILED 마킹 실패: {e}")


def main():
    # argv[1] = job_id 필수
    if len(sys.argv) < 2:
        logger.error("[F007][run_orchestrator] job_id 인수 없음 - 사용법: python run_orchestrator.py <job_id>")
        sys.exit(1)

    try:
        job_id = int(sys.argv[1])
    except ValueError:
        logger.error(f"[F007][run_orchestrator] 잘못된 job_id: {sys.argv[1]} (정수여야 함)")
        sys.exit(1)

    # 프로젝트 루트를 sys.path에 등록 (pipelines 패키지 임포트 가능하도록)
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    logger.info(f"[F007][run_orchestrator] 시작 - job_id={job_id}")

    try:
        from pipelines.f007_youtube_v5.orchestrator import F007Orchestrator
        orchestrator = F007Orchestrator()
        result = orchestrator.run(job_id)
        logger.info(f"[F007][run_orchestrator] 완료 - job_id={job_id}, result={result}")
    except Exception as e:
        logger.error(
            f"[F007][run_orchestrator] 실패 - job_id={job_id}: {e}",
            exc_info=True,
        )
        _mark_job_failed(job_id, str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
