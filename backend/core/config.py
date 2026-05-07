# 목적: 애플리케이션 전역 설정값 관리 (DB 경로, Ollama URL 등)
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# SQLite DB 파일 절대 경로
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"

# SQLAlchemy 비동기 DB URL
DATABASE_URL: str = f"sqlite+aiosqlite:///{DB_PATH}"

# Ollama 로컬 서버 기본 URL
OLLAMA_BASE_URL: str = "http://localhost:11434"

# 파이프라인 runner 스크립트 경로
PIPELINE_RUNNER_PATH: str = r"C:\Develop\Dash\pipelines\runner.py"

# 작업 목록 기본 페이지 크기
DEFAULT_TASK_LIMIT: int = 20

# SearXNG 로컬 메타 검색 엔진 기본 URL
SEARXNG_BASE_URL: str = "http://192.168.20.80:8888"
