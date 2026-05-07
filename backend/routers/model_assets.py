# 목적: /api/model-assets 엔드포인트 라우터 — 모델 인벤토리 조회 및 다운로드 관리
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Optional

import os

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query

from core.database import get_db
from schemas.model_asset import DownloadQueueResponse, DownloadRequest, ModelInventoryResponse
from services.download_service import download_service
from services.model_service import model_service

router = APIRouter(prefix="/api/model-assets", tags=["model-assets"])


@router.get("", response_model=list[ModelInventoryResponse])
async def list_model_assets(
    model_type: Optional[str] = Query(default=None, description="모델 유형 필터 (checkpoint/lora/motion_module/vae/clip)"),
    base_model: Optional[str] = Query(default=None, description="기반 모델 필터 (SD1.5/SDXL/Flux.1)"),
    db: aiosqlite.Connection = Depends(get_db),
) -> list[ModelInventoryResponse]:
    """모델 인벤토리 목록을 반환한다."""
    items = await model_service.list_models(db, model_type=model_type, base_model=base_model)
    return [ModelInventoryResponse.model_validate(item) for item in items]


@router.get("/downloads", response_model=list[DownloadQueueResponse])
async def list_downloads(
    db: aiosqlite.Connection = Depends(get_db),
) -> list[DownloadQueueResponse]:
    """다운로드 이력 목록을 반환한다 (진행 중 포함)."""
    items = await download_service.list_downloads(db)
    return [DownloadQueueResponse.model_validate(item) for item in items]


@router.post("/download", status_code=202)
async def trigger_download(
    request: DownloadRequest,
    db: aiosqlite.Connection = Depends(get_db),
) -> dict:
    """모델 다운로드를 큐에 추가한다. 실제 다운로드는 파이프라인 프로세스에서 실행."""
    # ComfyUI 기본 모델 디렉토리 매핑
    dir_map = {
        "checkpoint": r"C:\ComfyUI\models\checkpoints",
        "lora": r"C:\ComfyUI\models\loras",
        "motion_module": r"C:\ComfyUI\models\animatediff_models",
        "vae": r"C:\ComfyUI\models\vae",
        "clip": r"C:\ComfyUI\models\clip",
        "diffusion_model": r"C:\ComfyUI\models\diffusion_models",
    }
    # 경로 순회 방지 — 파일명에 디렉토리 구분자 포함 불가
    safe_filename = os.path.basename(request.filename)
    if safe_filename != request.filename or not safe_filename:
        raise HTTPException(status_code=400, detail="파일명에 경로 구분자를 포함할 수 없습니다.")
    target_dir = request.target_dir or dir_map.get(request.model_type, r"C:\ComfyUI\models\checkpoints")
    target_path = os.path.join(target_dir, safe_filename)

    queue_id = await download_service.enqueue(
        db,
        source=request.source,
        model_type=request.model_type,
        source_id=request.source_id,
        target_path=target_path,
    )
    return {"queue_id": queue_id, "status": "QUEUED", "message": "다운로드 큐에 추가됨"}


@router.post("/scan", status_code=202)
async def scan_local_models() -> dict:
    """ComfyUI 모델 디렉토리를 재스캔하도록 안내한다.

    실제 스캔은 파이프라인 시작 시 ModelManager.scan_local_models()에서 수행됨.
    """
    return {"message": "모델 스캔은 파이프라인 실행 시 자동으로 수행됩니다."}
