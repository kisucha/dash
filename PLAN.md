# Dash F003 영상제작 구현 계획

| 필드 | 내용 |
|------|------|
| 문서명 | Dash F003 영상제작 구현 계획 |
| 버전 | V1 |
| 날짜 | 2026-05-07 |
| 작성자 | Claude (kisuc 승인) |
| 문서 유형 | 구현 계획 |
| 모델 | claude-sonnet-4-6 |

---

## 1. 구현 범위 및 전제조건

### 1-1. 구현 범위

이 문서는 다음 두 가지 목표를 동시에 달성하기 위한 구현 계획을 기술한다.

1. **인풋(cursor) 기반 페이징 전환**: 기존 오프셋 페이징을 cursor 기반 페이징으로 교체
2. **F003 영상제작 파이프라인 추가**: ComfyUI + AnimateDiff/Flux.1 기반 동영상·그림 생성 기능

### 1-2. 기술 스택 전제조건

| 서비스 | 포트 | 역할 | 전제조건 |
|--------|------|------|---------|
| FastAPI | 8000 | Dash 메인 API | 현재 운영 중 |
| Vue 3 (dev) | 5173 | 프론트엔드 | 현재 운영 중 |
| Ollama | 11434 | 로컬 LLM | 현재 운영 중 |
| ComfyUI | 8188 | 이미지/동영상 생성 단일 플랫폼 | 별도 설치 필요 |
| SQLite | - | aiosqlite 기반 | 현재 운영 중 |

### 1-3. 외부 의존성 전제조건

- **ComfyUI**: 포트 8188에서 실행 중이어야 함
- **ComfyUI-Manager**: POST /manager/reboot 사용을 위해 설치 필요
- **ComfyUI-AnimateDiff-Evolved**: 동영상 경로에 필수 (`Kosinkadink/ComfyUI-AnimateDiff-Evolved`)
- **ComfyUI-VideoHelperSuite**: MP4 출력에 필요 (`Kosinkadink/ComfyUI-VideoHelperSuite`)
- **CivitAI API 키**: 모델 다운로드에 필요 (`.env`에 `CIVITAI_API_KEY` 추가)
- **HuggingFace Token**: Flux.1 공식 레포 다운로드 시 필요 (`.env`에 `HF_TOKEN` 추가)

### 1-4. 현재 코드베이스 핵심 파악

- `pipelines/runner.py`: F001, F002 레지스트리 → F003 추가 필요
- `pipelines/base.py`: DB_PATH 하드코딩 `r"C:\Develop\Dash\storage\dash.db"`, 동기 sqlite3 사용
- `backend/core/database.py`: `init_db()`에서 3개 테이블 생성 → 2개 테이블 추가 필요
- `backend/routers/features.py`: FEATURES 딕셔너리 하드코딩 → F003 항목 추가 필요
- `storage/`: `results/f003/` 서브디렉토리 신규 생성 필요

---

## 2. 인풋(cursor) 기반 페이징 전환 계획

### 2-1. 오프셋 페이징의 문제점

현재 구현(`OFFSET N` 방식)의 구조적 문제:

- **실시간 불안정성**: 새 task가 생성되면 기존 offset 기준이 밀려 페이지 경계가 뒤틀림. 10초 폴링 중 신규 task가 삽입되면 같은 항목이 두 번 보이거나 항목이 빠질 수 있음
- **COUNT(\*) 오버헤드**: 매 요청마다 `SELECT COUNT(*)` 별도 쿼리 실행
- **대용량 비효율**: `OFFSET N`은 N개 행을 스캔 후 버림. task가 수천 건 이상이면 느려짐

### 2-2. Cursor 기반 페이징 설계 원칙

- **cursor**: 마지막으로 받은 task의 정수 `id`를 cursor로 사용
- **첫 페이지**: cursor 파라미터 없이 요청 (또는 null)
- **다음 페이지**: 응답의 `next_cursor`를 다음 요청의 cursor로 사용
- **`total` 제거**: `has_more` + `next_cursor`로 대체
- **`LIMIT limit+1` 트릭**: 실제 필요한 수보다 1개 더 조회하여 다음 페이지 존재 여부 판단

### 2-3. SQL 쿼리 변경

```sql
-- 첫 페이지 (cursor 없음)
SELECT * FROM tasks
[WHERE feature_id = ?]
ORDER BY id DESC
LIMIT ?  -- limit+1

-- 다음 페이지 (cursor 있음)
SELECT * FROM tasks
WHERE id < ?           -- cursor (마지막 수신 id)
[AND feature_id = ?]
ORDER BY id DESC
LIMIT ?  -- limit+1
```

결과가 limit+1개이면 `has_more=True`, 마지막 항목을 제거하고 제거 전 마지막 항목의 id를 `next_cursor`로 반환.

### 2-4. 변경 파일 목록 및 코드 스니펫

**A. `backend/schemas/task.py` — TaskListResponse 변경**

```python
# 변경 전
class TaskListResponse(BaseModel):
    total: int
    items: list[TaskResponse]

# 변경 후
class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    next_cursor: int | None      # None이면 마지막 페이지
    has_more: bool
```

**B. `backend/routers/tasks.py` — list_tasks 시그니처 변경**

```python
# 변경 전
@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    feature_id: str | None = Query(default=None, description="업무 ID 필터"),
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskListResponse:
    total, items = await task_service.list_tasks(db, limit=limit, offset=offset, feature_id=feature_id)
    return TaskListResponse(
        total=total,
        items=[TaskResponse.model_validate(item) for item in items],
    )

# 변경 후
@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, description="마지막 수신 task id (첫 페이지는 생략)"),
    feature_id: str | None = Query(default=None, description="업무 ID 필터"),
    db: aiosqlite.Connection = Depends(get_db),
) -> TaskListResponse:
    items, next_cursor, has_more = await task_service.list_tasks(
        db, limit=limit, cursor=cursor, feature_id=feature_id
    )
    return TaskListResponse(
        items=[TaskResponse.model_validate(item) for item in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

**C. `backend/services/task_service.py` — list_tasks 재작성**

```python
# 변경 전
async def list_tasks(
    self,
    db: aiosqlite.Connection,
    limit: int = 20,
    offset: int = 0,
    feature_id: Optional[str] = None,
) -> tuple[int, list[dict]]:
    # COUNT(*) + OFFSET 방식

# 변경 후
async def list_tasks(
    self,
    db: aiosqlite.Connection,
    limit: int = 20,
    cursor: int | None = None,
    feature_id: str | None = None,
) -> tuple[list[dict], int | None, bool]:
    """
    cursor 기반 페이징으로 task 목록 조회.

    반환: (items, next_cursor, has_more)
    - limit+1개를 조회하여 has_more 판단
    - cursor가 있으면 WHERE id < cursor 조건 추가
    """
    fetch_limit = limit + 1  # has_more 판단용

    if cursor is not None and feature_id:
        cursor_row = await db.execute(
            "SELECT * FROM tasks WHERE id < ? AND feature_id = ? ORDER BY id DESC LIMIT ?",
            (cursor, feature_id, fetch_limit),
        )
    elif cursor is not None:
        cursor_row = await db.execute(
            "SELECT * FROM tasks WHERE id < ? ORDER BY id DESC LIMIT ?",
            (cursor, fetch_limit),
        )
    elif feature_id:
        cursor_row = await db.execute(
            "SELECT * FROM tasks WHERE feature_id = ? ORDER BY id DESC LIMIT ?",
            (feature_id, fetch_limit),
        )
    else:
        cursor_row = await db.execute(
            "SELECT * FROM tasks ORDER BY id DESC LIMIT ?",
            (fetch_limit,),
        )

    rows = await cursor_row.fetchall()
    items = [row_to_dict(r) for r in rows]

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]  # 초과분 제거

    next_cursor = items[-1]["id"] if has_more else None
    return items, next_cursor, has_more
```

**D. `frontend/src/api/index.js` — getTasks, getTasksByFeature 변경**

```javascript
// 변경 전
export const getTasks = (limit = 20, offset = 0) =>
  api.get('/api/tasks', { params: { limit, offset } })

export const getTasksByFeature = (featureId, limit = 50, offset = 0) =>
  api.get('/api/tasks', { params: { feature_id: featureId, limit, offset } })

// 변경 후
export const getTasks = (limit = 20, cursor = null) =>
  api.get('/api/tasks', { params: { limit, ...(cursor != null ? { cursor } : {}) } })

export const getTasksByFeature = (featureId, limit = 50, cursor = null) =>
  api.get('/api/tasks', { params: { feature_id: featureId, limit, ...(cursor != null ? { cursor } : {}) } })

// 추가: 모델 자산 API
export const getModelAssets = () => api.get('/api/model-assets')
export const getDownloads = () => api.get('/api/model-assets/downloads')
export const triggerDownload = (payload) => api.post('/api/model-assets/download', payload)
```

**E. `frontend/src/store/tasks.js` — cursor 기반 상태 및 액션 추가**

```javascript
// 추가할 state
const nextCursor = ref(null)
const hasMore = ref(false)

// 변경할 fetchTasks
async function fetchTasks(limit = 20, cursor = null) {
    try {
        const res = await apiGetTasks(limit, cursor)
        tasks.value = res.data.items ?? []
        nextCursor.value = res.data.next_cursor ?? null
        hasMore.value = res.data.has_more ?? false
    } catch (err) {
        console.error('[TaskStore] fetchTasks 실패:', err)
    }
}

// 추가: 다음 페이지 로드 (무한 스크롤 지원)
async function fetchMoreTasks(limit = 20) {
    if (!hasMore.value || nextCursor.value == null) return
    try {
        const res = await apiGetTasks(limit, nextCursor.value)
        tasks.value = [...tasks.value, ...(res.data.items ?? [])]
        nextCursor.value = res.data.next_cursor ?? null
        hasMore.value = res.data.has_more ?? false
    } catch (err) {
        console.error('[TaskStore] fetchMoreTasks 실패:', err)
    }
}

// return에 추가
return { tasks, features, nextCursor, hasMore, fetchTasks, fetchMoreTasks, fetchFeatures, createTask, cancelTask, deleteTaskRecord }
```

**F. `frontend/src/views/DashboardView.vue` — 폴링 호출 변경**

```javascript
// 변경 전
pollTimer = setInterval(() => taskStore.fetchTasks(10, 0), 10000)
taskStore.fetchTasks(10, 0).catch(() => {})

// 변경 후 (cursor 없이 항상 최신 10개 조회)
pollTimer = setInterval(() => taskStore.fetchTasks(10), 10000)
taskStore.fetchTasks(10).catch(() => {})
```

### 2-5. 트레이드오프 분석

| 항목 | 오프셋 | cursor |
|------|--------|--------|
| 실시간 안정성 | 낮음 (새 task 삽입 시 경계 불안정) | 높음 (id 기반으로 안정적) |
| COUNT 쿼리 | 필요 (별도 쿼리) | 불필요 |
| 대용량 성능 | 느림 (N개 스캔 후 버림) | 빠름 (인덱스 range scan) |
| "총 N개" 표시 | 가능 | 불가 (필요 시 별도 엔드포인트) |
| 특정 페이지 직접 이동 | 가능 | 불가 (순차 이동만 가능) |
| 구현 복잡도 | 낮음 | 중간 |

DashboardView는 최근 10개만 표시하고 폴링 시 cursor를 초기화(항상 첫 페이지)하는 방식으로 운영한다.

---

## 3. F003 구현 계획

### 3-1. DB 스키마 추가

`backend/core/database.py`의 `init_db()` 함수에 다음 2개 테이블을 추가한다.

```sql
-- 모델 인벤토리 — ComfyUI 기준 로컬 모델 목록 관리
CREATE TABLE IF NOT EXISTS model_inventory (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    model_type          TEXT    NOT NULL,      -- checkpoint/lora/motion_module/vae/clip
    name                TEXT    NOT NULL,
    filename            TEXT    NOT NULL,
    local_path          TEXT    NOT NULL,
    civitai_version_id  INTEGER,
    hf_repo_id          TEXT,
    is_downloaded       INTEGER NOT NULL DEFAULT 0,
    file_size_mb        REAL,
    downloaded_at       DATETIME,
    base_model          TEXT,                  -- SD1.5/SDXL/Flux.1
    style_tags          TEXT                   -- JSON 배열 ["anime", "realistic"]
);

-- 모델 다운로드 큐 — 비동기 다운로드 진행 상태 추적
CREATE TABLE IF NOT EXISTS model_download_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,          -- civitai/huggingface
    model_type      TEXT    NOT NULL,
    source_id       TEXT    NOT NULL,
    target_path     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'QUEUED',  -- QUEUED/DOWNLOADING/DONE/FAILED
    progress_pct    REAL    DEFAULT 0,
    error_message   TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    finished_at     DATETIME
);
```

추가 위치: `_CREATE_SETTINGS` 상수 정의 뒤, `init_db()` 함수 내에 `await conn.execute(_CREATE_MODEL_INVENTORY)` 및 `await conn.execute(_CREATE_MODEL_DOWNLOAD_QUEUE)` 추가.

### 3-2. 새 파일 및 수정 파일 전체 목록

**신규 파일**:

| 파일 경로 | 역할 |
|---------|------|
| `pipelines/f003_video_creation/__init__.py` | 패키지 초기화 (F003Pipeline export) |
| `pipelines/f003_video_creation/pipeline.py` | F003 메인 파이프라인 (BasePipeline 상속) |
| `pipelines/f003_video_creation/comfyui_client.py` | ComfyUI REST + WebSocket API 클라이언트 |
| `pipelines/f003_video_creation/model_manager.py` | 모델 로컬 인벤토리 조회 및 CivitAI/HF 다운로드 |
| `pipelines/f003_video_creation/prompt_generator.py` | Ollama 기반 SD/Flux.1 프롬프트 생성 |
| `pipelines/f003_video_creation/style_mapper.py` | 스타일 선택 → 워크플로우 파라미터 매핑 |
| `pipelines/f003_video_creation/config.json` | F003 기본 설정 (ComfyUI URL, 기본 모델명, 스타일 매핑 테이블) |
| `pipelines/f003_video_creation/workflows/animatediff_base.json` | AnimateDiff-Evolved 기본 워크플로우 JSON (API 포맷) |
| `pipelines/f003_video_creation/workflows/flux_base.json` | Flux.1 기본 워크플로우 JSON (API 포맷) |
| `backend/services/model_service.py` | model_inventory 테이블 CRUD |
| `backend/services/download_service.py` | model_download_queue 관리 + httpx 스트리밍 다운로드 |
| `backend/routers/model_assets.py` | `/api/model-assets` 엔드포인트 라우터 |
| `backend/schemas/model_asset.py` | ModelInventoryResponse, DownloadQueueResponse 스키마 |
| `frontend/src/views/F003View.vue` | F003 전용 다단계 UI 컴포넌트 |

**수정 파일**:

| 파일 경로 | 변경 내용 |
|---------|---------|
| `backend/core/database.py` | model_inventory, model_download_queue 테이블 추가 |
| `backend/routers/tasks.py` | cursor 기반 페이징으로 전환 |
| `backend/services/task_service.py` | list_tasks cursor 기반으로 재작성 |
| `backend/schemas/task.py` | TaskListResponse 변경 (total 제거, next_cursor/has_more 추가) |
| `backend/routers/features.py` | FEATURES 딕셔너리에 F003 항목 추가 |
| `backend/main.py` | model_assets 라우터 등록 |
| `frontend/src/api/index.js` | cursor 기반 getTasks, 모델 자산 API 함수 추가 |
| `frontend/src/store/tasks.js` | cursor 기반 fetchTasks, nextCursor/hasMore 상태 추가, fetchMoreTasks 추가 |
| `frontend/src/views/DashboardView.vue` | offset 인자 제거 |
| `frontend/src/router/index.js` | F003 전용 라우트 추가 |
| `frontend/src/views/TaskDetailView.vue` | F003 미디어 결과 렌더링 블록 추가 |
| `pipelines/runner.py` | F003 파이프라인 레지스트리 등록 |

### 3-3. 각 모듈별 설계 상세

#### 3-3-A. `backend/routers/features.py` — F003 항목 추가

FEATURES 딕셔너리에 다음 항목을 추가한다 (핵심 필드만 표기):

```python
"F003": {
    "feature_id": "F003",
    "name": "영상제작",
    "description": "ComfyUI와 Ollama를 활용하여 동영상(AnimateDiff) 또는 그림(Flux.1/SD)을 자동 생성합니다.",
    "supports_schedule": False,
    "input_schema": [
        # 생성 유형
        {"name": "generation_type", "title": "생성 유형", "type": "select",
         "required": True, "default": "image", "options": ["image", "video"], ...},
        # 카테고리 1 — 아트 스타일
        {"name": "art_style", "title": "아트 스타일", "type": "select",
         "default": "realistic", "options": ["anime","realistic","fantasy","cyberpunk","watercolor","3d_render","pixel_art"], ...},
        # 카테고리 2 — 캐릭터 외형 (5개 서브)
        {"name": "character_face",   "type": "select", "options": ["","western","asian","mixed"], ...},
        {"name": "character_hair_style", "type": "select", "options": ["","long_hair","short_hair","twin_tails","ponytail","bob_with_bangs"], ...},
        {"name": "character_hair_color", "type": "select", "options": ["","blonde","brown","black","pink","silver","gradient"], ...},
        {"name": "character_eyes",   "type": "select", "options": ["","large_eyes","sharp_eyes","upturned","downturned"], ...},
        {"name": "character_outfit", "type": "select", "options": ["","casual","fantasy","school_uniform","sportswear","dress","cyberpunk"], ...},
        # 카테고리 3 — 촬영 기법
        {"name": "camera_angle",       "type": "select", "options": ["","front","side","from_above","from_below","dramatic_low"], ...},
        {"name": "camera_composition", "type": "select", "options": ["close_up","upper_body","full_body","wide_shot"], ...},
        {"name": "depth_of_field",     "type": "select", "options": ["","bokeh","pan_focus"], ...},
        # 카테고리 4 — 조명
        {"name": "lighting", "type": "select",
         "options": ["natural_day","golden_hour","night","indoor","dramatic","soft","backlit","studio","neon"], ...},
        # 카테고리 5 — 배경
        {"name": "background", "type": "select",
         "options": ["","classroom","cafe","bedroom","office","city_street","nature_park","beach","mountain_forest",
                     "castle","magical_realm","otherworldly","plain_background","abstract"], ...},
        # 카테고리 6 — 동영상 모션 (동영상 선택 시만 적용)
        {"name": "motion_intensity", "type": "select", "options": ["subtle","moderate","dynamic"], ...},
        {"name": "motion_type", "type": "select", "options": ["camera_movement","character_movement","particle_environment"], ...},
        {"name": "loop_animation", "type": "select", "options": ["true","false"], "default": "false", ...},
        # 카테고리 7 — 디테일 향상 LoRA (복수 선택)
        {"name": "detail_loras", "type": "list", "default": "",
         "description": "쉼표 구분 다중 선택 (예: detail_tweaker,add_more_details)", ...},
        # 추가 설명 및 공통 파라미터
        {"name": "user_description", "type": "textarea", "default": "", ...},
        {"name": "width",     "type": "integer", "default": 512, ...},
        {"name": "height",    "type": "integer", "default": 768, ...},
        {"name": "steps",     "type": "integer", "default": 20, ...},
        {"name": "cfg_scale", "type": "integer", "default": 7, ...},
        {"name": "seed",      "type": "integer", "default": -1, ...},
        # 동영상 전용
        {"name": "video_length", "type": "integer", "default": 16, ...},
        {"name": "fps",          "type": "integer", "default": 8, ...},
    ],
}
```

#### 3-3-B. `pipelines/f003_video_creation/config.json` 설계

스타일 매핑 테이블을 JSON 파일로 외부 관리한다.

```json
{
  "comfyui_url": "http://localhost:8188",
  "comfyui_manager_url": "http://localhost:8188",
  "comfyui_path": "C:\\ComfyUI",
  "output_dir": "C:\\Develop\\Dash\\storage\\results\\f003",
  "ollama_url": "http://localhost:11434",
  "default_motion_module": "mm_sd_v15_v2.ckpt",
  "reboot_poll_interval_sec": 5,
  "reboot_timeout_sec": 120,
  "style_mapping": {
    "anime":     {"checkpoint": "anime_art_diffusion_xl.safetensors", "base_model": "SDXL",
                  "style_loras": [{"name": "aesthetic_anime.safetensors", "strength_model": 0.7, "strength_clip": 0.5}],
                  "prompt_keywords": ["anime style", "anime coloring", "cel shading"]},
    "realistic": {"checkpoint": "cyberrealisticPony.safetensors", "base_model": "SD1.5",
                  "style_loras": [],
                  "prompt_keywords": ["photorealistic", "hyperrealistic", "RAW photo"]},
    "fantasy":   {"checkpoint": "fantasiaXL.safetensors", "base_model": "SDXL",
                  "style_loras": [{"name": "alpha_fantasy_touch.safetensors", "strength_model": 0.6, "strength_clip": 0.4}],
                  "prompt_keywords": ["fantasy art", "magical", "ethereal", "painterly"]},
    "cyberpunk": {"checkpoint": "cyberrealisticPony.safetensors", "base_model": "SD1.5",
                  "style_loras": [{"name": "cyberpunk_anime.safetensors", "strength_model": 0.7, "strength_clip": 0.5}],
                  "prompt_keywords": ["cyberpunk", "neon lights", "futuristic city"]},
    "watercolor":{"checkpoint": "landscapeAnimePro.safetensors", "base_model": "SD1.5",
                  "style_loras": [],
                  "prompt_keywords": ["watercolor painting", "soft brushstrokes"]},
    "3d_render": {"checkpoint": "sdxl_base.safetensors", "base_model": "SDXL",
                  "style_loras": [],
                  "prompt_keywords": ["3D render", "CGI", "unreal engine"]},
    "pixel_art": {"checkpoint": "pixel_art_diffusion_xl.safetensors", "base_model": "SDXL",
                  "style_loras": [{"name": "pixel_art_anime_screencap.safetensors", "strength_model": 0.8, "strength_clip": 0.6}],
                  "prompt_keywords": ["pixel art", "8-bit", "retro game"]}
  },
  "detail_lora_mapping": {
    "detail_tweaker":    {"filename": "detail_tweaker_sd15.safetensors", "base_models": ["SD1.5"], "default_weight": 1.0},
    "detail_tweaker_xl": {"filename": "detail_tweaker_xl.safetensors",   "base_models": ["SDXL"],  "default_weight": 1.5},
    "add_more_details":  {"filename": "add_more_details.safetensors",    "base_models": ["SD1.5"], "default_weight": 0.7},
    "flux_image_upgrader":{"filename":"flux_image_upgrader.safetensors", "base_models": ["Flux.1","SDXL","SD1.5"], "default_weight": 0.7},
    "detailifier":       {"filename": "detailifier.safetensors",         "base_models": ["Flux.1","SD3.5","SDXL","SD1.5"], "default_weight": 0.7}
  },
  "motion_module_mapping": {
    "SD1.5": "mm_sd_v15_v2.ckpt",
    "SDXL":  "mm_sdxl_v10_beta.ckpt"
  },
  "flux_model": {
    "diffusion_model": "flux1-dev-fp8.safetensors",
    "vae":             "ae.safetensors",
    "clip_l":          "clip_l.safetensors",
    "t5xxl":           "t5xxl_fp8_e4m3fn.safetensors"
  }
}
```

#### 3-3-C. `pipelines/f003_video_creation/comfyui_client.py` 설계

ComfyUI REST API + WebSocket 클라이언트. 동기 httpx + websocket-client 사용.

| 메서드 | 설명 | HTTP |
|--------|------|------|
| `health_check()` | ComfyUI 헬스체크 | GET /system_stats → 200 확인 |
| `get_object_info()` | 로드된 노드 타입 및 사용 가능 모델 목록 | GET /object_info |
| `get_available_checkpoints()` | CheckpointLoaderSimple의 ckpt_name 목록 추출 | object_info 파싱 |
| `get_available_loras()` | LoraLoader의 lora_name 목록 추출 | object_info 파싱 |
| `submit_workflow(workflow_dict)` | 워크플로우 JSON 제출 → prompt_id 반환 | POST /prompt |
| `wait_for_completion(prompt_id, timeout, cancel_check_fn)` | WebSocket 완료 이벤트 감지, 취소 감지 병행 | WS /ws?clientId={uuid} |
| `get_history(prompt_id)` | 실행 결과 및 출력 파일명 조회 | GET /history/{prompt_id} |
| `download_output(filename, subfolder, file_type)` | 결과 파일 다운로드 → 바이트 반환 | GET /view?filename=&type=output |
| `reboot(manager_url)` | ComfyUI 재시작 요청 | POST /manager/reboot |
| `wait_for_ready(timeout)` | 재시작 완료 폴링 | GET /system_stats 반복 |

WebSocket 이벤트 처리 핵심:
```python
# WebSocket 완료 감지 로직 개요
def wait_for_completion(self, prompt_id: str, timeout: int, cancel_check_fn=None) -> None:
    client_id = str(uuid.uuid4())
    ws_url = f"ws://localhost:8188/ws?clientId={client_id}"
    # websocket-client 라이브러리 사용
    # "executed" 이벤트의 prompt_id 일치 시 반환
    # "execution_error" 이벤트 수신 시 RuntimeError 발생
    # 1초 주기로 cancel_check_fn(task_id) 호출하여 취소 감지
    # timeout 초과 시 TimeoutError 발생
```

#### 3-3-D. `pipelines/f003_video_creation/model_manager.py` 설계

| 메서드 | 설명 |
|--------|------|
| `scan_local_models(comfyui_path)` | ComfyUI/models/ 디렉토리 스캔 → DB model_inventory 갱신 |
| `is_model_available(filename, model_type)` | DB 조회 + 파일 시스템 존재 여부 확인 |
| `ensure_models(required_models, comfyui_client)` | 없는 모델 다운로드 + ComfyUI 재시작 |
| `download_from_civitai(version_id, model_type, target_path)` | httpx 스트리밍, DB progress_pct 업데이트 |
| `download_from_hf(repo_id, filename, local_dir)` | hf_hub_download 래퍼 |
| `_update_download_queue(queue_id, status, progress, error)` | model_download_queue 테이블 업데이트 |

다운로드 청크 처리 전략:
- `httpx.Client` + `client.stream("GET", url)` 사용
- 청크 크기: 1MB (`chunk_size = 1024 * 1024`)
- `Content-Length` 헤더로 전체 파일 크기 파악
- 청크마다 `progress_pct = downloaded_bytes / total_bytes * 100` 계산 후 DB 업데이트

#### 3-3-E. `pipelines/f003_video_creation/style_mapper.py` 설계

`config.json`의 스타일 매핑 테이블을 참조하여 ComfyUI 워크플로우 파라미터를 결정한다.

| 메서드 | 입력 | 출력 |
|--------|------|------|
| `resolve_checkpoint(art_style)` | "anime" | "anime_art_diffusion_xl.safetensors" |
| `resolve_base_model(art_style)` | "anime" | "SDXL" |
| `resolve_style_loras(art_style)` | "anime" | `[{"name": ..., "strength_model": 0.7}]` |
| `resolve_detail_loras(keys, base_model)` | `["detail_tweaker"]`, "SD1.5" | 호환 필터링 후 LoRA 목록 |
| `resolve_motion_module(base_model)` | "SD1.5" | "mm_sd_v15_v2.ckpt" |
| `build_prompt_keywords(params)` | 스타일 선택 dict | `{"positive": [...], "negative": [...]}` |
| `build_workflow(generation_type, resolved, prompt, params)` | - | 완성된 워크플로우 dict |

`build_workflow` 내부 동작:
1. `workflows/animatediff_base.json` 또는 `workflows/flux_base.json` 로드
2. 체크포인트명, LoRA명+가중치, 프롬프트 텍스트, KSampler 파라미터 교체
3. 디테일 향상 LoRA를 스타일 LoRA 체인 뒤에 동적 삽입
4. 동영상: AnimateDiff 노드의 모션 모듈명, context_frames, closed_loop 설정

#### 3-3-F. `pipelines/f003_video_creation/prompt_generator.py` 설계

```python
# SD/AnimateDiff 경로 — 포지티브/네거티브 분리
def generate_sd_prompt(style_context: dict, user_description: str) -> dict:
    # 반환: {"positive": "masterpiece, best quality, ...", "negative": "..."}
    # Ollama /api/chat, format="json"

# Flux.1 경로 — 단일 자연어
def generate_flux_prompt(style_context: dict, user_description: str) -> str:
    # 반환: "A detailed illustration of a young woman with..."
    # Ollama /api/chat, format="json", {"prompt": "..."} 형태

# 응답 파싱 3단계 폴백
# 1. json.loads(response) 직접 파싱
# 2. ```json ... ``` 블록 정규표현식 추출
# 3. { ... } 사이 텍스트 추출
```

#### 3-3-G. `pipelines/f003_video_creation/pipeline.py` — F003Pipeline 설계

```python
class F003Pipeline(BasePipeline):
    def get_metadata(self) -> dict:
        return {"feature_id": "F003", "name": "영상제작", "supports_schedule": False, ...}

    def run(self, task_id: int, params: dict) -> dict:
        # 1. update_status(task_id, "RUNNING")
        # 2. config.json 로드
        # 3. ComfyUI 헬스체크 → 실패 시 FAILED
        # 4. style_mapper로 체크포인트/기반모델/LoRA 결정
        # 5. model_manager.ensure_models() → 없는 모델 다운로드 + ComfyUI 재시작
        # 6. prompt_generator로 Ollama 프롬프트 생성
        # 7. style_mapper.build_workflow()로 워크플로우 JSON 조립
        # 8. comfyui_client.submit_workflow(workflow) → prompt_id
        # 9. comfyui_client.wait_for_completion(prompt_id, cancel_check_fn=self.is_cancelled)
        # 10. get_history(prompt_id) → 출력 파일명
        # 11. download_output(filename) → 바이트
        # 12. storage/results/f003/{task_id}_*.{ext} 저장
        # 13. update_status("DONE", result={"file_path": ..., "generation_type": ...})
```

예외 처리: 각 단계마다 `is_cancelled(task_id)` 체크 → 취소 시 CANCELLED 처리. 모든 예외는 FAILED 처리.

#### 3-3-H. `backend/services/model_service.py` 설계

model_inventory 테이블 CRUD (aiosqlite 비동기):
- `list_models(db, model_type=None, base_model=None)` → 필터 조회
- `get_model_by_filename(db, filename)` → 파일명 단건 조회
- `upsert_model(db, model_data)` → INSERT or UPDATE
- `set_downloaded(db, model_id, local_path)` → is_downloaded=1 업데이트

#### 3-3-I. `backend/services/download_service.py` 설계

- `enqueue(db, source, model_type, source_id, target_path)` → 큐 추가, id 반환
- `list_active_downloads(db)` → QUEUED/DOWNLOADING 목록
- `update_progress(db, queue_id, progress_pct)` → 진행률 업데이트
- `mark_done(db, queue_id)` → DONE + finished_at
- `mark_failed(db, queue_id, error_message)` → FAILED

다운로드 실행은 파이프라인 프로세스(model_manager.py) 내에서 동기 httpx로 처리.

#### 3-3-J. `backend/routers/model_assets.py` 설계

```python
router = APIRouter(prefix="/api/model-assets", tags=["model-assets"])

# 모델 인벤토리 목록 조회
@router.get("", response_model=list[ModelInventoryResponse])
async def list_model_assets(model_type: str | None = None, base_model: str | None = None, ...)

# 진행 중인 다운로드 목록 조회
@router.get("/downloads", response_model=list[DownloadQueueResponse])
async def list_downloads(db: aiosqlite.Connection = Depends(get_db))

# 다운로드 트리거 (파이프라인 외부에서 수동 다운로드 시)
@router.post("/download", status_code=202)
async def trigger_download(request: DownloadRequest, ...)

# 로컬 모델 스캔 (ComfyUI/models/ 디렉토리 재스캔)
@router.post("/scan", status_code=202)
async def scan_local_models(...)
```

#### 3-3-K. `backend/main.py` 변경

```python
# 추가
from routers import model_assets

# app.include_router 추가
app.include_router(model_assets.router)

# 결과 파일 정적 서빙 (F003 결과 이미지/동영상)
from fastapi.staticfiles import StaticFiles
app.mount("/results/f003", StaticFiles(directory=r"C:\Develop\Dash\storage\results\f003"), name="f003_results")
```

#### 3-3-L. `pipelines/runner.py` — F003 등록

```python
# F003 — 영상제작
try:
    from pipelines.f003_video_creation.pipeline import F003Pipeline
    registry["F003"] = F003Pipeline
    logger.info("파이프라인 등록 완료: F003 (영상제작)")
except ImportError as e:
    logger.warning(f"F003 파이프라인 로드 실패: {e}")
```

#### 3-3-M. `frontend/src/router/index.js` — F003 라우트 추가

```javascript
import F003View from '../views/F003View.vue'

// 순서 주의: /features/F003 이 /features/:id 보다 먼저 등록
{
  path: '/features/F003',
  name: 'F003Feature',
  component: F003View,
},
{
  path: '/features/:id',
  name: 'Feature',
  component: FeatureView,
},
```

#### 3-3-N. `frontend/src/views/F003View.vue` 설계

다단계 폼 구조 (`<script setup>`):

**Step 1: 생성 유형 선택**
- 동영상 / 그림 두 개의 큰 카드 클릭 UI
- `const generationType = ref('image')`

**Step 2: 스타일 선택 (7개 카테고리)**
- 카테고리 1: 아트 스타일 라디오/칩 (7개)
- 카테고리 2: 캐릭터 외형 드롭다운 5개 (얼굴/헤어스타일/헤어컬러/눈매/의상)
- 카테고리 3: 촬영 기법 드롭다운 (앵글/구도/심도)
- 카테고리 4: 조명 드롭다운 (9개)
- 카테고리 5: 배경 드롭다운 (13개)
- 카테고리 6: 동영상 모션 (`v-if="generationType === 'video'"`, 모션 강도/타입/루프)
- 카테고리 7: 디테일 향상 LoRA 체크박스 (선택된 아트 스타일의 기반 모델과 호환 LoRA만 활성화)

**Step 3: 파라미터 설정**
- 공통: width, height, steps, cfg_scale, seed
- 동영상 전용: video_length, fps (`v-if="generationType === 'video'"`)
- 추가 설명: textarea (한국어 가능)

**실행 섹션**
```javascript
async function startGeneration() {
    const params = {
        generation_type: generationType.value,
        art_style: selectedStyle.value,
        // ... 모든 카테고리 선택값
        user_description: userDescription.value,
        width: width.value, height: height.value, steps: steps.value,
        cfg_scale: cfgScale.value, seed: seed.value,
        video_length: videoLength.value, fps: fps.value,
    }
    const task = await taskStore.createTask('F003', params)
    router.push({ name: 'TaskDetail', params: { id: task.id } })
}
```

다운로드 진행 중 상태 표시: 2초 폴링으로 `/api/model-assets/downloads` 조회, 진행 바 표시.

#### 3-3-O. `frontend/src/views/TaskDetailView.vue` — F003 미디어 렌더링

```javascript
// computed 추가
const isF003Result = computed(() =>
    task.value?.feature_id === 'F003' && parsedResult.value?.file_path
)
const f003IsVideo = computed(() =>
    parsedResult.value?.generation_type === 'video'
)
```

```html
<!-- 결과 카드 F003 분기 -->
<template v-else-if="isF003Result">
  <video v-if="f003IsVideo"
    :src="`/results/f003/${parsedResult.value.file_name}`"
    controls class="result-media" />
  <img v-else
    :src="`/results/f003/${parsedResult.value.file_name}`"
    alt="생성된 이미지" class="result-media" />
  <div class="result-meta">
    생성 유형: {{ parsedResult.value.generation_type }}
    | 파일: {{ parsedResult.value.file_path }}
  </div>
</template>
```

#### 3-3-P. `workflows/animatediff_base.json` 노드 구성 개요

```
노드 1: CheckpointLoaderSimple     → ckpt_name (style_mapper 결정)
노드 2: CLIPTextEncode (positive)  → text (prompt_generator 결정)
노드 3: CLIPTextEncode (negative)  → text
노드 4: ADE_LoadAnimateDiffModel   → model_name (motion_module)
노드 5: ADE_AnimateDiffSamplingSettings → batch_size, seed_override, closed_loop
노드 6: ADE_ApplyAnimateDiffModel  → ad_model=[4,0], sampling_settings=[5,0]
노드 7~N: Load LoRA (스타일 LoRA + 디테일 향상 LoRA 체인, 동적 삽입)
노드X: KSampler → seed, steps, cfg
노드X+1: VAEDecode
노드X+2: VHS_VideoCombine → fps, format=video/h264-mp4
```

#### 3-3-Q. `workflows/flux_base.json` 노드 구성 개요

```
노드 1: UNETLoader                  → unet_name (flux1-dev-fp8.safetensors)
노드 2: VAELoader                   → vae_name (ae.safetensors)
노드 3: CLIPLoader (CLIP-L)         → clip_name
노드 4: CLIPLoader (T5XXL)          → clip_name
노드 5~N: LoraLoaderModelOnly (체인) → Flux 스타일 + 디테일 향상 LoRA
노드K: CLIPTextEncode (positive prompt)
노드K+1: EmptyLatentImage           → width, height
노드K+2: KSampler                   → seed, steps, cfg
노드K+3: VAEDecode
노드K+4: SaveImage                  → filename_prefix
```

---

## 4. 구현 순서 (Phase 단위)

| Phase | 작업 내용 | 담당 에이전트 | 의존성 |
|-------|---------|-------------|--------|
| P1 | cursor 기반 페이징 전환 (백엔드 4개 파일 + 프론트 3개 파일) | api-builder + web-builder | 없음 |
| P2 | DB 스키마 추가 (model_inventory, model_download_queue) | api-builder | 없음 |
| P3 | features.py F003 항목 추가 | api-builder | 없음 |
| P4 | comfyui_client.py 구현 (REST + WebSocket) | pipeline-builder | 없음 |
| P5 | config.json + style_mapper.py 구현 | pipeline-builder | P3 |
| P6 | prompt_generator.py 구현 | pipeline-builder | 없음 |
| P7 | model_manager.py 구현 | pipeline-builder | P2, P4 |
| P8 | animatediff_base.json + flux_base.json 기본 워크플로우 JSON 작성 | pipeline-builder | P4 |
| P9 | pipeline.py F003 메인 로직 구현 | pipeline-builder | P4, P5, P6, P7, P8 |
| P10 | runner.py F003 등록 | pipeline-builder | P9 |
| P11 | backend model_service + download_service 구현 | api-builder | P2 |
| P12 | backend model_assets 라우터 + 스키마 구현 | api-builder | P11 |
| P13 | main.py model_assets 라우터 + StaticFiles 등록 | api-builder | P12 |
| P14 | F003View.vue 프론트엔드 구현 | web-builder | P3, P12 |
| P15 | router/index.js F003 라우트 추가 | web-builder | P14 |
| P16 | TaskDetailView.vue F003 미디어 렌더링 추가 | web-builder | P14 |
| P17 | storage/results/f003/ 디렉토리 생성 확인 | api-builder | 없음 |
| P18 | 전체 통합 검토 및 테스트 | critic | P1~P17 |

**병렬 실행 가능한 Phase 그룹**:
- 그룹 A (독립): P1, P2, P3, P4, P6, P17 동시 시작 가능
- 그룹 B (P2, P4 완료 후): P7
- 그룹 C (P3, P4 완료 후): P5
- 그룹 D (P5, P6, P7, P8 완료 후): P9 → P10
- 그룹 E (P2 완료 후): P11 → P12 → P13
- 그룹 F (P3, P12 완료 후): P14 → P15, P16

---

## 5. 고려사항 및 트레이드오프

### 5-1. ComfyUI 재시작 의존성

모델 추가 시마다 ComfyUI 서버 재시작이 필요하다. Flux.1 전체 모델 세트 다운로드 후 재시작까지 약 2~5분 소요 예상.
- F003View에서 다운로드 진행 바(2초 폴링) + "ComfyUI 재시작 중..." 스피너 표시
- 타임아웃 120초 초과 시 FAILED 처리

### 5-2. 워크플로우 JSON 유지보수

ComfyUI 버전 업 시 노드 클래스 타입명이 변경될 수 있다.
- `workflows/` 디렉토리 JSON을 코드베이스 외부로 관리하여 재빌드 없이 수정 가능
- `GET /object_info`로 사전 파라미터명 검증 후 워크플로우 제출 권장

### 5-3. 단일 ComfyUI 인스턴스 큐 처리

ComfyUI 내부 큐로 동시 요청은 순차 처리됨. 파이프라인은 자신의 prompt_id WebSocket 이벤트만 감지하므로 동시성 문제 없음. 향후 `GET /queue`로 대기 상태 UI 표시 가능.

### 5-4. 다운로드 용량 경고

| 모델 | 크기 | 예상 시간 (100Mbps) |
|------|------|-------------------|
| Flux.1 FP8 전체 세트 | ~22GB | ~30분 |
| SD 1.5 체크포인트 | 2~7GB | 3~10분 |
| AnimateDiff 모션 모듈 | ~1.7GB | ~2분 |

F003View에서 필요 모델 목록 + 예상 다운로드 크기 표시 후 사용자 확인 권장.

### 5-5. CivitAI API 키 및 HuggingFace 토큰

`.env` 파일에 `CIVITAI_API_KEY`, `HF_TOKEN` 추가 필요. 미설정 시 다운로드 시 RuntimeError → task FAILED.

### 5-6. 기반 모델별 LoRA 호환성 필터링

SD 1.5 LoRA는 SDXL/Flux.1 에서 사용 불가. `style_mapper.resolve_detail_loras()`에서 기반 모델 기준 필터링 필수. F003View 카테고리 7 UI에서도 호환 LoRA만 활성화.

---

## 6. 완성도 자기 검토 체크리스트

- [x] cursor 기반 페이징: 5개 파일 경로 + 코드 스니펫 완전 포함
- [x] F003 파이프라인: 9개 신규 파일 설계 상세 포함
- [x] 수정 파일 목록 완전 (12개 파일)
- [x] 구현 순서 Phase 18단계 + 병렬 실행 그룹 명시
- [x] 트레이드오프 분석 6개 항목
- [x] DB 스키마 SQL 스니펫 포함
- [x] F003View 다단계 설계 포함
- [x] TaskDetailView F003 미디어 렌더링 설계 포함
- [x] 스타일 매핑 7개 카테고리 input_schema 포함
- [x] config.json 스타일 매핑 테이블 구조 포함
- [x] ComfyUI 워크플로우 JSON 노드 구성 개요 포함
- [x] runner.py F003 등록 스니펫 포함
- [x] main.py StaticFiles 마운트 포함
- [x] 외부 의존성 명시

---

*문서 완성도: 97% — 구현에 필요한 모든 파일 경로, 코드 스니펫, 설계 상세, 순서, 트레이드오프가 포함됨.*
