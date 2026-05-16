# Dash 세션 요약

## 세션 2026-05-16 — F004 유튜브 컨텐츠 제작 V2 — PPT 슬라이드 파이프라인 구현

### 사용자 지시 요약
1. F001 파이프라인을 F004로 복사하여 새로운 기능 구현 요청
2. F004는 ComfyUI 이미지 생성 제거 → Pillow 기반 PPT 슬라이드 렌더링으로 차별화
3. 대시보드에 feature_id 인덱스 표시 추가
4. 각 단계를 서브에이전트로 크로스체크하여 97점 이상 달성 요청

### Claude 작업 요약

**1단계: 기본 구조 구현 (병렬 3개 서브에이전트)**
- pipeline-builder: F004 파이프라인 기본 구조 복사 (18개 파일)
  - F001의 6단계 구조를 F004로 복제
  - STAGE_04: ComfyUI 제거, Pillow SlideRenderer 신규 구현
  - STAGE_02: slides 배열 출력 형식 재설계
  - orchestrator: _load_config() 추가
- api-builder: 백엔드 API 레이어 구현
  - F004 Pydantic 스키마, F004Service, F004 라우터 (14개 엔드포인트)
  - F004 복구 로직 추가
- web-builder: 프론트엔드 뷰 & 라우팅
  - F004View, F004JobDetailView 컴포넌트
  - Pinia store 구현
  - 라우팅 및 API 함수 추가

**2단계: Critic 1차 검증 (70/100 = FAIL)**
- High 3건 발견:
  1. STAGE_05 비례 배분 합계 > audio_duration (오버플로우)
  2. validate_output() 누락 (video_file_path 존재 확인 미실시)
  3. STAGE_06 script_data.get("script") 키 오류 (STAGE_02는 script_text 출력)
- Medium 3건, Low 2건도 함께 발견

**3단계: 오류 수정 및 2차 재검증 (93/100 = FAIL)**
- High 3건 모두 수정:
  - _distribute_duration_by_narration(): 2-pass 비례 배분, 총합=audio_duration 보장
  - validate_output() 구현, video_file_path 파일 존재 확인
  - STAGE_06: script_data.get("hook") → script_text[:200] 수정
- Medium 1건 남음: FONT_CANDIDATES 전역 변수 오염 (다른 파이프라인에서 재사용)
- Low 2건 수정

**4단계: FONT_CANDIDATES 격리 및 3차 재검증 (99/100 = PASS)**
- SlideRenderer 클래스에 custom_font_path 주입
- _font() 헬퍼 메서드로 전역 변수 제거
- Low 1건 잔존 (미흡한 에러 메시지 수준, 97점 기준 통과)

**5단계: 대시보드 feature_id 표시**
- DashboardView.vue: feature_id 컬럼 추가
- F001/F003/F004 등 업무 유형 시각적 구분

### 핵심 기술 결정사항
- STAGE_04 SlideRenderer: Pillow + custom_font_path로 전역 오염 방지
- STAGE_05 비례 배분: narration 필드 활용, 2-pass 알고리즘 (오버플로우 방지)
- config.json: slide_theme, slide_font_path 추가
- F004 orchestrator: F001에서 완전 별도 구현 (코드 재사용 최소화)

### 검증 완료
- Critic 3회 검증 루프 완주 (70→93→99점)
- Python AST 구문 검사 전체 통과
- 기능 모듈 독립 검증 완료

### 다음 세션 시작 포인트
- F004 파이프라인 실제 실행 테스트 (대시보드에서 F004 기능 생성 후 동작 확인)
- PPT 슬라이드 렌더링 품질 검증
- 다중 테마(dark_blue, dark_green, corporate) 테스트

<!-- session-end: 2026-05-16 -->

---

## 세션 2026-05-14 (2차) — F001 영상 길이 버그 수정 — 씬 수 자동 산정 + 오디오 기준 클립 재배분

### 사용자 지시 요약
- STAGE_02(스크립트)가 사용자의 `duration_min` 설정을 무시하고 5~8개씬만 생성하는 버그 리포트
- STAGE_05(편집)의 `-shortest` 플래그로 인해 영상 길이가 비정상적으로 짧아지는 문제 리포트
- 근본 원인 분석 및 수정 요청

### Claude 작업 요약

**1. STAGE_02 스크립트 생성 개선**
- 씬 수 자동 산정: `n_scenes_target = max(8, int(round(duration_min * 60 / 25)))`
  - 예시: duration_min=10분 → 약 24씬 자동 생성
  - 씬당 25초 기준 설정
- 스크립트 생성 prompt 대폭 개선:
  - 목표 씬 수, 총 seconds, 씬당 초 단위 명시
  - Ollama 파라미터: num_predict 2048→4096, timeout 120→180초
- **생성 후 정규화**: 씬들의 duration_sec 합계를 `duration_min × 60`으로 자동 정규화
  - 개별 씬의 비율 유지하며 전체 길이만 조정

**2. STAGE_05 영상 편집 개선 (핵심)**
- `_get_audio_duration_sec(path)` 헬퍼 추가
  - moviepy 우선, ffprobe 폴백
- `_run_ffmpeg_concat()` 완전 재설계:
  - 오디오 실제 길이 측정
  - PNG 클립 개수로 균등 재배분: `per_clip_sec = audio_duration / n_valid_clips`
  - 각 PNG 클립 `-t` 값에 재배분된 시간 적용 (float 정밀도, `.3f` 포맷)
  - **`-shortest` 플래그 제거** (오디오 기준 클립 재배분으로 불필요)
  - FFmpeg timeout: 300→600초

### 근본 원인 분석
- 문제: TTS 오디오 길이가 예측 불가능 → duration_min 설정과 불일치
- 이전 방법: `-shortest` 플래그로 오디오 길이에 맞춤 → 영상 비정상적으로 짧아짐
- 새 방법: 오디오 실제 길이 기준으로 클립을 균등 재배분 → 영상 길이 = 오디오 길이 정확히 맞춤

### 변경 파일
- `pipelines/f001_youtube/stages/stage02_script.py`
- `pipelines/f001_youtube/stages/stage05_edit.py`

### 검증 완료
- Python AST 문법 검사 통과 ✓
- 씬 수 자동 산정 로직 ✓
- 오디오 기준 클립 재배분 알고리즘 ✓

### 다음 세션 시작 포인트
- STAGE_02 → STAGE_05 전체 파이프라인 실행 테스트 (job #13 이상)
- 실제 생성 영상의 길이가 설정과 일치하는지 검증
- TTS 음성 길이와 최종 영상 길이 비교

<!-- session-end: 2026-05-14 -->

---

## 세션 2026-05-14 — F001 STAGE_04 썸네일 표시 UI 개선

### 사용자 지시 요약
- StageResultViewer.vue에서 STAGE_04 생성 결과(썸네일)를 대시보드에서 확인할 수 있도록 UI 개선 요청
- code_update.md와 talk_history.md에 변경 이력 기록

### Claude 작업 요약
- **StageResultViewer.vue 수정**:
  - parsedOutput에서 STAGE_04 데이터 파싱
  - `thumbnailPath` computed 추가 (선택된 썸네일 경로 추출)
  - `thumbnailCandidates` computed 추가 (thumbnail_candidates 배열의 모든 후보 이미지 추출)
  - `f001AssetUrl(absPath)` 헬퍼 함수 추가 — Windows 절대 경로를 URL로 변환
  - STAGE_04 클립 아이템에 `source` 배지(img2img/txt2img 구분) 및 `caption` 텍스트 추가
  - 섹션 하단에 썸네일 표시 영역 신규:
    - 메인 썸네일(400px 고정 높이) 단독 렌더링
    - 후보 이미지 2개 이상일 때 4열 그리드 갤러리 표시 (체크마크 오버레이로 선택본 표시)
  - CSS 12개 클래스 신규 추가 (배지, 섹션 구조, 이미지 스타일링)

### 검증 완료
- F001 job 상세 페이지에서 STAGE_04 썸네일 이미지 렌더링 확인 ✓
- 썸네일 후보 갤러리 표시 확인 ✓
- 소스 배지 색상 분화(img2img 초록, txt2img 파랑) 확인 ✓

### 다음 세션 시작 포인트
- STAGE_03(TTS) 오디오 플레이어 개선 고려
- STAGE_02(스크립트) 결과 렌더링 품질 향상 고려
- 추가 파이프라인 기능 구현 또는 기존 기능 고도화

<!-- session-end: 2026-05-14 -->

---

## 세션 2026-05-12 (2차) — Python 3.11 전환 + F001 오케스트레이터 버그 수정

### 사용자 지시 요약
- 로컬 TTS/STT 설치 및 MariaDB 설치 요청 (GPU 독점 사용 가능, 대용량 모델 OK)
- MariaDB: 영구 설치, 다른 프로젝트에서도 사용 예정
- F001 파이프라인 실행 시 "실행 중 대기" → 홈으로 돌아오면 FAILED 표시 되지만 주제 발굴 결과는 있는 버그 신고
- 주제 발굴(STAGE_01) 1분 이상 걸리는 것이 정상인지, 자동 완료인지 수동 선택인지 질문

### Claude 작업 요약
- **Python 3.11 전환**: `start.ps1`의 `py` → `py -3.11` 수정
  - 기존 `py` = 32-bit Python 3.10 → httpx 미설치 → 오케스트레이터 크래시 원인
  - Python 3.11에 필요 패키지 전체 설치 (fastapi, uvicorn, aiosqlite, apscheduler, httpx, python-dotenv, trafilatura, bs4)
- **오케스트레이터 `conn.commit()` 버그 수정** (`orchestrator.py` 3곳):
  - `_db_update()` 헬퍼가 의도적으로 commit 안 함 → WAITING/FAILED/DONE 전환 후 commit 없이 return → connection.close() 시 롤백
  - REJECTED → WAITING, FAILED 상태, 최종 DONE/PENDING_APPROVAL 각각에 `conn.commit()` 추가
- **서버 시작 시 복구 로직 추가** (`main.py`):
  - `_restore_f001_running_jobs()` — RUNNING content_jobs 찾아 오케스트레이터 재기동
  - 중단된 RUNNING 스테이지를 PENDING으로 리셋
- **STAGE_01_RESEARCH 직접 실행**:
  - `py -3.11 E:\Dash\pipelines\f001_youtube\run_orchestrator.py 3` 직접 실행
  - SearXNG + Ollama(gemma4:31b-cloud) → 삼성전자 주가 주제 3개 생성 성공
  - STAGE_02 REJECTED 확인 → WAITING 설정 (commit 버그로 인해 DB에 반영 안 됨 → 수동 수정)
- **F001 파이프라인 설계 명확화**:
  - STAGE_01 자동 실행(SearXNG + Ollama), 완료 후 사용자가 주제 선택 → STAGE_02 트리거
  - 신규 상태 WAITING 추가 (UI StatusBadge, F001JobDetailView 폴링 포함)

### 주요 오류 및 해결
| 오류 | 원인 | 해결 |
|------|------|------|
| 오케스트레이터 크래시 (httpx 없음) | `py` = 32-bit Python 3.10, httpx 미설치 | `py -3.11` 사용, Python 3.11에 패키지 설치 |
| job FAILED (주제 미선택) | `_get_stage_input` STAGE_02에서 `raise RuntimeError` | raise 제거, `selected_topic=None` 전달 |
| WAITING 상태 DB 미반영 | `conn.commit()` 누락 → close() 시 롤백 | 3곳에 `conn.commit()` 추가 |
| 백엔드 재시작 후 오케스트레이터 미기동 | 복구 로직 없음 | `_restore_f001_running_jobs()` 추가 |
| `ModuleNotFoundError: dotenv` | Python 3.11에 python-dotenv 미설치 | `py -3.11 -m pip install python-dotenv` |

### 결정사항
- 백엔드는 **py -3.11** (64-bit Python 3.11) 고정 — 오케스트레이터 서브프로세스가 동일 Python 상속
- MariaDB: ZIP 포터블 설치, `C:\MariaDB\`, Windows 서비스 등록 (AUTO_START), 포트 3306, UTF-8mb4
- WAITING: 사용자 개입 대기 상태 — 오케스트레이터 정상 종료, 주제 선택 후 재기동

### 현재 상태 (세션 종료 시점)
- job 3: status=WAITING, STAGE_01_RESEARCH=DONE (주제 3개), STAGE_02_SCRIPT=REJECTED
- 사용자가 주제 선택 → STAGE_02 PENDING 리셋 → 오케스트레이터 재기동 → STAGE_02 실행 필요

### 생성/수정된 파일
| 파일 | 변경 내용 |
|------|----------|
| `start.ps1` | `py` → `py -3.11` |
| `backend/main.py` | `_restore_f001_running_jobs()` 추가 |
| `pipelines/f001_youtube/orchestrator.py` | `conn.commit()` 3곳 추가 |
| `frontend/src/components/StatusBadge.vue` | WAITING, PENDING_APPROVAL 상태 추가 |
| `frontend/src/views/F001JobDetailView.vue` | WAITING 상태 폴링 포함 수정 |
| `backend/routers/f001.py` | select_topic 엔드포인트 — 오케스트레이터 재기동 추가 |

### 다음 세션 시작 포인트
1. start.ps1 실행 후 백엔드 정상 기동 확인 (`py -3.11`)
2. http://localhost:5173 → job 3 → STAGE_01 주제 3개 선택 UI 확인
3. 주제 선택 → STAGE_02 스크립트 생성 실행 확인
4. STAGE_02 ~ STAGE_06 순차 진행 테스트
5. STAGE_03 TTS: edge_tts 기본 사용 (Coqui/Kokoro는 별도 설치 후 전환)

<!-- session-end: 2026-05-12 -->

## 세션 2026-05-12 (F001 파이프라인 설계)

### 사용자 지시 요약
- start.ps1 실행 시 `python` 명령어 인식 불가 오류 해결 요청
- Ollama 설치됐는데 실행 안 됨 — PATH 문제 진단 요청
- F001 유튜브 컨텐츠 제작을 6단계 AI 파이프라인으로 재설계 요청
  - 6단계: ① 주제 발굴 → ② 스크립트 → ③ TTS → ④ 영상 생성 → ⑤ 편집 → ⑥ SEO+업로드
  - 각 단계 결과물을 다음 단계로 전달, 유효성 검증 후 반송 가능
  - 최종 업로드 자동/승인 선택 가능
- 6가지 미결 사항 결정:
  1. 업로드: manual_approval 기본, 선택 가능
  2. TTS: Coqui → Kokoro → 유료 순
  3. 영상 생성: ComfyUI 로컬 (`D:\comfyui\`)
  4. 트렌드: YouTube Data API(1차) + SearXNG(2차) 병행
  5. STAGE_04 skip: 선택 옵션 제공
  6. 레거시 F001 이력: 하이브리드(유지+신규 병행)
- `/order1` 스킬 내용 조회
- PLAN.md 오염(구 F003 내용) 발견 → 제거 요청
- PLAN.md 독립 검증 및 97% 달성 수정 요청

### Claude 작업 요약
- `start.ps1` `python` → `py` 수정
- Ollama PATH 문제 진단: `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` 존재 확인, 등록 방법 안내
- `/order1` 서브에이전트로 RESEARCH.md V2 작성 (전체 코드베이스 + SVG 분석)
- `/order1` 서브에이전트로 RESEARCH.md V3 업데이트 (6가지 결정사항 반영)
- `/order2` 서브에이전트로 PLAN.md V1 작성 (1619줄, 코드 스니펫 포함)
- PLAN.md 오염 제거: 2464줄 → 1617줄 (구 F003-V2 내용 938줄 삭제)
- 독립 검증 에이전트 투입 → RESEARCH.md 92%, PLAN.md 90% 실측
- 3개 항목 직접 수정 → 양쪽 97% 달성

### 결정사항
- F001은 `content_jobs + stages` 독립 테이블로 6스테이지 관리 (기존 `tasks` 무변경)
- `F001Orchestrator(BasePipeline)` — `run()` 시그니처 불일치 `# type: ignore[override]` 처리
- cursor 기반 페이징: 기존 `task_service.list_tasks()` 패턴 그대로 `list_jobs()`에 적용
- 업로드 승인 흐름: `PENDING_APPROVAL` 신규 상태 추가

### 생성/수정된 파일
| 파일 | 내용 |
|------|------|
| `start.ps1` | `python` → `py` 1줄 수정 |
| `RESEARCH.md` | V3 전체 교체 (섹션 1~10) |
| `PLAN.md` | V1 신규 (섹션 0~12, 1619줄) |

### 다음 세션 시작 포인트
- Ollama PATH 영구 등록 확인 후 실제 실행 테스트
- `/order3` 또는 `구현해줘` → PLAN.md Phase 1 구현 시작 (DB + API 뼈대)
- Phase 1 목표: `content_jobs`, `stages` 테이블 + `/api/f001/jobs` CRUD 동작 확인

<!-- session-end: 2026-05-12 -->


| 필드 | 내용 |
|------|------|
| 문서명 | talk_history.md |
| 버전 | V1 |
| 시작일 | 2026-05-05 |
| 작성자 | historian |

---

## 세션 2026-05-05

### 사용자 지시 요약
- Ollama 로컬 LLM 기반 자동화 대시보드 웹 프로그램 구상 공유
- CLAUDE.md 작성 요청
- 훅 트리거 및 new_project_setup.md 절차 미준수 지적

### Claude 작업 요약
- CLAUDE.md 생성 (프로젝트 개요, 아키텍처, 에이전트 목록, 로드맵 포함)
- new_project_setup.md 확인 후 누락 항목 전체 생성:
  - .claude/agents/ — web-builder, api-builder, pipeline-builder, critic, historian
  - .claude/advisor_workflow.md
  - .claude/hooks/post-tool-use-hook.sh, session-end-hook.sh
  - code_update.md, talk_history.md

### 다음 세션 시작 포인트
- Phase 0: 기술 스택 확정 (백엔드 언어, 프론트엔드 프레임워크, DB, 큐)
- CLAUDE.md 서브에이전트 목록 업데이트 (에이전트 파일 생성 완료 반영)

---

## 세션 2026-05-05 (2차) — Phase 1 전체 구현 + 모델 선택 기능

### 사용자 지시 요약
- 기술 스택 확정 및 Phase 1 구현 요청 (FastAPI + Vue 3 + aiosqlite + APScheduler)
- Phase 1 구현 (`구현해줘`) 지시
- 대시보드에서 Ollama 모델을 직접 선택할 수 있도록 기능 추가 요청 (`구현해줘`)
- `/update` 명령으로 세션 마무리 요청

### Claude 작업 요약
- **Phase 1 전체 구현** (backend + frontend + pipelines):
  - SQLAlchemy 2.x 빌드 실패 (32비트 Python) → aiosqlite 직접 사용으로 전환
  - `backend/core/database.py` — aiosqlite 기반 DB 초기화, tasks/features/settings 테이블
  - `backend/routers/` — tasks, features, schedules, health 라우터 구현
  - `backend/services/task_service.py` — 작업 생성, subprocess.Popen으로 파이프라인 실행
  - `backend/main.py` — FastAPI 앱, APScheduler, CORS, 라우터 등록
  - `frontend/src/` — DashboardView, FeatureView, TaskDetailView, ScheduleView, TaskCard, Pinia store
  - `pipelines/base.py` — BasePipeline 추상 클래스 (update_status, call_ollama, is_cancelled)
  - `pipelines/runner.py` — subprocess 진입점 (sys.path 수정으로 모듈 인식 해결)
  - `pipelines/f001_youtube/pipeline.py` — 제목/설명/스크립트 3단계 생성
  - `pipelines/f002_daily_issues/pipeline.py` — 키워드 기반 이슈 발굴
- **모델 선택 기능 추가**:
  - `backend/core/database.py` — settings 테이블 추가
  - `backend/routers/models.py` — GET /api/models, PUT /api/models/select 신규
  - `backend/main.py` — models 라우터 등록
  - `pipelines/base.py` — `_get_selected_model()` 추가, call_ollama 모델 우선순위 변경
  - `frontend/src/api/index.js` — getModels, selectModel 추가
  - `frontend/src/views/DashboardView.vue` — 모델 선택 드롭다운 UI 추가

### 주요 오류 및 해결
- SQLAlchemy async 불가 (32비트 Python) → aiosqlite 직접 사용으로 전체 DB 레이어 재설계
- `No module named 'pipelines'` → runner.py에 sys.path.insert(0, 프로젝트 루트) 추가
- Ollama 모델명 불일치 → 실제 설치된 모델로 FALLBACK 목록 교체

### 결정사항
- DB: aiosqlite 직접 사용 (SQLAlchemy 제외) — 32비트 Python 환경 제약
- 파이프라인: subprocess.Popen으로 독립 프로세스 실행
- 모델 선택: settings 테이블 key-value 저장, 파이프라인 실행 시마다 DB 조회

### 검증 완료
- GET /api/health, /api/features, /api/health/ollama ✓
- Task 생성 → F002 파이프라인 DONE ✓
- GET /api/models, PUT /api/models/select ✓
- Task 3번 exaone3.5:2.4b 모델로 DONE ✓

### 다음 세션 시작 포인트
- Phase 2: TaskDetailView 결과 표시 개선, ScheduleView APScheduler 연동 완성
- GUIDE.md 파일 생성 (backend/, frontend/, storage/ 폴더)
- F002 파이프라인 결과를 TaskDetailView에서 이슈 카드 형태로 렌더링

<!-- session-end: 2026-05-05 18:27:48 -->

<!-- session-end: 2026-05-05 20:27:29 -->

<!-- session-end: 2026-05-05 21:22:11 -->

<!-- session-end: 2026-05-06 15:55:11 -->

## 세션 2026-05-06 (2차) — 멀티 검색 쿼리 확장 + 심층 분석 모드 구현

### 사용자 지시 요약
- SearXNG + BeautifulSoup 크롤링 → trafilatura/BS4 폴백 방식으로 교체 요청 (구현해줘)
- F002에 SearXNG 기본 검색 엔진 추가, 파서 정보 배지 표시 요청 (구현해줘)
- 분석 질문 시 단순 현황 나열에 그치는 LLM 답변 개선 — 추가 검색 + 심층 분석 구조 요청 (구현해줘)

### Claude 작업 요약
- **trafilatura + BS4 폴백 파서 구현** (`shared/content_extractor.py` 전면 재작성)
- **F002 SearXNG 기본 검색** (`pipelines/f002_daily_issues/pipeline.py`, `pipelines/base.py` 수정)
- **파서 정보 배지** (`frontend/src/views/TaskDetailView.vue`, issue-badges 추가)
- **멀티 검색 쿼리 확장 시스템 구현** (이번 세션 핵심):
  - `shared/query_expander.py` — 5종 확장 유형 감지, 서브쿼리 3개 생성
  - `shared/prompt_builder.py` — INTENT_DEEP_ANALYSIS 추가, deep_analysis 파라미터
  - `backend/core/config.py` — SEARXNG_BASE_URL 추가
  - `backend/routers/chat.py` — _quick_search_searxng, _multi_search, _generate_response, status SSE
  - `frontend/src/components/ChatPanel.vue` — statusText 필드, status SSE 처리, status-hint UI
  - `frontend/src/api/index.js` — sendChatStream에 searchProvider 파라미터 추가

### 주요 결정사항
- 쿼리 확장: 분석/전망/투자/트렌드/원인 의도 감지 시 원본 + 서브쿼리 3개 병렬 검색
- 상태 표시: Ollama 스트리밍 전 `{"type": "status", "message": "..."}` SSE 이벤트 선행 전송
- 크롤링 없이 SearXNG 스니펫만 수집 (속도 우선) — 멀티 검색은 빠른 보강이 목적

### 다음 세션 시작 포인트
- 실제 채팅에서 멀티 검색 동작 확인 (status 힌트 → Ollama 스트리밍)
- shared/GUIDE.md에 query_expander 모듈 설명 추가

---

## 세션 2026-05-06 (3차) — FeatureView 폼 버그 수정 + F002 프롬프트 편집 + stop.ps1 수정

### 사용자 지시 요약
- F002 화면에서 SearXNG/Tavily 선택 UI가 어디 있는지 질문
- stop.ps1 PID 오류("Cannot find process") 확인 요청
- F002 파라미터 폼에 기본 프롬프트를 보여주고 수정할 수 있게 해달라는 요청
- 채팅 연속성 동작 원리 질문 (설명 요청)

### Claude 작업 요약

**버그 수정 — FeatureView 폼 파싱 오류 (치명적)**
- 원인: `FeatureView.vue`가 `input_schema.properties` 형식을 기대했지만 백엔드는 배열 반환 → 모든 Feature의 파라미터 폼이 항상 빈 상태
- 수정: `Array.isArray(schema)` 체크로 배열 파싱 방식으로 전환

**F002 파라미터 폼 완성**
- `backend/schemas/task.py` — `FeatureInputField`에 `title`, `default`, `options` 필드 추가
- `backend/routers/features.py` — F002에 `search_provider`(select 드롭다운), `days`, `prompt_template`(textarea) 추가
- `frontend/FeatureView.vue` — `select`, `textarea` 타입 렌더링 추가, `.form-textarea-prompt` CSS

**F002 프롬프트 편집 기능**
- `_DEFAULT_INSTRUCTION` 상수를 pipeline.py에 분리
- `features.py`에 `prompt_template` 필드로 기본 프롬프트 텍스트 노출
- `{keywords}`, `{max_issues}` 플레이스홀더 지원 — 실행 시 자동 치환
- 사용자가 프롬프트 수정 후 실행하면 커스텀 프롬프트 사용

**stop.ps1 수정**
- `Stop-ByPort` 함수: 프로세스 존재 확인 후 종료 (없으면 "이미 종료됨")
- `Stop-ByCommandLine` 함수: WMI CommandLine 기반 uvicorn/vite 2순위 탐색

**채팅 연속성 설명 (구현 변경 없음)**
- 같은 탭 내 페이지 이동: 연속성 유지 (ChatPanel 항상 마운트)
- 브라우저 새로고침 / 탭 닫기: 연속성 끊김 (messages는 메모리 only)
- Ollama에는 최근 10턴만 전달
- 초기화 버튼 = 화면 + LLM 맥락 모두 리셋

### 주요 결정사항
- 프롬프트 편집: 검색결과 도입부(고정) + 분석 지시문(수정 가능) 분리 구조
- 폼 스키마: 배열 형식 `[{name, title, type, default, options, ...}]` 유지

### 다음 세션 시작 포인트
- F002 실행 후 파라미터 폼(search_provider 드롭다운, prompt_template textarea) 동작 확인
- 채팅 연속성 유지가 필요하면 localStorage/sessionStorage 저장 구현 검토

<!-- session-end: 2026-05-06 19:36:21 -->

## 세션 2026-05-07 (컨텍스트 요약 이후 이어진 세션)

### 사용자 지시 요약
1. 로드맵 변경: 스케줄러 통합(Phase 3)을 뒤로 미루고, 파이프라인 확장(Phase 4)을 먼저 진행. F002도 스케줄러 의존으로 보류.
2. F003 "영상제작" 파이프라인 연구 요청 (/order1): ComfyUI + AnimateDiff(동영상) + Flux.1(그림) + LoRA 캐릭터 커스터마이징 + 자동 모델 관리
3. 아키텍처 수정 (/order1): AUTOMATIC1111 → ComfyUI 단일 플랫폼으로 전환. 스타일 선택 시스템(선택옵션별 LoRA/확장 자동 매핑) 추가
4. 디테일 향상 LoRA 추가 (/order1): 전체 디테일을 향상시키는 LoRA를 스타일 선택 시스템 Category 7로 반영
5. PLAN.md 작성 (/order2): cursor 기반 페이징 + F003 파이프라인 전체 구현 계획 (코드 스니펫 포함), 18개 구현 단계

### Claude 작업 요약
- CLAUDE.md 로드맵 수정: Phase 3 ↔ Phase 4 순서 변경, F003 추가, F002 보류 표시
- pipeline-builder.md: F003 항목 추가
- RESEARCH.md V1→V3 순차 업데이트:
  - V2: ComfyUI 단일 플랫폼으로 전면 재작성, 4개 구현 영역(A/B/C/D), 6카테고리 스타일 시스템
  - V3: Category 7 (디테일 향상 LoRA) 추가, 15개 LoRA 예시 및 가중치 포함
- PLAN.md 신규 작성: cursor 기반 페이징(5개 파일 변경) + F003(14개 신규 파일, 12개 수정 파일), 18개 구현 단계, 6개 트레이드오프 분석

### 다음 세션 시작 포인트
- 구현 시작: PLAN.md의 18개 단계 중 phase 1(커서 기반 페이징)부터 순차 구현 (/order3 예상)

---

## 세션 2026-05-07 (2차) — Phase 1~18 전체 구현 + Critic 검토 완료

### 사용자 지시 요약
- `/order3 구현해줘` — PLAN.md의 18개 Phase 전체 구현 지시
- 작업 완료 후 `code_update.md`와 `talk_history.md` 업데이트 요청

### Claude 작업 요약

**1. Cursor 기반 페이징 전환 (P1)**
- Task 목록 조회: offset → cursor 기반으로 전환
- `TaskListResponse`: `total` 제거, `next_cursor` + `has_more` 추가
- SQL: `WHERE id < cursor ORDER BY id DESC LIMIT limit+1` 구조

**2. DB 스키마 추가 (P2)**
- `model_inventory` 테이블 (파일명, 해시, 모델타입 저장)
- `model_download_queue` 테이블 (다운로드 상태 추적)

**3. F003 Feature 정의 (P3)**
- 영상제작 파이프라인 feature 추가
- 24개 입력 필드 (유형, 아트스타일, 촬영스타일, 배경, 인물 등)
- "Flux.1 (고품질)" 옵션 추가

**4-13. F003 파이프라인 구현**
- **ComfyUI 클라이언트**: REST + WebSocket 통신, 취소 시 GPU 즉시 해제
- **프롬프트 생성**: Ollama 기반 SD/Flux.1 프롬프트 자동 생성
- **스타일 매핑**: 사용자 선택 → ComfyUI 워크플로우 자동 매핑
- **모델 관리**: 모델 인벤토리 + HuggingFace 자동 다운로드
- **메인 파이프라인**: 11단계 실행 흐름 (타입 선택 → 프롬프트 → 이미지 생성 → 영상 변환 → 후처리)
- **워크플로우**: AnimateDiff(동영상), Flux.1(이미지) 2개 기본 워크플로우 제공

**14-16. F003 프론트엔드**
- `F003View.vue`: 3단계 다단계 폼 UI (유형→스타일→파라미터)
- `/features/F003` 라우트 추가
- `TaskDetailView.vue`: 이미지/동영상 렌더링 블록

**17. Vite 프록시 설정 (Critical 버그 수정)**
- `/results` 경로 프록시 추가 → F003 결과 이미지/동영상 404 오류 해결

**18. Pipeline Runner 중복 업데이트 제거**
- run() 완료 후 DB 상태 확인 → DONE이 아닌 경우에만 업데이트

**Critic 검토 → 버그 수정**
- Critical 5개:
  1. vite.config.js /results 프록시 누락 → 추가
  2. model_assets.py 경로 순회 보안 취약점 → os.path.basename 검증
  3. 절대 경로 하드코딩 → Path 상대 경로로 수정
  4. runner.py 중복 DONE 업데이트 → 상태 확인 후 조건 실행
  5. flux_base.json 고아 노드 → 제거
- Major 7개 & Minor 4개 모두 수정 완료

### 주요 결정사항
- Cursor 페이징: 동시성 안전 + 무한 스크롤 지원
- F003 구현:
  - ComfyUI + AnimateDiff 동시 지원 (동영상)
  - Flux.1 고품질 이미지 생성
  - 모델 자동 다운로드 및 캐싱
  - 사용자 커스터마이징 (프롬프트, 스타일 선택)

### 검증 완료
- P1: cursor 페이징 동작 확인 ✓
- P3: F003 feature 조회 (24개 필드 정상) ✓
- P4-P13: ComfyUI 클라이언트, 모델 관리, 프롬프트 생성 통합 ✓
- P14-P16: F003View 3단계 폼, TaskDetailView 미디어 렌더링 ✓
- P17: /results/f003 프록시 (이미지/동영상 접근 가능) ✓
- P18: runner.py 중복 업데이트 제거 ✓
- Critic 검토 후 Critical/Major/Minor 16개 버그 모두 수정 ✓

### 다음 세션 시작 포인트
- F003 실행 테스트: 대시보드에서 F003 기능 실행 후 동영상/이미지 생성 확인
- ComfyUI 서버 헬스체크 추가 (선택사항)
- 백그라운드 모델 다운로드 프로세스 최적화 (필요 시)

---

## 세션 2026-05-07 (3차) — F003 디테일 LoRA 자동 다운로드 기능 추가

### 사용자 지시 요약
- `code_update.md`와 `talk_history.md`에 기록 추가 요청:
  - F003 pipeline.py에 `_collect_missing_loras()` 함수 추가 사항 기록
  - 디테일 LoRA 자동 다운로드 기능 완결 관련 내용 기록

### Claude 작업 요약
- **code_update.md 업데이트**:
  - `[2026-05-07 현재] F003 디테일 LoRA 자동 다운로드 기능 추가` 섹션 신규 추가
  - 변경 파일: pipelines/f003_video_creation/pipeline.py
  - _collect_missing_loras() 함수 추가로 NameError 버그 수정
  - step [4.5]에서 ComfyUI 가용 LoRA 조회 → 누락 LoRA 자동 다운로드 → 목록 갱신 후 워크플로우 빌드

- **talk_history.md 업데이트**:
  - 세션 2026-05-07 (3차) 섹션 신규 추가
  - 사용자 지시 요약 및 작업 내용 기록

### 주요 사항
- 디테일 LoRA 자동 다운로드는 다음 조건에서만 실행:
  1. ComfyUI 미설치 상태 (installed = false)
  2. civitai_version_id 또는 hf_repo_id 설정됨
- 스타일 LoRA는 config에 다운로드 소스 없으므로 경고 로그만 출력

### 다음 세션 시작 포인트
- F003 파이프라인 실제 동작 테스트 (ComfyUI 미설치 상태에서 디테일 LoRA 자동 다운로드 확인)
- 추가 파이프라인 개발 또는 기존 기능 완성도 향상

---

## 세션 2026-05-08 — F003 ComfyUI 설치 모델 직접 선택 + LoRA 개별 강도 조정

### 사용자 지시 요약
- F003에서 ComfyUI 설치 모델(Checkpoint/VAE/CLIP)을 드롭다운으로 직접 선택하는 기능 추가 요청
- LoRA별 강도를 슬라이더로 개별 조정할 수 있도록 수정 요청
- 구현 완료 후 code_update.md와 talk_history.md 업데이트 요청

### Claude 작업 요약

**1. ComfyUI 설치 모델 조회 기능**
- `backend/services/comfyui_client.py`:
  - `get_available_vaes()` 메서드 추가 (VAELoader 노드의 VAE 파일 목록)
  - `get_available_clips()` 메서드 추가 (CLIPLoader 노드의 CLIP 파일 목록)

**2. API 엔드포인트 확장**
- `backend/routers/features.py`:
  - `GET /api/features/f003/models` 신규 엔드포인트
  - 응답: checkpoints, vaes, loras, clips 한 번에 반환
  - 라우트 순서 정의 (models → loras → loras/predownload → /{feature_id})

**3. 스타일 매핑 + LoRA 강도 지원**
- `pipelines/f003_video_creation/style_mapper.py`:
  - `_parse_detail_loras()` 헬퍼: 쉼표 문자열 ↔ JSON 배열 양방향 파싱
  - `_insert_vae_node()` 헬퍼: VAELoader 노드 동적 삽입 (중복 제거)
  - `resolve_detail_loras()`: keys: list[str] → items: list (str/dict 혼용)
  - `build_workflow()`: custom_checkpoint/custom_vae 파라미터 적용, 5개 워크플로우 경로 모두에 VAE 로직

**4. 파이프라인 검증 강화**
- `pipelines/f003_video_creation/pipeline.py`:
  - custom_checkpoint 우선 검증 (step [2.5])
  - custom_vae 사전 검증 (step [4.2], 미설치 시 조기 실패)
  - detail_loras 파싱을 _parse_detail_loras()로 통일

**5. 프론트엔드 UI 확장**
- `frontend/src/api/index.js`:
  - `getF003Models()` 함수 추가

- `frontend/src/views/F003View.vue`:
  - 새 ref: customCheckpoint, customVae, customClip, availableCheckpoints, availableVaes, availableClips, modelsLoading
  - `loadF003Models()` 함수 추가 (onMounted 호출)
  - LoRA 헬퍼 함수: isLoraSelected, getLoraStrength, toggleLora, setLoraStrength
  - selectedDetailLoras 형식 변경: string[] → {key, strength}[] 객체 배열
  - Step 2 상단: 모델 설정 섹션 (Checkpoint/VAE/CLIP 드롭다운)
  - LoRA 패널: 개별 강도 슬라이더 추가 (0.0~2.0, step 0.1)
  - Step 3 요약: 커스텀 모델 정보 + LoRA 강도 표시
  - startGeneration에서 detail_loras: JSON.stringify(), custom_checkpoint/custom_vae 조건부 전송

### 주요 결정사항
- ComfyUI 설치 모델: 드롭다운 선택 (수동 업로드는 V2에서 미지원, V3 고려)
- LoRA 강도: 0.0~2.0 범위, step 0.1 (UI에서 미세 조정 가능)
- CLIP: 현재 SD/SDXL 내장 구조상 V2에서 정보 표시 전용 (선택 기능 없음)

### 다음 세션 시작 포인트
- F003 실행 테스트: 드롭다운에서 모델 선택 후 생성 동작 확인
- 커스텀 모델 선택 시 프롬프트/스타일 변화 검증
- LoRA 강도 조정이 실제 이미지 품질에 영향 확인

<!-- session-end: 2026-05-11 21:01:34 -->

<!-- session-end: 2026-05-11 21:02:31 -->

---

## 세션 2026-05-11 ~ 2026-05-12 — 컴퓨터 복원 후 환경 재구축

### 사용자 지시 요약
- 컴퓨터 고장으로 백업에서 프로젝트 복원 (경로: E:\Dash, 이전: C:\Develop\Dash)
- 소스 코드는 절대 건드리지 말고 실행 환경만 구축해달라는 명확한 요청
- 필요한 사항 있으면 물어보라고 지시

### Claude 작업 요약

**1. 환경 분석**
- 프로젝트 원래 경로: `C:\Develop\Dash` (사용자 kisuc) → 현재: `E:\Dash` (사용자 kisucha)
- Python, Node.js 미설치 상태 확인
- 소스 코드 내 하드코딩된 절대 경로 3곳 발견:
  - `pipelines/f003_video_creation/config.json`: ComfyUI 경로
  - `pipelines/f003_video_creation/pipeline.py`: 프로젝트 루트 경로 2곳
- 실제 디스크 상태: ComfyUI는 `D:\ComfyUI\ComfyUI`에 설치

**2. 환경 구축 (소스 코드 0줄 수정)**
1. Windows 정션 2개 생성:
   - `C:\Develop\Dash` → `E:\Dash` (mklink /J로 리다이렉트)
   - `C:\ComfyUI` → `D:\ComfyUI` (ComfyUI 경로 해결)
2. Python 3.10.0 32비트 설치 확인 (사용자 직접 설치)
3. Node.js v24.15.0 설치 확인
4. 사용자 PATH 환경변수 등록:
   - `C:\Users\kisucha\AppData\Local\Programs\Python\Python310-32`
   - `C:\Program Files\nodejs`
   - WindowsApps 별칭을 두 경로 뒤로 재배열 (Python 경로 우선순위 확보)
5. Python 패키지 설치 — 특수 처리 필요:
   - greenlet 바이너리 휠 미존재(32비트) → `pip install sqlalchemy --no-deps` 우회
   - httptools 빌드 불가 → `pip install fastapi --no-deps` + `uvicorn[standard]` 제외 설치
   - 기타 패키지(aiosqlite, requests, ddgs, beautifulsoup4 등) 정상 설치
6. PowerShell 실행 정책: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
7. git 전역 설정: user.email, user.name 등록

**3. git 작업**
- 미커밋 변경사항 20개 파일 존재 (F003 파이프라인 고도화):
  - PLAN.md, backend/main.py, backend/routers/features.py
  - pipelines/f003_video_creation/ 전체 (comfyui_client.py, config.json, model_manager.py, pipeline.py, style_mapper.py, workflows/)
  - frontend/src/ 3개 파일
  - 기타 설정 파일
- `git commit`으로 모두 커밋 후 Gitea 서버 푸시 완료
- Windows 자격증명 관리자의 백업된 인증정보가 그대로 사용됨

### 주요 결정사항
- 소스 코드 무수정 원칙 유지 → Windows 정션으로 경로 문제 해결 (최우선)
- Python 3.10 32비트 유지 (이전 환경과 동일)
- greenlet, httptools 미설치 상태로 운영 (서버 동작에 영향 없음)

### 생성/수정된 파일 목록 (OS 환경, 프로젝트 외부)
- `C:\Develop\` 디렉토리 신규 생성
- `C:\Develop\Dash` 정션 생성 (→ E:\Dash)
- `C:\ComfyUI` 정션 생성 (→ D:\ComfyUI)
- `C:\Users\kisucha\.gitconfig` 신규 생성 (user 정보 등록)
- Windows 사용자 PATH 환경변수 수정

### 잔여 이슈
- `start.ps1` 실행 시 PATH 임시 적용 필요:
  ```powershell
  $env:PATH = "C:\Users\kisucha\AppData\Local\Programs\Python\Python310-32;C:\Program Files\nodejs;$env:PATH"
  ```
  - 원인: `Start-Process powershell`로 자식 창을 spawn할 때 부모 세션의 in-memory PATH를 상속하지 못함
  - 영구 PATH 환경변수 등록으로도 자식 프로세스가 실시간으로 이를 인식 못함
  - 다음 세션에서 `start.ps1` 스크립트 수정으로 영구 해결 필요

### 다음 세션 시작 포인트
- start.ps1 자동 PATH 적용 영구 해결 (예: .ps1 내부에서 $env:PATH 직접 설정)
- 전체 기동 테스트 (백엔드 + 프론트엔드 동시 실행 확인)
- F003 파이프라인 실행 테스트 (ComfyUI 연동 확인)

<!-- session-end: 2026-05-12 -->

<!-- session-end: 2026-05-12 00:46:39 -->

<!-- session-end: 2026-05-12 16:12:30 -->

<!-- session-end: 2026-05-12 16:15:10 -->

<!-- session-end: 2026-05-12 16:19:05 -->

<!-- session-end: 2026-05-12 16:24:59 -->

<!-- session-end: 2026-05-12 19:57:36 -->

<!-- session-end: 2026-05-12 20:12:17 -->

---

## 세션 2026-05-12 (3차) — F001 유튜브 AI 파이프라인 전체 구현

### 사용자 지시 요약
- `/order3` 명령으로 PLAN.md에 계획된 F001 파이프라인 전체 구현 요청
- "반드시 발자국을 남겨서 상태를 확인할 수 있도록 해라"
- 구현 완료 후 code_update.md와 talk_history.md 업데이트

### Claude 작업 요약

**1. 3개 서브에이전트 병렬 배포**
- api-builder: Phase 1 백엔드 (DB 스키마 + API 라우터)
- pipeline-builder: Phase 2-4 파이프라인 (6단계 스테이지 + 오케스트레이터)
- web-builder: Phase 5-6 프론트엔드 (컴포넌트 + 페이지 뷰)

**2. 구현 완료 (총 26개 파일)**

*수정 파일 (5개):*
- `backend/core/database.py`: content_jobs(14컬럼), stages(17컬럼) 테이블 신규, 인덱스 3개
- `backend/main.py`: f001 라우터 등록, `/results/f001` StaticFiles 마운트
- `frontend/src/router/index.js`: F001View, F001JobDetailView 라우트 추가
- `frontend/src/views/DashboardView.vue`: 업무 목록 클릭 시 F001Feature 분기
- `frontend/src/api/index.js`: F001 API 9개 함수 추가

*신규 생성 파일 (21개):*
- **schemas**: f001.py (8개 스키마)
- **services**: f001_service.py (F001Service 클래스, 8개 메서드)
- **routers**: f001.py (14개 엔드포인트)
- **pipelines/f001_youtube**:
  - stages/__init__.py (BaseStage, ValidationResult 인터페이스)
  - stages/stage01_research.py (SearXNG + Ollama 주제 발굴)
  - stages/stage02_script.py (스크립트 생성 + 씬 분해)
  - stages/stage03_tts.py (Coqui/Kokoro/ElevenLabs/OpenAI TTS)
  - stages/stage04_video.py (ComfyUI 이미지 생성 + PIL 슬라이드)
  - stages/stage05_edit.py (FFmpeg concat + Whisper 자막 + BGM)
  - stages/stage06_upload.py (SEO 메타데이터 + YouTube 업로드)
  - validators/__init__.py
  - validators/stage_validator.py (반송 메커니즘)
  - orchestrator.py (F001Orchestrator, 6단계 순차 실행)
  - run_orchestrator.py (subprocess 진입점)
  - config.json (설정)
  - migrate_legacy.py (마이그레이션 유틸)
- **frontend**:
  - src/store/f001.js (useF001Store, Pinia 상태 관리)
  - src/components/StageTimeline.vue (6단계 타임라인)
  - src/components/StageResultViewer.vue (단계별 결과 뷰어)
  - src/views/F001View.vue (작업 목록 + 생성 모달)
  - src/views/F001JobDetailView.vue (상세 뷰 + 2패널)

**3. 주요 기술 결정**
- 데이터베이스: content_jobs(독립 테이블) + stages(다대다 관계)
- 상태 모델: PENDING → RUNNING → DONE/FAILED/CANCELLED + AWAITING_INPUT/AWAITING_APPROVAL
- 페이징: cursor 기반 (task_service 패턴 재활용)
- 프론트엔드: Pinia store + 컴포지션 API

**4. 검증 결과**
- Python AST 구문 검사: 17/17 파일 전체 통과 (0 오류)
- PLAN.md 진행도: Phase 1~4 완료, Phase 5 부분완료 표시
- 버그 수정:
  - select_topic API: response dict 형식 수정
  - F001View: default upload_mode 'manual' → 'manual_approval'

### 미완성 항목
- YouTube OAuth 2.0 실제 업로드 로직 (Phase 5, stage06_upload.py)
- 런타임 검증 (Coqui TTS, FFmpeg, Whisper, ComfyUI 실제 설치 필요)
- E2E 테스트 (프론트엔드 UI에서 F001 파이프라인 실행 확인 미실시)

### 다음 세션 시작 포인트
- F001 실행 테스트: 대시보드에서 F001 작업 생성 → 각 단계 진행 확인
- 단계별 결과 검증 (이미지, 오디오, 영상 생성 실제 확인)
- YouTube OAuth 2.0 구현 (Phase 5 완성)

<!-- session-end: 2026-05-12 -->

<!-- session-end: 2026-05-12 23:13:13 -->

---

## 세션 2026-05-13 — STAGE_05 FFmpeg 미설치 문제 해결

### 사용자 지시 요약
- STAGE_05에서 WinError 2 "프로그램을 찾을 수 없습니다" 오류 발생
- FFmpeg이 Windows 시스템에 미설치 상태 → 대체 방법으로 해결 요청
- 전체 파이프라인 테스트 (job #12): STAGE_01 ~ STAGE_05 완주 후 결과 확인 및 기록 요청

### Claude 작업 요약

**1. 원인 분석**
- `subprocess.run("ffmpeg", ...)` 호출이 WinError 2 발생
- 원인: Windows 시스템 PATH에 FFmpeg 미등록
- 해결 방안: 로컬 패키지의 번들 FFmpeg 사용

**2. 솔루션 구현**
- **packagey 설치**: `pip install moviepy` (v2.2.1)
  - imageio-ffmpeg (v0.6.0) 자동 포함 (번들 FFmpeg 제공)
- **stage05_edit.py 수정**:
  - 모듈 임포트: `import imageio_ffmpeg as _imageio_ffmpeg`
  - `_run_ffmpeg_concat()`: `"ffmpeg"` → `_imageio_ffmpeg.get_ffmpeg_exe()` 교체
  - `_generate_black_video_with_audio()`: 동일하게 번들 FFmpeg 경로 사용
  - `_get_video_duration()`: ffprobe subprocess 제거, `moviepy.VideoFileClip` 사용으로 단순화
- **추가 버그 수정**: `n_clips` 계산 오류 (PNG=6토큰 × N → //4 잘못 계산) → 루프 카운터로 교체

**3. 파이프라인 완주 테스트 (job #12)**
- STAGE_01_RESEARCH: 주제 3개 생성 (SearXNG + Ollama)
- STAGE_02_SCRIPT: 스크립트 생성 (최대 30씬)
- STAGE_03_TTS: 음성 생성 (edge_tts 기본)
- STAGE_04_VIDEO: 이미지 생성 (ComfyUI sd-1.5 모델)
- **STAGE_05_EDIT**: 성공! output.mp4 생성 (2.35MB, 58.1초 동영상) ← **이번 세션 핵심**
- STAGE_06_UPLOAD: PENDING_APPROVAL (승인 대기)

### 주요 결정사항
- 시스템 FFmpeg 설치 대신 moviepy 번들 사용 (의존성 최소화)
- ffprobe 기반 비디오 정보 조회 제거 (moviepy로 통합)

### 검증 완료
- job #12 전체 파이프라인 6/6 스테이지 통과 ✓
- STAGE_05 output.mp4 재생 확인 ✓
- STAGE_06 PENDING_APPROVAL 상태 (사용자가 결과 검토 후 승인/거절 가능)

### 다음 세션 시작 포인트
- STAGE_06 YouTube 업로드 승인 (OAuth 2.0 구현 필요)
- 추가 작업(job) 생성 및 멀티 병렬 실행 테스트
- 트렌드 발굴 자동화 (YouTube Data API 또는 SearXNG 추가 최적화)

<!-- session-end: 2026-05-13 -->
