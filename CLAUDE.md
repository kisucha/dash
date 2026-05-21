# Dash — 로컬 LLM 기반 자동화 대시보드

| 필드 | 내용 |
|------|------|
| 프로젝트명 | Dash |
| 버전 | V1 |
| 시작일 | 2026-05-05 |
| 작성자 | kisuc |
| 문서 유형 | 프로젝트 CLAUDE.md |
| 모델 | claude-sonnet-4-6 |

> **전역 규칙 참조:** `~/.claude/CLAUDE.md` 적용. 이 파일은 프로젝트 고유 정보만 포함.

---

## 프로젝트 개요

웹 기반 대시보드에서 자동화 업무를 선택·실행·관리하는 플랫폼.
핵심은 **Ollama 로컬 LLM**을 파이프라인 엔진으로 사용하는 것.

```
사용자 → 웹 대시보드 → 기능 선택 → 파라미터/프롬프트 입력
       → 백그라운드 파이프라인 실행 (독립 프로세스)
       → 결과 대시보드 표시
```

---

## 핵심 아키텍처

### 레이어 구조

| 레이어 | 역할 |
|--------|------|
| **Web UI** | 기능 목록 대시보드, 입력 폼, 실행 현황, 결과 뷰 |
| **API Server** | 작업 요청 수신, 프로세스 생성, 상태 조회 |
| **Pipeline Runner** | 독립 프로세스로 실행되는 업무 파이프라인 |
| **Scheduler** | 크론탭/스케줄 기반 자동 실행 |
| **Ollama Client** | 로컬 LLM 호출 레이어 |
| **Storage** | 작업 이력, 결과물, 설정 저장 |

### 작업 생명주기

```
생성(PENDING) → 실행중(RUNNING) → 완료(DONE) / 실패(FAILED)
                               → 취소(CANCELLED)
```

---

## 기술 스택 (확정)

| 구분 | 선택 | 비고 |
|------|------|------|
| Frontend | Vue 3 + Vite + Pinia | SPA, 가볍고 빠른 셋업 |
| Backend | FastAPI (Python 3.11+) | 비동기, 프로세스 관리 용이 |
| LLM | Ollama | 로컬 실행, REST API 제공 |
| 스케줄러 | APScheduler | FastAPI 내장, 별도 서버 불필요 |
| DB | SQLite + SQLAlchemy ORM | 초기 단계, 마이그레이션 불필요 |
| 작업 큐 | SQLite 상태 컬럼 기반 | 별도 큐 서버 없이 DB로 관리 |
| HTTP 통신 | Axios (프론트) / httpx (백엔드→Ollama) | 비동기 지원 |

---

## 업무(Feature) 목록

각 업무는 독립된 파이프라인 모듈로 구현.

| 업무 ID | 이름 | 실행 방식 | 상태 |
|---------|------|----------|------|
| F001 | 유튜브 컨텐츠 제작 | 수동 실행 | 계획 |
| F002 | 매일 아침 주요 이슈 발굴 | 크론 자동 실행 (스케줄러 통합 후 구현) | 보류 |
| F003 | 영상제작 (동영상/그림) | 수동 실행 | 계획 |
| F006 | YouTube 자동화 파이프라인 v4 | 수동 실행 | 구현완료 |
| F007 | YouTube 자동화 파이프라인 v5 (channel_type 분기) | 수동 실행 | 구현완료 |

> 업무 추가 시 이 표에 먼저 등록 후 구현.

---

## 디렉토리 구조 (확정)

```
Dash/
├── CLAUDE.md
├── GUIDE.md
├── code_update.md
├── talk_history.md
├── frontend/                   # Vue 3 + Vite SPA
│   ├── GUIDE.md
│   ├── src/
│   │   ├── views/              # 페이지 컴포넌트 (Dashboard, Feature, TaskDetail)
│   │   ├── components/         # 공통 컴포넌트 (TaskCard, StatusBadge 등)
│   │   ├── store/              # Pinia 상태 관리
│   │   └── api/                # Axios API 통신 레이어
│   └── vite.config.js
├── backend/                    # FastAPI
│   ├── GUIDE.md
│   ├── main.py                 # FastAPI 앱 진입점 + APScheduler 초기화
│   ├── routers/                # API 라우터 (tasks, features, schedules, health)
│   ├── models/                 # SQLAlchemy 모델
│   ├── schemas/                # Pydantic 요청/응답 스키마
│   ├── services/               # 비즈니스 로직 (task_service, ollama_service)
│   └── core/                   # DB 연결, 설정, 공통 유틸
├── pipelines/                  # 업무 파이프라인 모듈
│   ├── GUIDE.md
│   ├── base.py                 # 파이프라인 베이스 클래스
│   ├── f001_youtube/           # F001 유튜브 컨텐츠 제작
│   └── f002_daily_issues/      # F002 매일 아침 이슈 발굴
└── storage/                    # SQLite DB 파일, 결과물
    └── GUIDE.md
```

---

## 업무 파이프라인 설계 원칙

1. **독립성**: 각 파이프라인은 독립 프로세스로 실행 — 하나가 실패해도 전체에 영향 없음
2. **멱등성**: 같은 입력으로 재실행해도 안전해야 함
3. **관측 가능성**: 모든 단계에서 로그 기록, 대시보드에서 실시간 확인
4. **Ollama 우선**: LLM 추론은 반드시 Ollama 로컬 API 경유

---

## Ollama 연동 원칙

- Ollama 기본 엔드포인트: `http://localhost:11434`
- 모델 선택: 업무 유형별로 적합한 모델 지정 (설정 파일에서 관리)
- 스트리밍 응답 지원 — 장시간 생성 작업은 스트리밍으로 상태 표시
- Ollama 미실행 시 → 파이프라인 실행 전 헬스체크 필수

---

## 스케줄 관리 원칙

- 크론 표현식으로 실행 주기 정의
- 스케줄 등록/수정/삭제는 대시보드 UI에서 관리
- 수동 즉시 실행 항상 지원
- 실행 이력과 스케줄 로그는 별도 보관

---

## 서브에이전트 구성

| 에이전트 | 파일 | 역할 | 모델 |
|---------|------|------|------|
| web-builder | `.claude/agents/web-builder.md` | 웹 UI 구현 | Sonnet |
| api-builder | `.claude/agents/api-builder.md` | API 서버 + 프로세스 관리 | Sonnet |
| pipeline-builder | `.claude/agents/pipeline-builder.md` | 업무 파이프라인 구현 | Sonnet |
| critic | `.claude/agents/critic.md` | 비판 검토 (보안·아키텍처) | Sonnet |
| historian | `.claude/agents/historian.md` | 변경 이력 기록 | Haiku |
| advisor | (에스컬레이션 전용) | 아키텍처 판단 | Opus |

---

## 개발 단계 (로드맵)

| 단계 | 내용 | 상태 |
|------|------|------|
| Phase 0 | 아키텍처 설계 및 기술 스택 확정 | **완료** |
| Phase 1 | 기본 대시보드 + API 서버 + Ollama 연동 뼈대 | 대기 |
| Phase 2 | 첫 번째 파이프라인 구현 (F001 또는 F002) | 대기 |
| Phase 3 | 파이프라인 확장 (수동 실행 파이프라인 위주) | 대기 |
| Phase 4 | 스케줄러 통합 + F002 구현 | 대기 |
