# 파이프라인 실행 진입점 — FastAPI에서 subprocess.Popen으로 호출되는 스크립트.
# 인자: task_id, feature_id
# DB에서 params를 읽고, 해당 파이프라인 클래스를 찾아 실행한 뒤 결과를 DB에 저장한다.

import sys
import sqlite3
import json
import logging
import traceback
from datetime import datetime, timezone

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# pipelines 패키지 임포트를 위해 프로젝트 루트를 sys.path에 추가
_PROJECT_ROOT = r"C:\Develop\Dash"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 로깅 기본 설정 — 독립 프로세스이므로 콘솔 출력으로 확인 가능
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("runner")

# DB 경로 상수 (backend/core/config.py 생성 전까지 고정값 사용)
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"


# ------------------------------------------------------------------
# 파이프라인 레지스트리 — feature_id → 파이프라인 클래스 매핑
# 새 파이프라인 추가 시 이 딕셔너리에 등록 필수
# ------------------------------------------------------------------

def _build_registry() -> dict:
    """
    파이프라인 레지스트리를 빌드한다.
    임포트 오류 시 해당 파이프라인만 제외하고 계속 진행한다.

    Returns:
        {feature_id: PipelineClass} 형태의 딕셔너리
    """
    from pipelines.base import BasePipeline

    registry: dict[str, type[BasePipeline]] = {}

    # F001 — 유튜브 컨텐츠 제작
    try:
        from pipelines.f001_youtube.pipeline import F001Pipeline
        registry["F001"] = F001Pipeline
        logger.info("파이프라인 등록 완료: F001 (유튜브 컨텐츠 제작)")
    except ImportError as e:
        logger.warning(f"F001 파이프라인 로드 실패 (임포트 오류): {e}")

    # F002 — 매일 아침 이슈 발굴
    try:
        from pipelines.f002_daily_issues.pipeline import F002Pipeline
        registry["F002"] = F002Pipeline
        logger.info("파이프라인 등록 완료: F002 (매일 아침 이슈 발굴)")
    except ImportError as e:
        logger.warning(f"F002 파이프라인 로드 실패 (임포트 오류): {e}")

    return registry


# ------------------------------------------------------------------
# DB 유틸 함수
# ------------------------------------------------------------------

def load_task_params(task_id: int) -> tuple[str, dict]:
    """
    DB에서 task 정보를 읽어 feature_id와 params를 반환한다.

    Args:
        task_id: 조회할 task의 ID

    Returns:
        (feature_id, params_dict) 튜플

    Raises:
        ValueError: task를 찾을 수 없거나 params 파싱 실패 시
        sqlite3.Error: DB 접근 오류 시
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(
            "SELECT feature_id, params FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"task_id={task_id} 에 해당하는 task를 찾을 수 없음")

        db_feature_id: str = row[0]

        # params 파싱 — None이거나 빈 문자열이면 빈 딕셔너리 사용
        raw_params: str = row[1] or "{}"
        try:
            params: dict = json.loads(raw_params)
        except json.JSONDecodeError as e:
            raise ValueError(f"params JSON 파싱 실패: {e} / 원본: {raw_params!r}")

        return db_feature_id, params
    finally:
        conn.close()


def mark_failed(task_id: int, error_message: str) -> None:
    """
    DB에서 task 상태를 FAILED로 업데이트하고 error_message를 저장한다.
    runner.py 레벨의 최후 안전망 — 파이프라인 내부 예외 처리와 별개로 동작.

    Args:
        task_id: 실패 처리할 task의 ID
        error_message: 저장할 오류 메시지
    """
    now: str = datetime.now(timezone.utc).isoformat()
    try:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                UPDATE tasks
                SET status = 'FAILED',
                    error_message = ?,
                    finished_at = ?
                WHERE id = ?
                """,
                (error_message, now, task_id),
            )
            conn.commit()
            logger.info(f"[task_id={task_id}] FAILED 상태로 업데이트 완료")
        finally:
            conn.close()
    except sqlite3.Error as db_err:
        # DB 업데이트마저 실패한 경우 — 콘솔에만 기록
        logger.critical(f"[task_id={task_id}] FAILED 업데이트 자체도 실패: {db_err}")


# ------------------------------------------------------------------
# 메인 실행 로직
# ------------------------------------------------------------------

def main() -> None:
    """
    runner.py 메인 함수.

    실행 흐름:
    1. 명령줄 인자에서 task_id, feature_id 추출
    2. DB에서 params 로드
    3. 레지스트리에서 파이프라인 클래스 탐색
    4. 파이프라인 실행 (run 메서드 호출)
    5. 결과/오류를 DB에 저장
    """
    logger.info("=== 파이프라인 runner 시작 ===")

    # ------------------------------------------------------------------
    # [1] 명령줄 인자 파싱
    # ------------------------------------------------------------------
    if len(sys.argv) < 3:
        logger.critical(
            f"인자 부족. 사용법: python runner.py <task_id> <feature_id> "
            f"(받은 인자: {sys.argv})"
        )
        sys.exit(1)

    try:
        task_id: int = int(sys.argv[1])
    except ValueError:
        logger.critical(f"task_id가 정수가 아님: {sys.argv[1]!r}")
        sys.exit(1)

    feature_id: str = sys.argv[2].upper().strip()
    logger.info(f"실행 대상 — task_id: {task_id}, feature_id: {feature_id}")

    # ------------------------------------------------------------------
    # [2] 레지스트리 빌드
    # ------------------------------------------------------------------
    try:
        registry = _build_registry()
    except Exception as e:
        error_msg = f"파이프라인 레지스트리 빌드 실패: {e}"
        logger.critical(error_msg)
        mark_failed(task_id, error_msg)
        sys.exit(1)

    # ------------------------------------------------------------------
    # [3] DB에서 params 로드
    # ------------------------------------------------------------------
    try:
        db_feature_id, params = load_task_params(task_id)
    except (ValueError, sqlite3.Error) as e:
        error_msg = f"DB에서 task 정보 로드 실패: {e}"
        logger.error(error_msg)
        mark_failed(task_id, error_msg)
        sys.exit(1)

    # feature_id 일치 검증 — DB와 인자가 다르면 경고 후 인자 기준으로 진행
    if db_feature_id.upper() != feature_id:
        logger.warning(
            f"feature_id 불일치 — 인자: {feature_id}, DB: {db_feature_id}. "
            f"인자 기준으로 실행합니다."
        )

    logger.info(f"params 로드 완료: {params}")

    # ------------------------------------------------------------------
    # [4] 파이프라인 클래스 탐색
    # ------------------------------------------------------------------
    pipeline_class = registry.get(feature_id)
    if pipeline_class is None:
        error_msg = (
            f"등록되지 않은 feature_id: '{feature_id}'. "
            f"등록된 목록: {list(registry.keys())}"
        )
        logger.error(error_msg)
        mark_failed(task_id, error_msg)
        sys.exit(1)

    logger.info(f"파이프라인 클래스 발견: {pipeline_class.__name__}")

    # ------------------------------------------------------------------
    # [5] 파이프라인 인스턴스 생성 및 실행
    # ------------------------------------------------------------------
    pipeline = pipeline_class()

    try:
        logger.info(f"[task_id={task_id}] 파이프라인 실행 시작")
        result: dict = pipeline.run(task_id=task_id, params=params)
        logger.info(f"[task_id={task_id}] 파이프라인 실행 완료")

        # run()이 None을 반환하면 빈 딕셔너리로 처리
        if result is None:
            result = {}

        # 최종 상태를 DONE으로 업데이트 (run() 내부에서 이미 했을 수 있으나 보장용)
        pipeline.update_status(task_id=task_id, status="DONE", result=result)
        logger.info(f"[task_id={task_id}] 최종 상태 DONE 저장 완료")

    except Exception as e:
        # 어떤 예외도 FAILED + 오류 메시지로 저장
        error_msg: str = f"{type(e).__name__}: {e}"
        full_traceback: str = traceback.format_exc()
        logger.error(f"[task_id={task_id}] 파이프라인 실행 실패:\n{full_traceback}")

        # 오류 메시지는 최대 2000자로 잘라 저장 (DB 컬럼 길이 고려)
        truncated_error: str = error_msg[:2000]
        mark_failed(task_id=task_id, error_message=truncated_error)
        sys.exit(1)

    logger.info("=== 파이프라인 runner 종료 ===")


if __name__ == "__main__":
    main()
