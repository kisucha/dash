# 목적: /api/models 엔드포인트 — Ollama 모델 목록 조회 및 선택 모델 저장
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from core.database import get_db
from schemas.task import ModelSelectRequest, ModelsResponse
from services.ollama_service import ollama_service

router = APIRouter(prefix="/api/models", tags=["models"])

# settings 테이블 키 상수
_SETTING_KEY = "selected_model"


async def _get_selected_model(db: aiosqlite.Connection) -> str | None:
    """DB settings 테이블에서 현재 선택된 모델명을 반환한다."""
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = ?", (_SETTING_KEY,)
    )
    row = await cursor.fetchone()
    return row[0] if row else None


async def _save_selected_model(db: aiosqlite.Connection, model: str) -> None:
    """DB settings 테이블에 선택된 모델명을 저장한다 (없으면 INSERT, 있으면 UPDATE)."""
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_SETTING_KEY, model),
    )
    await db.commit()


@router.get("", response_model=ModelsResponse)
async def get_models(db: aiosqlite.Connection = Depends(get_db)) -> ModelsResponse:
    """Ollama에서 사용 가능한 모델 목록과 현재 선택된 모델을 반환한다."""
    health = await ollama_service.check_health()
    models: list[str] = health.get("models", [])

    selected = await _get_selected_model(db)

    # 선택된 모델이 없거나 목록에 없으면 첫 번째 로컬 모델로 초기화
    if models and (selected is None or selected not in models):
        selected = models[0]
        await _save_selected_model(db, selected)

    return ModelsResponse(models=models, selected_model=selected)


@router.put("/select", response_model=ModelsResponse)
async def select_model(
    request: ModelSelectRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> ModelsResponse:
    """모델을 선택하고 DB에 저장한다."""
    # Ollama에 해당 모델이 실제로 존재하는지 검증
    health = await ollama_service.check_health()
    models: list[str] = health.get("models", [])

    if request.model not in models:
        raise HTTPException(
            status_code=400,
            detail=f"'{request.model}' 모델이 Ollama에 없습니다. 설치된 모델: {models}",
        )

    await _save_selected_model(db, request.model)
    return ModelsResponse(models=models, selected_model=request.model)
