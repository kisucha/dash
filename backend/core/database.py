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


async def init_db() -> None:
    """DB 파일이 없으면 생성하고 테이블을 초기화한다."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(_CREATE_TASKS)
        await conn.execute(_CREATE_SCHEDULES)
        await conn.execute(_CREATE_SETTINGS)
        await conn.commit()


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI 의존성 주입용 aiosqlite 연결 제공자."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
