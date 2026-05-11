# 목적: FastAPI 앱 진입점 — CORS 설정, 라우터 등록, DB 초기화, APScheduler 시작
import sys
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트를 sys.path에 추가 — shared 패키지 임포트를 위해 필요
_PROJECT_ROOT = str(Path(__file__).parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# 프로젝트 루트의 .env 로드 (TAVILY_API_KEY 등)
load_dotenv(Path(__file__).parent.parent / '.env')

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.config import DB_PATH
from core.database import init_db
from models.task import row_to_dict
from routers import chat, features, health, models, model_assets, schedules, search, tasks


async def _restore_schedules(app: FastAPI) -> None:
    """앱 시작 시 DB에 저장된 활성 스케줄을 APScheduler에 복원 등록한다."""
    from routers.schedules import _register_job

    scheduler: AsyncIOScheduler = app.state.scheduler
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM schedules WHERE is_active = 1"
        )
        rows = await cursor.fetchall()
        for row in rows:
            sched = row_to_dict(row)
            try:
                await _register_job(scheduler, sched)
                print(
                    f"[Scheduler] 스케줄 복원 완료: id={sched['id']} "
                    f"feature={sched['feature_id']} cron={sched['cron_expr']}"
                )
            except ValueError as exc:
                print(
                    f"[Scheduler] 스케줄 복원 실패: id={sched['id']} — {exc}",
                    file=sys.stderr,
                )


async def _cleanup_stale_running_tasks() -> None:
    """서버 시작 시 이전 프로세스가 비정상 종료되어 RUNNING에 묶인 태스크를 FAILED로 정리한다."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'RUNNING'"
        )
        row = await cursor.fetchone()
        count = row[0] if row else 0
        if count:
            await conn.execute(
                """
                UPDATE tasks
                SET status = 'FAILED',
                    error_message = '서버 재시작으로 인해 중단된 작업',
                    finished_at = CURRENT_TIMESTAMP
                WHERE status = 'RUNNING'
                """
            )
            await conn.commit()
            print(f"[App] 미완료 RUNNING 태스크 {count}건 → FAILED 처리 완료")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 생명주기 관리 — 시작 시 DB/스케줄러 초기화, 종료 시 스케줄러 정지."""
    await init_db()
    print("[App] DB 초기화 완료")

    # 이전 실행에서 비정상 종료된 RUNNING 태스크 정리
    await _cleanup_stale_running_tasks()

    scheduler = AsyncIOScheduler()
    scheduler.start()
    app.state.scheduler = scheduler
    print("[App] APScheduler 시작 완료")

    await _restore_schedules(app)

    yield

    scheduler.shutdown(wait=False)
    print("[App] APScheduler 종료 완료")


def create_app() -> FastAPI:
    """FastAPI 앱 인스턴스를 생성하고 설정을 적용한다."""
    app = FastAPI(
        title="Dash API",
        description="Ollama 기반 자동화 대시보드 백엔드 API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(tasks.router)
    app.include_router(features.router)
    app.include_router(schedules.router)
    app.include_router(health.router)
    app.include_router(models.router)
    app.include_router(chat.router)
    app.include_router(search.router)
    app.include_router(model_assets.router)

    # F003 결과 파일 정적 서빙 (이미지/동영상) — 프로젝트 루트 기준 상대 경로
    f003_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f003"
    f003_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f003", StaticFiles(directory=str(f003_results_dir)), name="f003_results")

    @app.get("/", include_in_schema=False)
    async def root():
        """루트 접근 시 API 문서로 리다이렉트."""
        return RedirectResponse(url="/docs")

    return app


app: FastAPI = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
