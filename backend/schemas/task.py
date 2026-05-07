# 목적: Tasks, Schedules, Features API의 Pydantic 요청/응답 스키마 정의
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Task 스키마 ────────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    """POST /api/tasks 요청 바디 스키마."""

    # 실행할 업무 식별자
    feature_id: str = Field(..., description="업무 식별자 (예: F001)")

    # 파이프라인 입력 파라미터 — 업무별로 구조가 다름
    params: dict[str, Any] = Field(default_factory=dict, description="파이프라인 입력 파라미터")


class TaskResponse(BaseModel):
    """Task 단건 응답 스키마."""

    id: int
    feature_id: str
    status: str
    params: str | None
    result: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    triggered_by: str

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    """GET /api/tasks 목록 응답 스키마."""

    total: int
    items: list[TaskResponse]


# ── Schedule 스키마 ────────────────────────────────────────────

class ScheduleCreateRequest(BaseModel):
    """POST /api/schedules 요청 바디 스키마."""

    feature_id: str = Field(..., description="업무 식별자")
    cron_expr: str = Field(..., description="cron 표현식 (예: '0 9 * * *')")
    default_params: dict[str, Any] = Field(
        default_factory=dict, description="스케줄 기본 파라미터"
    )
    is_active: bool = Field(default=True, description="스케줄 활성화 여부")


class ScheduleUpdateRequest(BaseModel):
    """PUT /api/schedules/{id} 요청 바디 스키마 — 모든 필드 선택적."""

    cron_expr: str | None = Field(default=None, description="cron 표현식")
    default_params: dict[str, Any] | None = Field(default=None, description="기본 파라미터")
    is_active: bool | None = Field(default=None, description="활성화 여부")


class ScheduleResponse(BaseModel):
    """Schedule 단건 응답 스키마."""

    id: int
    feature_id: str
    cron_expr: str
    default_params: str | None
    is_active: bool
    last_run_at: datetime | None

    model_config = {"from_attributes": True}


# ── Feature 스키마 ─────────────────────────────────────────────

class FeatureInputField(BaseModel):
    """Feature 입력 필드 메타데이터."""

    name: str
    title: str | None = None          # 폼 레이블 (없으면 name 사용)
    type: str
    required: bool
    description: str
    default: Any = None               # 폼 초기값
    options: list[str] = Field(default_factory=list)  # select 타입 전용 선택지 목록


class FeatureResponse(BaseModel):
    """Feature 단건 응답 스키마."""

    feature_id: str
    name: str
    description: str
    supports_schedule: bool
    input_schema: list[FeatureInputField]


# ── Models 스키마 ─────────────────────────────────────────────

class ModelsResponse(BaseModel):
    """GET /api/models 응답 스키마."""

    models: list[str]
    selected_model: str | None = None


class ModelSelectRequest(BaseModel):
    """PUT /api/models/select 요청 바디 스키마."""

    model: str = Field(..., description="선택할 Ollama 모델명")


# ── Health 스키마 ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    """GET /api/health 응답 스키마."""

    status: str


class OllamaHealthResponse(BaseModel):
    """GET /api/health/ollama 응답 스키마."""

    status: str
    # Ollama 에서 반환된 모델 태그 목록 (연결 성공 시 채워짐)
    models: list[str] = Field(default_factory=list)
    error: str | None = None
