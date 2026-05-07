# 목적: /api/health 엔드포인트 라우터 — 서버 및 Ollama 연결 상태 확인
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi import APIRouter

from schemas.task import HealthResponse, OllamaHealthResponse
from services.ollama_service import ollama_service

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """FastAPI 서버가 정상 실행 중인지 확인한다."""
    return HealthResponse(status="ok")


@router.get("/ollama", response_model=OllamaHealthResponse)
async def ollama_health_check() -> OllamaHealthResponse:
    """Ollama 로컬 서버 연결 상태와 사용 가능한 모델 목록을 반환한다."""
    result = await ollama_service.check_health()
    return OllamaHealthResponse(**result)
