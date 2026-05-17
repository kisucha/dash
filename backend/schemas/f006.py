# 목적: F006 유튜브 컨텐츠 제작 V4 (채팅 기반) 파이프라인 Pydantic 스키마 정의
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── 작업 생성 요청 스키마 ─────────────────────────────────────────

class F006JobCreateRequest(BaseModel):
    """POST /api/f006/jobs 요청 바디 — 채팅 기반 유튜브 콘텐츠 작업 생성 파라미터.

    F004와 달리 topic/user_context 필수 입력, target_count/search_provider 제거.
    """

    # 채널 카테고리 (스크립트 톤/방향 결정에 사용 — 예: IT/기술, 경제/재테크)
    channel_category: str = Field(..., min_length=1, max_length=100, description="채널 카테고리")
    # 채널 이름 (슬라이드 헤더 브랜딩용 — 예: 누구나 다아는 주식 이야기)
    channel_name: Optional[str] = Field(default=None, max_length=100, description="채널 이름 (슬라이드 헤더용)")
    # 영상 주제 — AI 채팅에서 확인한 주제 (필수)
    topic: str = Field(..., min_length=2, max_length=200, description="영상 주제 — 채팅에서 확인한 주제")
    # 채팅에서 수집한 정보/메모 (필수)
    user_context: str = Field(..., min_length=10, max_length=50000, description="채팅에서 수집한 정보/메모")
    # 추가 키워드 힌트 (선택)
    keywords_hint: Optional[str] = Field(default=None, max_length=200, description="추가 키워드 힌트")
    # 트렌드 보완 검색 기간(일) — 보완 검색은 항상 searxng 사용
    days: int = Field(default=7, ge=1, le=30, description="보완 검색 기간(일)")
    # 채널 톤앤매너
    channel_tone: str = Field(default="educational", description="educational/entertaining/tutorial")
    # 목표 영상 길이(분)
    duration_min: int = Field(default=10, ge=1, le=60, description="목표 영상 길이(분)")
    # 훅 스타일 (도입부 형식)
    hook_style: str = Field(default="question", description="question/shocking_fact/story")
    # CTA 유형 (행동 유도)
    cta_type: str = Field(default="subscribe", description="subscribe/like/comment")
    # TTS 엔진 선택
    tts_provider: str = Field(default="edge_tts", description="edge_tts/coqui/gtts/elevenlabs/openai")
    # TTS 목소리 ID (프로바이더별 상이 — edge_tts: ko-KR-SunHiNeural 등)
    tts_voice: Optional[str] = Field(default=None, description="TTS 목소리 ID")
    # TTS 발화 속도 (edge_tts 전용 — "+0%"기본, "+20%"=1.2배속, "-20%"=0.8배속)
    tts_rate: Optional[str] = Field(default="+0%", description="TTS 발화 속도 (edge_tts)")
    # TTS 음성 피치 (edge_tts 전용 — "+0Hz"기본)
    tts_pitch: Optional[str] = Field(default="+0Hz", description="TTS 피치 (edge_tts)")
    # TTS 건너뛰기 여부
    tts_skip: bool = Field(default=False, description="TTS 건너뛰기")
    # 이미지/영상 생성 백엔드
    generation_backend: str = Field(default="comfyui", description="comfyui/skip")
    # 생성 건너뛰기 모드 (generation_backend=skip 시 적용)
    skip_mode: Optional[str] = Field(default=None, description="text_slide/script_only")
    # 영상 비주얼 스타일
    visual_style: str = Field(default="presentation", description="영상 비주얼 스타일")
    # 업로드 방식 (수동승인 / 자동)
    upload_mode: str = Field(default="manual_approval", description="auto/manual_approval")
    # YouTube 공개 설정
    privacy: str = Field(default="private", description="public/unlisted/private")
    # 렌더링 모드 선택 (ffmpeg/kenburns/video_bg/remotion_native)
    # ffmpeg: 기존 FFmpeg concat (기본값)
    # kenburns: Remotion + Ken Burns 애니메이션 (PNG 슬라이드 유지)
    # video_bg: Remotion + 애니메이션 그라디언트 배경 + 텍스트 JSON 렌더링 (PNG 없음)
    # remotion_native: Remotion 전체 네이티브 렌더링 (PNG 없음, 차트 애니메이션 포함)
    render_mode: str = Field(default="ffmpeg", description="렌더링 모드 (ffmpeg/kenburns/video_bg/remotion_native/cardnews)")
    # [DEPRECATED] Remotion 렌더링 사용 여부 — render_mode 도입으로 deprecated. 하위 호환성 유지
    use_remotion: bool = Field(default=False, description="[DEPRECATED] Remotion 렌더링 활성화 — render_mode='kenburns' 사용 권장")
    # Remotion 테마 선택 (dark_blue/warm_gray/clean_white)
    remotion_theme: str = Field(default="dark_blue", description="Remotion 테마 (dark_blue/warm_gray/clean_white)")
    # Remotion 슬라이드 전환 모드 (auto/fade_only/slide_only)
    remotion_transition: str = Field(default="auto", description="Remotion 전환 모드 (auto/fade_only/slide_only)")
    # Remotion 병렬 렌더 스레드 수
    remotion_concurrency: int = Field(default=4, ge=1, le=16, description="Remotion 병렬 렌더링 스레드 수")


# ── 단건 응답 스키마 ──────────────────────────────────────────────

class F006StageResponse(BaseModel):
    """stages 테이블 단건 응답 스키마 (F006 전용)."""

    # 스테이지 PK
    id: int
    # 소속 content_jobs ID
    job_id: int
    # 스테이지 식별자 (STAGE_01_INPUT 등)
    stage_id: str
    # 실행 순서 (1~6)
    stage_order: int
    # 스테이지 상태 (PENDING/RUNNING/DONE/FAILED/REJECTED/SKIPPED)
    status: str
    # 스테이지 입력 JSON 문자열
    input_data: Optional[str] = None
    # 스테이지 출력 JSON 문자열
    output_data: Optional[str] = None
    # 반송 사유
    rejection_reason: Optional[str] = None
    # 반송 대상 스테이지 ID
    rejection_target: Optional[str] = None
    # 재시도 횟수
    retry_count: int
    # skip 여부 (0=false, 1=true)
    skip: int
    # skip 모드 (text_slide/script_only)
    skip_mode: Optional[str] = None
    # 생성 시각
    created_at: datetime
    # 시작 시각
    started_at: Optional[datetime] = None
    # 완료 시각
    finished_at: Optional[datetime] = None
    # 실행 프로세스 PID (취소용)
    task_pid: Optional[int] = None

    model_config = {"from_attributes": True}


class F006ContentJobResponse(BaseModel):
    """content_jobs 테이블 단건 응답 스키마 (F006 전용) — 스테이지 목록 포함."""

    # 작업 PK
    id: int
    # 업무 식별자 (F006 고정)
    feature_id: str
    # 전체 작업 상태 (PENDING/RUNNING/DONE/FAILED/CANCELLED/PENDING_APPROVAL)
    status: str
    # 채널 카테고리
    channel_category: Optional[str] = None
    # 최초 입력 파라미터 JSON 문자열
    initial_params: Optional[str] = None
    # 현재 실행 중인 스테이지 ID
    current_stage: Optional[str] = None
    # 업로드 방식
    upload_mode: str
    # 생성 시각
    created_at: datetime
    # 시작 시각
    started_at: Optional[datetime] = None
    # 완료 시각
    finished_at: Optional[datetime] = None
    # 실행 트리거 (manual/schedule)
    triggered_by: str
    # YouTube 영상 ID (업로드 완료 후 채워짐)
    youtube_video_id: Optional[str] = None
    # 관리자 메모
    notes: Optional[str] = None
    # 레거시 tasks 테이블 연동 ID
    legacy_task_id: Optional[int] = None
    # 소속 스테이지 목록 (stage_order ASC)
    stages: list[F006StageResponse] = []

    model_config = {"from_attributes": True}


class F006ContentJobListResponse(BaseModel):
    """GET /api/f006/jobs 목록 응답 스키마 — cursor 기반 페이징 (F006 전용)."""

    # 작업 목록
    items: list[F006ContentJobResponse]
    # 다음 페이지 시작 cursor (없으면 마지막 페이지)
    next_cursor: Optional[int]
    # 다음 페이지 존재 여부
    has_more: bool


# ── 스테이지 제어 요청 스키마 ─────────────────────────────────────

class F006StageRetryRequest(BaseModel):
    """POST /api/f006/jobs/{job_id}/stages/{stage_id}/retry 요청 바디 (F006 전용)."""

    # 재시도 시 입력 파라미터 override (없으면 기존 input_data 사용)
    override_params: Optional[dict[str, Any]] = None


class F006StageRejectRequest(BaseModel):
    """POST /api/f006/jobs/{job_id}/stages/{stage_id}/reject 요청 바디 (F006 전용)."""

    # 반송 사유 (필수)
    rejection_reason: str = Field(..., min_length=1, description="반송 사유")
    # 반송 대상 스테이지 ID (없으면 직전 스테이지)
    rejection_target: Optional[str] = None


class F006ApproveRequest(BaseModel):
    """POST /api/f006/jobs/{job_id}/approve 요청 바디 — 업로드 최종 승인 (F006 전용)."""

    # 최종 YouTube 제목 (없으면 STAGE_06 생성값 사용)
    final_title: Optional[str] = None
    # 최종 YouTube 설명
    final_description: Optional[str] = None
    # 최종 태그 목록
    final_tags: Optional[list[str]] = None


class F006ScriptRerunRequest(BaseModel):
    """POST /api/f006/jobs/{job_id}/rerun-from-tts 요청 바디 — 스크립트 수정 후 TTS부터 재생성 (F006 전용)."""

    # 수정된 전체 나레이션 텍스트 (STAGE_03 TTS에 전달)
    script_text: str = Field(..., min_length=1, description="수정된 나레이션 전체 텍스트")
    # 슬라이드 배열 (없으면 STAGE_02 기존 slides 유지)
    slides: Optional[list[dict]] = None
