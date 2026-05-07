# Dash 변경 이력

| 필드 | 내용 |
|------|------|
| 문서명 | code_update.md |
| 버전 | V1 |
| 시작일 | 2026-05-05 |
| 작성자 | historian |

---

## [2026-05-05] 레이아웃 완전 수정 — body scroll 차단, Ollama 단순화, 루트 경로 추가

- 변경 내용:
  - `frontend/src/style.css` — `body { overflow: hidden }` 추가, `#app { height: 100% }` (min-height → height)
  - `frontend/src/App.vue` CSS — `#app-wrapper { height: 100% }` (100vh → 100%로 #app 높이 상속)
  - `frontend/src/views/DashboardView.vue` — `checkOllamaHealth` 완전 제거, `loadModels()`만으로 Ollama 상태 결정
  - `backend/main.py` — 루트 경로 `/` 추가 (307 리다이렉트 → /docs)
- 변경 이유:
  1. `min-height: 100%`를 가진 `#app` + body scroll이 root cause — `body { overflow: hidden }`이 유일한 확실한 차단 방법
  2. `checkOllamaHealth`와 `loadModels`가 비동기 경쟁 상태에서 올라마 status를 덮어쓰는 문제 제거
  3. localhost:8000 접속 시 Not Found 응답 개선

---

## [2026-05-05] CSS 레이아웃 근본 수정 — 빈 화면·스크롤 연동·포커스 4종 수정

- 변경 내용:
  - `frontend/src/App.vue` CSS — `#app-wrapper`: `min-height:100vh` → `height:100vh; overflow:hidden` (window 스크롤 차단); `.body-layout`: `height:calc(100vh-56px)` 제거, `min-height:0` 추가 (패널 독립 스크롤 활성화)
  - `frontend/src/App.vue` script — `onContentClick()` 추가: 왼쪽 패널의 비인터랙티브 영역 클릭 시 채팅창 포커스 복귀; `:key="route.path"` 제거 (이전 회귀 수정)
  - `반복실수.md` — ERR-006 원인 수정 (RouterView :key → CSS flex 스크롤 격리 실패)
- 변경 이유:
  1. (빈 화면) window 스크롤이 이전 페이지 위치에 고정되어 콘텐츠가 뷰포트 위로 사라짐 → CSS로 해결
  2. (스크롤 연동) window 레벨 스크롤로 양 패널이 함께 움직임 → height:100vh+overflow:hidden으로 해결
  3. (포커스) 왼쪽 클릭 후 채팅창 포커스 손실 → onContentClick으로 복귀
  4. (Ollama 확인 중) CSS 버그로 배너가 스크롤 위쪽에 있어 보이지 않았던 것 → CSS 수정으로 해결

---

## [2026-05-05] 3대 버그 수정 — RouterView 재마운트, Ollama 상태 덮어쓰기, 포커스 전달

- 변경 내용:
  - `frontend/src/App.vue` — `<RouterView :key="route.path" />` 추가로 라우트마다 강제 재마운트 (ERR-006); `chatPanelRef` 추가 + route watch에서 `chatPanelRef.value?.focusInput()` 호출; `nextTick` import 추가
  - `frontend/src/components/ChatPanel.vue` — `defineExpose({ focusInput })` 추가 (부모가 포커스 복원 가능)
  - `frontend/src/views/DashboardView.vue` — `checkOllamaHealth`가 이미 'ok' 상태일 때 덮어쓰지 않도록 수정; 'loading' 같은 중간값은 무시
  - `반복실수.md` — ERR-006 (RouterView :key 누락) 추가, 체크리스트 항목 8번 추가
- 변경 이유:
  1. 상단 RouterLink 클릭 시 왼쪽 패널 빈 화면 — :key 강제 재마운트로 해결
  2. Ollama 상태가 'ok' → 'loading'으로 덮어쓰이는 race condition 방지
  3. 라우트 이동 후에도 채팅창 포커스 유지 — defineExpose + route watch 연동

---

## [2026-05-05] Phase 2 — 채팅 패널, 인터넷 검색, 레이아웃 개선

- 변경 내용:
  - `backend/routers/chat.py` — 신규. `/api/chat` SSE 스트리밍 채팅 엔드포인트 (Ollama 스트리밍)
  - `backend/routers/search.py` — 신규. `/api/search` DuckDuckGo 인터넷 검색 (run_in_executor로 이벤트루프 분리)
  - `backend/main.py` — chat, search 라우터 등록
  - `backend/requirements.txt` — ddgs>=9.0.0 추가
  - `frontend/src/App.vue` — 2패널 레이아웃(메인+채팅), 드래그 핸들, 인터넷 검색 토글 스위치 (localStorage 저장)
  - `frontend/src/components/ChatPanel.vue` — 신규. SSE 스트리밍 채팅 UI (타이핑 애니메이션, 스크롤 자동 하단, 인터넷 검색 상태 표시)
  - `frontend/src/api/index.js` — sendChatStream (fetch SSE), searchWeb 함수 추가
  - `frontend/src/views/ScheduleView.vue` — 대시보드 이동 버튼 추가 (버그 수정)
- 변경 이유:
  1. 스케줄→대시보드 이동 불가 버그 수정
  2. Ollama 스트리밍으로 체감 속도 개선
  3. 화면 50% 채팅창 + 드래그 크기 조절 요청
  4. DuckDuckGo 인터넷 검색 + Ollama 정리 응답 요청
- 검증: /api/chat SSE 스트리밍 ✓, /api/search ddgs 3건 결과 ✓, 채팅 패널 드래그 ✓, 대시보드 버튼 ✓

---

## [2026-05-06] 파서 고도화 + F002 SearXNG 기본값 + 파서 배지 표시

- 변경 내용:
  - `shared/content_extractor.py` — trafilatura 1순위 + BeautifulSoup 폴백 구조로 전면 교체
    - `_extract_from_html()` 내부 함수: trafilatura 추출 300자 이상이면 사용, 미달 시 BS4 폴백
    - `enrich_search_results()` / `_async` — `body_parser` 필드 추가 ("trafilatura" | "BeautifulSoup" | "")
    - `PARSER_TRAFILATURA`, `PARSER_BEAUTIFULSOUP` 상수 추가
  - `pipelines/base.py`
    - `SEARXNG_BASE_URL` 상수 추가
    - `call_searxng()` 유틸 메서드 추가 (httpx 동기, max_results 파라미터 지원)
  - `pipelines/f002_daily_issues/pipeline.py` 전면 재작성
    - `search_provider` 파라미터 추가 (기본값 "searxng")
    - SearXNG 사용 시: `call_searxng()` → `enrich_results()` 크롤링 보강
    - Tavily 사용 시: `call_tavily()` 그대로 (이미 본문 추출됨)
    - `_build_parser_summary()` 추가 — 사용 파서 요약 ("trafilatura", "BeautifulSoup", "trafilatura/BeautifulSoup", "Tavily")
    - 각 이슈에 `parser` 필드 추가
    - `_build_search_context()` — body_text 우선, content 폴백
    - 결과에 `search_provider` 필드 추가
  - `frontend/src/views/TaskDetailView.vue`
    - F002 이슈 카드에 파서 배지 추가 (`파싱: trafilatura` 형태)
    - `.issue-badges` 가로 flex 컨테이너 추가
    - `.issue-parser` CSS 스타일 추가 (파란 계열 배지)
  - `backend/requirements.txt` — `trafilatura>=2.0.0`, `lxml_html_clean>=0.4.0` 추가
- 변경 이유:
  1. 사용자 제안: trafilatura가 BeautifulSoup 수동 구현보다 본문 추출 정확도 높음 → 채택
  2. lxml 6.x 호환성 이슈(`lxml_html_clean` 분리) → 의존성 추가 설치로 해결
  3. F002에서 SearXNG(로컬, 무료)를 기본값으로 사용해 비용 절감
  4. 이슈 결과 화면에서 어떤 파서로 추출했는지 가시화 요청
- 검증: trafilatura nav 제거 + 본문 추출 OK ✓, BS4 폴백 로직 ✓, F002 search_provider 기본값 searxng ✓, parser_summary 혼합/Tavily ✓

---

## [2026-05-06] F002 파라미터 폼 수정 + 프롬프트 편집 기능 추가

- 변경 내용:
  - `backend/schemas/task.py` — `FeatureInputField`에 `title`, `default`, `options` 필드 추가
  - `backend/routers/features.py`
    - F001: 모든 필드에 `title`, `default` 추가
    - F002: `search_provider`(select), `days`(integer), `prompt_template`(textarea) 필드 신규 추가
    - F002 설명문 업데이트 (SearXNG/Tavily 언급)
  - `frontend/src/views/FeatureView.vue`
    - `initForm()` — `input_schema.properties` 기대 → 배열 형식(`Array.isArray`) 처리로 수정 (버그 수정)
    - `fields` computed — 배열 형식 파싱, `options`/`default` 포함
    - `buildParams()` — 빈 optional 필드 제외, `textarea` 타입 지원
    - template — `select` 드롭다운, `textarea` 자유 텍스트 타입 렌더링 추가
    - CSS — `.form-select`, `.form-textarea-prompt` (모노스페이스, 220px) 추가
  - `pipelines/f002_daily_issues/pipeline.py`
    - `_DEFAULT_INSTRUCTION` 모듈 상수 분리
    - `prompt_template` 파라미터 추출 추가
    - 프롬프트 구성: 검색결과 도입부(고정) + 분석 지시문(커스텀 가능) 분리 구조로 변경
    - `{keywords}`, `{max_issues}` 플레이스홀더 `.replace()` 치환 방식 적용
- 변경 이유:
  1. `input_schema.properties` 파싱 버그로 F001·F002 파라미터 폼이 전혀 렌더링되지 않던 치명적 버그 수정
  2. F002에 search_provider(SearXNG/Tavily 선택) 드롭다운 추가
  3. 사용자가 LLM 분석 지시 프롬프트를 직접 확인하고 수정할 수 있도록 textarea 노출
- 영향 범위: backend/schemas, backend/routers/features, frontend/FeatureView, pipelines/F002
- 검증: 배열 형식 파싱 ✓, select 드롭다운 초기값 'searxng' ✓, prompt_template 기본값 노출 ✓

---

## [2026-05-06] stop.ps1 PID 오류 수정

- 변경 내용:
  - `stop.ps1` 전면 재작성
    - `Stop-ByPort` 함수 — `Stop-Process` 전에 `Get-Process`로 존재 확인, 없으면 "이미 종료됨"(오류 아님)
    - `Stop-ByCommandLine` 함수 — WMI `CommandLine LIKE '%uvicorn%'` / `'%vite%'` 기반 2순위 탐색
    - PID 0 건너뜀 처리 추가
- 변경 이유:
  - `Get-NetTCPConnection`이 이미 종료된 프로세스의 PID를 반환하는 Windows TCP 지연 해제 현상으로 "Cannot find process" 오류 반복 발생
  - 오류 대신 "이미 종료됨"으로 처리, uvicorn/vite 이름 기반 폴백 추가
- 영향 범위: stop.ps1 단일 파일

---

## [2026-05-06] 멀티 검색 쿼리 확장 + 심층 분석 모드 구현

- 변경 내용:
  - `shared/query_expander.py` — 신규
    - ANALYSIS / FORECAST / INVESTMENT / TREND / CAUSAL 5종 확장 유형 상수 정의
    - `detect_expansion_type(question)` — 키워드 기반 즉시 판별 (LLM 호출 없음)
    - `needs_expansion(question)` — 확장 필요 여부 bool 반환
    - `_extract_topic(question)` — 트리거 구문 제거 후 핵심 주제어 추출
    - `expand_query(question)` — [원본, 서브쿼리1, 서브쿼리2, 서브쿼리3] 반환
  - `shared/prompt_builder.py`
    - `INTENT_DEEP_ANALYSIS = 'DEEP_ANALYSIS'` 상수 추가
    - DEEP_ANALYSIS 지시문: 현황 요약 → 원인·배경 → 전망·시사점 3섹션 구조 강제
    - `build_optimized_prompt()` — `deep_analysis: bool = False` 파라미터 추가
  - `backend/core/config.py` — `SEARXNG_BASE_URL = "http://192.168.20.80:8888"` 추가
  - `backend/routers/chat.py` 전면 재작성
    - `ChatRequest`에 `search_provider: str = "searxng"` 필드 추가
    - `_quick_search_searxng(query)` — 스니펫 전용 SearXNG 검색 (크롤링 없음)
    - `_multi_search(queries)` — asyncio.gather로 쿼리별 병렬 검색 후 통합 컨텍스트 반환
    - `_status_sse(message)` — 상태 안내용 SSE 이벤트 생성 헬퍼
    - `_generate_response()` — 확장 감지 → status SSE → 멀티 검색 → Ollama 스트리밍 통합 제너레이터
  - `frontend/src/components/ChatPanel.vue`
    - `assistantMsg`에 `statusText: ''` 필드 추가
    - SSE 리더: `chunk.type === 'status'` 처리 → `assistantMsg.statusText` 업데이트
    - 첫 토큰 수신 시 `statusText` 초기화
    - 어시스턴트 말풍선 템플릿: typing-dots / status-hint / msg-text 조건 분기
    - `.status-hint` CSS 추가 (이탤릭, 회색, 12px)
    - 인터넷 배지 레이블 'DuckDuckGo' → 'SearXNG' 수정
  - `frontend/src/api/index.js`
    - `sendChatStream()` — `searchProvider = 'searxng'` 파라미터 추가, 요청 바디에 `search_provider` 포함
- 변경 이유:
  1. "분석해줘", "전망", "투자", "트렌드" 등 심층 분석 질문에서 LLM이 단순 현황 나열에 그치는 문제 해결
  2. 추가 검색으로 컨텍스트를 보강한 후 DEEP_ANALYSIS 구조 프롬프트로 인과관계·전망 포함 답변 생성
  3. 검색 중 상태를 말풍선 안에 표시해 UX 개선
- 영향 범위: shared/, backend/routers/chat.py, backend/core/config.py, frontend/src/
- 검증: query_expander 5종 유형 판별 ✓, expand_query 서브쿼리 생성 ✓, status SSE 형식 ✓

---

## [2026-05-06] shared 패키지 신설 — 크롤링 본문 추출 + 의도 기반 프롬프트 최적화

- 변경 내용:
  - `shared/__init__.py`, `shared/GUIDE.md` — 전역 공유 패키지 신설
  - `shared/content_extractor.py` — 신규
    - BeautifulSoup4 + lxml으로 URL 크롤링 후 본문 추출·정제
    - 광고/메뉴/네비/스크립트 등 노이즈 제거, 20자 미만 라인 제거
    - article > main > 본문 클래스 > body 우선순위로 본문 탐색
    - 동기(`extract_article_text`, `enrich_search_results`) / 비동기(`*_async`) 두 인터페이스 제공
    - 병렬 크롤링 최대 5개, 실패 시 snippet 자동 폴백
  - `shared/prompt_builder.py` — 신규
    - 키워드 기반 의도 파악 7종: CODING / HOW_TO / COMPARISON / SUMMARY / CREATIVE / FACTUAL / GENERAL
    - 검색 컨텍스트 있으면 자동으로 SEARCH_ANALYSIS 적용
    - `build_optimized_prompt()` — 지시문 + 검색결과 + 이전대화 + 질문 구조화
  - `backend/main.py` — 프로젝트 루트를 sys.path에 추가 (shared 임포트 경로 확보)
  - `backend/routers/search.py` — SearchRequest에 `enrich: bool = True` 추가, SearchResult에 `body_text` 필드 추가, `_enrich()` 함수 추가, `_build_context_text()`에서 body_text 우선 사용
  - `backend/routers/chat.py` — `_build_prompt()` 제거, `shared.prompt_builder.build_optimized_prompt()` 적용
  - `pipelines/base.py` — shared 임포트 추가, `enrich_results()` / `build_prompt()` 래퍼 메서드 추가
  - `backend/requirements.txt` — beautifulsoup4, lxml 추가
- 변경 이유:
  1. SearXNG 스니펫(짧은 발췌)만으로는 LLM 컨텍스트 품질이 낮음 → 실제 본문 크롤링으로 해결
  2. 동일 프롬프트 템플릿을 모든 질문에 쓰면 LLM 답변 품질 낮음 → 의도별 구조화 프롬프트로 해결
  3. 채팅/파이프라인 모두에서 재사용 가능한 전역 모듈로 구현
- 검증: 의도 파악 7종 케이스 모두 통과 ✓, body_text 우선/snippet 폴백 로직 ✓, 라우터 임포트 ✓

---

## [2026-05-06] F002 파이프라인 — Tavily 실검색 연동 + 검색엔진 교체

- 변경 내용:
  - `pipelines/base.py`
    - `import os`, `Path`, `dotenv` 로드 추가 (파이프라인 독립 프로세스에서 .env 읽기)
    - `TAVILY_API_URL`, `TAVILY_ISSUE_DOMAINS` 상수 추가
    - `call_tavily()` 유틸 메서드 추가 (httpx 동기 호출, include_domains/days 파라미터 지원)
  - `pipelines/f002_daily_issues/pipeline.py` 전면 재작성
    - Ollama 단독 생성(환각) → **Tavily 실검색 → Ollama 분석** 2단계 구조로 교체
    - `days` 파라미터 추가 (기본 2일 = 최근 48시간)
    - 검색 도메인: reddit.com, news.ycombinator.com, techcrunch.com, arxiv.org, huggingface.co, wired.com, theverge.com, dev.to, producthunt.com
    - Ollama 프롬프트에 실검색 컨텍스트 삽입 — 없는 내용 생성 금지 조건 명시
  - `backend/routers/search.py`: ddgs → Tavily REST API (httpx 직접 호출)로 교체
  - `backend/requirements.txt`: ddgs 제거, python-dotenv 추가
  - `backend/main.py`: 앱 시작 시 .env 로드 추가
  - `.env` (신규): TAVILY_API_KEY 저장
  - `frontend/src/components/ChatPanel.vue`: 검색 건수 5 → 10 → 20건으로 변경
- 변경 이유:
  1. LLM이 없는 이슈를 환각으로 생성하는 문제 해결 — 실데이터 기반으로 전환
  2. 사용자 요청: Tavily 실검색 + quality 소스 도메인 필터링 적용
  3. DuckDuckGo(ddgs) → Tavily로 검색 엔진 교체 (LLM 최적화, IP 차단 위험 없음)

---

## [2026-05-05] TaskDetailView 결과 표시 개선 — 파라미터 테이블 + F002 이슈 카드

- 변경 내용:
  - `frontend/src/views/TaskDetailView.vue`
    - `parsedParams`, `parsedResult`, `featureName`, `isF002Issues` computed 추가
    - `tryParse()` — JSON 문자열/객체 모두 처리하는 범용 파싱 함수
    - `renderMd()` — `**text**` → `<strong>text</strong>` 마크다운 변환
    - `importanceCls()` — 중요도(높음/중간/낮음) → CSS 클래스 매핑
    - 파라미터 카드: raw JSON `<pre>` → 키/값 테이블(`.param-table`) 로 개선
    - 결과 카드(F002): `issues` 배열을 이슈 카드 목록으로 렌더링 (날짜 헤더, 제목 bold, 요약, 중요도 배지)
    - 결과 카드(기타 feature): 기존 JSON `<pre>` fallback 유지
    - 헤더의 `feature_id` → store에서 조회한 feature 이름으로 표시
    - features 미로드 시 onMounted에서 `fetchFeatures()` 자동 호출
- 변경 이유: 실행 결과가 raw JSON/마크다운 태그 그대로 노출되어 가독성이 없다는 사용자 요청
- 영향 범위: TaskDetailView.vue 단일 파일
- 검증: F002 이슈 카드 렌더링 — `**텍스트**` bold 변환, 중요도 배지 색상 분기

---

## [2026-05-05] 대시보드 모델 선택 기능 추가

- 변경 내용:
  - `backend/core/database.py` — settings 테이블 추가 (key-value 설정 저장)
  - `backend/schemas/task.py` — ModelsResponse, ModelSelectRequest 스키마 추가
  - `backend/routers/models.py` — `/api/models` GET/PUT 라우터 신규 생성
  - `backend/main.py` — models 라우터 등록
  - `pipelines/base.py` — `_get_selected_model()` 추가, `call_ollama` 시그니처 변경 (DB 선택 모델 우선 사용)
  - `pipelines/f001_youtube/pipeline.py`, `f002_daily_issues/pipeline.py` — `model=` 파라미터 제거
  - `frontend/src/api/index.js` — getModels, selectModel 함수 추가
  - `frontend/src/views/DashboardView.vue` — 모델 선택 드롭다운 UI 추가
- 변경 이유: 사용자가 대시보드에서 직접 Ollama 모델을 선택할 수 있도록 요청
- 영향 범위: 백엔드 models 라우터, 파이프라인 전체 (모델 우선순위 변경), 대시보드 UI
- 검증: GET /api/models ✓, PUT /api/models/select ✓, 선택 모델로 파이프라인 실행 DONE ✓

---

## [2026-05-05] Phase 1 구현 완료 — backend/frontend/pipelines 전체 연동

- 변경 내용:
  - `backend/` — FastAPI 앱, aiosqlite DB, tasks/features/schedules/health 라우터, APScheduler
  - `frontend/` — Vue 3 + Vite SPA, DashboardView/FeatureView/TaskDetailView/ScheduleView
  - SQLAlchemy 2.x 호환 불가(32비트 Python) → aiosqlite 직접 사용으로 교체
  - `pipelines/runner.py` — sys.path에 프로젝트 루트 추가 (모듈 인식 문제 수정)
  - `pipelines/base.py` — Ollama 모델 목록을 실제 설치 모델로 수정 (exaone3.5:2.4b 등)
- 변경 이유: Phase 1 뼈대 구축 및 전체 연동 테스트 완료
- 영향 범위: backend/, frontend/src/, pipelines/ 전체
- 검증: /api/health ✓, /api/features ✓, /api/health/ollama ✓, Task 생성 + F002 파이프라인 DONE ✓
- 담당 에이전트: api-builder, web-builder, pipeline-builder + Claude (수정)

---

## [2026-05-05] 파이프라인 베이스 클래스 및 runner 구현

- 변경 내용:
  - `pipelines/GUIDE.md` — 파이프라인 폴더 가이드 (새 파이프라인 추가 방법 포함)
  - `pipelines/__init__.py` — 패키지 초기화 파일
  - `pipelines/base.py` — BasePipeline 추상 클래스 (update_status, call_ollama, is_cancelled 유틸 포함)
  - `pipelines/runner.py` — 파이프라인 실행 진입점 (task_id, feature_id 인자 처리, 예외 FAILED 저장)
  - `pipelines/f001_youtube/__init__.py` — F001 패키지 초기화
  - `pipelines/f001_youtube/pipeline.py` — F001 유튜브 컨텐츠 제작 파이프라인 (제목/설명/스크립트 3단계)
  - `pipelines/f002_daily_issues/__init__.py` — F002 패키지 초기화
  - `pipelines/f002_daily_issues/pipeline.py` — F002 이슈 발굴 파이프라인 (키워드 기반 이슈 분석)
- 변경 이유: Phase 1 파이프라인 인프라 구축 — FastAPI subprocess 호출 구조 완성
- 영향 범위: pipelines/ 폴더 전체 신규 생성
- 담당 에이전트: pipeline-builder

---

## [2026-05-05] 프로젝트 초기 셋업

- 변경 내용: 프로젝트 CLAUDE.md 및 에이전트 파일 일체 생성
- 변경 이유: Dash 프로젝트 신규 시작 — new_project_setup.md 절차 적용
- 영향 범위: CLAUDE.md, .claude/agents/*.md, .claude/advisor_workflow.md, .claude/hooks/*.sh
- 담당 에이전트: Claude (초기 셋업)

---

## [2026-05-07] 로드맵 변경 및 F003 연구·계획

### 변경 파일
- `CLAUDE.md`: 로드맵 Phase 3/4 순서 변경, F003 추가, F002 보류 표시
- `.claude/agents/pipeline-builder.md`: F003 파이프라인 항목 추가
- `RESEARCH.md`: V1→V3 대폭 업데이트 (900+ 라인)
  - V2: AUTOMATIC1111 → ComfyUI 단일 플랫폼 전환, 스타일 선택 시스템 6카테고리
  - V3: Category 7 디테일 향상 LoRA 추가 (15개 예시)

### 신규 파일
- `PLAN.md`: F003 영상제작 파이프라인 + cursor 기반 페이징 전환 구현 계획
  - 18개 구현 단계
  - cursor 페이징: backend/schemas/task.py, backend/routers/tasks.py, backend/services/task_service.py, frontend/src/api/index.js, frontend/src/store/tasks.js
  - F003 신규: 14개 파일 (pipelines/f003_*, backend/routers/comfyui.py, frontend 컴포넌트 등)
  - 6개 트레이드오프 분석

### 변경 이유
사용자 요청에 따른 로드맵 조정 및 신기능(F003) 연구·계획 수립.
구현은 아직 시작하지 않음 — "구현해줘" 트리거 대기 중.

---

## [2026-05-07] Phase 1~18 전체 구현 완료 — cursor 페이징 + F003 영상제작 파이프라인

- 변경 내용:

### 1. Cursor 기반 페이징 전환 (P1)
- `backend/schemas/task.py`:
  - `TaskListResponse`: `total` 필드 제거, `next_cursor: int|None`, `has_more: bool` 추가
- `backend/routers/tasks.py`:
  - `list_tasks`: `offset` 파라미터 → `cursor: int|None` 변경
  - SQL: `WHERE id < cursor ORDER BY id DESC LIMIT limit+1` 구조
- `backend/services/task_service.py`:
  - `list_tasks()`: cursor 기반 SQL 쿼리로 재구현
- `frontend/src/api/index.js`:
  - `getTasks(limit, cursor)`, `getTasksByFeature(featureId, limit, cursor)` cursor 기반으로 변경
- `frontend/src/store/tasks.js`:
  - `nextCursor`, `hasMore` 상태 추가
  - `fetchMoreTasks()` 메서드 추가
  - `totalTasks` 제거
- `frontend/src/views/DashboardView.vue`:
  - `fetchTasks(10, 0)` → `fetchTasks(10)` 시그니처 변경

### 2. DB 스키마 추가 (P2)
- `backend/core/database.py`:
  - `model_inventory` 테이블 (filename UNIQUE 제약)
  - `model_download_queue` 테이블

### 3. F003 Feature 정의 (P3)
- `backend/routers/features.py`:
  - F003 영상제작 항목 추가
  - 24개 입력 필드 (영상유형, 아트스타일, 촬영스타일, 배경, 인물, 감정, 무드, 색상톤 등)
  - art_style options에 "flux" 추가 (Flux.1 지원)

### 4. F003 파이프라인 핵심 모듈 (P4-P13)
- `pipelines/f003_video_creation/comfyui_client.py`:
  - ComfyUI REST API + WebSocket 클라이언트
  - 취소 시 `POST /interrupt` 전송 → GPU 즉시 해제
- `pipelines/f003_video_creation/prompt_generator.py`:
  - Ollama 기반 SD/Flux.1 프롬프트 생성
- `pipelines/f003_video_creation/style_mapper.py`:
  - 사용자 선택 스타일 → ComfyUI 워크플로우 매핑
- `pipelines/f003_video_creation/model_manager.py`:
  - 모델 인벤토리 + 자동 다운로드 관리
  - `download_from_hf`: model_type 파라미터 추가 (기존 "checkpoint" 하드코딩 수정)
- `pipelines/f003_video_creation/pipeline.py`:
  - F003Pipeline 메인 실행 로직 (11단계)
  - 절대 경로 `r"C:\Develop\Dash"` → `Path(__file__).parent.parent.parent` 상대 경로로 수정
- `pipelines/f003_video_creation/config.json`:
  - "flux" 스타일 매핑 추가 (base_model: Flux.1)
- `pipelines/f003_video_creation/workflows/animatediff_base.json`:
  - AnimateDiff 기본 워크플로우
- `pipelines/f003_video_creation/workflows/flux_base.json`:
  - Flux.1 기본 워크플로우 (고아 노드 3, 4 제거)

### 5. 백엔드 모델·다운로드 관리 (P4-P13 계속)
- `backend/services/model_service.py`:
  - model_inventory CRUD 로직
- `backend/services/download_service.py`:
  - 다운로드 큐 관리
- `backend/routers/model_assets.py`:
  - `/api/model-assets` 엔드포인트
  - 보안: filename 경로 순회 취약점 패치 (os.path.basename 검증)
- `backend/schemas/model_asset.py`:
  - ModelAsset 요청/응답 스키마
- `backend/main.py`:
  - model_assets 라우터 등록
  - `/results/f003` StaticFiles 마운트
  - 절대 경로 → Path(__file__).parent.parent 상대 경로로 수정

### 6. F003 프론트엔드 (P14-P16)
- `frontend/src/views/F003View.vue`:
  - 3단계 다단계 UI: 유형→스타일→파라미터
  - "Flux.1 (고품질)" 아트 스타일 추가
- `frontend/src/router/index.js`:
  - `/features/F003` 라우트 추가 (F003View 전용)
- `frontend/src/views/TaskDetailView.vue`:
  - F003 미디어(이미지/동영상) 렌더링 블록 추가

### 7. Vite 프록시 설정 (P17) — Critical 버그
- `frontend/vite.config.js`:
  - `/results` 경로 프록시 추가 → F003 결과 이미지/동영상 404 해결

### 8. Pipeline Runner 중복 업데이트 수정 (P18)
- `pipelines/runner.py`:
  - run() 완료 후 DB 상태 확인 후 DONE이 아닌 경우에만 보장용 업데이트 실행

### 9. 결과 저장소
- `storage/results/f003/`: 신규 생성 (이미지/동영상 저장)

- 변경 이유:
  1. 페이징 개선: offset 기반 → cursor 기반으로 전환 (무한 스크롤 + 동시성 안전)
  2. F003 구현: 영상 생성(동영상/이미지), ComfyUI 워크플로우 자동화, 모델 자동 관리
  3. 프로세스 안정화: runner.py 중복 업데이트 방지, 경로 상대화

- 영향 범위:
  - Backend: schemas, routers, services (model, download), main.py
  - Frontend: api, store, views (DashboardView, F003View, TaskDetailView), router, vite.config.js
  - Pipelines: f003 전체 모듈 신규, base.py 수정 없음
  - DB: model_inventory, model_download_queue 테이블 신규

- Critic 검토 결과:
  - Critical 5개: vite.config.js /results 프록시 누락, 경로 순회 보안 취약점, 절대 경로 하드코딩, 중복 DONE 업데이트, JSON 파일 형식
  - Major 7개: 에러 처리 미흡, 로깅 부족, 타입 검증 결함, 문서 미비
  - Minor 4개: 코멘트 누락, CSS 정렬, 불필요 import 등
  - 모두 수정 완료

- 검증 완료:
  - P1: cursor 페이징 동작 ✓
  - P3: F003 feature 정의 조회 ✓
  - P4-P13: ComfyUI 클라이언트 연동, 모델 다운로드, 프롬프트 생성 ✓
  - P14-P16: F003View 3단계 폼, TaskDetailView 미디어 렌더링 ✓
  - P17: /results/f003 프록시 ✓ (이미지/동영상 접근 가능)
  - P18: 중복 업데이트 제거 ✓

- 담당 에이전트: pipeline-builder, api-builder, web-builder, critic
