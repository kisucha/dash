# 목적: 레거시 tasks 테이블 F001 이력을 content_jobs + stages로 선택적 마이그레이션하는 유틸.
# 원본 tasks 레코드는 삭제하지 않고 legacy_task_id로 연결만 한다.
# backend/routers/f001.py의 POST /api/f001/migrate-legacy 엔드포인트에서 호출된다.

import sys
import sqlite3
import json
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from typing import Optional

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# DB 경로 상수 — base.py와 동일 (독립 실행 고려)
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"

# 스테이지 순서 — content_jobs 생성 시 6개 stages INSERT에 사용
_STAGE_SEQUENCE: list[tuple[str, int]] = [
    ("STAGE_01_RESEARCH", 1),
    ("STAGE_02_SCRIPT", 2),
    ("STAGE_03_TTS", 3),
    ("STAGE_04_VIDEO_GEN", 4),
    ("STAGE_05_EDIT", 5),
    ("STAGE_06_UPLOAD", 6),
]


def migrate_f001_tasks(task_ids: Optional[list[int]] = None) -> dict:
    """레거시 tasks 테이블의 F001 이력을 content_jobs + stages로 마이그레이션.

    변환 규칙:
      - tasks.id → content_jobs.legacy_task_id (원본 참조)
      - tasks.params.topic → content_jobs.channel_category
      - tasks.params → content_jobs.initial_params
      - tasks.status → content_jobs.status (그대로)
      - tasks.result → stages STAGE_02 output_data (스크립트 결과 보존)
      - 원본 tasks 레코드는 삭제하지 않음 (안전 유지)

    Args:
        task_ids: 마이그레이션할 task_id 목록. None이면 F001 전체.

    Returns:
        {"migrated_count": int, "skipped_count": int, "details": list}
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    migrated_count = 0
    skipped_count = 0
    details: list[dict] = []

    try:
        # ----------------------------------------------------------------
        # 1. 마이그레이션 대상 tasks 조회
        # ----------------------------------------------------------------
        if task_ids:
            placeholders = ",".join("?" * len(task_ids))
            cursor = conn.execute(
                f"SELECT * FROM tasks WHERE feature_id = 'F001' AND id IN ({placeholders})",
                task_ids,
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM tasks WHERE feature_id = 'F001'"
            )

        tasks = [dict(row) for row in cursor.fetchall()]
        logger.info(f"[migrate_f001] 마이그레이션 대상 tasks: {len(tasks)}건")

        for task in tasks:
            task_id: int = task["id"]

            # ----------------------------------------------------------------
            # 2. 이미 마이그레이션된 tasks 건너뜀 (legacy_task_id 중복 확인)
            # ----------------------------------------------------------------
            dup_cursor = conn.execute(
                "SELECT id FROM content_jobs WHERE legacy_task_id = ?",
                (task_id,),
            )
            if dup_cursor.fetchone():
                logger.info(f"[migrate_f001] task_id={task_id} 이미 마이그레이션됨 — 건너뜀")
                skipped_count += 1
                details.append({
                    "task_id": task_id,
                    "result": "skipped",
                    "reason": "이미 마이그레이션됨",
                })
                continue

            # ----------------------------------------------------------------
            # 3. tasks.params JSON 파싱
            # ----------------------------------------------------------------
            try:
                params_raw = task.get("params") or "{}"
                params: dict = json.loads(params_raw)
            except (json.JSONDecodeError, TypeError):
                params = {}

            # channel_category 추출 — tasks.params.topic 또는 'legacy'
            channel_category: str = str(params.get("topic", "legacy")).strip() or "legacy"

            # tasks.status 상태 매핑
            legacy_status: str = task.get("status", "DONE")
            if legacy_status in ("DONE", "FAILED", "CANCELLED", "PENDING", "RUNNING"):
                content_job_status = legacy_status
            else:
                content_job_status = "DONE"

            # ----------------------------------------------------------------
            # 4. content_jobs INSERT
            # ----------------------------------------------------------------
            now: str = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """INSERT INTO content_jobs
                   (feature_id, status, channel_category, initial_params,
                    upload_mode, created_at, started_at, finished_at,
                    triggered_by, legacy_task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "F001",
                    content_job_status,
                    channel_category,
                    params_raw,
                    "manual_approval",
                    task.get("created_at", now),
                    task.get("started_at"),
                    task.get("finished_at"),
                    "legacy",
                    task_id,
                ),
            )
            job_id: int = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            # ----------------------------------------------------------------
            # 5. stages 6개 INSERT (기본 PENDING)
            # ----------------------------------------------------------------
            for stage_id, stage_order in _STAGE_SEQUENCE:
                conn.execute(
                    """INSERT INTO stages
                       (job_id, stage_id, stage_order, status,
                        created_at)
                       VALUES (?, ?, ?, 'PENDING', ?)""",
                    (job_id, stage_id, stage_order, now),
                )

            # ----------------------------------------------------------------
            # 6. STAGE_02에 tasks.result를 output_data로 저장 (스크립트 보존)
            # ----------------------------------------------------------------
            result_raw: Optional[str] = task.get("result")
            if result_raw:
                try:
                    # 레거시 결과 JSON 파싱 후 STAGE_02 형식으로 래핑
                    legacy_result: dict = json.loads(result_raw)
                    stage02_output = {
                        "stage_id": "STAGE_02_SCRIPT",
                        "status": "COMPLETED",
                        "selected_topic": channel_category,
                        "script": {
                            "hook": legacy_result.get("title", ""),
                            "body": [
                                {
                                    "section_title": "스크립트",
                                    "content": legacy_result.get("script", ""),
                                    "duration_sec": 60,
                                }
                            ],
                            "cta": legacy_result.get("description", ""),
                        },
                        "scenes": [],
                        "script_text": legacy_result.get("script", ""),
                        "total_chars": len(legacy_result.get("script", "")),
                        "estimated_duration_min": len(legacy_result.get("script", "")) // 170,
                        "generated_at": task.get("finished_at", now),
                        "_migrated_from_task_id": task_id,
                    }
                    stage02_output_json = json.dumps(stage02_output, ensure_ascii=False)
                    conn.execute(
                        """UPDATE stages
                           SET status = 'DONE', output_data = ?
                           WHERE job_id = ? AND stage_id = 'STAGE_02_SCRIPT'""",
                        (stage02_output_json, job_id),
                    )
                    logger.info(
                        f"[migrate_f001] task_id={task_id} STAGE_02 output_data 저장 완료"
                    )
                except (json.JSONDecodeError, TypeError, KeyError) as e:
                    logger.warning(
                        f"[migrate_f001] task_id={task_id} result 파싱 실패 — "
                        f"STAGE_02 output 없이 진행: {e}"
                    )

            conn.commit()
            migrated_count += 1
            details.append({
                "task_id": task_id,
                "job_id": job_id,
                "result": "migrated",
                "channel_category": channel_category,
                "status": content_job_status,
            })
            logger.info(
                f"[migrate_f001] task_id={task_id} → job_id={job_id} 마이그레이션 완료"
            )

    except Exception as e:
        conn.rollback()
        logger.error(f"[migrate_f001] 마이그레이션 실패: {e}")
        raise

    finally:
        conn.close()

    logger.info(
        f"[migrate_f001] 완료 — 성공: {migrated_count}건, 건너뜀: {skipped_count}건"
    )
    return {
        "migrated_count": migrated_count,
        "skipped_count": skipped_count,
        "details": details,
    }


if __name__ == "__main__":
    """직접 실행 시 F001 전체 마이그레이션 수행."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )
    result = migrate_f001_tasks()
    print(f"마이그레이션 결과: {result}")
