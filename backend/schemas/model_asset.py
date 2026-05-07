# 목적: model_inventory 및 model_download_queue API 응답/요청 스키마 정의
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ModelInventoryResponse(BaseModel):
    """model_inventory 단건 응답 스키마."""

    id: int
    model_type: str
    name: str
    filename: str
    local_path: str
    civitai_version_id: Optional[int] = None
    hf_repo_id: Optional[str] = None
    is_downloaded: bool
    file_size_mb: Optional[float] = None
    downloaded_at: Optional[datetime] = None
    base_model: Optional[str] = None
    style_tags: Optional[str] = None

    model_config = {"from_attributes": True}


class DownloadQueueResponse(BaseModel):
    """model_download_queue 단건 응답 스키마."""

    id: int
    source: str
    model_type: str
    source_id: str
    target_path: str
    status: str
    progress_pct: float = 0.0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DownloadRequest(BaseModel):
    """POST /api/model-assets/download 요청 스키마."""

    source: str = Field(..., description="civitai 또는 huggingface")
    model_type: str = Field(..., description="checkpoint/lora/motion_module/vae/clip")
    source_id: str = Field(..., description="CivitAI version_id 또는 HF repo_id")
    filename: str = Field(..., description="저장할 파일명")
    target_dir: Optional[str] = Field(default=None, description="저장 디렉토리 (None이면 기본값)")
