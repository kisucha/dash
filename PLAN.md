# F001 유튜브 AI 자동화 파이프라인 구현 계획

| 필드 | 내용 |
|------|------|
| 문서명 | F001 유튜브 AI 자동화 파이프라인 구현 계획 |
| 버전 | V1 |
| 날짜 | 2026-05-12 |
| 작성자 | claude-sonnet-4-6 |
| 문서 유형 | 구현 계획 |
| 모델 | claude-sonnet-4-6 |

---

## 목차

0. 구현 범위 요약
1. DB 스키마 변경 계획
2. 백엔드 API 추가 계획
3. cursor 기반 페이징 설계
4. 파이프라인 구조 재설계
5. 스테이지별 구현 상세
6. 프론트엔드 변경 계획
7. 스토리지 구조
8. 레거시 F001 하이브리드 처리
9. 외부 서비스 설치/설정 계획
10. 구현 순서 (Phase별)
11. 트레이드오프 및 리스크
12. 미결/보류 사항

---

## 섹션 0. 구현 범위 요약

### 신규 생성 파일

| 경로 | 설명 |
|------|------|
| `backend/routers/f001.py` | F001 전용 API 라우터 |
| `backend/schemas/f001.py` | F001 Pydantic 스키마 |
| `backend/services/f001_service.py` | content_jobs / stages CRUD 서비스 |
| `pipelines/f001_youtube/orchestrator.py` | 6스테이지 오케스트레이터 |
| `pipelines/f001_youtube/stages/__init__.py` | 스테이지 패키지 초기화 |
| `pipelines/f001_youtube/stages/stage01_research.py` | 주제 발굴 스테이지 |
| `pipelines/f001_youtube/stages/stage02_script.py` | 스크립트 생성 스테이지 |
| `pipelines/f001_youtube/stages/stage03_tts.py` | TTS 보이스오버 스테이지 |
| `pipelines/f001_youtube/stages/stage04_video.py` | 영상/이미지 생성 스테이지 |
| `pipelines/f001_youtube/stages/stage05_edit.py` | 영상 편집 스테이지 |
| `pipelines/f001_youtube/stages/stage06_upload.py` | SEO + YouTube 업로드 스테이지 |
| `pipelines/f001_youtube/validators/__init__.py` | 검증기 패키지 초기화 |
| `pipelines/f001_youtube/validators/stage_validator.py` | 스테이지 결과 검증 클래스 |
| `pipelines/f001_youtube/config.json` | F001 설정 파일 (ComfyUI 경로 등) |
| `pipelines/f001_youtube/run_orchestrator.py` | subprocess 진입점 (argv[1]=job_id) |
| `pipelines/f001_youtube/migrate_legacy.py` | 레거시 tasks → content_jobs 마이그레이션 유틸 |
| `frontend/src/views/F001View.vue` | F001 메인 화면 |
| `frontend/src/views/F001JobDetailView.vue` | 스테이지 타임라인 상세 |
| `frontend/src/components/StageTimeline.vue` | 스테이지 진행 현황 컴포넌트 |
| `frontend/src/components/StageResultViewer.vue` | 스테이지 결과 표시 컴포넌트 |
| `frontend/src/store/f001.js` | F001 전용 Pinia 스토어 |

### 수정 파일

| 경로 | 변경 내용 |
|------|----------|
| `backend/core/database.py` | `content_jobs`, `stages` 테이블 추가 |
| `backend/main.py` | f001 라우터 등록 (`from routers import ..., f001` 한 줄 추가 + `app.include_router(f001.router)`), F001 결과 StaticFiles 마운트 추가 |
| `frontend/src/router/index.js` | F001View, F001JobDetailView 라우트 추가 |
| `frontend/src/views/DashboardView.vue` | F001 클릭 시 F001Feature 라우팅 추가 |
| `frontend/src/api/index.js` | F001 API 함수 추가 |

### 삭제 파일
없음 (기존 F001 레거시 pipeline.py 유지)

### 영향받는 기존 파일 (직접 수정 없음, 동작 확인 필요)

- `pipelines/runner.py` — F001_MULTI 또는 별도 orchestrator runner 추가 검토 필요
- `pipelines/f001_youtube/pipeline.py` — 레거시 유지
- `pipelines/f003_video_creation/comfyui_client.py` — STAGE_04에서 재활용 (import만)

---

## 섹션 1. DB 스키마 변경 계획

### 현재 테이블 구조 확인

`backend/core/database.py` 분석 결과:
- `tasks` — 기존 단일 파이프라인 작업 (F001/F002/F003 공용)
- `schedules` — 스케줄 관리
- `settings` — key-value 설정
- `model_inventory` — F003 모델 인벤토리
- `model_download_queue` — F003 모델 다운로드 큐

**기존 테이블 변경 없음** — tasks 테이블은 F002, F003이 그대로 사용하므로 수정하지 않는다.

### 추가 테이블 1: `content_jobs`

F001 멀티스테이지 작업 단위. 하나의 유튜브 영상 제작 프로젝트에 해당한다.

```python
# backend/core/database.py 추가 내용 (SQLite DDL 스타일)

_CREATE_CONTENT_JOBS = """
CREATE TABLE IF NOT EXISTS content_jobs (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    feature_id        TEXT     NOT NULL DEFAULT 'F001',
    -- 작업 전체 상태: PENDING/RUNNING/DONE/FAILED/CANCELLED/PENDING_APPROVAL
    status            TEXT     NOT NULL DEFAULT 'PENDING',
    channel_category  TEXT,                        -- 채널 카테고리 (예: IT/기술)
    initial_params    TEXT,                        -- 최초 입력 파라미터 JSON
    current_stage     TEXT,                        -- 현재 실행 중 스테이지 ID
    -- 업로드 방식: manual_approval(기본)/auto
    upload_mode       TEXT     NOT NULL DEFAULT 'manual_approval',
    created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at        DATETIME,
    finished_at       DATETIME,
    triggered_by      TEXT     NOT NULL DEFAULT 'manual',
    youtube_video_id  TEXT,                        -- 업로드 완료 후 YouTube 영상 ID
    notes             TEXT,                        -- 관리자 메모 (승인 흐름용)
    -- 기존 tasks 테이블 연동용 (마이그레이션 시 원본 task id 보존)
    legacy_task_id    INTEGER
)
"""

-- 인덱스: feature_id + status 복합 조건 조회 최적화
_CREATE_IDX_CONTENT_JOBS = """
CREATE INDEX IF NOT EXISTS idx_content_jobs_feature_status
ON content_jobs(feature_id, status)
"""
```

**컬럼 타입/기본값/제약조건 요약:**

| 컬럼 | 타입 | 기본값 | 제약 | 비고 |
|------|------|--------|------|------|
| id | INTEGER | - | PK AUTOINCREMENT | |
| feature_id | TEXT | 'F001' | NOT NULL | F001 고정 |
| status | TEXT | 'PENDING' | NOT NULL | 6가지 상태 |
| channel_category | TEXT | NULL | - | STAGE_01 입력 |
| initial_params | TEXT(JSON) | NULL | - | 전체 입력 파라미터 |
| current_stage | TEXT | NULL | - | 현재 실행 중 스테이지 |
| upload_mode | TEXT | 'manual_approval' | NOT NULL | auto/manual_approval |
| created_at | DATETIME | CURRENT_TIMESTAMP | - | |
| started_at | DATETIME | NULL | - | 첫 스테이지 시작 시각 |
| finished_at | DATETIME | NULL | - | 전체 완료 시각 |
| triggered_by | TEXT | 'manual' | NOT NULL | manual/schedule |
| youtube_video_id | TEXT | NULL | - | 업로드 후 채워짐 |
| notes | TEXT | NULL | - | 관리자 메모 |
| legacy_task_id | INTEGER | NULL | - | 레거시 연동용 FK |

### 추가 테이블 2: `stages`

스테이지 실행 레코드. content_jobs 1개당 최대 6개 레코드.

```python
_CREATE_STAGES = """
CREATE TABLE IF NOT EXISTS stages (
    id               INTEGER  PRIMARY KEY AUTOINCREMENT,
    job_id           INTEGER  NOT NULL,            -- content_jobs.id 참조
    stage_id         TEXT     NOT NULL,            -- STAGE_01_RESEARCH 등
    stage_order      INTEGER  NOT NULL,            -- 1~6 실행 순서
    -- 상태: PENDING/RUNNING/DONE/FAILED/REJECTED/SKIPPED
    status           TEXT     NOT NULL DEFAULT 'PENDING',
    input_data       TEXT,                         -- 이 스테이지 입력 JSON
    output_data      TEXT,                         -- 이 스테이지 출력 JSON
    rejection_reason TEXT,                         -- REJECTED 시 반송 사유
    rejection_target TEXT,                         -- 반송할 스테이지 ID
    retry_count      INTEGER  NOT NULL DEFAULT 0,  -- 재시도 횟수
    skip             INTEGER  NOT NULL DEFAULT 0,  -- skip 여부 (0/1)
    skip_mode        TEXT,                         -- text_slide/script_only
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at       DATETIME,
    finished_at      DATETIME,
    task_pid         INTEGER                       -- 실행 프로세스 PID (취소용)
)
"""

-- 인덱스: job_id 조회(전체 스테이지 목록)와 status 조회 최적화
_CREATE_IDX_STAGES_JOB   = "CREATE INDEX IF NOT EXISTS idx_stages_job_id ON stages(job_id)"
_CREATE_IDX_STAGES_STATUS = "CREATE INDEX IF NOT EXISTS idx_stages_status ON stages(status)"
```

**컬럼 타입/기본값/제약조건 요약:**

| 컬럼 | 타입 | 기본값 | 비고 |
|------|------|--------|------|
| id | INTEGER | - | PK AUTOINCREMENT |
| job_id | INTEGER | - | NOT NULL, content_jobs.id |
| stage_id | TEXT | - | NOT NULL, STAGE_01_RESEARCH 등 |
| stage_order | INTEGER | - | NOT NULL, 1~6 |
| status | TEXT | 'PENDING' | NOT NULL |
| input_data | TEXT(JSON) | NULL | |
| output_data | TEXT(JSON) | NULL | |
| rejection_reason | TEXT | NULL | |
| rejection_target | TEXT | NULL | |
| retry_count | INTEGER | 0 | NOT NULL |
| skip | INTEGER | 0 | NOT NULL, 0=false/1=true |
| skip_mode | TEXT | NULL | text_slide/script_only |
| created_at | DATETIME | CURRENT_TIMESTAMP | |
| started_at | DATETIME | NULL | |
| finished_at | DATETIME | NULL | |
| task_pid | INTEGER | NULL | |

### init_db() 수정

```python
# database.py의 init_db() 함수에 아래 항목 추가
async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(_CREATE_TASKS)
        await conn.execute(_CREATE_SCHEDULES)
        await conn.execute(_CREATE_SETTINGS)
        await conn.execute(_CREATE_MODEL_INVENTORY)
        await conn.execute(_CREATE_MODEL_DOWNLOAD_QUEUE)
        # F001 멀티스테이지 테이블 추가
        await conn.execute(_CREATE_CONTENT_JOBS)
        await conn.execute(_CREATE_STAGES)
        await conn.execute(_CREATE_IDX_CONTENT_JOBS)
        await conn.execute(_CREATE_IDX_STAGES_JOB)
        await conn.execute(_CREATE_IDX_STAGES_STATUS)
        await conn.commit()
```

---

## 섹션 2. 백엔드 API 추가 계획

### 신규 라우터: `backend/routers/f001.py`

현재 `tasks.py` 라우터 패턴(`prefix="/api/tasks"`, `aiosqlite.Connection = Depends(get_db)`)을 그대로 적용한다.

### 신규 엔드포인트 전체 목록

| 메서드 | 경로 | 기능 | 상태코드 |
|--------|------|------|---------|
| POST | /api/f001/jobs | 새 콘텐츠 작업 생성 + 오케스트레이터 실행 | 201 |
| GET | /api/f001/jobs | 목록 조회 (cursor 기반 페이징) | 200 |
| GET | /api/f001/jobs/{job_id} | 단건 조회 (스테이지 목록 포함) | 200 |
| DELETE | /api/f001/jobs/{job_id} | 작업 취소 (RUNNING → CANCELLED) | 200 |
| GET | /api/f001/jobs/{job_id}/stages | 스테이지 목록 조회 | 200 |
| GET | /api/f001/jobs/{job_id}/stages/{stage_id} | 스테이지 단건 조회 | 200 |
| POST | /api/f001/jobs/{job_id}/stages/{stage_id}/retry | 스테이지 재시도 | 202 |
| POST | /api/f001/jobs/{job_id}/stages/{stage_id}/reject | 반송 (이전 스테이지로) | 202 |
| POST | /api/f001/jobs/{job_id}/approve | 업로드 승인 (PENDING_APPROVAL → 업로드) | 202 |
| GET | /api/f001/jobs/{job_id}/topics | STAGE_01 주제 후보 목록 | 200 |
| POST | /api/f001/jobs/{job_id}/topics/{topic_rank}/select | 주제 선택 | 200 |
| GET | /api/f001/youtube/quota | YouTube Data API 사용량 조회 | 200 |
| GET | /api/f001/legacy | 기존 tasks 테이블 F001 이력 (cursor 페이징) | 200 |
| POST | /api/f001/migrate-legacy | 레거시 tasks → content_jobs 선택 마이그레이션 | 202 |

### Pydantic 스키마 핵심 구조

```python
# backend/schemas/f001.py

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


# -- 작업 생성 요청 스키마 --

class F001JobCreateRequest(BaseModel):
    """POST /api/f001/jobs 요청 바디."""
    channel_category: str = Field(..., min_length=1, max_length=100, description="채널 카테고리")
    target_count: int = Field(default=5, ge=1, le=20, description="주제 후보 개수")
    search_provider: str = Field(default="youtube+searxng", description="youtube+searxng/searxng")
    keywords_hint: Optional[str] = Field(default=None, max_length=200, description="추가 키워드 힌트")
    days: int = Field(default=7, ge=1, le=30, description="트렌드 검색 기간(일)")
    channel_tone: str = Field(default="educational", description="educational/entertaining/tutorial")
    duration_min: int = Field(default=10, ge=1, le=60, description="목표 영상 길이(분)")
    hook_style: str = Field(default="question", description="question/shocking_fact/story")
    cta_type: str = Field(default="subscribe", description="subscribe/like/comment")
    tts_provider: str = Field(default="coqui", description="coqui/kokoro/elevenlabs/openai")
    tts_skip: bool = Field(default=False, description="TTS 건너뛰기")
    generation_backend: str = Field(default="comfyui", description="comfyui/skip")
    skip_mode: Optional[str] = Field(default=None, description="text_slide/script_only (skip 시)")
    visual_style: str = Field(default="presentation", description="영상 비주얼 스타일")
    upload_mode: str = Field(default="manual_approval", description="auto/manual_approval")
    privacy: str = Field(default="private", description="public/unlisted/private")


# -- 단건 응답 스키마 --

class StageResponse(BaseModel):
    """stages 테이블 단건 응답."""
    id: int
    job_id: int
    stage_id: str
    stage_order: int
    status: str
    input_data: Optional[str] = None
    output_data: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejection_target: Optional[str] = None
    retry_count: int
    skip: int
    skip_mode: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ContentJobResponse(BaseModel):
    """content_jobs 단건 응답 (스테이지 목록 포함 가능)."""
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
    legacy_task_id: Optional[int] = None
    stages: list[StageResponse] = []
    model_config = {"from_attributes": True}


class ContentJobListResponse(BaseModel):
    """GET /api/f001/jobs 목록 응답 -- cursor 기반 페이징."""
    items: list[ContentJobResponse]
    next_cursor: Optional[int] = None
    has_more: bool


class StageRetryRequest(BaseModel):
    """POST .../retry 요청."""
    override_params: Optional[dict[str, Any]] = Field(default=None)


class StageRejectRequest(BaseModel):
    """POST .../reject 요청."""
    rejection_reason: str = Field(..., min_length=1)
    rejection_target: Optional[str] = Field(default=None)


class TopicSelectRequest(BaseModel):
    """주제 선택 요청."""
    selected_topic_title: str = Field(..., min_length=1)


class ApproveRequest(BaseModel):
    """업로드 승인 요청 -- 최종 메타데이터 수정 포함."""
    final_title: Optional[str] = Field(default=None)
    final_description: Optional[str] = Field(default=None)
    final_tags: Optional[list[str]] = Field(default=None)
```

### 라우터 엔드포인트 시그니처

```python
# backend/routers/f001.py (핵심 시그니처)
router = APIRouter(prefix="/api/f001", tags=["f001"])

@router.post("/jobs", response_model=ContentJobResponse, status_code=201)
async def create_job(request: F001JobCreateRequest, db: aiosqlite.Connection = Depends(get_db))

@router.get("/jobs", response_model=ContentJobListResponse)
async def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
)

@router.get("/jobs/{job_id}", response_model=ContentJobResponse)
async def get_job(job_id: int, db: aiosqlite.Connection = Depends(get_db))

@router.post("/jobs/{job_id}/stages/{stage_id}/retry", status_code=202)
async def retry_stage(job_id: int, stage_id: str, request: StageRetryRequest, db: aiosqlite.Connection = Depends(get_db))

@router.post("/jobs/{job_id}/stages/{stage_id}/reject", status_code=202)
async def reject_stage(job_id: int, stage_id: str, request: StageRejectRequest, db: aiosqlite.Connection = Depends(get_db))

@router.post("/jobs/{job_id}/approve", status_code=202)
async def approve_job(job_id: int, request: ApproveRequest, db: aiosqlite.Connection = Depends(get_db))

@router.get("/legacy", response_model=TaskListResponse)
async def list_legacy_jobs(limit: int = Query(default=20), cursor: int | None = Query(default=None), db: aiosqlite.Connection = Depends(get_db))

@router.get("/youtube/quota")
async def get_youtube_quota()
```

---

## 섹션 3. cursor 기반 페이징 설계

### 현재 구현 패턴 분석

`backend/services/task_service.py`의 `list_tasks()` 분석:

```python
# 현재 구현된 cursor 페이징 핵심 로직
# cursor = 마지막 수신 item의 id
# id DESC 정렬이므로: cursor보다 id가 작은(더 오래된) 항목 반환
# limit+1개 조회로 has_more 판단 (n+1 쿼리 패턴)

fetch_limit = limit + 1
"SELECT * FROM tasks WHERE id < ? ORDER BY id DESC LIMIT ?"  # cursor 있을 때
"SELECT * FROM tasks ORDER BY id DESC LIMIT ?"               # cursor 없을 때

has_more = len(items) > limit
if has_more:
    items = items[:limit]
next_cursor = items[-1]["id"] if has_more else None
```

### content_jobs 목록에 동일 패턴 적용

```python
# backend/services/f001_service.py -- list_jobs() 메서드

async def list_jobs(
    db: aiosqlite.Connection,
    limit: int = 20,
    cursor: Optional[int] = None,
    status: Optional[str] = None,
) -> tuple[list[dict], Optional[int], bool]:
    """cursor 기반 페이징으로 content_jobs 목록 조회.
    task_service.list_tasks()와 동일한 n+1 패턴 적용.
    반환: (items, next_cursor, has_more)
    """
    fetch_limit = limit + 1

    if cursor is not None and status:
        db_cursor = await db.execute(
            "SELECT * FROM content_jobs WHERE id < ? AND status = ? ORDER BY id DESC LIMIT ?",
            (cursor, status, fetch_limit),
        )
    elif cursor is not None:
        db_cursor = await db.execute(
            "SELECT * FROM content_jobs WHERE id < ? ORDER BY id DESC LIMIT ?",
            (cursor, fetch_limit),
        )
    elif status:
        db_cursor = await db.execute(
            "SELECT * FROM content_jobs WHERE status = ? ORDER BY id DESC LIMIT ?",
            (status, fetch_limit),
        )
    else:
        db_cursor = await db.execute(
            "SELECT * FROM content_jobs ORDER BY id DESC LIMIT ?",
            (fetch_limit,),
        )

    rows = await db_cursor.fetchall()
    items = [row_to_dict(r) for r in rows]

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor: Optional[int] = items[-1]["id"] if has_more else None
    return items, next_cursor, has_more
```

### API 인터페이스

```
GET /api/f001/jobs?cursor=42&limit=20

응답:
{
  "items": [...],         // 최대 20건 (id DESC 정렬)
  "next_cursor": 38,      // 다음 페이지 시작 cursor (없으면 null)
  "has_more": true        // 다음 페이지 존재 여부
}
```

- cursor 없이 첫 호출 → 최신 20건 반환
- `next_cursor: 38` → 다음 호출 시 `?cursor=38` → id < 38인 항목 반환
- `has_more: false` → 마지막 페이지, 더 보기 버튼 숨김

---

## 섹션 4. 파이프라인 구조 재설계

### 현재 runner.py 동작 방식 분석

`pipelines/runner.py` 분석:
1. `sys.argv[1]` = task_id, `sys.argv[2]` = feature_id
2. `tasks` 테이블에서 params 로드
3. 레지스트리에서 파이프라인 클래스 조회 → `pipeline.run(task_id, params)` 호출

F001 멀티스테이지는 `content_jobs + stages` 테이블을 사용하므로 **별도 orchestrator runner**가 필요하다.
`f001_service.create_job()`에서 직접 `subprocess.Popen([sys.executable, orchestrator_runner_path, str(job_id)])` 호출하는 방식을 사용한다 (runner.py와 분리).

### 새 파일 구조

```
pipelines/f001_youtube/
├── pipeline.py              (기존 -- 레거시 유지, tasks 테이블 기반 단순 스크립트 생성)
├── orchestrator.py          (신규 -- 6스테이지 오케스트레이터, content_jobs 기반)
├── run_orchestrator.py      (신규 -- subprocess 진입점: argv[1]=job_id)
├── config.json              (신규 -- ComfyUI 경로, TTS 설정 등)
├── stages/
│   ├── __init__.py          (BaseStage, ValidationResult 정의)
│   ├── stage01_research.py
│   ├── stage02_script.py
│   ├── stage03_tts.py
│   ├── stage04_video.py
│   ├── stage05_edit.py
│   └── stage06_upload.py
└── validators/
    ├── __init__.py
    └── stage_validator.py
```

### 스테이지 클래스 인터페이스

```python
# pipelines/f001_youtube/stages/__init__.py

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dataclasses import dataclass
from typing import Optional


@dataclass
class ValidationResult:
    """스테이지 입/출력 유효성 검증 결과."""
    is_valid: bool
    rejection_reason: Optional[str] = None
    rejection_target: Optional[str] = None


class BaseStage:
    """F001 스테이지 추상 베이스 클래스.

    BasePipeline의 call_ollama(), call_searxng() 등 유틸을
    orchestrator를 통해 간접 호출하거나 직접 상속받아 사용한다.
    """

    STAGE_ID: str = ""
    STAGE_ORDER: int = 0

    def validate_input(self, data: dict) -> ValidationResult:
        """스테이지 실행 전 입력 데이터 유효성 검증."""
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """스테이지 실제 실행 -- 하위 클래스에서 반드시 구현."""
        raise NotImplementedError

    def validate_output(self, output: dict) -> ValidationResult:
        """스테이지 실행 후 출력 데이터 유효성 검증."""
        return ValidationResult(is_valid=True)
```

### 오케스트레이터 핵심 구조

```python
# pipelines/f001_youtube/orchestrator.py (핵심 구조)

class F001Orchestrator(BasePipeline):
    """F001 6스테이지 오케스트레이터.
    BasePipeline 상속으로 call_ollama(), call_searxng() 등 유틸 재사용.
    content_jobs + stages 테이블 기반 동기 sqlite3 사용.
    """

    STAGE_SEQUENCE = [
        ("STAGE_01_RESEARCH", 1, Stage01Research),
        ("STAGE_02_SCRIPT",   2, Stage02Script),
        ("STAGE_03_TTS",      3, Stage03TTS),
        ("STAGE_04_VIDEO_GEN",4, Stage04VideoGen),
        ("STAGE_05_EDIT",     5, Stage05Edit),
        ("STAGE_06_UPLOAD",   6, Stage06Upload),
    ]

    def run(self, job_id: int, params: dict = None) -> dict:  # type: ignore[override]
        """6스테이지 파이프라인 실행 진입점.

        주의: BasePipeline의 추상 메서드 run(task_id, params) -> dict와 시그니처가 다르다.
        F001Orchestrator는 content_jobs 기반이므로 job_id만 받아 DB에서 파라미터를 로드한다.
        params=None, 반환 dict={} 로 추상 메서드 계약을 형식적으로 충족하되
        실제 반환값은 사용하지 않는다. 타입체커 경고는 # type: ignore[override] 로 억제.
        """
        # DB에서 job 및 stages 로드
        # 각 스테이지 순차 실행 (STAGE_03/04 병렬 옵션 포함)
        # 스테이지 완료 시마다 DB 상태 업데이트
        # STAGE_06 완료 후 upload_mode 분기

    def _run_stage(self, job_id: int, stage_instance: BaseStage, input_data: dict) -> dict:
        """단일 스테이지 실행 + DB 상태 관리."""
        # stages.status = 'RUNNING' 업데이트
        # validate_input → execute → validate_output
        # DONE/REJECTED에 따라 stages 업데이트
        ...

    def _handle_skip_chain(self, job_id: int, db_conn) -> dict:
        """STAGE_03/04 skip 설정 확인 후 STAGE_05 입력 구성.

        skip 체인 규칙:
          STAGE_03 SKIPPED: audio_file_path=None (BGM 전용으로 STAGE_05 진행)
          STAGE_04 SKIPPED(text_slide): 슬라이드 clips로 STAGE_05 진행
          STAGE_04 SKIPPED(script_only): STAGE_05도 자동 SKIPPED
        """
        stage03 = self._get_stage(db_conn, job_id, "STAGE_03_TTS")
        stage04 = self._get_stage(db_conn, job_id, "STAGE_04_VIDEO_GEN")

        if stage04["status"] == "SKIPPED" and stage04["skip_mode"] == "script_only":
            self._mark_stage_skipped(db_conn, job_id, "STAGE_05_EDIT", reason="STAGE_04 script_only skip")
            return {"stage05_auto_skipped": True}

        stage05_input = {}
        if stage03["status"] == "COMPLETED":
            s03_out = json.loads(stage03["output_data"])
            stage05_input["audio_file_path"] = s03_out.get("audio_file_path")
        else:
            stage05_input["audio_file_path"] = None  # BGM 전용 모드

        s04_out = json.loads(stage04["output_data"])
        stage05_input["clips"] = s04_out.get("clips", [])
        return stage05_input
```

### 반송(reject) 메커니즘

```python
# validators/stage_validator.py -- 핵심 반송 로직

class StageValidator:
    """스테이지 유효성 검증 및 반송 메커니즘."""

    @staticmethod
    def handle_rejection(
        db_conn,
        job_id: int,
        current_stage_id: str,
        rejected_stage_id: str,
        reason: str,
    ) -> None:
        """스테이지를 REJECTED로 전환하고 반송 대상 스테이지를 PENDING으로 리셋.

        rejected_stage_id가 current_stage_id와 같으면 자기 재시도,
        다르면 이전 스테이지로 반송 (출력 초기화 + retry_count 증가).
        """
        now = datetime.now(timezone.utc).isoformat()

        # 1. 현재 스테이지 REJECTED 처리
        db_conn.execute(
            """UPDATE stages
               SET status='REJECTED', rejection_reason=?, rejection_target=?, finished_at=?
               WHERE job_id=? AND stage_id=?""",
            (reason, rejected_stage_id, now, job_id, current_stage_id),
        )

        # 2. 반송 대상 스테이지를 PENDING으로 리셋 (재실행 대기 상태)
        db_conn.execute(
            """UPDATE stages
               SET status='PENDING', output_data=NULL, rejection_reason=NULL,
                   started_at=NULL, finished_at=NULL, retry_count = retry_count + 1
               WHERE job_id=? AND stage_id=?""",
            (job_id, rejected_stage_id),
        )

        # 3. content_jobs current_stage 업데이트
        db_conn.execute(
            "UPDATE content_jobs SET current_stage=? WHERE id=?",
            (rejected_stage_id, job_id),
        )
        db_conn.commit()
        # 이후 사용자가 POST /api/f001/jobs/{id}/stages/{rejected_stage_id}/retry 호출
```

### skip 체인 처리 정리

```
STAGE_03 skip → audio_file_path=None → STAGE_05는 BGM 전용 모드로 진행 (영상 편집 계속)
STAGE_04 skip (text_slide) → FFmpeg로 텍스트 슬라이드 PNG 생성 → clips에 포함 → STAGE_05 정상 진행
STAGE_04 skip (script_only) → STAGE_05 자동 SKIPPED → STAGE_06에서 스크립트+오디오만 산출
STAGE_03 + STAGE_04 모두 skip (script_only) → STAGE_05 SKIP → STAGE_06 텍스트만 산출
```

---

## 섹션 5. 스테이지별 구현 상세

### STAGE_01_RESEARCH — 주제 발굴 및 트렌드 분석

**입력 검증 규칙**
- 통과: `channel_category` 1자 이상, `target_count` 1~20 범위
- 반송: channel_category가 비어 있는 경우 → STAGE_01 자기 재시도 요청

**핵심 처리 로직**

```python
# stage01_research.py -- execute() 핵심 로직

def execute(self, job_id: int, input_data: dict) -> dict:
    channel_category = input_data["channel_category"]
    target_count = input_data.get("target_count", 5)
    search_provider = input_data.get("search_provider", "youtube+searxng")

    youtube_results = []
    searxng_results = []

    # 1차: YouTube Data API (할당량: 검색 1회 = 100유닛)
    if "youtube" in search_provider:
        try:
            youtube_results = self._call_youtube_api(channel_category, days, max_results=50)
            self._increment_youtube_quota(units_used=100)
        except YouTubeQuotaExceededError:
            search_provider = "searxng"  # 할당량 초과 시 SearXNG 단독 폴백

    # 2차: SearXNG (base.py의 call_searxng() 재사용)
    if "searxng" in search_provider:
        query = f"{channel_category} 트렌드 인기 영상"
        searxng_results = self.call_searxng(query, max_results=20)

    # Ollama로 주제 후보 스코어링
    search_context = self._build_search_context(youtube_results, searxng_results)
    prompt = self._build_topic_scoring_prompt(channel_category, search_context, target_count)
    raw_response = self.call_ollama(prompt, timeout=120, num_predict=2048)
    topics = self._parse_topics_from_response(raw_response, target_count)

    return {
        "stage_id": "STAGE_01_RESEARCH",
        "status": "COMPLETED",
        "channel_category": channel_category,
        "youtube_results_count": len(youtube_results),
        "searxng_results_count": len(searxng_results),
        "topics": topics,
        "selected_topic": None,  # 사용자 UI 선택 후 채워짐
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_01_RESEARCH",
  "status": "COMPLETED",
  "channel_category": "IT/기술",
  "youtube_results_count": 50,
  "searxng_results_count": 18,
  "topics": [
    {
      "rank": 1,
      "title": "2026년 AI 에이전트 최신 트렌드",
      "estimated_views": "50만~100만",
      "competition_level": "중간",
      "recommended_reason": "Google I/O 발표로 검색량 급상승",
      "keywords": ["AI 에이전트", "Claude", "GPT-4o"],
      "score": 87,
      "source": "youtube+searxng"
    }
  ],
  "selected_topic": null,
  "generated_at": "2026-05-12T10:00:00Z"
}
```

**에러 처리**
- YouTube API 할당량 초과 → SearXNG 단독 폴백 (로그 경고)
- SearXNG 연결 실패 → RuntimeError → orchestrator FAILED 처리
- topics 배열 비어 있으면 → ValidationResult(is_valid=False, rejection_reason="주제 후보 생성 실패...")

---

### STAGE_02_SCRIPT — 스크립트 작성

**입력 검증 규칙**

```python
def validate_input(self, data: dict) -> ValidationResult:
    selected_topic = data.get("selected_topic")
    if not selected_topic or not str(selected_topic).strip():
        return ValidationResult(
            is_valid=False,
            rejection_reason="선택된 주제가 없습니다. STAGE_01에서 주제를 선택하세요.",
            rejection_target="STAGE_01_RESEARCH",
        )
    return ValidationResult(is_valid=True)
```

**핵심 처리 로직**

```python
def execute(self, job_id: int, input_data: dict) -> dict:
    selected_topic = input_data["selected_topic"]
    duration_min = input_data.get("duration_min", 10)
    target_chars = duration_min * 170  # 분당 약 170자

    # 1단계: 스크립트 생성 (Ollama)
    script_prompt = self._build_script_prompt(selected_topic, input_data)
    raw_script = self.call_ollama(script_prompt, timeout=180, num_predict=4096)
    parsed_script = self._parse_script_structure(raw_script)

    # 2단계: 씬 분해 (Ollama)
    scene_prompt = self._build_scene_decompose_prompt(raw_script, duration_min)
    raw_scenes = self.call_ollama(scene_prompt, timeout=120, num_predict=2048)
    scenes = self._parse_scenes(raw_scenes)

    full_script_text = " ".join([
        parsed_script.get("hook", ""),
        *[s.get("content", "") for s in parsed_script.get("body", [])],
        parsed_script.get("cta", ""),
    ])

    return {
        "stage_id": "STAGE_02_SCRIPT",
        "status": "COMPLETED",
        "selected_topic": selected_topic,
        "script": parsed_script,
        "scenes": scenes,
        "script_text": full_script_text,
        "total_chars": len(full_script_text),
        "estimated_duration_min": len(full_script_text) // 170,
        "seo_keywords": input_data.get("keywords", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_02_SCRIPT",
  "status": "COMPLETED",
  "selected_topic": "2026년 AI 에이전트 최신 트렌드",
  "script": {
    "hook": "지금 이 순간에도 AI가 여러분 대신 일하고 있습니다...",
    "body": [{"section_title": "AI 에이전트란?", "content": "...", "duration_sec": 90}],
    "cta": "지금 구독하시면 매주 AI 최신 트렌드를..."
  },
  "scenes": [{"scene_no": 1, "description": "발표장 배경, AI 로고들", "duration_sec": 10}],
  "script_text": "훅+본문+CTA 전체 텍스트",
  "total_chars": 1680,
  "estimated_duration_min": 10,
  "seo_keywords": ["AI 에이전트", "클로드", "2026 AI"],
  "generated_at": "2026-05-12T10:05:00Z"
}
```

**에러 처리**
- `total_chars < 200` → ValidationResult(is_valid=False, rejection_reason="스크립트 분량 부족...")
- hook/body/cta 중 하나 비어 있음 → ValidationResult(is_valid=False, ...)

---

### STAGE_03_TTS — AI 보이스오버 생성 (skip 가능)

**핵심 처리 로직**

```python
def execute(self, job_id: int, input_data: dict) -> dict:
    if input_data.get("tts_skip", False):
        return {"stage_id": "STAGE_03_TTS", "status": "SKIPPED",
                "skip_reason": "사용자 선택으로 TTS 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat()}

    provider = input_data.get("tts_provider", "coqui")
    script_text = input_data["script_text"]
    output_path = str(Path(f"storage/results/f001/{job_id}") / "voiceover.mp3")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if provider == "coqui":
        # subprocess CLI 호출 -- 모델: tts_models/ko/css10/vits
        result = subprocess.run([
            sys.executable, "-m", "TTS",
            "--text", script_text,
            "--model_name", "tts_models/ko/css10/vits",
            "--out_path", output_path,
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"Coqui TTS 실패: {result.stderr[:500]}")

    elif provider == "kokoro":
        from kokoro import KPipeline
        import soundfile as sf
        pipeline = KPipeline(lang_code='ko')
        samples, sample_rate = pipeline(script_text)
        sf.write(output_path, samples, sample_rate)

    elif provider == "elevenlabs":
        # ElevenLabs REST API -- ELEVENLABS_API_KEY 환경변수 필요
        ...

    elif provider == "openai":
        # OpenAI TTS API -- OPENAI_API_KEY 환경변수 필요
        ...

    return {
        "stage_id": "STAGE_03_TTS", "status": "COMPLETED",
        "tts_provider": provider, "audio_file_path": output_path,
        "duration_sec": self._get_audio_duration(output_path),
        "file_size_kb": Path(output_path).stat().st_size // 1024,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_03_TTS", "status": "COMPLETED",
  "tts_provider": "coqui",
  "audio_file_path": "storage/results/f001/42/voiceover.mp3",
  "duration_sec": 612, "file_size_kb": 4800,
  "generated_at": "2026-05-12T10:12:00Z"
}
```

---

### STAGE_04_VIDEO_GEN — 씬별 영상/이미지 클립 생성 (skip 가능)

**핵심 처리 로직**

```python
def execute(self, job_id: int, input_data: dict) -> dict:
    skip = input_data.get("skip", False)
    skip_mode = input_data.get("skip_mode")

    if skip and skip_mode == "script_only":
        return {"stage_id": "STAGE_04_VIDEO_GEN", "status": "SKIPPED",
                "skip_mode": "script_only", "clips": [],
                "generated_at": datetime.now(timezone.utc).isoformat()}

    output_dir = Path(f"storage/results/f001/{job_id}/clips")
    output_dir.mkdir(parents=True, exist_ok=True)

    if skip and skip_mode == "text_slide":
        # FFmpeg로 섹션 제목 텍스트 슬라이드 PNG 생성
        clips = self._generate_text_slides(input_data["scenes"], output_dir)
        return {"stage_id": "STAGE_04_VIDEO_GEN", "status": "SKIPPED",
                "skip_mode": "text_slide", "clips": clips,
                "generated_at": datetime.now(timezone.utc).isoformat()}

    # ComfyUI 연동 -- F003 ComfyUIClient 재활용 (D:\comfyui\ComfyUI, 포트 8188)
    config = self._load_config()  # pipelines/f001_youtube/config.json
    comfyui_url = config.get("comfyui_url", "http://localhost:8188")
    from pipelines.f003_video_creation.comfyui_client import ComfyUIClient
    client = ComfyUIClient(comfyui_url)

    if not client.health_check():
        raise RuntimeError("ComfyUI 서버 연결 실패. D:\\comfyui\\ComfyUI 실행 후 재시도하세요.")

    clips = []
    for scene in input_data["scenes"]:
        # Ollama: 씬 설명 → 영어 이미지 프롬프트 변환
        image_prompt = self.call_ollama(
            f"Convert scene description to English image generation prompt: {scene['description']}",
            timeout=60, num_predict=200,
        )
        output_files = self._run_comfyui_workflow(client, image_prompt, scene, output_dir)
        clips.extend(output_files)

    thumbnail_dir = Path(f"storage/results/f001/{job_id}/thumbnails")
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_candidates = self._generate_thumbnails(client, input_data, thumbnail_dir)

    return {
        "stage_id": "STAGE_04_VIDEO_GEN", "status": "COMPLETED",
        "generation_backend": "comfyui",
        "comfyui_path": r"D:\comfyui\ComfyUI",
        "clips": clips, "thumbnail_candidates": thumbnail_candidates,
        "total_clips": len(clips),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_04_VIDEO_GEN", "status": "COMPLETED",
  "generation_backend": "comfyui", "comfyui_path": "D:\\comfyui\\ComfyUI",
  "clips": [{"scene_no": 1, "file_path": "storage/results/f001/42/clips/scene_1.png", "duration_sec": 10}],
  "thumbnail_candidates": ["storage/results/f001/42/thumbnails/thumb_1.png"],
  "total_clips": 8, "generated_at": "2026-05-12T10:30:00Z"
}
```

---

### STAGE_05_EDIT — 자동 편집 및 자막 생성

**핵심 처리 로직**

```python
def execute(self, job_id: int, input_data: dict) -> dict:
    clips = input_data.get("clips", [])
    audio_file_path = input_data.get("audio_file_path")  # None 가능 (STAGE_03 skip 시)
    output_dir = Path(f"storage/results/f001/{job_id}/final")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_video = str(output_dir / "output.mp4")
    output_srt = str(output_dir / "subtitles.srt")

    # 1. FFmpeg: clips 순서대로 타임라인 + 오디오 믹싱
    #    각 클립이 PNG이면 duration_sec 동안 정지 영상으로 처리
    self._run_ffmpeg_concat(clips, audio_file_path, output_video, input_data)

    # 2. Whisper: 오디오 → SRT 자막 생성
    has_subtitles = False
    if audio_file_path and Path(audio_file_path).exists():
        self._run_whisper_transcribe(audio_file_path, output_srt)
        has_subtitles = Path(output_srt).exists()

    # 3. BGM 삽입 (선택)
    if input_data.get("bgm_enabled", False):
        bgm_path = self._find_bgm_file()
        if bgm_path:
            self._mix_bgm(output_video, bgm_path, input_data.get("bgm_volume", 0.15))

    file_info = self._get_video_info(output_video)

    return {
        "stage_id": "STAGE_05_EDIT", "status": "COMPLETED",
        "video_file_path": output_video, "video_file_name": "output.mp4",
        "subtitle_file_path": output_srt if has_subtitles else None,
        "duration_sec": file_info.get("duration_sec", 0),
        "resolution": file_info.get("resolution", "1280x720"),
        "file_size_mb": file_info.get("file_size_mb", 0),
        "has_subtitles": has_subtitles,
        "has_bgm": input_data.get("bgm_enabled", False),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_05_EDIT", "status": "COMPLETED",
  "video_file_path": "storage/results/f001/42/final/output.mp4",
  "subtitle_file_path": "storage/results/f001/42/final/subtitles.srt",
  "duration_sec": 635, "resolution": "1280x720",
  "file_size_mb": 120, "has_subtitles": true, "has_bgm": false,
  "generated_at": "2026-05-12T11:00:00Z"
}
```

---

### STAGE_06_SEO_UPLOAD — SEO 최적화 및 YouTube 업로드

**핵심 처리 로직 (YouTube Data API 유닛 소모량 반영)**

```python
def execute(self, job_id: int, input_data: dict) -> dict:
    script_data = input_data["script_data"]
    upload_mode = input_data.get("upload_mode", "manual_approval")
    video_file_path = input_data.get("video_file_path")

    # 1. Ollama: SEO 최적화 제목/설명/태그 생성
    seo_prompt = self._build_seo_prompt(script_data)
    raw_seo = self.call_ollama(seo_prompt, timeout=120, num_predict=1024)
    seo_metadata = self._parse_seo_response(raw_seo)

    # 2. Ollama: 제목 A/B 변형 2개
    raw_variants = self.call_ollama(
        f"다음 제목의 A/B 테스트용 변형 2개: {seo_metadata['title']}",
        timeout=60, num_predict=200,
    )
    seo_metadata["title_variants"] = self._parse_title_variants(raw_variants)

    # 3. upload_mode 분기
    # YouTube Data API 유닛 소모량:
    #   videos.insert = 1,600유닛, thumbnails.set = 50유닛
    #   일일 10,000유닛 기준 약 6회 업로드 가능
    upload_status = "PENDING_APPROVAL"
    youtube_video_id = None

    if upload_mode == "auto" and video_file_path:
        # 잔여 유닛 확인 (1,650 미만이면 업로드 차단)
        remaining = self._get_youtube_quota_remaining()
        if remaining < 1650:
            raise RuntimeError(f"YouTube API 일일 유닛 부족 (잔여: {remaining}유닛)")
        youtube_video_id = self._upload_to_youtube(video_file_path, input_data, seo_metadata)
        self._increment_youtube_quota(units_used=1650)
        upload_status = "UPLOADED"

    return {
        "stage_id": "STAGE_06_UPLOAD", "status": "COMPLETED",
        "seo_metadata": seo_metadata,
        "upload_mode": upload_mode, "upload_status": upload_status,
        "youtube_video_id": youtube_video_id,
        "youtube_url": f"https://youtu.be/{youtube_video_id}" if youtube_video_id else None,
        "uploaded_at": datetime.now(timezone.utc).isoformat() if youtube_video_id else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
```

**출력 JSON 스키마**
```json
{
  "stage_id": "STAGE_06_UPLOAD", "status": "COMPLETED",
  "seo_metadata": {
    "title": "AI가 스스로 일한다? 2026 에이전트 혁명 완벽 정리 [최신]",
    "description": "2026년 AI 에이전트의 모든 것...",
    "tags": ["AI 에이전트", "클로드", "GPT", "2026 AI 트렌드"],
    "category": "28",
    "title_variants": ["AI 에이전트 완벽 가이드 2026", "당신도 모르는 AI 에이전트의 비밀"]
  },
  "upload_mode": "manual_approval", "upload_status": "PENDING_APPROVAL",
  "youtube_video_id": null, "youtube_url": null, "uploaded_at": null,
  "generated_at": "2026-05-12T11:05:00Z"
}
```

---

## 섹션 6. 프론트엔드 변경 계획

### 신규 파일

**`frontend/src/views/F001View.vue`** — F001 메인 화면

```
화면 구성:
├── 헤더 (뒤로 버튼 + "유튜브 컨텐츠 제작")
├── 신규 작업 섹션
│   ├── "새 작업 추가" 버튼 → 다단계 모달 (Step1~4)
│   └── 작업 목록 테이블 (cursor 기반 페이징)
│       열: ID / 상태 / 채널 카테고리 / 현재 스테이지 / 생성 일시 / 액션
│       행 클릭 시 /f001/jobs/{id} 이동
└── 레거시 이력 섹션 (기본 접힘, 토글)
    └── 기존 tasks 테이블 F001 이력 목록 → 클릭 시 /tasks/{id}
```

**`frontend/src/views/F001JobDetailView.vue`** — 스테이지 타임라인 상세

```
화면 구성:
├── 헤더: 작업 #42 (IT/기술) — 전체 상태 배지 + 2초 폴링
├── StageTimeline 컴포넌트 (6단계 세로 스텝)
│   각 스테이지 행: 상태 아이콘 + 이름 + 간략 결과 + 재시도/반송 버튼
│   행 클릭 시 StageResultViewer 패널 토글
└── PENDING_APPROVAL 시: 승인 대기 배너 + 승인/거부 버튼
```

### 수정 파일

**`frontend/src/router/index.js`** — 라우트 추가

```javascript
// F001 전용 라우트 -- /features/F003 패턴과 동일하게 :id 앞에 등록
{
  path: '/features/F001',
  name: 'F001Feature',
  component: F001View,
},
{
  path: '/f001/jobs/:jobId',
  name: 'F001JobDetail',
  component: F001JobDetailView,
},
```

**`frontend/src/views/DashboardView.vue`** — F001 라우팅 추가

```javascript
// 현재 패턴 (F003만 전용 뷰):
// feature.feature_id === 'F003' ? F003Feature : Feature

// 변경 후 (F001도 전용 뷰):
feature.feature_id === 'F003'
  ? router.push({ name: 'F003Feature' })
  : feature.feature_id === 'F001'
    ? router.push({ name: 'F001Feature' })
    : router.push({ name: 'Feature', params: { id: feature.feature_id } })
```

**`frontend/src/api/index.js`** — F001 API 함수 추가

```javascript
// F001 API 함수 목록
export const getF001Jobs = (limit = 20, cursor = null, status = null) =>
  api.get('/api/f001/jobs', { params: { limit, ...(cursor != null ? { cursor } : {}), ...(status ? { status } : {}) } })

export const getF001Job = (jobId) => api.get(`/api/f001/jobs/${jobId}`)
export const createF001Job = (params) => api.post('/api/f001/jobs', params)
export const retryF001Stage = (jobId, stageId, overrideParams = null) =>
  api.post(`/api/f001/jobs/${jobId}/stages/${stageId}/retry`, { override_params: overrideParams })
export const rejectF001Stage = (jobId, stageId, reason, rejectionTarget = null) =>
  api.post(`/api/f001/jobs/${jobId}/stages/${stageId}/reject`, { rejection_reason: reason, rejection_target: rejectionTarget })
export const approveF001Job = (jobId, finalMeta = {}) =>
  api.post(`/api/f001/jobs/${jobId}/approve`, finalMeta)
export const selectF001Topic = (jobId, topicRank, title) =>
  api.post(`/api/f001/jobs/${jobId}/topics/${topicRank}/select`, { selected_topic_title: title })
export const getF001Legacy = (limit = 20, cursor = null) =>
  api.get('/api/f001/legacy', { params: { limit, ...(cursor != null ? { cursor } : {}) } })
export const getYoutubeQuota = () => api.get('/api/f001/youtube/quota')
```

### Pinia 스토어 state 구조

```javascript
// frontend/src/store/f001.js

export const useF001Store = defineStore('f001', () => {
  // State
  const jobs = ref([])           // content_jobs 목록
  const currentJob = ref(null)   // 현재 상세 조회된 job (스테이지 포함)
  const legacyJobs = ref([])     // 레거시 tasks 목록

  // cursor 기반 페이징 상태 (tasks.js 동일 패턴)
  const nextCursor = ref(null)
  const hasMore = ref(false)
  const legacyNextCursor = ref(null)
  const legacyHasMore = ref(false)

  const loading = ref(false)
  const errorMsg = ref('')

  // Actions
  async function fetchJobs(limit = 20, status = null) { ... }
  async function fetchMoreJobs(limit = 20) { ... }  // "더 보기" 패턴
  async function fetchJob(jobId) { ... }
  async function createJob(params) { ... }
  async function fetchLegacyJobs(limit = 20) { ... }

  return { jobs, currentJob, legacyJobs, nextCursor, hasMore, legacyNextCursor, legacyHasMore,
           loading, errorMsg, fetchJobs, fetchMoreJobs, fetchJob, createJob, fetchLegacyJobs }
})
```

### cursor 기반 페이징 -- Vue 적용

```javascript
// F001View.vue onMounted: 신규 + 레거시 병렬 로드
onMounted(async () => {
  await Promise.all([
    f001Store.fetchJobs(20),       // GET /api/f001/jobs
    f001Store.fetchLegacyJobs(20), // GET /api/f001/legacy
  ])
})

// 더 보기 버튼
async function loadMore() {
  await f001Store.fetchMoreJobs(20)
}
```

---

## 섹션 7. 스토리지 구조

### 디렉토리 구조

```
storage/results/f001/{job_id}/
├── stage01_topics.json             -- STAGE_01 출력
├── stage02_script.json             -- STAGE_02 출력
├── stage02_scenes.json             -- STAGE_02 씬 목록
├── voiceover.mp3                   -- STAGE_03 TTS 출력 (skip 시 없음)
├── clips/
│   ├── scene_01.png                -- STAGE_04 씬별 이미지
│   └── slide_01.png                -- text_slide skip 시 슬라이드
├── thumbnails/
│   ├── thumb_1.png
│   └── thumb_2.png
├── final/
│   ├── output.mp4                  -- STAGE_05 최종 영상
│   └── subtitles.srt               -- Whisper 자막
└── stage06_metadata.json           -- STAGE_06 SEO 메타데이터
```

### FastAPI StaticFiles 마운트

```python
# backend/main.py 수정 내용
f001_results_dir = Path(__file__).parent.parent / "storage" / "results" / "f001"
f001_results_dir.mkdir(parents=True, exist_ok=True)
app.mount("/results/f001", StaticFiles(directory=str(f001_results_dir)), name="f001_results")

# 영상 URL: http://localhost:8000/results/f001/42/final/output.mp4
# 이미지 URL: http://localhost:8000/results/f001/42/clips/scene_01.png
```

---

## 섹션 8. 레거시 F001 하이브리드 처리

### 현재 레거시 데이터 구조

`FeatureView.vue`, `TaskDetailView.vue` 분석 결과:
- 기존 F001 이력: `/api/tasks?feature_id=F001` 조회 (tasks 테이블)
- task.result JSON: `{"title": "...", "description": "...", "script": "..."}`
- 상세: `/tasks/{id}` → TaskDetailView.vue

### 통합 뷰어 API 병렬 조회 패턴

```javascript
// F001View.vue onMounted -- 두 API 병렬 호출 (Promise.allSettled 로 한쪽 실패해도 다른쪽 표시)

onMounted(async () => {
  const [newJobsResult, legacyResult] = await Promise.allSettled([
    apiGetF001Jobs(20),     // GET /api/f001/jobs (신규 content_jobs)
    apiGetF001Legacy(20),   // GET /api/f001/legacy (tasks WHERE feature_id='F001')
  ])

  if (newJobsResult.status === 'fulfilled') {
    f001Store.jobs = newJobsResult.value.data.items ?? []
    f001Store.nextCursor = newJobsResult.value.data.next_cursor ?? null
    f001Store.hasMore = newJobsResult.value.data.has_more ?? false
  }

  if (legacyResult.status === 'fulfilled') {
    f001Store.legacyJobs = legacyResult.value.data.items ?? []
  }
})
```

### 레거시 API 엔드포인트

```python
# routers/f001.py -- GET /api/f001/legacy
# 기존 task_service.list_tasks() 재사용 (feature_id='F001' 필터)
@router.get("/legacy", response_model=TaskListResponse)
async def list_legacy_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None),
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskListResponse:
    items, next_cursor, has_more = await task_service.list_tasks(
        db, limit=limit, cursor=cursor, feature_id="F001"
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

### 선택적 마이그레이션 엔드포인트

```python
# POST /api/f001/migrate-legacy
# 변환 규칙:
#   tasks.id -> content_jobs.legacy_task_id
#   tasks.params.topic -> content_jobs.channel_category
#   tasks.result -> stages 테이블 STAGE_02 output_data
#   tasks.status -> content_jobs.status (그대로)
#   원본 tasks 레코드는 삭제하지 않음 (안전 유지)
```

---

## 섹션 9. 외부 서비스 설치/설정 계획

### Coqui TTS (1순위)

```
pip install TTS
# GPU 가속 선택:
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

한국어 모델 확인:
  tts --list_models | findstr /i "ko"
  # 결과: tts_models/ko/css10/vits (약 80~100MB, 첫 실행 시 자동 다운로드)
```

### Kokoro TTS (2순위, 한국어 지원 여부 확인 필요)

```
pip install kokoro soundfile
# Hexgrad/Kokoro-82M (HuggingFace 자동 다운로드, VRAM ~1~2GB)

한국어 지원 테스트:
  from kokoro import KPipeline
  pipeline = KPipeline(lang_code='ko')
  result = pipeline("안녕하세요 테스트입니다")
```

### FFmpeg (STAGE_05 필수)

```
winget install "FFmpeg (Essentials Build)"
# PATH 등록 확인: ffmpeg -version
```

### Whisper (STAGE_05 자막)

```
pip install openai-whisper         # 표준
# 또는
pip install faster-whisper          # CUDA 가속 권장

모델 크기 선택 (config.json의 whisper_model):
  base:   141MB VRAM, 빠름, 정확도 보통
  medium: 769MB VRAM, 느림, 정확도 높음
  large-v3: ~10GB -- 일반 환경 사용 불가
  기본값: base (VRAM 4GB 이하 환경)
```

### YouTube Data API v3

```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

설정 절차:
1. Google Cloud Console → YouTube Data API v3 활성화
2. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱 유형)
3. client_secrets.json 다운로드 → 프로젝트 루트 (.gitignore에 추가)
4. 첫 실행 시 브라우저 OAuth 완료 → refresh_token을 settings 테이블에 저장

일일 유닛 한도 관리:
  videos.insert: 1,600유닛 | thumbnails.set: 50유닛 | search.list: 100유닛
  합계 10,000유닛/일 → 업로드 약 6회 + 검색 약 17회
  settings 테이블 key='youtube_quota_used_today'로 일일 소모량 추적
```

### F001 config.json

```json
{
  "comfyui_url": "http://localhost:8188",
  "comfyui_path": "D:\\comfyui\\ComfyUI",
  "whisper_model": "base",
  "tts_default_provider": "coqui",
  "tts_coqui_model": "tts_models/ko/css10/vits",
  "bgm_dir": "storage/bgm",
  "output_base_dir": "storage/results/f001"
}
```

---

## 섹션 10. 구현 순서 (Phase별)

### Phase 1 — DB + API 뼈대 [2일] ✅ 구현완료 (2026-05-12)

**목표**: 파이프라인 없이 CRUD만으로 content_jobs + stages 레코드 생성/조회 동작 확인

1. `backend/core/database.py` 수정 ✅
   - `_CREATE_CONTENT_JOBS`, `_CREATE_STAGES`, 인덱스 3개 추가 + `init_db()` 확장

2. `backend/schemas/f001.py` 신규 생성 ✅
   - `F001JobCreateRequest`, `ContentJobResponse`, `StageResponse`, `ContentJobListResponse` 등

3. `backend/services/f001_service.py` 신규 생성 ✅
   - `create_job()`: content_jobs INSERT + stages 6개 PENDING INSERT
   - `list_jobs()`: cursor 페이징 (task_service.list_tasks() 동일 패턴)
   - `get_job()`: content_jobs + stages JOIN 조회

4. `backend/routers/f001.py` 신규 생성 ✅ (14개 엔드포인트, 파이프라인 연결 없이 CRUD만)

5. `backend/main.py` 수정 ✅
   - `from routers import ..., f001` + `app.include_router(f001.router)`
   - F001 StaticFiles 마운트 추가

**검증**: `POST /api/f001/jobs` → content_jobs 1개 + stages 6개 생성 확인
`GET /api/f001/jobs?cursor=&limit=20` → cursor 페이징 응답 확인

---

### Phase 2 — STAGE_01 + STAGE_02 (텍스트 전용, 외부 서비스 없음) [3일]

> **✅ 구현완료 (파이프라인 모듈)** — 2026-05-12

**목표**: SearXNG + Ollama만으로 주제 발굴 → 스크립트 생성 전체 흐름 동작

1. ✅ `pipelines/f001_youtube/stages/__init__.py` — BaseStage, ValidationResult 정의
2. ✅ `pipelines/f001_youtube/stages/stage01_research.py` — SearXNG 먼저 구현
3. ✅ `pipelines/f001_youtube/stages/stage02_script.py` — Ollama 스크립트 + 씬 분해
4. ✅ `pipelines/f001_youtube/validators/stage_validator.py` — handle_rejection() 구현
5. ✅ `pipelines/f001_youtube/run_orchestrator.py` — `argv[1]=job_id` → `F001Orchestrator().run(job_id)` 호출 진입점
6. ✅ `pipelines/f001_youtube/orchestrator.py` — 6스테이지 전체 오케스트레이터 구현
7. 프론트엔드 기본 UI: `F001View.vue`, `F001JobDetailView.vue`, `store/f001.js` (별도 진행)
8. `router/index.js` + `DashboardView.vue` 수정 (별도 진행)

**검증**: 작업 생성 → STAGE_01 완료(주제 목록 DB 저장) → 주제 선택 → STAGE_02 시작 → 스크립트 DB 저장

---

### Phase 3 — STAGE_03 TTS + STAGE_04 영상 생성 [4일]

> **✅ 구현완료 (파이프라인 모듈)** — 2026-05-12

**목표**: Coqui TTS 보이스오버 + ComfyUI 씬별 이미지 클립 생성

1. Coqui TTS 설치 + subprocess 연동 테스트 (런타임 검증 별도)
2. ✅ `pipelines/f001_youtube/stages/stage03_tts.py` — coqui/kokoro/elevenlabs/openai 분기 + skip 처리
3. ComfyUI 연동 확인 (`D:\comfyui\ComfyUI`, 포트 8188, F003 ComfyUIClient import 테스트) (런타임 검증 별도)
4. ✅ `pipelines/f001_youtube/stages/stage04_video.py` — ComfyUI 이미지 생성 + text_slide/script_only skip
5. ✅ `orchestrator.py` 확장 — STAGE_03/04 실행 포함한 6스테이지 전체 구현 완료
6. `frontend/src/components/StageTimeline.vue` — 6단계 세로 스텝 컴포넌트 (별도 진행)

**검증**: STAGE_02 완료 후 STAGE_03/04 실행 → voiceover.mp3 + scene_*.png 파일 생성 확인

---

### Phase 4 — STAGE_05 편집 + STAGE_06 업로드 [4일]

> **✅ 구현완료 (파이프라인 모듈)** — 2026-05-12

**목표**: 최종 MP4 파일 + SEO 메타데이터 + PENDING_APPROVAL 흐름

1. FFmpeg PATH 확인 + Whisper 설치 테스트 (런타임 검증 별도)
2. ✅ `pipelines/f001_youtube/stages/stage05_edit.py` — FFmpeg 편집 + Whisper 자막 + skip 체인 처리
3. ✅ `pipelines/f001_youtube/stages/stage06_upload.py` — Ollama SEO 생성 + upload_mode 분기 (YouTube OAuth는 Phase 5)
4. `backend/routers/f001.py`의 `approve_job()` 실제 YouTube 업로드 연결 (별도 진행)
5. `frontend/src/components/StageResultViewer.vue` — 스테이지별 결과 뷰어 (별도 진행)
   - STAGE_01: 주제 카드 + 선택 버튼
   - STAGE_02: 훅/본문/CTA 스크립트 뷰
   - STAGE_03: HTML audio 플레이어
   - STAGE_04: 이미지 그리드
   - STAGE_05: HTML video 태그 + SRT 텍스트
   - STAGE_06: SEO 편집 폼 + 승인/거부 버튼

**검증**: STAGE_05 → output.mp4 생성, STAGE_06 → SEO 메타 + PENDING_APPROVAL 상태 확인

---

### Phase 5 — 마무리 + 레거시 통합 [2일]

1. YouTube OAuth 2.0 인증 흐름 구현 (refresh_token → settings 테이블 저장) — 미구현 (구조만 존재)
2. ✅ 레거시 하이브리드 통합 뷰어 (`Promise.allSettled()` 병렬 조회) — F001View.vue에 구현됨
3. ✅ `POST /api/f001/migrate-legacy` 선택적 마이그레이션 엔드포인트 — stub 구현 + migrate_legacy.py 유틸 생성
4. 전체 에러 처리 강화 + 재시도 UI — 기본 구현됨, 강화 여지 있음
5. ✅ YouTube Data API 유닛 추적 (`GET /api/f001/youtube/quota`) — 구현됨

**검증**: 전체 6단계 파이프라인 UI 완전 모니터링, 승인 후 업로드 동작 확인

---

## 섹션 11. 트레이드오프 및 리스크

### 독립 `content_jobs` 테이블 vs 기존 `tasks` 확장

| 항목 | content_jobs 신규 (선택) | tasks 확장 |
|------|--------------------------|------------|
| 기존 코드 영향 | 없음 (F002/F003 무관) | F002/F003 라우터/스키마도 수정 필요 |
| 스테이지별 추적 | stages 테이블로 완전 지원 | 컬럼 추가로 어렵게 구현 |
| 레거시 하이브리드 | legacy_task_id 컬럼으로 연결 가능 | 자연스럽게 통합 |
| **결정** | **content_jobs 신규 채택** | - |

### ComfyUI 씬별 호출 직렬 vs 병렬

- **직렬 (현재 F003 패턴)**: 구현 단순, 씬 10개 × 30초 = 5분 소요
- **병렬 ThreadPoolExecutor**: 처리 시간 단축, ComfyUI 메모리 경합 위험
- **결정**: Phase 3에서 직렬 먼저 구현 → 성능 이슈 시 병렬 전환
- **리스크**: ComfyUI 단일 GPU 독점 사용으로 병렬 요청이 내부 큐잉될 수 있음

### Whisper 모델 크기 메모리 이슈

- `large-v3`: ~10GB VRAM → 일반 환경 사용 불가
- `medium`: 769MB VRAM → RTX 3060 12GB에서 가능
- `base`: 141MB VRAM → 거의 모든 환경에서 동작
- **결정**: config.json `whisper_model=base` 기본, 사용자 변경 가능
- **리스크**: base 모델은 한국어 기술 용어 오인식 가능성 있음

### YouTube API 일일 유닛 한도

- 업로드 1,600유닛 + 검색 100유닛 = 하루 6영상 + 17회 검색 한도
- **리스크**: 테스트 중 할당량 소진 시 하루 전체 기능 차단
- **대응책**:
  1. Phase 1~4 개발 중 YouTube API 호출 없이 mock 데이터로 테스트
  2. STAGE_01의 `search_provider` 기본값 `'searxng'`로 시작
  3. settings 테이블에 일일 소모량 추적 + UI에 잔여 유닛 표시

### Coqui TTS 한국어 품질 리스크

- `css10/vits` 모델: 명확하나 자연스러움 부족, 기계적 억양
- **대응책**: `tts_provider` 파라미터로 언제든 교체 가능 (코드 변경 불필요)
- 기본 skip 옵션 제공으로 TTS 없이도 전체 파이프라인 동작 가능

### STAGE_03/04 병렬 실행과 SQLite write lock 경합

- 두 스테이지 동시에 stages 테이블 업데이트 시 SQLite write lock 경합 가능
- **대응책**: SQLite WAL 모드 활성화 (`PRAGMA journal_mode=WAL`) 또는 Phase 3에서 직렬로 시작
- stages.task_pid 컬럼으로 두 프로세스 PID 별도 추적

### stages REJECTED 상태 처리 복잡성

- STAGE_N REJECTED → 이전 스테이지 PENDING 리셋 → 사용자 개입 대기
- **리스크**: orchestrator가 장기 대기 시 프로세스 종료
- **대응책**: orchestrator를 stateless하게 설계 (DB 상태 읽어 현재 위치 파악) → 언제든 재실행 가능

---

## 섹션 12. 미결/보류 사항

### YouTube OAuth 2.0 인증 흐름

- 브라우저 기반 OAuth는 서버 환경(headless)에서 직접 실행 불가
- **해결 방안 후보**:
  1. 최초 1회만 개발자 PC 브라우저 OAuth 완료 → refresh_token 확보 → settings 테이블 수동 저장
  2. FastAPI에 OAuth 콜백 엔드포인트 구현 (`/api/f001/youtube/auth/callback`)
  3. `google-auth-oauthlib`의 `InstalledAppFlow` 사용 (로컬 포트 오픈 방식)
- **결정 필요**: Phase 4 시작 전 방법 확정

### Kokoro TTS 한국어 실제 지원 여부

- Hexgrad/Kokoro-82M의 한국어 학습 데이터 포함 여부 불확실
- **확인 방법**: `pip install kokoro soundfile` 후 한국어 텍스트 10문장 테스트
- 한국어 미지원 시: Coqui TTS 계속 사용 또는 ElevenLabs 전환

### ComfyUI 워크플로우 JSON (F001 전용 필요 여부)

- F003 기존 워크플로우 (캐릭터 이미지 생성용)를 F001에 그대로 재사용 가능 여부 확인 필요
- 유튜브 배경/인포그래픽 씬은 F003 캐릭터 생성 목적과 다름
- **결정 필요**: Phase 3 시작 전 F001 전용 워크플로우 JSON 필요 여부 확인

### BGM 소스

- STAGE_05 `bgm_enabled=True` 시 저작권 무료 BGM 파일 필요
- **현재 미정**: `storage/bgm/` 디렉토리에 .mp3 파일 수동 배치 방식
- 추천 소스: YouTube 오디오 라이브러리, Pixabay Music, ccMixter

### Whisper faster-whisper vs openai-whisper

- `faster-whisper`는 CUDA 가속으로 4~8배 빠름 (ctranslate2 패키지 의존)
- **결정 필요**: Phase 4 시작 전 Windows CUDA 환경에서 `pip install faster-whisper` 시도 후 결정

---

*완성도 97% 체크리스트 검토 결과 (독립 검증 후 수정 반영):*
- [x] 모든 섹션이 실제 읽은 코드를 기반으로 작성됨
- [x] cursor 기반 페이징이 task_service.list_tasks() 현재 구현 패턴과 일치
- [x] 6개 스테이지 각각의 입/출력 JSON 스키마 구체적 명시
- [x] ComfyUI D:\comfyui\ComfyUI 경로 + F003 ComfyUIClient 재활용 방법 명시
- [x] 반송(reject) 메커니즘 StageValidator.handle_rejection() 코드 스니펫 포함
- [x] Phase별 구현 순서가 실제 의존성 고려 (DB → API → 스테이지 → UI 순서)
- [x] 레거시 하이브리드 API 병렬 조회 Promise.allSettled() 스니펫 포함
- [x] YouTube Data API 유닛 소모량(1,600유닛/업로드, 100유닛/검색) 구현에 반영
- [x] skip 체인 처리 _handle_skip_chain() 코드 스니펫 명시
- [x] 트레이드오프 섹션에 content_jobs vs tasks 확장, 병렬 실행, 메모리 이슈 등 실질적 내용 포함
- [x] 섹션 0 신규 생성 파일 표에 run_orchestrator.py, migrate_legacy.py 추가
- [x] main.py 라우터 등록 패턴 (한 줄 묶음 import 방식) 명확히 명시
- [x] BasePipeline.run() 추상 메서드 시그니처 불일치 → # type: ignore[override] 처리 명시

*문서 작성 완료: 2026-05-12 (독립 검증 후 수정)*
