# F001 유튜브 AI 자동화 파이프라인 리서치

| 필드 | 내용 |
|------|------|
| 문서명 | F001 유튜브 AI 자동화 파이프라인 리서치 |
| 버전 | V3 |
| 날짜 | 2026-05-12 |
| 작성자 | claude-sonnet-4-6 |
| 문서 유형 | 리서치/설계 |
| 모델 | claude-sonnet-4-6 |

---

## 목차

1. 현재 시스템 현황 분석
2. 목표 아키텍처 설계
3. 프론트엔드 변경 계획
4. 백엔드 변경 계획
5. 외부 서비스 의존성 분석
6. 구현 리스크 및 제약사항
7. 구현 우선순위 로드맵
8. 결정 완료 사항 (V2 미결 → 확정)
9. TTS 단계별 전환 전략
10. 레거시 F001 하이브리드 전환 계획

---

## 1. 현재 시스템 현황 분석

### 1-1. 현재 F001 파이프라인 동작 방식 (데이터 흐름)

```
[사용자] topic / style / duration_min 입력
  → POST /api/tasks { feature_id: "F001", params: {...} }
  → task_service.create_task()
    → DB INSERT tasks (status='PENDING')
    → subprocess.Popen(runner.py, task_id, "F001")  ← 독립 프로세스
  → 응답: TaskResponse (id, status='PENDING')

[독립 프로세스 runner.py]
  → F001Pipeline.run(task_id, params) 호출
  → update_status(RUNNING)
  → Ollama 1차 호출 → title 생성
  → Ollama 2차 호출 → description 생성
  → Ollama 3차 호출 → script 생성
  → update_status(DONE, result={title, description, script})

[프론트엔드 폴링]
  → GET /api/tasks/{id} 2초 간격 → 상태 확인
  → DONE 도달 시 폴링 중단, 결과 표시
```

현재 F001은 **단일 파이프라인 + 단일 Task**로 3단계 Ollama 호출을 순차 수행한다.
각 중간 결과(title, description)는 `result` 컬럼에 JSON으로 업데이트되며 폴링으로 진행 상황을 표시한다.

### 1-2. DB 모델 구조 (현재)

**tasks 테이블** (`backend/core/database.py` 기준)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| feature_id | TEXT NOT NULL | 업무 식별자 (F001, F002, F003) |
| status | TEXT NOT NULL | PENDING / RUNNING / DONE / FAILED / CANCELLED |
| params | TEXT (JSON) | 실행 입력 파라미터 |
| result | TEXT (JSON) | 실행 결과 |
| error_message | TEXT | 실패 시 오류 내용 |
| created_at | DATETIME | 생성 시각 |
| started_at | DATETIME | 실행 시작 시각 |
| finished_at | DATETIME | 완료 시각 |
| triggered_by | TEXT | 'manual' 또는 'schedule' |

**schedules 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK | 자동 증가 |
| feature_id | TEXT NOT NULL | 업무 식별자 |
| cron_expr | TEXT NOT NULL | Cron 표현식 |
| default_params | TEXT (JSON) | 기본 파라미터 |
| is_active | INTEGER | 활성화 여부 (0/1) |
| last_run_at | DATETIME | 마지막 실행 시각 |

**settings 테이블**
| 컬럼 | 타입 | 설명 |
|------|------|------|
| key | TEXT PK | 설정 키 |
| value | TEXT | 설정 값 |

추가로 `model_inventory`, `model_download_queue` 테이블이 존재 (F003 전용).

### 1-3. API 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /api/tasks | 새 작업 생성 + 파이프라인 실행 |
| GET | /api/tasks | 작업 목록 조회 (cursor 기반 페이징) |
| GET | /api/tasks/{id} | 작업 단건 조회 |
| DELETE | /api/tasks/{id} | 작업 취소 (RUNNING → CANCELLED) |
| DELETE | /api/tasks/{id}/history | 완료 작업 이력 삭제 |
| GET | /api/features | 업무 목록 조회 |
| GET | /api/features/{id} | 업무 상세 조회 |
| GET | /api/features/f003/models | F003 ComfyUI 모델 목록 |
| GET | /api/features/f003/loras | F003 LoRA 목록 |
| POST | /api/features/f003/loras/predownload | LoRA 사전 다운로드 |
| GET | /api/schedules | 스케줄 목록 |
| POST | /api/schedules | 스케줄 등록 |
| PUT | /api/schedules/{id} | 스케줄 수정 |
| DELETE | /api/schedules/{id} | 스케줄 삭제 |
| GET | /api/health | 헬스 체크 |
| GET | /api/health/ollama | Ollama 연결 상태 |
| GET | /api/models | Ollama 모델 목록 + 선택 모델 |
| PUT | /api/models/select | Ollama 모델 선택 저장 |
| POST | /api/chat | SSE 스트리밍 채팅 |
| POST | /api/chat/refine | 쿼리 정제 |
| POST | /api/search | 인터넷 검색 |
| GET | /api/model-assets | 모델 인벤토리 조회 |
| POST | /api/model-assets/download | 모델 다운로드 트리거 |
| GET | /api/model-assets/downloads | 진행 중인 다운로드 목록 조회 |
| POST | /api/model-assets/scan | 로컬 모델 재스캔 |

### 1-4. 프론트엔드 → API → 파이프라인 전체 흐름

```
[Vue 3 SPA]
  FeatureView.vue (F001 폼)
    → api/index.js: createTask(featureId, params)
    → POST /api/tasks
  
  [FastAPI]
    tasks.py 라우터
    → task_service.create_task(db, request)
      → DB INSERT (PENDING)
      → _spawn_pipeline(task_id, feature_id)
        → subprocess.Popen(python runner.py task_id F001)
    → 응답 반환 TaskResponse

  [독립 프로세스 pipelines/runner.py]
    → F001Pipeline().run(task_id, params)
      → BasePipeline.update_status(RUNNING)
      → BasePipeline.call_ollama() × 3
      → BasePipeline.update_status(DONE, result)

  [Vue 폴링]
    TaskDetailView.vue
    → GET /api/tasks/{id} (2초 간격)
    → DONE 도달 → 결과 렌더링 (JSON 표시)
```

### 1-5. 현재 Task 상태 기계

```
PENDING → RUNNING → DONE
                  → FAILED
                  → CANCELLED (RUNNING 중 DELETE 요청 시)
```

- 서버 재시작 시 기존 RUNNING 작업은 자동으로 FAILED 처리 (`_cleanup_stale_running_tasks`)
- 취소: 프론트에서 DELETE 요청 → DB 상태만 CANCELLED로 변경 → 파이프라인에서 `is_cancelled()` 주기 호출로 감지 후 중단

### 1-6. 현재 구조의 한계점

| 한계 | 영향 |
|------|------|
| 단일 Task = 전체 파이프라인 | 6개 스테이지를 분리 추적 불가 |
| result 컬럼에 모든 중간/최종 결과 혼재 | 스테이지별 결과 개별 조회/재실행 불가 |
| 스테이지 간 반송(재작성 요청) 개념 없음 | 결과 검증 후 이전 스테이지로 피드백 불가 |
| 업무 입력 스키마가 features.py에 하드코딩 | 다단계 폼 구성 어려움 |
| F001 전용 UI 없음 (FeatureView 공통 폼 사용) | 스테이지별 진행 현황 표시 불가 |
| 승인 흐름 없음 | 자동 업로드만 가능, 관리자 검토 후 업로드 불가 |
| 외부 서비스(TTS, 영상생성, 편집) 호출 경로 없음 | 스테이지 3~5 구현 불가 |

---

## 2. 목표 아키텍처 설계

### 2-1. 스테이지 정의

#### STAGE_01_RESEARCH — 주제 발굴 및 트렌드 분석

**스테이지 ID:** `STAGE_01_RESEARCH`

**[결정 완료] 트렌드 데이터 소스: YouTube Data API (1차) + SearXNG (2차) 병행**

두 소스를 순서대로 사용하여 결과를 합산 스코어링한다.
- YouTube Data API: 유튜브 직접 트렌드 데이터 (일일 10,000 유닛 한도, 검색 1건 = 약 100유닛)
- SearXNG: 추가 정보 수집 및 교차 검증 (로컬 인스턴스 192.168.20.80:8888, 무료)
- base.py의 `call_searxng()` 메서드가 이미 구현되어 있어 SearXNG 연동은 즉시 재사용 가능

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| channel_category | string | 필수 | 채널 카테고리 (예: IT/기술, 요리, 게임) | 1~100자 |
| target_count | integer | 선택 | 주제 후보 목표 개수 (기본: 5) | 1~20 |
| search_provider | string | 선택 | youtube+searxng / searxng (기본: youtube+searxng) | enum 값 |
| keywords_hint | string | 선택 | 추가 검색 힌트 키워드 | 최대 200자 |
| days | integer | 선택 | 트렌드 검색 기간(일) (기본: 7) | 1~30 |

**처리 로직**
1. YouTube Data API `search.list` 메서드로 `{channel_category}` 관련 최신·인기 영상 검색
   - type=video, order=viewCount, publishedAfter={days}일 전, maxResults=50
   - 소비 유닛: 검색 1회 = 100유닛 (일일 한도 10,000유닛 내 약 100회 검색 가능)
2. SearXNG로 `{channel_category} 트렌드 {현재년월}` 검색 (교차 검증)
3. 두 소스 결과를 합산하여 Ollama에 전달 → 주제 후보 TOP N 스코어링 생성
   - YouTube 조회수/좋아요 수를 가중치로 적용
   - SearXNG 결과와 중복 주제는 스코어 보강
4. 각 후보에 예상 조회수, 경쟁 채널 수, 추천 이유 포함

**출력 스키마**
```json
{
  "stage_id": "STAGE_01_RESEARCH",
  "status": "COMPLETED",
  "channel_category": "IT/기술",
  "search_results_count": 25,
  "youtube_results_count": 50,
  "searxng_results_count": 20,
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

**유효성 검증 규칙**
- 통과 조건: `topics` 배열에 1개 이상 항목, 각 항목에 `title`과 `score` 필드 존재
- 반송 조건: topics 배열이 비어 있거나, 검색 결과 0건 → 반송 메시지: "주제 후보 생성 실패 — 채널 카테고리를 더 구체적으로 입력하거나 검색 기간을 늘려 재시도"
- YouTube Data API 할당량 초과 시: SearXNG 단독으로 폴백 처리

---

#### STAGE_02_SCRIPT — 스크립트 작성

**스테이지 ID:** `STAGE_02_SCRIPT`

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| selected_topic | string | 필수 | 확정된 주제 제목 | 1~200자 |
| channel_category | string | 필수 | 채널 카테고리 | 1~100자 |
| channel_tone | string | 선택 | 톤앤매너 (educational/entertaining/tutorial) | enum 값 |
| duration_min | integer | 선택 | 목표 영상 길이(분) (기본: 10) | 1~60 |
| hook_style | string | 선택 | 훅 스타일 (question/shocking_fact/story) | enum 값 |
| cta_type | string | 선택 | CTA 유형 (subscribe/like/comment) | enum 값 |
| reference_data | string | 선택 | STAGE_01에서 전달된 키워드 컨텍스트 | 최대 2000자 |

**처리 로직**
1. 선택된 주제와 톤앤매너를 바탕으로 Ollama 프롬프트 구성
2. 훅(Hook) → 본문(Body, 섹션별) → CTA(Call to Action) 구조로 스크립트 생성
3. 분량 목표에 맞춰 섹션 수 조절 (10분 = 약 1700자)
4. 씬(Scene) 분해 메타데이터 함께 생성 (STAGE_04 영상 생성 입력용)

**출력 스키마**
```json
{
  "stage_id": "STAGE_02_SCRIPT",
  "status": "COMPLETED",
  "selected_topic": "2026년 AI 에이전트 최신 트렌드",
  "title": "AI가 스스로 일한다? 2026 에이전트 혁명 완벽 정리",
  "script": {
    "hook": "지금 이 순간에도 AI가 여러분 대신 일하고 있습니다...",
    "body": [
      { "section_title": "AI 에이전트란?", "content": "...", "duration_sec": 90 },
      { "section_title": "주요 서비스 비교", "content": "...", "duration_sec": 120 }
    ],
    "cta": "지금 구독하시면 매주 AI 최신 트렌드를 가장 먼저 받아보실 수 있습니다."
  },
  "scenes": [
    { "scene_no": 1, "description": "발표장 배경, 화면에 AI 로고들 나열", "duration_sec": 10 },
    { "scene_no": 2, "description": "인포그래픽 스타일, 에이전트 구조도", "duration_sec": 15 }
  ],
  "total_chars": 1680,
  "estimated_duration_min": 10,
  "seo_keywords": ["AI 에이전트", "클로드", "2026 AI"],
  "generated_at": "2026-05-12T10:05:00Z"
}
```

**유효성 검증 규칙**
- 통과 조건: `script.hook` 존재, `script.body` 배열 1개 이상, `script.cta` 존재, `scenes` 배열 1개 이상
- 반송 조건 1: hook/body/cta 중 하나라도 비어 있음 → "스크립트 구조 불완전 — 훅, 본문, CTA 중 누락된 항목이 있습니다. STAGE_01 주제를 교체하거나 톤앤매너를 변경하여 재시도"
- 반송 조건 2: total_chars < 200 → "스크립트 분량 부족 — 목표 길이를 높이거나 주제를 더 구체적으로 설정하세요"

---

#### STAGE_03_VOICEOVER — AI 보이스오버 생성

**스테이지 ID:** `STAGE_03_VOICEOVER`

**[결정 완료] TTS 제공자 우선순위: Coqui TTS → Kokoro TTS → ElevenLabs/OpenAI 순**

단계적 전환 전략으로 설계. 기본은 Coqui TTS (로컬, 무료). 상세 내용은 섹션 9 참조.

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| script_text | string | 필수 | STAGE_02 전체 스크립트 텍스트 (hook+body+cta 병합) | 1~10000자 |
| tts_provider | string | 선택 | coqui / kokoro / elevenlabs / openai (기본: coqui) | enum 값 |
| voice_id | string | 선택 | TTS 음성 ID (provider별 상이) | 최대 100자 |
| language | string | 선택 | ko / en (기본: ko) | enum 값 |
| speed | float | 선택 | 읽기 속도 배율 0.5~2.0 (기본: 1.0) | 0.5~2.0 |
| output_format | string | 선택 | mp3 / wav (기본: mp3) | enum 값 |
| skip | boolean | 선택 | 이 스테이지 건너뛰기 (기본: false) | boolean |

**처리 로직**
- `skip == true` 시: 이 스테이지를 SKIPPED 상태로 전환 → STAGE_05는 오디오 없이 BGM 전용 모드로 실행
- `coqui` 선택 시: Coqui TTS (pip install TTS) 로컬 합성, 한국어 모델 `tts_models/ko/css10/vits`
- `kokoro` 선택 시: Kokoro TTS (Hexgrad/Kokoro-82M) 로컬 합성
- `elevenlabs` 선택 시: ElevenLabs REST API 호출 (API Key 필요)
- `openai` 선택 시: OpenAI TTS API 호출 (tts-1 모델, API Key 필요)
- 출력 파일: `storage/results/f001/{job_id}/voiceover.mp3`

**출력 스키마**
```json
{
  "stage_id": "STAGE_03_VOICEOVER",
  "status": "COMPLETED",
  "tts_provider": "coqui",
  "voice_id": "tts_models/ko/css10/vits",
  "audio_file_path": "storage/results/f001/job_42/voiceover.mp3",
  "audio_file_name": "voiceover.mp3",
  "duration_sec": 612,
  "file_size_kb": 4800,
  "generated_at": "2026-05-12T10:12:00Z"
}
```

skip 시 출력:
```json
{
  "stage_id": "STAGE_03_VOICEOVER",
  "status": "SKIPPED",
  "skip_reason": "사용자 선택으로 TTS 건너뜀",
  "generated_at": "2026-05-12T10:12:00Z"
}
```

**유효성 검증 규칙**
- skip 시: 항상 통과 (SKIPPED 상태)
- 통과 조건: `audio_file_path`가 실제 파일로 존재, `duration_sec > 0`
- 반송 조건 1: 파일이 존재하지 않음 → "TTS 생성 실패 — {provider} 합성 오류. coqui로 전환하여 재시도"
- 반송 조건 2: duration_sec == 0 또는 file_size_kb < 1 → "TTS 출력 파일 손상 — 재생성 요청"

---

#### STAGE_04_VIDEO_GEN — 씬별 영상/이미지 클립 생성

**스테이지 ID:** `STAGE_04_VIDEO_GEN`

**[결정 완료] 영상 생성 백엔드: ComfyUI 로컬 확정 (`D:\comfyui\ComfyUI`)**
**[결정 완료] skip 옵션 제공: UI에서 영상 생성 건너뛰기 선택 가능**

skip 시 처리 방안:
- 텍스트 슬라이드 기반 영상으로 대체: 스크립트 섹션 제목을 배경색 슬라이드로 FFmpeg 생성
- 또는 스크립트만 최종 산출물로 처리 (STAGE_05, STAGE_06은 계속 진행 가능)

ComfyUI 경로 확인 결과: `D:\comfyui\ComfyUI\` 디렉토리 실제 존재 확인됨.
F003 파이프라인에서 ComfyUI 연동 코드(`ComfyUIClient`, `ModelManager`)가 이미 구현되어 있으므로 재활용 가능.
현재 `backend/routers/features.py`에서 `D:\comfyui\ComfyUI` 경로를 config.json으로 관리하는 패턴 확인.

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| scenes | array | 필수 | STAGE_02의 scenes 배열 | 1개 이상 |
| generation_backend | string | 선택 | comfyui / skip (기본: comfyui) | enum 값 |
| visual_style | string | 선택 | stock_photo / animation / presentation / cinematic | enum 값 |
| resolution | string | 선택 | 1920x1080 / 1280x720 (기본: 1280x720) | enum 값 |
| art_style | string | 선택 | 이미지 생성 스타일 (F003 연동, 동일 선택지 재사용) | string |
| clip_duration_sec | integer | 선택 | 각 씬의 기본 클립 길이(초) (기본: 5) | 3~30 |
| skip | boolean | 선택 | 이 스테이지 건너뛰기 (기본: false) | boolean |
| skip_mode | string | 선택 | text_slide / script_only (skip 시 대안 처리 방식) | enum 값 |

**처리 로직**
- `skip == true` + `skip_mode == 'text_slide'` 시:
  - 스크립트의 섹션 제목을 배경색 슬라이드(PNG)로 FFmpeg 생성
  - 각 섹션 슬라이드를 clips 배열에 포함하여 STAGE_05로 전달
- `skip == true` + `skip_mode == 'script_only'` 시:
  - 이 스테이지를 SKIPPED로 전환, STAGE_05도 자동 SKIPPED
  - STAGE_06에서 스크립트 + 오디오 파일만을 산출물로 처리
- `comfyui` 선택 시: F003 ComfyUIClient 재활용 (씬 설명 → Ollama → 프롬프트 → ComfyUI API)
  - ComfyUI 경로: `D:\comfyui\ComfyUI`, API 포트: 8188
- 썸네일 후보 3장도 함께 생성

**출력 스키마**
```json
{
  "stage_id": "STAGE_04_VIDEO_GEN",
  "status": "COMPLETED",
  "generation_backend": "comfyui",
  "comfyui_path": "D:\\comfyui\\ComfyUI",
  "clips": [
    { "scene_no": 1, "file_path": "storage/results/f001/job_42/clips/scene_1.mp4", "duration_sec": 10 },
    { "scene_no": 2, "file_path": "storage/results/f001/job_42/clips/scene_2.png", "duration_sec": 0 }
  ],
  "thumbnail_candidates": [
    "storage/results/f001/job_42/thumbnails/thumb_1.png",
    "storage/results/f001/job_42/thumbnails/thumb_2.png",
    "storage/results/f001/job_42/thumbnails/thumb_3.png"
  ],
  "total_clips": 8,
  "generated_at": "2026-05-12T10:30:00Z"
}
```

skip 시 출력 (text_slide):
```json
{
  "stage_id": "STAGE_04_VIDEO_GEN",
  "status": "SKIPPED",
  "skip_mode": "text_slide",
  "clips": [
    { "scene_no": 1, "file_path": "storage/results/f001/job_42/clips/slide_1.png", "duration_sec": 5, "slide_text": "AI 에이전트란?" }
  ],
  "generated_at": "2026-05-12T10:30:00Z"
}
```

**유효성 검증 규칙**
- skip + script_only 시: 항상 통과 (SKIPPED, clips 없음)
- skip + text_slide 시: slides 배열이 비어 있지 않으면 통과
- 통과 조건: `clips` 배열이 비어 있지 않음, 각 clip의 `file_path` 실제 파일 존재
- 반송 조건 1: clips 배열이 비어 있음 → "영상 생성 실패 — ComfyUI 연결 오류 또는 미실행. ComfyUI(D:\comfyui\ComfyUI, 포트 8188) 상태를 확인하고 재시도"
- 반송 조건 2: 파일 중 하나라도 존재하지 않음 → "일부 씬 생성 실패 — {n}번 씬 파일 누락. STAGE_04를 부분 재실행"

---

#### STAGE_05_EDIT — 자동 편집 및 자막 생성

**스테이지 ID:** `STAGE_05_EDIT`

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| clips | array | 조건부 필수 | STAGE_04의 clips 배열 (SKIPPED가 아닐 때 필수) | 1개 이상 |
| audio_file_path | string | 조건부 필수 | STAGE_03의 오디오 파일 경로 (SKIPPED가 아닐 때 필수) | 실제 파일 존재 |
| subtitle_language | string | 선택 | ko / en / both (기본: ko) | enum 값 |
| bgm_enabled | boolean | 선택 | 배경음악 삽입 여부 (기본: false) | boolean |
| bgm_volume | float | 선택 | BGM 볼륨 비율 0~1.0 (기본: 0.15) | 0~1.0 |
| output_format | string | 선택 | mp4 (기본 및 유일 지원) | mp4 |
| output_resolution | string | 선택 | 1920x1080 / 1280x720 (기본: 1280x720) | enum 값 |

**처리 로직**
1. FFmpeg: clips 순서대로 타임라인 배치, 오디오 믹싱
2. Whisper: 오디오에서 자막 자동 생성 → SRT 파일 출력
3. FFmpeg: 자막 파일을 영상에 합성 (burn-in 또는 별도 SRT 첨부)
4. BGM enabled 시: 저작권 자유 BGM 파일에서 선택하여 오디오 레이어에 합성
5. 출력: `storage/results/f001/{job_id}/final/output.mp4` + `subtitles.srt`
- STAGE_03 SKIPPED 시: 오디오 없이 슬라이드 영상 + BGM만으로 편집
- STAGE_04 SKIPPED (script_only) 시: 이 스테이지도 SKIPPED 처리

**출력 스키마**
```json
{
  "stage_id": "STAGE_05_EDIT",
  "status": "COMPLETED",
  "video_file_path": "storage/results/f001/job_42/final/output.mp4",
  "video_file_name": "output.mp4",
  "subtitle_file_path": "storage/results/f001/job_42/final/subtitles.srt",
  "duration_sec": 635,
  "resolution": "1280x720",
  "file_size_mb": 120,
  "has_subtitles": true,
  "has_bgm": false,
  "generated_at": "2026-05-12T11:00:00Z"
}
```

**유효성 검증 규칙**
- SKIPPED 시: 항상 통과
- 통과 조건: `video_file_path` 실제 파일 존재, `duration_sec > 0`, `file_size_mb > 0.1`
- 반송 조건 1: 파일 존재하지 않음 → "영상 편집 실패 — FFmpeg 오류. FFmpeg 설치 여부를 확인하고 재시도"
- 반송 조건 2: duration_sec == 0 → "편집 결과 영상 손상 — 클립 파일 또는 오디오 파일 재확인 후 STAGE_05 재실행"

---

#### STAGE_06_UPLOAD — SEO 최적화 및 YouTube 업로드

**스테이지 ID:** `STAGE_06_UPLOAD`

**[결정 완료] 업로드 방식: UI에서 선택 가능, 기본값 `manual_approval`**

UI에서 radio 버튼으로 업로드 방식 선택. 초기 기본값은 `manual_approval`로 설정.
결과 안정화 확인 후 `auto`로 전환 가능하도록 설계.

**입력 스키마**
| 필드 | 타입 | 필수 | 설명 | 유효성 조건 |
|------|------|------|------|-------------|
| video_file_path | string | 조건부 필수 | STAGE_05의 최종 영상 파일 경로 (SKIPPED가 아닐 때) | 실제 파일 존재 |
| script_data | object | 필수 | STAGE_02 출력 (title, seo_keywords 등) | 필수 필드 포함 |
| thumbnail_path | string | 선택 | 사용할 썸네일 경로 (없으면 자동 선택) | 실제 파일 존재 |
| upload_mode | string | 선택 | auto / manual_approval **(기본: manual_approval)** | enum 값 |
| privacy | string | 선택 | public / unlisted / private (기본: private) | enum 값 |
| scheduled_publish | string | 선택 | 예약 발행 시각 ISO8601 또는 null | ISO8601 또는 null |

**처리 로직**
1. Ollama: script_data + seo_keywords 기반으로 최적화된 제목, 설명문, 태그 목록 생성
2. Ollama: 썸네일 A/B 테스트용 제목 변형 2개 추가 생성
3. `upload_mode == 'manual_approval'` 시 (기본): SEO 메타데이터를 생성하고 DB에 `PENDING_APPROVAL` 상태로 저장 → 관리자 승인 대기
4. `upload_mode == 'auto'` 또는 승인 완료 시: YouTube Data API v3로 업로드 + 썸네일 업로드
5. STAGE_04/05가 SKIPPED (script_only) 시: 스크립트 파일과 SEO 메타데이터만 산출물로 저장, 영상 업로드 생략

**출력 스키마**
```json
{
  "stage_id": "STAGE_06_UPLOAD",
  "status": "COMPLETED",
  "seo_metadata": {
    "title": "AI가 스스로 일한다? 2026 에이전트 혁명 완벽 정리 [최신]",
    "description": "2026년 AI 에이전트의 모든 것을 한 영상에 담았습니다...",
    "tags": ["AI 에이전트", "클로드", "GPT", "2026 AI 트렌드"],
    "category": "28",
    "title_variants": ["AI 에이전트 완벽 가이드 2026", "당신도 모르는 AI 에이전트의 비밀"]
  },
  "upload_mode": "manual_approval",
  "upload_status": "PENDING_APPROVAL",
  "youtube_video_id": null,
  "youtube_url": null,
  "uploaded_at": null,
  "generated_at": "2026-05-12T11:05:00Z"
}
```

승인 후 업로드 완료 시:
```json
{
  "upload_status": "UPLOADED",
  "youtube_video_id": "dQw4w9WgXcQ",
  "youtube_url": "https://youtu.be/dQw4w9WgXcQ",
  "uploaded_at": "2026-05-12T12:00:00Z"
}
```

**유효성 검증 규칙**
- 통과 조건: `seo_metadata.title` 존재, `seo_metadata.tags` 1개 이상
- 반송 조건: SEO 메타데이터 생성 실패 → "SEO 최적화 실패 — STAGE_02 스크립트 데이터 또는 STAGE_01 키워드를 확인하여 재시도"
- 업로드 실패 시: STAGE_06을 FAILED로 전환 (이전 스테이지는 유지) + YouTube API 인증 오류 메시지 제공

---

### 2-2. 스테이지 간 데이터 전달 구조

#### 핸드오프 방식

각 스테이지 결과는 `stage_results` 테이블에 독립 저장된다.
다음 스테이지 실행 시 `job_id`로 이전 스테이지 결과를 조회하여 입력으로 사용한다.

#### 스테이지 간 데이터 매핑

```
STAGE_01 출력                    STAGE_02 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
topics[selected].title      →   selected_topic
topics[selected].keywords   →   reference_data
channel_category            →   channel_category

STAGE_02 출력                    STAGE_03 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
script.(hook+body+cta) 병합  →   script_text

STAGE_02 출력                    STAGE_04 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
scenes                      →   scenes

STAGE_03 출력 + STAGE_04 출력    STAGE_05 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
audio_file_path             →   audio_file_path (SKIPPED 시 null)
clips                       →   clips (SKIPPED + script_only 시 없음)

STAGE_05 출력 + STAGE_02 출력    STAGE_06 입력
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
video_file_path             →   video_file_path (SKIPPED 시 null)
title + seo_keywords        →   script_data
thumbnail_candidates[0]     →   thumbnail_path (기본 선택)
```

#### skip 체인 처리 규칙

```
STAGE_03 skip → STAGE_05는 오디오 없이 BGM 전용 모드 실행 (계속 진행)
STAGE_04 skip (text_slide) → 슬라이드 clips 생성 후 STAGE_05 계속 진행
STAGE_04 skip (script_only) → STAGE_05도 자동 SKIP, STAGE_06에서 스크립트만 산출
STAGE_03 + STAGE_04 모두 skip (script_only) → STAGE_05 SKIP, STAGE_06 스크립트 산출
```

#### 반송(재작성 요청) 메커니즘

유효성 검증 실패 시 해당 스테이지를 `REJECTED` 상태로 전환한다.
`rejection_target` 필드에 반송할 스테이지 ID를 기록하며, 오케스트레이터가 해당 스테이지를 `PENDING`으로 리셋 후 재실행한다.

```json
{
  "stage_id": "STAGE_03_VOICEOVER",
  "status": "REJECTED",
  "rejection_reason": "TTS 생성 실패 — elevenlabs API 키 오류",
  "rejection_target": "STAGE_03_VOICEOVER",
  "can_retry": true,
  "retry_suggestion": "tts_provider를 coqui로 변경하여 재시도"
}
```

STAGE_02가 REJECTED되면 STAGE_01의 topics에서 다음 순위 주제로 교체하여 재실행 옵션을 UI에 제공한다.

---

### 2-3. DB 스키마 변경 계획

#### 현재 tasks 테이블의 한계

단일 `result` TEXT 컬럼에 모든 중간/최종 결과를 JSON으로 저장하는 방식은
6개 스테이지의 독립적 추적, 반송, 재실행을 지원하기 어렵다.

#### 신규 테이블 설계

**content_jobs 테이블** (새로운 멀티스테이지 작업 단위)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 작업 ID |
| feature_id | TEXT NOT NULL | 'F001' 고정 |
| status | TEXT NOT NULL | PENDING / RUNNING / DONE / FAILED / CANCELLED / PENDING_APPROVAL |
| channel_category | TEXT | 채널 카테고리 |
| initial_params | TEXT (JSON) | 최초 입력 파라미터 전체 |
| current_stage | TEXT | 현재 실행 중인 스테이지 ID |
| upload_mode | TEXT DEFAULT 'manual_approval' | **auto / manual_approval (기본: manual_approval)** |
| created_at | DATETIME DEFAULT CURRENT_TIMESTAMP | 생성 시각 |
| started_at | DATETIME | 첫 스테이지 시작 시각 |
| finished_at | DATETIME | 전체 완료 시각 |
| triggered_by | TEXT DEFAULT 'manual' | manual / schedule |
| youtube_video_id | TEXT | 업로드 완료 후 YouTube 영상 ID |
| notes | TEXT | 관리자 메모 (승인 흐름용) |
| legacy_task_id | INTEGER | 기존 tasks 테이블 연동용 (마이그레이션 시 사용) |

**stages 테이블** (스테이지 실행 레코드)
| 컬럼 | 타입 | 설명 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 스테이지 레코드 ID |
| job_id | INTEGER NOT NULL | content_jobs.id 외래키 |
| stage_id | TEXT NOT NULL | STAGE_01_RESEARCH 등 |
| stage_order | INTEGER NOT NULL | 1~6 |
| status | TEXT NOT NULL | PENDING / RUNNING / DONE / FAILED / REJECTED / **SKIPPED** |
| input_data | TEXT (JSON) | 이 스테이지의 입력 데이터 |
| output_data | TEXT (JSON) | 이 스테이지의 출력 데이터 |
| rejection_reason | TEXT | REJECTED 시 반송 사유 |
| rejection_target | TEXT | 반송할 스테이지 ID |
| retry_count | INTEGER DEFAULT 0 | 재시도 횟수 |
| skip | INTEGER DEFAULT 0 | **STAGE_04 등 skip 여부 (0/1)** |
| skip_mode | TEXT | **text_slide / script_only (skip 시 대안 처리 방식)** |
| created_at | DATETIME DEFAULT CURRENT_TIMESTAMP | 레코드 생성 시각 |
| started_at | DATETIME | 실행 시작 시각 |
| finished_at | DATETIME | 완료 시각 |
| task_pid | INTEGER | 실행 프로세스 PID (취소용) |

**인덱스**
```sql
CREATE INDEX idx_stages_job_id ON stages(job_id);
CREATE INDEX idx_stages_status ON stages(status);
CREATE INDEX idx_content_jobs_feature_status ON content_jobs(feature_id, status);
```

#### 기존 tasks 테이블과의 관계

기존 tasks 테이블은 **유지**한다 (F002, F003 등 단일 파이프라인 기능에 계속 사용).
F001 멀티스테이지는 `content_jobs + stages` 테이블로 독립 운영한다.
`content_jobs.legacy_task_id` 컬럼으로 기존 F001 tasks와 연동 가능하다.
하이브리드 전환 전략 상세는 섹션 10 참조.

---

### 2-4. 업로드 정책 설계

#### [결정 완료] 기본값: manual_approval, UI에서 변경 가능

**업로드 방식 UI 선택 컴포넌트 구조**

작업 생성 모달의 Step 4 (업로드 설정)에 radio 그룹으로 배치:

```
업로드 방식 선택:
  (●) 승인 후 업로드 (manual_approval) [기본값]
      → SEO 메타데이터 생성 후 대시보드에서 검토 및 수정 가능
      → "업로드 승인" 버튼 클릭 시 YouTube 업로드 시작
  ( ) 자동 업로드 (auto)
      → SEO 생성 완료 즉시 YouTube 업로드 (검토 없음)
      → 충분한 테스트 후 선택 권장
```

**자동 업로드 (`upload_mode: 'auto'`)**
```
STAGE_06 완료 → SEO 메타데이터 생성 → YouTube API 즉시 업로드
```

**관리자 승인 후 업로드 (`upload_mode: 'manual_approval'`) [기본]**
```
STAGE_06 SEO 생성 완료
  → content_jobs.status = 'PENDING_APPROVAL'
  → 대시보드에 승인 대기 배너 표시
  → 관리자: 메타데이터 검토 → 수정 가능 (제목/설명/태그)
  → "업로드 승인" 버튼 클릭
  → POST /api/f001/jobs/{id}/approve
  → YouTube API 업로드 시작
  → content_jobs.status = 'DONE'
```

**PENDING_APPROVAL 상태 흐름**
```
DONE (STAGE_05) → PENDING_APPROVAL → 승인 → 업로드 시작 → DONE (전체)
                                   → 거부 → REJECTED (관리자가 STAGE_06 재실행 트리거)
```

#### YouTube Data API 연동 방식
- OAuth 2.0 인증 (youtube.upload scope 필요)
- 인증 토큰을 `settings` 테이블에 저장 (`youtube_oauth_token` 키)
- 갱신 토큰(refresh token)으로 만료 시 자동 재발급
- 업로드 API: `videos.insert` 메서드 (multipart upload)
- 썸네일 API: `thumbnails.set` 메서드
- **일일 유닛 한도: 10,000유닛** — 업로드 1회 = 1,600유닛, STAGE_01 검색 1회 = 100유닛
  → 하루 최대 영상 업로드 약 6회, 트렌드 검색 최대 약 100회

---

## 3. 프론트엔드 변경 계획

### 3-1. F001View.vue — F001 전용 메인 화면

현재 F001은 `FeatureView.vue` 공통 폼을 사용한다.
F003에 `F003View.vue`가 별도 존재하듯, F001도 전용 뷰가 필요하다.

**화면 구성**
```
F001View.vue
├── 상단: 채널 기본 설정 (channel_category, channel_tone, upload_mode 선택)
├── 중단: 세부업무 목록 테이블
│   ├── 열: ID / 상태 / 채널 카테고리 / 현재 스테이지 / 생성 일시 / 액션
│   └── "세부업무 추가" 버튼 → 신규 작업 생성 모달
├── 하단 (레거시 섹션): 기존 tasks 테이블의 F001 이력 표시
│   └── "레거시 이력 보기" 토글 → 기존 단순 스크립트 생성 작업 목록
└── 페이지네이션
```

**라우팅 변경**
- `DashboardView.vue`에서 F001 클릭 시: `router.push({ name: 'F001Feature' })`
- 현재 F003 처리 패턴 그대로 적용 (`feature.feature_id === 'F001'` 조건 추가)

### 3-2. 세부업무 추가 모달/폼 구조

**Step 1 — 기본 정보 입력**
- 채널 카테고리 (text input, 필수)
- 주제 후보 개수 (number, 기본 5)
- 검색 기간(일) (number, 기본 7)
- 추가 키워드 힌트 (textarea, 선택)
- 트렌드 소스 (checkbox: YouTube Data API / SearXNG — 기본 둘 다 체크)

**Step 2 — 스크립트 설정**
- 영상 목표 길이(분) (number, 기본 10)
- 채널 톤앤매너 (select: educational/entertaining/tutorial)
- 훅 스타일 (select: question/shocking_fact/story)
- CTA 유형 (select: subscribe/like/comment)

**Step 3 — 영상 생성 설정**
- 영상 생성 백엔드 (select: comfyui / skip)
  - skip 선택 시: 대안 처리 방식 (radio: 텍스트 슬라이드 / 스크립트만)
- TTS 제공자 (select: coqui / kokoro / elevenlabs / openai / skip)
- 아트 스타일 (F003와 동일 선택지, comfyui 선택 시만 활성화)
- 음성 ID (text input, 선택)

**Step 4 — 업로드 설정**
- 업로드 방식 (radio: 승인 후 업로드[기본] / 자동 업로드)
- 공개 범위 (select: private/unlisted/public)
- 예약 발행 (datetime input, 선택)

### 3-3. 스테이지별 진행 현황 표시 UI

**F001JobDetailView.vue** (신규) — `/f001/jobs/{id}`
```
페이지 상단: 작업 #42 (AI/기술 채널) — 전체 상태 배지

스테이지 타임라인 (세로 스텝 표시)
├── STAGE_01 주제 발굴    [DONE]    → "2026 AI 에이전트 트렌드" 선택됨
├── STAGE_02 스크립트     [DONE]    → 스크립트 요약 + "전체 보기" 링크
├── STAGE_03 보이스오버   [RUNNING] → 진행 중 애니메이션 (skip 시 회색 SKIPPED 뱃지)
├── STAGE_04 영상 생성    [PENDING] (skip 시 skip_mode에 따라 SKIPPED / 슬라이드 생성 중)
├── STAGE_05 편집         [PENDING]
└── STAGE_06 업로드       [PENDING_APPROVAL] → 승인 대기 배너

[각 스테이지 행 클릭 시 결과 패널 토글 확장]
```

**스테이지 상태별 표시**
- PENDING: 회색 점선 원
- RUNNING: 파란 스피너
- DONE: 초록 체크
- FAILED/REJECTED: 빨간 X + 오류 메시지 + 재시도 버튼
- SKIPPED: 회색 대시(--) + skip 이유 텍스트

### 3-4. 각 스테이지 결과 뷰어

| 스테이지 | 결과 표시 방식 |
|---------|----------------|
| STAGE_01 | 주제 카드 목록 (랭킹, 예상 조회수, 추천 이유, 소스 구분) — 다른 주제 선택 가능 |
| STAGE_02 | 훅/본문/CTA 구분된 스크립트 뷰 + 씬 목록 |
| STAGE_03 | 오디오 플레이어 (HTML audio 태그) + 파일 정보 / SKIPPED 시 안내 메시지 |
| STAGE_04 | 씬별 이미지/클립 그리드 + 썸네일 후보 선택 UI / SKIPPED 시 슬라이드 목록 또는 안내 메시지 |
| STAGE_05 | HTML video 태그 (최종 영상 미리보기) + SRT 자막 텍스트 |
| STAGE_06 | SEO 메타데이터 편집 폼 + 승인/거부 버튼 (upload_mode에 따라 버튼 표시 여부 결정) |

### 3-5. 승인/반송 버튼 UI

STAGE_06 결과 뷰어 하단에 배치:
- "업로드 승인" 버튼 (초록) → POST /api/f001/jobs/{id}/approve (`manual_approval` 모드일 때만 표시)
- "수정 후 재시도" 버튼 (노랑) → 메타데이터 인라인 편집 모드 전환
- "업로드 거부" 버튼 (빨강) → 사유 입력 모달 → STAGE_06 재실행

---

## 4. 백엔드 변경 계획

### 4-1. 새 API 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /api/f001/jobs | 새 콘텐츠 작업 생성 (6단계 파이프라인 시작) |
| GET | /api/f001/jobs | 콘텐츠 작업 목록 (cursor 페이징) |
| GET | /api/f001/jobs/{job_id} | 콘텐츠 작업 상세 (스테이지 목록 포함) |
| DELETE | /api/f001/jobs/{job_id} | 콘텐츠 작업 취소 |
| GET | /api/f001/jobs/{job_id}/stages | 스테이지 목록 조회 |
| GET | /api/f001/jobs/{job_id}/stages/{stage_id} | 스테이지 단건 조회 |
| POST | /api/f001/jobs/{job_id}/stages/{stage_id}/retry | 특정 스테이지 재시도 |
| POST | /api/f001/jobs/{job_id}/approve | PENDING_APPROVAL → 업로드 시작 |
| POST | /api/f001/jobs/{job_id}/reject | PENDING_APPROVAL → STAGE_06 재실행 |
| GET | /api/f001/jobs/{job_id}/result | 최종 결과(영상 URL, SEO 메타데이터) |
| GET | /api/f001/legacy | 기존 tasks 테이블에서 F001 이력 조회 (legacy 뷰어용) |

### 4-2. 파이프라인 실행 오케스트레이터 구조

기존 `task_service._spawn_pipeline(task_id, feature_id)` 방식을 확장한다.

**F001 오케스트레이터 (`pipelines/f001_youtube/orchestrator.py`)**
```
F001Orchestrator.run(job_id)
  → STAGE_01 실행 → 출력 유효성 검증
    → 통과: STAGE_01.status = DONE, STAGE_02.status = PENDING
    → 실패: STAGE_01.status = REJECTED → 재시도 요청
  → STAGE_02 실행 (STAGE_01 출력을 입력으로) → ...
  → STAGE_03 실행 (STAGE_02 출력을 입력으로) 또는 SKIP 처리
  → STAGE_04 실행 (STAGE_02 출력을 입력으로) 또는 SKIP 처리  ← STAGE_03과 병렬 가능
  → STAGE_05 실행 (STAGE_03 + STAGE_04 출력) 또는 SKIP 체인
  → STAGE_06 실행 → upload_mode 분기
    → manual_approval: job.status = PENDING_APPROVAL, 대기 (기본)
    → auto: YouTube 업로드 → job.status = DONE
```

**STAGE_03과 STAGE_04 병렬 실행 고려**
- TTS 합성과 영상 클립 생성은 입력이 서로 다름 (STAGE_03은 STAGE_02 스크립트, STAGE_04는 STAGE_02 씬 데이터)
- 두 스테이지를 병렬 subprocess로 실행하면 처리 시간을 단축 가능
- 단, STAGE_05는 두 스테이지 완료 후에만 시작

### 4-3. 스테이지 간 핸드오프 메커니즘

```
각 스테이지 파이프라인 클래스:
  F001Stage01Pipeline(BasePipeline)
    - run(job_id, stage_record_id, input_data) → output_data
    - validate_output(output_data) → (bool, rejection_reason)

오케스트레이터 핸드오프 흐름:
  output = stage.run(job_id, stage_id, input_data)
  valid, reason = stage.validate_output(output)
  if valid:
    db.update stages SET status='DONE', output_data=json(output)
    next_input = extract_next_input(output, next_stage_id)
    db.update stages SET status='PENDING' WHERE stage_id=next_stage_id
    spawn_next_stage(next_stage_id, next_input)
  else:
    db.update stages SET status='REJECTED', rejection_reason=reason
    notify_orchestrator_for_retry()
```

---

## 5. 외부 서비스 의존성 분석

**[결정 완료] 트렌드: YouTube Data API(1차) + SearXNG(2차) 병행**
**[결정 완료] TTS: Coqui TTS(기본) → Kokoro TTS → 유료 서비스**
**[결정 완료] 영상 생성: ComfyUI 로컬 확정 (D:\comfyui\ComfyUI, 포트 8188), Runway 제거**

| 서비스 | 용도 | 로컬/클라우드 | 설치 필요 여부 | 비용 | 우선순위 |
|--------|------|--------------|----------------|------|---------|
| Ollama | 스크립트 생성, SEO 메타 생성, 프롬프트 빌드 | 로컬 | 이미 설치됨 | 무료 | 필수 |
| YouTube Data API | 트렌드 검색 1차 소스 (STAGE_01) | 클라우드 | Google Cloud OAuth 설정 | 무료 (일일 10,000유닛 한도) | 1순위 |
| SearXNG | 트렌드 검색 2차 소스 + 교차 검증 (STAGE_01) | 로컬 인스턴스 | 이미 설치됨 (192.168.20.80:8888) | 무료 | 2순위 |
| Coqui TTS | 보이스오버 기본 (STAGE_03) | 로컬 | pip install TTS | 무료 (오픈소스) | 1순위 TTS |
| Kokoro TTS | 보이스오버 2순위 대안 (STAGE_03) | 로컬 | pip install kokoro | 무료 (오픈소스) | 2순위 TTS |
| ElevenLabs | 보이스오버 고품질 유료 (STAGE_03) | 클라우드 | API 키 필요 | 유료 ($5/월 시작) | 3순위 TTS |
| OpenAI TTS | 보이스오버 유료 대안 (STAGE_03) | 클라우드 | API 키 필요 | 유료 ($0.015/1K자) | 3순위 TTS |
| ComfyUI | 영상/이미지 클립 생성 (STAGE_04) | 로컬 | 설치 확인됨 (D:\comfyui\ComfyUI) | 무료 | 확정 유일 옵션 |
| FFmpeg | 영상 편집, 클립 병합 (STAGE_05) | 로컬 | `winget install ffmpeg` | 무료 (오픈소스) | 필수 |
| Whisper (openai-whisper) | 자막 생성 (STAGE_05) | 로컬 GPU | pip install openai-whisper | 무료 (오픈소스) | 필수 |
| faster-whisper | 자막 생성 고속 대안 (STAGE_05) | 로컬 GPU | pip install faster-whisper | 무료 | 대안 |
| YouTube Data API v3 | 영상 업로드 (STAGE_06) | 클라우드 | Google Cloud OAuth 설정 (STAGE_01과 공유) | 무료 (업로드 1회 1,600유닛) | 필수 |

**Runway, Kling AI 제거됨**: 유료 클라우드 서비스는 사용하지 않기로 확정. ComfyUI 로컬만 사용.

**로컬만으로 완전 실행 가능 경로 (API 키 없이, YouTube 업로드 제외):**
- STAGE_01: SearXNG 단독 사용 (YouTube API 없을 때 폴백)
- STAGE_02: Ollama (이미 가동 중)
- STAGE_03: Coqui TTS (설치 필요) 또는 skip
- STAGE_04: ComfyUI (D:\comfyui\ComfyUI, 이미 설치됨) 또는 skip
- STAGE_05: FFmpeg + Whisper (설치 필요)
- STAGE_06: SEO 메타 생성까지는 로컬, 실제 업로드는 YouTube API 필요

---

## 6. 구현 리스크 및 제약사항

### 6-1. 단계별 처리 시간 예상

| 스테이지 | 예상 시간 | 병목 요인 |
|---------|-----------|-----------|
| STAGE_01 검색+분석 | 1~3분 | YouTube API 응답 + Ollama 추론 시간 |
| STAGE_02 스크립트 | 2~5분 | Ollama 추론 (긴 스크립트 = 긴 생성 시간) |
| STAGE_03 TTS | 1~10분 | Coqui: GPU 사용 시 빠름; CPU 전용 시 느림 |
| STAGE_04 영상 생성 | 5~30분 | ComfyUI 이미지 N장 × 생성 시간 (씬당 20~60초) |
| STAGE_05 편집 | 1~5분 | FFmpeg CPU 인코딩; Whisper 모델 크기에 따라 차이 |
| STAGE_06 SEO+업로드 | 2~10분 | Ollama SEO 생성 + YouTube 업로드 대역폭 |

**전체 파이프라인 예상 소요 시간: 12분~50분** (로컬 환경, STAGE_03/04 병렬 시)

### 6-2. 외부 API 비용/제한

| 서비스 | 제한 사항 |
|--------|-----------|
| ElevenLabs 무료 | 월 10,000자 한도 — 10분 영상(약 1,700자) 기준 약 6회 |
| OpenAI TTS | 분당 50 요청 제한 |
| **YouTube Data API** | **하루 10,000 유닛 (업로드 1,600유닛/회 → 하루 약 6회; 검색 100유닛/회 → 검색 최대 100회)** |

### 6-3. 로컬 환경 제약

- **Whisper 모델 크기**: `base` 모델 141MB, `medium` 모델 769MB — GPU VRAM 부족 시 `base` 강제
- **ComfyUI 씬 처리**: 씬 1개당 20~30초 × 씬 수 = 10개 씬이면 3~5분 추가 소요. 경로: `D:\comfyui\ComfyUI`
- **Coqui TTS 한국어**: `css10/vits` 모델 품질이 ElevenLabs보다 낮음. 명확한 발음이지만 자연스러움 부족 → 불만족 시 Kokoro TTS로 전환
- **Kokoro TTS 한국어**: Hexgrad/Kokoro-82M 기반. 한국어 지원 여부를 설치 후 실제 테스트로 확인 필요 (기본 학습 데이터에 한국어 포함이나 품질은 미검증)
- **FFmpeg 경로**: Windows에서 PATH 설정 필요 (`winget install ffmpeg` 후 재시작)
- **DB 경로 하드코딩**: `base.py`의 `DB_PATH = r"C:\Develop\Dash\storage\dash.db"` — 다른 환경 이동 시 수정 필요

### 6-4. Ollama로 대체 가능한 스테이지

| 스테이지 | 외부 서비스 | Ollama 대체 가능 여부 |
|---------|-------------|----------------------|
| STAGE_01 주제 분석 | 유료 SEO 툴 | 가능 (SearXNG + YouTube API + Ollama로 완전 대체) |
| STAGE_02 스크립트 | GPT-4o | 가능 (현재 F001이 이미 Ollama 사용) |
| STAGE_03 TTS | ElevenLabs/OpenAI | 불가 (Ollama는 텍스트 전용) — Coqui TTS/Kokoro TTS 로컬 대안 사용 |
| STAGE_04 영상 생성 | 유료 클라우드 서비스 | 불가 — ComfyUI 로컬 사용 (확정) |
| STAGE_05 자막 | 유료 STT | 불가 (Ollama는 STT 미지원) — Whisper 로컬 사용 |
| STAGE_06 SEO 메타 | 유료 SEO 툴 | 가능 (Ollama로 SEO 최적 메타데이터 생성) |

---

## 7. 구현 우선순위 로드맵

### Phase 1 — 스테이지 분리 아키텍처 구축 (DB + API) [2~3일]

- `content_jobs`, `stages` 테이블 추가 (`core/database.py`)
  - `upload_mode DEFAULT 'manual_approval'` 컬럼 포함
  - `stages.skip`, `stages.skip_mode` 컬럼 포함
  - `content_jobs.legacy_task_id` 컬럼 포함
- `F001Orchestrator` 기반 클래스 (`pipelines/f001_youtube/orchestrator.py`)
- `/api/f001/jobs` CRUD 엔드포인트 (`backend/routers/f001_jobs.py`)
  - `/api/f001/legacy` 엔드포인트 포함 (레거시 tasks 조회)
- F001 라우터를 `main.py`에 등록
- 기존 `tasks` 테이블은 건드리지 않음 (F002, F003 호환 유지)

**완료 기준**: POST /api/f001/jobs 호출 시 content_jobs + 6개 stages 레코드 생성 확인

### Phase 2 — STAGE_01, STAGE_02 구현 (주제 발굴 + 스크립트) [3~4일]

- YouTube Data API 연동 (`google-api-python-client` 설치, OAuth 설정)
- `F001Stage01Pipeline` 구현 (YouTube Data API 1차 + SearXNG 2차 병행)
- `F001Stage02Pipeline` 구현 (Ollama 스크립트 + 씬 분해)
- 각 스테이지의 유효성 검증 및 반송 로직
- 오케스트레이터에 STAGE_01 → STAGE_02 핸드오프 구현

**완료 기준**: 작업 생성 → STAGE_01 완료 → STAGE_02 자동 시작 → 스크립트 DB 저장 확인

### Phase 3 — STAGE_03, STAGE_04 구현 (TTS + 영상 생성) [4~5일]

- FFmpeg, Coqui TTS 설치 및 Python 래퍼 구현
- `F001Stage03Pipeline` 구현 (Coqui TTS 기본, Kokoro/ElevenLabs/OpenAI 선택, skip 처리)
- `F001Stage04Pipeline` 구현 (ComfyUI `D:\comfyui\ComfyUI` 연동, F003 ComfyUIClient 재활용, skip 처리)
- STAGE_03/STAGE_04 병렬 실행 구현 (두 subprocess 동시 spawn)
- skip 체인 로직 구현 (text_slide 슬라이드 생성 또는 script_only 경로)

**완료 기준**: STAGE_02 완료 후 STAGE_03/04 병렬 실행 → 오디오 파일 + 클립 파일 생성 확인

### Phase 4 — STAGE_05, STAGE_06 구현 (편집 + SEO/업로드) [4~5일]

- Whisper 설치 및 Python 래퍼 구현
- `F001Stage05Pipeline` 구현 (FFmpeg 편집 + Whisper 자막)
- `F001Stage06Pipeline` 구현 (Ollama SEO 메타 생성)
- YouTube OAuth 설정 + `videos.insert` API 연동 (upload_mode 분기 처리)
- `manual_approval` 기본 흐름: PENDING_APPROVAL 상태 + approve/reject API

**완료 기준**: STAGE_05 완료 후 최종 MP4 파일 생성, STAGE_06에서 SEO 메타데이터 생성 + PENDING_APPROVAL 상태 전환 확인

### Phase 5 — 관리자 승인 흐름 + UI 완성 [3~4일]

- `PENDING_APPROVAL` 상태 처리 (approve/reject API)
- `F001View.vue` 전용 화면 구현 (세부업무 목록 + 추가 모달 + 레거시 이력 통합 표시)
- `F001JobDetailView.vue` 구현 (스테이지 타임라인 + 결과 뷰어 + SKIPPED 상태 표시)
- `DashboardView.vue` 라우팅 업데이트 (F001 전용 뷰로 연결)
- 승인/거부 UI 구현 (upload_mode 선택 radio 포함)

**완료 기준**: 전체 6단계 파이프라인이 UI에서 완전히 모니터링되며 승인 후 업로드까지 동작 확인. 레거시 F001 이력이 동일 뷰에서 표시 확인.

---

## 8. 결정 완료 사항 (V2 미결 → 확정)

> V2에서 "미결 사항"으로 분류된 6개 항목이 모두 사용자 결정으로 확정됨. (2026-05-12)

### 결정 1 — 업로드 방식 [확정]

**결정 내용**: 업로드 방식은 UI에서 선택 가능. **기본값: `manual_approval` (승인 후 업로드)**

| 모드 | 설명 |
|------|------|
| manual_approval (기본) | SEO 메타데이터 생성 후 대시보드에서 검토·수정 가능. 승인 버튼 클릭 시 업로드 |
| auto | SEO 생성 완료 즉시 YouTube 업로드. 결과 안정화 확인 후 전환 권장 |

**후속 조치**:
- STAGE_06 입력 스키마에 `upload_mode` 필드, `content_jobs` 테이블에 `upload_mode DEFAULT 'manual_approval'` 컬럼 추가
- Step 4 폼의 radio 그룹에서 `manual_approval`을 기본 선택값으로 설정

---

### 결정 2 — TTS 제공자 [확정]

**결정 내용**: 단계적 전환 전략. 우선순위:

| 순위 | 제공자 | 방식 | 기본 적용 여부 |
|------|--------|------|----------------|
| 1순위 | **Coqui TTS** | 로컬, 무료, 오픈소스 | 기본 적용 |
| 2순위 | **Kokoro TTS** | 로컬, 무료 (Hexgrad/Kokoro-82M) | Coqui 품질 불만족 시 전환 |
| 3순위 | ElevenLabs / OpenAI TTS | 유료 클라우드 | 더 높은 품질 필요 시 선택 |

**후속 조치**: 섹션 9에서 각 TTS의 설치 방법, 한국어 지원 여부, 전환 판단 기준 상세 기술

---

### 결정 3 — 영상 생성 백엔드 [확정]

**결정 내용**: **ComfyUI 로컬 사용 확정** — Runway 등 유료 클라우드 서비스 미사용

- 경로: `D:\comfyui\ComfyUI` (실제 존재 확인됨)
- API 포트: 8188
- F003 파이프라인에서 이미 `ComfyUIClient` 및 `ModelManager`를 사용 중 — 재활용 가능
- `backend/routers/features.py`에서 comfyui_path를 config.json으로 관리하는 패턴 확인

**후속 조치**: F001 config.json에 `comfyui_path: "D:\\comfyui\\ComfyUI"` 설정 추가. F003 ComfyUIClient import 경로 정리

---

### 결정 4 — 트렌드 데이터 소스 [확정]

**결정 내용**: **YouTube Data API(1차) + SearXNG(2차) 병행 사용**

- YouTube Data API: 유튜브 직접 트렌드 데이터 (1차 소스, 일일 10,000유닛)
- SearXNG: 추가 정보 수집 + 교차 검증 (2차 소스, 무료)
- 두 소스 결과를 합산하여 주제 후보 스코어링
- YouTube API 할당량 초과 시 SearXNG 단독 폴백

**후속 조치**: `google-api-python-client` 설치, YouTube API 키/OAuth 설정. base.py의 `call_searxng()` 재사용.

---

### 결정 5 — STAGE_04 skip 옵션 [확정]

**결정 내용**: **UI에서 선택 가능** — 영상 생성 및 TTS 모두 개별 skip 선택 지원

| skip 대상 | skip 시 동작 |
|-----------|-------------|
| STAGE_03 (TTS) | 오디오 없이 STAGE_05에서 BGM 전용 편집 |
| STAGE_04 (영상) - text_slide 모드 | 스크립트 섹션 제목을 배경색 슬라이드로 대체, STAGE_05 계속 진행 |
| STAGE_04 (영상) - script_only 모드 | STAGE_04/05 모두 SKIP, STAGE_06에서 스크립트+오디오만 산출 |
| STAGE_03 + STAGE_04 모두 skip (script_only) | 스크립트 텍스트만 최종 산출물 |

**후속 조치**: `stages.skip`, `stages.skip_mode` 컬럼 추가. Step 3 폼에 skip 옵션 UI 추가.

---

### 결정 6 — 기존 F001 이력 처리 [확정]

**결정 내용**: **하이브리드 방식** — 마이그레이션 + 유지 병행

- 기존 `tasks` 테이블의 F001 이력: **레거시 뷰에서 계속 표시** (삭제 없음)
- 신규 작업: `content_jobs + stages` 체계로 처리
- `content_jobs.legacy_task_id` 컬럼으로 기존 tasks와 연동 가능
- 선택적 마이그레이션 유틸: 기존 F001 tasks를 content_jobs로 변환하는 스크립트 제공 (강제 아님)
- F001View.vue에서 레거시 tasks와 새 content_jobs를 통합 표시

**후속 조치**: 섹션 10에서 하이브리드 전환 계획 상세 기술.

---

## 9. TTS 단계별 전환 전략

### 9-1. 1순위: Coqui TTS (기본 적용)

**개요**: Mozilla에서 시작한 오픈소스 TTS 프레임워크. `pip install TTS`로 설치.

**설치 방법 개요**
```
pip install TTS
# GPU 사용 시 (CUDA 기반):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**한국어 지원 여부**: 지원됨
- 모델: `tts_models/ko/css10/vits` (CSS10 한국어 데이터셋 기반 VITS 모델)
- 모델 크기: 약 80~100MB
- 첫 실행 시 자동 다운로드됨

**예상 품질 수준**
- 명확한 발음, 자연스러운 억양은 제한적
- 영상 내레이션으로 사용 가능한 수준이나 ElevenLabs 대비 기계적 느낌
- GPU 없이 CPU만으로도 동작하나 속도 저하 (10분 스크립트 = CPU로 약 5~10분 소요)

**전환 판단 기준 (2순위로 전환할 때)**
- 발음이 부정확하거나 어색하여 시청자 이탈이 우려될 때
- 억양이 너무 단조로워 콘텐츠 품질에 악영향을 줄 때
- 특정 기술 용어나 영어 혼용 단어의 발음이 심하게 왜곡될 때

---

### 9-2. 2순위: Kokoro TTS (Coqui 품질 불만족 시)

**개요**: Hexgrad의 Kokoro-82M 모델 기반 고품질 경량 TTS. `pip install kokoro` 또는 직접 모델 로드.

**설치 방법 개요**
```
# 방법 1: kokoro 패키지 (가능한 경우)
pip install kokoro soundfile

# 방법 2: HuggingFace에서 직접 모델 로드
# Hexgrad/Kokoro-82M 모델 다운로드 후 로컬 실행
```

**한국어 지원 여부**: **설치 후 실제 테스트로 확인 필요**
- Kokoro-82M은 주로 영어/일본어 데이터로 학습됨
- 한국어 텍스트 처리 가능 여부와 발음 품질은 테스트 없이 보장 불가
- 한국어 지원이 미흡할 경우 다음 두 가지 대안 검토:
  - a) Kokoro를 영어 내레이션 전용으로 사용 (콘텐츠를 영어로 생성하는 경우)
  - b) 한국어 품질이 충분치 않으면 바로 3순위(유료 서비스)로 전환

**예상 품질 수준**
- 영어 기준: ElevenLabs에 근접한 자연스러운 발음
- 한국어 기준: 테스트 필요 — Coqui보다 좋거나 비슷한 수준으로 추정

**전환 판단 기준 (3순위로 전환할 때)**
- Kokoro의 한국어 발음이 Coqui와 동등하거나 오히려 나쁜 경우
- 모델 로드 시 메모리 문제가 발생하는 경우 (82M 파라미터, VRAM 약 1~2GB 필요)

---

### 9-3. 3순위: ElevenLabs / OpenAI TTS (높은 품질 필요 시)

**ElevenLabs**

**설치/설정 방법 개요**
```
pip install elevenlabs
# 환경변수 설정: ELEVENLABS_API_KEY=xxx
```

**한국어 지원 여부**: 공식 지원. 다국어 v1/v2 모델로 자연스러운 한국어 발음 가능.

**예상 품질 수준**: 최고 수준. 자연스러운 억양, 감정 표현, 구어체 자연스러움.

**비용**: 무료 플랜 월 10,000자 한도. 10분 영상 약 1,700자 기준 월 약 6회. 유료 플랜 $5/월부터.

---

**OpenAI TTS**

**설치/설정 방법 개요**
```
pip install openai
# 환경변수 설정: OPENAI_API_KEY=xxx
# 모델: tts-1 (빠름, 저품질) 또는 tts-1-hd (느림, 고품질)
```

**한국어 지원 여부**: 공식 지원. 안정적인 한국어 발음.

**예상 품질 수준**: 높음. ElevenLabs보다 약간 낮으나 충분히 자연스러움.

**비용**: $0.015/1,000자. 10분 영상(1,700자) 약 $0.025/회.

---

### 9-4. 전환 절차 요약

```
현재: Coqui TTS 설치 및 테스트
  → 발음 만족: 계속 사용
  → 발음 불만족: Kokoro TTS 테스트
    → 한국어 지원 확인 → 만족: Kokoro로 전환
    → 한국어 미지원/불만족: ElevenLabs 또는 OpenAI TTS로 전환
      → 비용 최소화 원할 때: OpenAI TTS ($0.015/1K자)
      → 최고 품질 원할 때: ElevenLabs ($5/월~)
```

**단계적 전환 설계 원칙**: `tts_provider` 파라미터를 UI에서 선택 가능하게 하므로,
구현 후 실제 사용 시점에서 자유롭게 provider를 교체할 수 있다. 코드 변경 없이 파라미터 변경만으로 전환 가능.

---

## 10. 레거시 F001 하이브리드 전환 계획

### 10-1. 현재 F001 이력의 구조

기존 `tasks` 테이블에 저장된 F001 이력의 특징:
- `feature_id = 'F001'`
- `result` 컬럼: `{"title": "...", "description": "...", "script": "..."}` JSON
- `params` 컬럼: `{"topic": "...", "style": "...", "duration_min": 10}` JSON
- 단일 파이프라인 결과 (스테이지 구분 없음)
- `status`: DONE / FAILED / CANCELLED

### 10-2. 신규 content_jobs 체계와의 공존 방법

**하이브리드 방식 원칙:**

| 항목 | 기존 tasks 테이블 (레거시) | 신규 content_jobs 테이블 |
|------|--------------------------|--------------------------|
| 적용 범위 | 기존 F001 실행 이력 | 신규 F001 멀티스테이지 작업 |
| 테이블 | tasks (feature_id='F001') | content_jobs + stages |
| UI 표시 | F001View.vue 레거시 섹션 | F001View.vue 메인 섹션 |
| API | GET /api/f001/legacy | GET /api/f001/jobs |
| 연동 | content_jobs.legacy_task_id | (신규) |

**기존 tasks 테이블**: 수정 없이 유지. F002, F003도 동일 테이블을 사용하므로 변경 시 영향 범위가 큼.

**신규 작업**: 반드시 content_jobs + stages를 사용. tasks 테이블에 F001 신규 레코드를 삽입하지 않음.

### 10-3. 통합 뷰어 (F001View.vue) 구조

F001View.vue는 두 체계의 데이터를 동시에 표시한다:

```
F001View.vue
├── [상단] 신규 콘텐츠 작업 목록 (content_jobs 기반)
│   ├── "새 작업 추가" 버튼
│   └── 작업 테이블: ID / 상태 / 채널 카테고리 / 현재 스테이지 / 생성 일시 / 액션
│       → 클릭 시 F001JobDetailView.vue (/f001/jobs/{id}) 이동
│
└── [하단] 레거시 이력 섹션 (토글, 기본 접힘)
    ├── "기존 F001 이력 보기 ▼" 버튼 (토글 확장/접기)
    └── 레거시 작업 테이블: ID / 상태 / 주제(topic) / 생성 일시 / 결과 보기
        → "결과 보기" 클릭 시 기존 TaskDetailView.vue (/tasks/{id}) 이동
        → (또는 모달로 title/description/script 표시)
```

**구현 방식**:
- F001View 마운트 시: `GET /api/f001/jobs`와 `GET /api/f001/legacy` 병렬 호출
- 레거시 섹션은 기본 접힌 상태 (toggle로 펼치기), 사용 빈도가 낮아질수록 자연스럽게 묻힘
- 시각적으로 두 섹션을 구분 (신규: 기본 카드 스타일, 레거시: 회색 배경 + "이전 방식" 뱃지)

### 10-4. 선택적 마이그레이션 절차

**목적**: 기존 F001 tasks 레코드를 content_jobs로 변환하여 통합 관리 원하는 경우.
**실행 방식**: 수동 트리거 (자동 실행 없음, 사용자 선택)

**마이그레이션 스크립트 위치**: `pipelines/f001_youtube/migrate_legacy.py` (구현 예정)

**변환 규칙:**
- tasks.id → content_jobs.legacy_task_id
- tasks.status → content_jobs.status (DONE/FAILED/CANCELLED 그대로)
- tasks.params.topic → content_jobs.channel_category (간략 매핑)
- tasks.result → stages 테이블에 STAGE_02_SCRIPT 레코드로 변환 (title, description, script를 output_data에 저장)
- tasks.created_at → content_jobs.created_at

**마이그레이션 후 레거시 섹션 처리**:
- 마이그레이션된 tasks는 content_jobs.legacy_task_id로 추적
- 레거시 섹션에서 마이그레이션된 항목은 "이전됨" 뱃지로 표시
- 원본 tasks 레코드는 삭제하지 않음 (안전을 위해 유지)

### 10-5. 레거시 이력 API 설계

`GET /api/f001/legacy` 엔드포인트:
- `tasks` 테이블에서 `feature_id = 'F001'` 레코드 조회
- cursor 기반 페이징 지원 (기존 task_service.list_tasks 재사용)
- 응답 형식: tasks의 기존 TaskResponse 구조 그대로 반환
- 이미 content_jobs로 마이그레이션된 항목은 `migrated: true` 플래그 포함

---

*리서치 문서 V3 업데이트 완료: 2026-05-12 (독립 검증 후 수정)*
*6가지 미결 사항 전부 결정 완료로 전환. 섹션 9(TTS 전환 전략), 섹션 10(레거시 하이브리드 전환) 신규 추가.*
*수정 이력: GET /api/model-assets/downloads 엔드포인트 API 목록에 추가 (독립 검증에서 누락 발견)*
*코드 작성 금지 -- 사용자의 `구현해줘` 트리거 전까지 이 문서는 설계/분석 문서로만 사용*
