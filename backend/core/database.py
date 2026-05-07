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


async def init_db() -> None:
    """DB 파일이 없으면 생성하고 테이블을 초기화한다."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(_CREATE_TASKS)
        await conn.execute(_CREATE_SCHEDULES)
        await conn.execute(_CREATE_SETTINGS)
        await conn.execute(_CREATE_MODEL_INVENTORY)
        await conn.execute(_CREATE_MODEL_DOWNLOAD_QUEUE)
        await conn.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI 의존성 주입용 aiosqlite 연결 제공자."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
