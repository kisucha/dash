# 목적: aiosqlite 기반 DB 초기화 및 연결 제공 (SQLAlchemy 없이 직접 사용)
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import AsyncGenerator
import aiosqlite
from core.config import DB_PATH

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_id   TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'PENDING',
    params       TEXT,
    result       TEXT,
    error_message TEXT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at   DATETIME,
    finished_at  DATETIME,
    triggered_by TEXT    NOT NULL DEFAULT 'manual'
)
"""

_CREATE_SCHEDULES = """
CREATE TABLE IF NOT EXISTS schedules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    feature_id     TEXT    NOT NULL,
    cron_expr      TEXT    NOT NULL,
    default_params TEXT,
    is_active      INTEGER NOT NULL DEFAULT 1,
    last_run_at    DATETIME
)
"""

_CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
)
"""

# AI 이미지/동영상 생성에 사용하는 모델 파일 인벤토리 (F003 영상제작 파이프라인 용)
_CREATE_MODEL_INVENTORY = """
CREATE TABLE IF NOT EXISTS model_inventory (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type          TEXT    NOT NULL,
    name                TEXT    NOT NULL,
    filename            TEXT    NOT NULL UNIQUE,
    local_path          TEXT    NOT NULL,
    civitai_version_id  INTEGER,
    hf_repo_id          TEXT,
    is_downloaded       INTEGER NOT NULL DEFAULT 0,
    file_size_mb        REAL,
    downloaded_at       DATETIME,
    base_model          TEXT,
    style_tags          TEXT
)
"""

# 모델 파일 다운로드 작업 큐 (F003 영상제작 파이프라인 용)
_CREATE_MODEL_DOWNLOAD_QUEUE = """
CREATE TABLE IF NOT EXISTS model_download_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,
    model_type      TEXT    NOT NULL,
    source_id       TEXT    NOT NULL,
    target_path     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'QUEUED',
    progress_pct    REAL    DEFAULT 0,
    error_message   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME
)
"""

# F001 유튜브 컨텐츠 제작 — 멀티스테이지 작업 단위 (영상 1개 제작 프로젝트)
_CREATE_CONTENT_JOBS = """
CREATE TABLE IF NOT EXISTS content_jobs (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    feature_id        TEXT     NOT NULL DEFAULT 'F001',
    status            TEXT     NOT NULL DEFAULT 'PENDING',
    channel_category  TEXT,
    initial_params    TEXT,
    current_stage     TEXT,
    upload_mode       TEXT     NOT NULL DEFAULT 'manual_approval',
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at        DATETIME,
    finished_at       DATETIME,
    triggered_by      TEXT     NOT NULL DEFAULT 'manual',
    youtube_video_id  TEXT,
    notes             TEXT,
    legacy_task_id    INTEGER
)
"""

# F001 스테이지 실행 레코드 — content_jobs 1개당 최대 6개
_CREATE_STAGES = """
CREATE TABLE IF NOT EXISTS stages (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER  NOT NULL,
    stage_id         TEXT     NOT NULL,
    stage_order      INTEGER  NOT NULL,
    status           TEXT     NOT NULL DEFAULT 'PENDING',
    input_data       TEXT,
    output_data      TEXT,
    rejection_reason TEXT,
    rejection_target TEXT,
    retry_count      INTEGER  NOT NULL DEFAULT 0,
    skip             INTEGER  NOT NULL DEFAULT 0,
    skip_mode        TEXT,
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at       DATETIME,
    finished_at      DATETIME,
    task_pid         INTEGER
)
"""

# 인덱스: feature_id + status 복합 조회 최적화
_CREATE_IDX_CONTENT_JOBS = """
CREATE INDEX IF NOT EXISTS idx_content_jobs_feature_status
ON content_jobs(feature_id, status)
"""

# 인덱스: job_id 기준 전체 스테이지 목록 조회 최적화
_CREATE_IDX_STAGES_JOB = "CREATE INDEX IF NOT EXISTS idx_stages_job_id ON stages(job_id)"

# 인덱스: 스테이지 상태 필터 조회 최적화
_CREATE_IDX_STAGES_STATUS = "CREATE INDEX IF NOT EXISTS idx_stages_status ON stages(status)"


async def init_db() -> None:
    """DB 파일이 없으면 생성하고 테이블을 초기화한다."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(_CREATE_TASKS)
        await conn.execute(_CREATE_SCHEDULES)
        await conn.execute(_CREATE_SETTINGS)
        await conn.execute(_CREATE_MODEL_INVENTORY)
        await conn.execute(_CREATE_MODEL_DOWNLOAD_QUEUE)
        # F001 멀티스테이지 테이블 추가
        await conn.execute(_CREATE_CONTENT_JOBS)
        await conn.execute(_CREATE_STAGES)
        await conn.execute(_CREATE_IDX_CONTENT_JOBS)
        await conn.execute(_CREATE_IDX_STAGES_JOB)
        await conn.execute(_CREATE_IDX_STAGES_STATUS)
        await conn.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI 의존성 주입용 aiosqlite 연결 제공자."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
