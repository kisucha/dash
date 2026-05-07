# Dash 소개 및 작동 원리

| 필드 | 내용 |
|------|------|
| 문서명 | Dash 소개 및 작동 원리 |
| 버전 | V1 |
| 날짜 | 2026-05-06 |
| 작성자 | Claude (kisuc 승인) |
| 문서 유형 | 시스템 설명서 |
| 모델 | claude-sonnet-4-6 |

---

## 1. Dash란?

Dash는 **Ollama 로컬 LLM**을 핵심 엔진으로 사용하는 웹 기반 자동화 대시보드다.
사용자가 브라우저에서 자동화 업무를 선택·실행·관리하고, AI 채팅으로 로컬 LLM과 대화할 수 있다.

- **프론트엔드**: Vue 3 SPA (`localhost:5173`)
- **백엔드**: FastAPI (`localhost:8000`)
- **로컬 LLM**: Ollama (`localhost:11434`)
- **DB**: SQLite (`storage/dash.db`)

---

## 2. 전체 아키텍처 흐름

```
[브라우저 — Vue 3 SPA]
        │  Axios REST / Fetch SSE
        ▼
[FastAPI 서버 — localhost:8000]
        │
        ├── /api/chat    → Ollama 로컬 LLM 스트리밍 채팅
        ├── /api/search  → SearXNG / Tavily 인터넷 검색
        ├── /api/tasks   → 파이프라인 작업 관리
        ├── /api/features→ 업무 목록 조회
        ├── /api/schedules→ 크론 스케줄 관리
        ├── /api/health  → 서버/Ollama 상태 확인
        └── /api/models  → 사용 가능한 Ollama 모델 목록
                │
                ├── [Pipeline 독립 프로세스] → Ollama (httpx 동기 호출)
                └── [APScheduler]           → 크론 자동 실행
```

---

## 3. 핵심 기능별 작동 원리

### 3-1. AI 채팅 패널 — 인터넷 OFF (기본)

```
[사용자 입력]
      │
      ▼
ChatPanel.vue — sendMessage()
      │  POST /api/chat  {message, history}
      ▼
chat.py — _build_prompt()
      │  대화 이력(최근 6턴) + 현재 메시지 조합
      ▼
Ollama /api/generate (stream=True)
      │  SSE 토큰 스트리밍
      ▼
브라우저 실시간 출력
```

- LLM 자체 학습 지식만으로 답변
- 인터넷 정보 없음

---

### 3-2. AI 채팅 패널 — 인터넷 ON (핵심!)

```
[사용자 입력]
      │
      ▼
ChatPanel.vue — sendMessage()
      │
      ├── Step 1: POST /api/search  {query, provider:"searxng"|"tavily"}
      │           │
      │           ├── SearXNG (로컬, http://192.168.20.80:8888)
      │           │    → 여러 검색엔진 결과 집계 (LLM 처리 없음)
      │           │    → 원시 검색 결과 반환 (제목, URL, 스니펫)
      │           │
      │           └── Tavily (유료 API)
      │                → LLM 최적화 검색 결과 반환
      │
      │           search.py — _build_context_text()
      │           → 검색 결과를 LLM 프롬프트용 텍스트로 포맷
      │
      └── Step 2: POST /api/chat  {message, history, search_context}
                  │
                  ▼
            chat.py — _build_prompt()
                  │  [검색결과 텍스트] + [대화이력] + [현재질문] 조합
                  ▼
            Ollama /api/generate (stream=True)
                  │  LLM이 검색 결과를 읽고 답변 생성
                  ▼
            브라우저 실시간 출력
```

**핵심 포인트:**
- SearXNG 검색 자체는 LLM과 무관 — 원시 결과 그대로 반환
- 검색 결과를 프롬프트에 삽입한 뒤 Ollama가 읽고 답변 생성
- 즉, **검색 = SearXNG**, **요약/답변 = Ollama 로컬 LLM** 이 담당

---

### 3-3. 파이프라인 실행 흐름

```
[사용자: 업무 실행 클릭]
      │  POST /api/tasks  {feature_id, params}
      ▼
task_service.py
      │  tasks 테이블에 PENDING 상태로 저장
      │  subprocess.Popen()으로 독립 프로세스 생성
      ▼
pipelines/runner.py (독립 프로세스)
      │  파이프라인 모듈 동적 로드
      │  status → RUNNING
      ▼
BasePipeline.run()  (F001 / F002 등)
      │  단계별 진행하며 DB result 컬럼 갱신
      │  BasePipeline.call_ollama() — Ollama 동기 호출
      │  BasePipeline.call_tavily() — Tavily 검색 (F002용)
      │  BasePipeline.is_cancelled() — 취소 감지
      ▼
status → DONE / FAILED / CANCELLED
```

- 파이프라인은 **독립 프로세스** — 하나 실패해도 서버 영향 없음
- 진행 상황은 2초 폴링으로 프론트엔드에 실시간 표시

---

### 3-4. F002 파이프라인 (매일 아침 이슈 발굴)

```
[입력: keywords, date, max_issues, days]
      │
      ▼
Step 1: Tavily 검색
      │  최근 N일 내 관련 뉴스·커뮤니티 검색
      │  reddit, HackerNews, TechCrunch 등 고품질 소스 필터
      ▼
Step 2: Ollama 분석
      │  검색 결과 텍스트를 프롬프트에 포함
      │  이슈 제목·요약·중요도 구조화 요청
      ▼
[출력: {date, issues: [{title, summary, importance}]}]
```

---

### 3-5. 스케줄러 동작

```
FastAPI 시작 시 APScheduler 초기화
      │
      ▼
DB schedules 테이블에서 is_active=1 스케줄 복원 등록
      │
      ▼
크론 표현식 도달 시 자동 파이프라인 실행 (triggered_by="scheduler")
```

---

## 4. 검색 엔진 비교

| 항목 | SearXNG | Tavily |
|------|---------|--------|
| 방식 | 로컬 서버 (192.168.20.80:8888) | 외부 유료 API |
| 비용 | 무료, 무제한 | 1크레딧/호출 |
| LLM 처리 | 없음 — 원시 결과 반환 | 없음 — LLM 최적화 포맷 |
| 검색 품질 | 일반 메타 검색 | 고품질, 최신 뉴스 특화 |
| 사용처 | 채팅 인터넷 검색 | 채팅 + F002 파이프라인 |

---

## 5. Ollama 모델 선택 우선순위

```
1. DB settings 테이블 ('selected_model' 키) — 사용자 UI에서 선택한 모델
2. 파이프라인 호출 시 명시한 model 인자
3. 폴백 순서: exaone3.5:2.4b → qwen3.5:4b → gemma4:e4b
```

- 모델이 없으면(HTTP 404) 자동으로 다음 폴백 모델 시도
- Ollama 서버 미실행 시 즉시 오류 (폴백 없음)

---

## 6. 작업 상태 생명주기

```
PENDING → RUNNING → DONE
                  → FAILED
                  → CANCELLED  (사용자 취소)
```

- `is_cancelled()` 메서드로 파이프라인이 주기적으로 취소 여부 확인
- 취소 감지 시 파이프라인 즉시 중단

---

## 7. 핵심 파일 위치

| 파일 | 역할 |
|------|------|
| `backend/main.py` | FastAPI 앱 진입점, 스케줄러 초기화 |
| `backend/routers/chat.py` | 채팅 SSE 스트리밍 엔드포인트 |
| `backend/routers/search.py` | SearXNG / Tavily 검색 엔드포인트 |
| `backend/services/ollama_service.py` | Ollama 헬스체크 + 생성 서비스 |
| `pipelines/base.py` | 파이프라인 베이스 클래스 (Ollama/Tavily/DB 유틸) |
| `pipelines/runner.py` | 독립 프로세스 실행 진입점 |
| `pipelines/f002_daily_issues/pipeline.py` | F002 이슈 발굴 파이프라인 |
| `frontend/src/components/ChatPanel.vue` | AI 채팅 UI + 검색 연동 |
| `frontend/src/App.vue` | 레이아웃, 인터넷 토글, 검색 엔진 선택 |
| `storage/dash.db` | SQLite DB (tasks, schedules, settings) |
