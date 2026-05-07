# Advisor 워크플로우 — Dash 프로젝트

## 프로젝트 성격
Ollama 로컬 LLM 기반 자동화 대시보드.
웹 UI + API 서버 + 독립 파이프라인 프로세스 구조.
각 업무(F001, F002...)는 독립 파이프라인 모듈로 분리.

## 에스컬레이션 특수 코드

| 코드 | 에이전트 | 조건 |
|------|----------|------|
| `ESC-WB01` | web-builder | 실시간 상태 업데이트 방식 결정 불가 |
| `ESC-WB02` | web-builder | UI 구조 변경이 3개 이상 페이지에 영향 |
| `ESC-AB01` | api-builder | 프로세스 관리 방식 결정 불가 |
| `ESC-AB02` | api-builder | DB 스키마 변경이 기존 이력에 영향 |
| `ESC-AB03` | api-builder | Ollama 연결 실패 폴백 전략 필요 |
| `ESC-PB01` | pipeline-builder | Ollama 모델 선택 기준 불명확 |
| `ESC-PB02` | pipeline-builder | 비가역적 외부 작업 포함 파이프라인 |
| `ESC-PB03` | pipeline-builder | 새 파이프라인이 기존 아키텍처와 충돌 |
| `ESC-CR01` | critic | 발견 결함이 아키텍처 수준 재설계 요구 |
| `ESC-CR02` | critic | 보안 취약점이 실질적 위험 수준 |

## 판단 기준 (프로젝트 특화)

### 아키텍처 원칙 (변경 전 반드시 확인)
- **파이프라인 실행 문제** → 독립 프로세스 여부 먼저 확인
- **Ollama 호출 실패** → 헬스체크 로직 + 타임아웃 설정 먼저 확인
- **작업 상태 불일치** → DB 상태 컬럼 업데이트 로직 먼저 확인
- **UI 미반영** → API 응답 형식 + 프론트 폴링 주기 먼저 확인

### 트레이드오프 판단 기준
- 폴링 vs SSE vs WebSocket: **초기에는 폴링** (복잡도 최소화, 나중에 SSE로 전환)
- SQLite vs PostgreSQL: **초기에는 SQLite** (규모 확장 시 마이그레이션)
- 동기 vs 비동기 파이프라인: **항상 비동기** (메인 서버 블로킹 금지)

## Advisor 전용 모델
`claude-opus-4-7` — 에스컬레이션 응답 전용, 직접 코드 작성 불가

## 에스컬레이션 절차
1. Executor 자체 해결 시도 1회
2. 실패 시 표준 템플릿으로 Advisor 호출 (`~/.claude/guides/escalation_templates.md` 참조)
3. Advisor 응답 참조 후 Executor가 최종 결론 도출
4. 동일 문제 최대 2회 → 초과 시 사용자에게 직접 보고
