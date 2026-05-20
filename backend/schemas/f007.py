# 목적: F007 YouTube 자동화 파이프라인 Pydantic 스키마
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class F007JobCreateRequest(BaseModel):
    """F007 작업 생성 요청 스키마 — channel_type(finance/language) 분기 지원."""

    channel_type: str = Field(..., description="채널 유형: finance 또는 language")
    channel_name: Optional[str] = Field(default=None, max_length=100)
    keywords_hint: Optional[str] = Field(default=None, max_length=200)
    days: int = Field(default=3, ge=1, le=14)
    channel_tone: str = Field(default="educational")
    duration_min: int = Field(default=8, ge=1, le=60)
    hook_style: str = Field(default="question")
    cta_type: str = Field(default="subscribe")
    tts_provider: str = Field(default="supertone3")
    tts_voice: str = Field(default="F1")
    tts_skip: bool = Field(default=False)
    slide_theme: str = Field(default="dark_blue")
    bgm_path: str = Field(default="random")
    bgm_volume: float = Field(default=0.15, ge=0.0, le=1.0)
    upload_mode: str = Field(default="manual_approval")
    privacy: str = Field(default="private")

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        """channel_type이 허용된 값인지 검증한다."""
        allowed = {"finance", "language"}
        if v not in allowed:
            raise ValueError(f"channel_type은 {allowed} 중 하나여야 합니다. 입력값: {v!r}")
        return v

    @field_validator("upload_mode")
    @classmethod
    def validate_upload_mode(cls, v: str) -> str:
        """upload_mode가 허용된 값인지 검증한다."""
        allowed = {"auto", "manual_approval", "skip"}
        if v not in allowed:
            raise ValueError(f"upload_mode는 {allowed} 중 하나여야 합니다.")
        return v


class F007ContentJobResponse(BaseModel):
    """F007 content_job 단건 응답 스키마 — stages 목록 포함."""

    id: int
    feature_id: str
    status: str
    channel_category: Optional[str] = None
    initial_params: Optional[str] = None
    current_stage: Optional[str] = None
    upload_mode: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    triggered_by: str
    youtube_video_id: Optional[str] = None
    notes: Optional[str] = None
    stages: list[dict] = []

    model_config = {"from_attributes": True}


class F007ContentJobListResponse(BaseModel):
    """F007 content_jobs 페이지 목록 응답 스키마 — cursor 기반 페이징."""

    items: list[F007ContentJobResponse]
    next_cursor: Optional[int]
    has_more: bool
