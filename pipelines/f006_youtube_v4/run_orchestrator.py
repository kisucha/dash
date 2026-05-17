# 목적: F006 오케스트레이터 subprocess 진입점 - argv[1]=job_id.
# f006_service.create_job()에서 subprocess.Popen([sys.executable, this_file, str(job_id)])으로 호출된다.

import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 - 독립 프로세스로 실행되므로 경로 명시 필요
PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import sqlite3

# 로깅 설정 - 인코딩 명시 (Windows 콘솔 UTF-8 호환)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    encoding='utf-8',
)

# 오케스트레이터 임포트 (sys.path 설정 후 임포트해야 함)
from pipelines.f006_youtube_v4.orchestrator import F006Orchestrator

# DB 경로 상수 - run_orchestrator.py 기준 세 단계 상위가 프로젝트 루트
DB_PATH: str = str(Path(__file__).parent.parent.parent / "storage" / "dash.db")

# 로거
logger = logging.getLogger("run_orchestrator")


def main() -> None:
    """엔트리포인트 - argv[1]에서 job_id를 읽어 오케스트레이터를 실행한다."""
    # 인수 검증
    if len(sys.argv) < 2:
        print("사용법: python run_orchestrator.py <job_id>", file=sys.stderr)
        sys.exit(1)

    try:
        job_id = int(sys.argv[1])
    except ValueError:
        print(
            f"오류: job_id는 정수여야 합니다. 입력값: {sys.argv[1]}",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info(f"[run_orchestrator] f006 오케스트레이터 시작 - job_id={job_id}")

    try:
        orchestrator = F006Orchestrator()
        result = orchestrator.run(job_id)
        logger.info(f"[run_orchestrator] f006 오케스트레이터 완료 - job_id={job_id}, 결과: {result}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"[run_orchestrator] f006 오케스트레이터 실패 - job_id={job_id}: {e}")

        # orchestrator 내부에서 FAILED 처리를 못한 경우를 대비해 여기서도 시도
        _mark_job_failed(job_id, str(e))
        sys.exit(1)


def _mark_job_failed(job_id: int, error_msg: str) -> None:
    """content_jobs를 FAILED로 업데이트하는 안전망 함수.

    orchestrator 내부 예외 처리가 실패했을 때 최후 수단으로 호출된다.
    DB 오류가 발생해도 로그만 남기고 시스템 종료를 진행한다.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE content_jobs SET status = 'FAILED', finished_at = ?, notes = ? WHERE id = ?",
            (now, error_msg[:500], job_id),
        )
        conn.commit()
        conn.close()
        logger.info(f"[run_orchestrator] job_id={job_id} FAILED 상태 기록 완료")
    except Exception as db_e:
        logger.error(
            f"[run_orchestrator] FAILED 상태 기록 실패 - job_id={job_id}: {db_e}"
        )


if __name__ == "__main__":
    main()
