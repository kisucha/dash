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
from routers import chat, features, health, models, model_assets, schedules, search, tasks, f001, f004, f005, f006, f007


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


async def _restore_f001_running_jobs() -> None:
    """서버 재시작 시 RUNNING 상태 content_jobs에 대해 오케스트레이터를 재기동한다.

    중단된 RUNNING 스테이지는 PENDING으로 리셋해 재실행을 보장한다.
    WAITING 상태 job은 사용자 개입이 필요하므로 건드리지 않는다.
    """
    from services.f001_service import f001_service

    async with aiosqlite.connect(DB_PATH) as conn:
        # 중단된 RUNNING 스테이지를 PENDING으로 리셋
        await conn.execute(
            """
            UPDATE stages
            SET status = 'PENDING', started_at = NULL, finished_at = NULL
            WHERE status = 'RUNNING'
            """
        )
        # RUNNING 상태 content_jobs 목록 조회
        cursor = await conn.execute(
            "SELECT id FROM content_jobs WHERE status = 'RUNNING'"
        )
        rows = await cursor.fetchall()
        await conn.commit()

    for row in rows:
        job_id = row[0]
        f001_service._spawn_orchestrator(job_id)
        print(f"[App] content_jobs id={job_id} 오케스트레이터 재기동 완료")


async def _restore_f004_running_jobs() -> None:
    """서버 재시작 시 F004 RUNNING 상태 content_jobs 오케스트레이터 재기동."""
    from services.f004_service import f004_service
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE stages
            SET status = 'PENDING', started_at = NULL, finished_at = NULL
            WHERE status = 'RUNNING' AND job_id IN (
                SELECT id FROM content_jobs WHERE feature_id = 'F004' AND status = 'RUNNING'
            )
            """
        )
        cursor = await conn.execute(
            "SELECT id FROM content_jobs WHERE feature_id = 'F004' AND status = 'RUNNING'"
        )
        rows = await cursor.fetchall()
        await conn.commit()
    for row in rows:
        job_id = row[0]
        f004_service._spawn_orchestrator(job_id)
        print(f"[App] F004 content_jobs id={job_id} 오케스트레이터 재기동 완료")


async def _restore_f005_running_jobs() -> None:
    """서버 재시작 시 F005 RUNNING 상태 content_jobs 오케스트레이터 재기동."""
    from services.f005_service import f005_service
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE stages
            SET status = 'PENDING', started_at = NULL, finished_at = NULL
            WHERE status = 'RUNNING' AND job_id IN (
                SELECT id FROM content_jobs WHERE feature_id = 'F005' AND status = 'RUNNING'
            )
            """
        )
        cursor = await conn.execute(
            "SELECT id FROM content_jobs WHERE feature_id = 'F005' AND status = 'RUNNING'"
        )
        rows = await cursor.fetchall()
        await conn.commit()
    for row in rows:
        job_id = row[0]
        f005_service._spawn_orchestrator(job_id)
        print(f"[App] F005 content_jobs id={job_id} 오케스트레이터 재기동 완료")


async def _restore_f006_running_jobs() -> None:
    """서버 재시작 시 F006 RUNNING 상태 content_jobs 오케스트레이터 재기동."""
    from services.f006_service import f006_service
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE stages
            SET status = 'PENDING', started_at = NULL, finished_at = NULL
            WHERE status = 'RUNNING' AND job_id IN (
                SELECT id FROM content_jobs WHERE feature_id = 'F006' AND status = 'RUNNING'
            )
            """
        )
        cursor = await conn.execute(
            "SELECT id FROM content_jobs WHERE feature_id = 'F006' AND status = 'RUNNING'"
        )
        rows = await cursor.fetchall()
        await conn.commit()
    for row in rows:
        job_id = row[0]
        f006_service._spawn_orchestrator(job_id)
        print(f"[App] F006 content_jobs id={job_id} 오케스트레이터 재기동 완료")


async def _restore_f007_running_jobs() -> None:
    """서버 재시작 시 F007 RUNNING 상태 content_jobs 오케스트레이터 재기동."""
    from services.f007_service import f007_service
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """
            UPDATE stages
            SET status = 'PENDING', started_at = NULL, finished_at = NULL
            WHERE status = 'RUNNING' AND job_id IN (
                SELECT id FROM content_jobs WHERE feature_id = 'F007' AND status = 'RUNNING'
            )
            """
        )
        cursor = await conn.execute(
            "SELECT id FROM content_jobs WHERE feature_id = 'F007' AND status = 'RUNNING'"
        )
        rows = await cursor.fetchall()
        await conn.commit()
    for row in rows:
        job_id = row[0]
        f007_service._spawn_orchestrator(job_id)
        print(f"[App] F007 content_jobs id={job_id} 오케스트레이터 재기동 완료")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """앱 생명주기 관리 — 시작 시 DB/스케줄러 초기화, 종료 시 스케줄러 정지."""
    await init_db()
    print("[App] DB 초기화 완료")

    # 이전 실행에서 비정상 종료된 RUNNING 태스크 정리
    await _cleanup_stale_running_tasks()

    # F001 RUNNING content_jobs 오케스트레이터 재기동
    await _restore_f001_running_jobs()

    # F004 RUNNING content_jobs 오케스트레이터 재기동
    await _restore_f004_running_jobs()

    # F005 RUNNING content_jobs 오케스트레이터 재기동
    await _restore_f005_running_jobs()

    # F006 RUNNING content_jobs 오케스트레이터 재기동
    await _restore_f006_running_jobs()

    # F007 RUNNING content_jobs 오케스트레이터 재기동
    await _restore_f007_running_jobs()

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
    app.include_router(f001.router)
    app.include_router(f004.router)
    app.include_router(f005.router)
    app.include_router(f006.router)
    app.include_router(f007.router)

    # F003 결과 파일 정적 서빙 (이미지/동영상) — 프로젝트 루트 기준 상대 경로
    f003_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f003"
    f003_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f003", StaticFiles(directory=str(f003_results_dir)), name="f003_results")

    # F001 결과 파일 정적 서빙 (스크립트/TTS/영상) — 프로젝트 루트 기준 상대 경로
    f001_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f001"
    f001_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f001", StaticFiles(directory=str(f001_results_dir)), name="f001_results")

    # F004 결과 파일 정적 서빙 (스크립트/TTS/영상) — 프로젝트 루트 기준 상대 경로
    f004_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f004"
    f004_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f004", StaticFiles(directory=str(f004_results_dir)), name="f004_results")

    # F005 결과 파일 정적 서빙 (스크립트/TTS/영상) — 프로젝트 루트 기준 상대 경로
    f005_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f005"
    f005_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f005", StaticFiles(directory=str(f005_results_dir)), name="f005_results")

    # F006 결과 파일 정적 서빙 (스크립트/TTS/영상) — 프로젝트 루트 기준 상대 경로
    f006_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f006"
    f006_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f006", StaticFiles(directory=str(f006_results_dir)), name="f006_results")

    # F007 결과 파일 정적 서빙 (스크립트/TTS/영상) — 프로젝트 루트 기준 상대 경로
    f007_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f007"
    f007_results_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/results/f007", StaticFiles(directory=str(f007_results_dir), html=False), name="f007_results")

    @app.get("/", include_in_schema=False)
    async def root():
        """루트 접근 시 API 문서로 리다이렉트."""
        return RedirectResponse(url="/docs")

    return app


app: FastAPI = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
