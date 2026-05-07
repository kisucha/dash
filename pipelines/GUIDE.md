# Dash 파이프라인 폴더 가이드

| 필드 | 내용 |
|------|------|
| 문서명 | pipelines GUIDE |
| 버전 | V1 |
| 날짜 | 2026-05-05 |
| 작성자 | pipeline-builder agent |
| 문서 유형 | 폴더 가이드 |
| 모델 | claude-sonnet-4-6 |

---

## 폴더 역할

이 폴더는 Dash 프로젝트의 모든 업무 파이프라인 모듈을 포함한다.
각 파이프라인은 FastAPI 서버에서 독립 프로세스로 실행된다.

## 실행 흐름

```
FastAPI → subprocess.Popen("python runner.py {task_id} {feature_id}")
       → runner.py: DB에서 params 로드 → 파이프라인 클래스 찾기 → run() 호출
       → 결과를 DB에 저장
```

## 파일 구조

```
pipelines/
├── GUIDE.md          # 이 파일
├── __init__.py       # 패키지 초기화 (빈 파일)
├── base.py           # BasePipeline 추상 클래스
├── runner.py         # 파이프라인 실행 진입점 (subprocess 호출 대상)
├── f001_youtube/     # F001 유튜브 컨텐츠 제작
│   ├── __init__.py
│   └── pipeline.py
└── f002_daily_issues/ # F002 매일 아침 이슈 발굴
    ├── __init__.py
    └── pipeline.py
```

---

## 새 파이프라인 추가 방법

### 1단계: CLAUDE.md 업무 목록에 등록

`C:\Develop\Dash\CLAUDE.md`의 "업무(Feature) 목록" 표에 새 업무를 추가한다.

```
| F003 | 새로운 업무 이름 | 실행 방식 | 계획 |
```

### 2단계: 폴더 및 파일 생성

```
pipelines/
└── f003_new_feature/
    ├── __init__.py     # 빈 파일
    └── pipeline.py     # 파이프라인 구현
```

### 3단계: pipeline.py 구현 규칙

- `BasePipeline`을 상속받아야 한다
- `get_metadata()`와 `run()` 두 추상 메서드를 반드시 구현한다
- `get_metadata()`에서 올바른 `feature_id`를 반환해야 한다

**get_metadata() 반환 형식:**
```python
{
    "feature_id": "F003",
    "name": "업무 이름",
    "description": "업무 설명",
    "input_schema": {
        "field_name": {"type": "str", "required": True, "description": "필드 설명"}
    },
    "supports_schedule": False
}
```

**run() 반환 형식:**
```python
# 성공 시 dict 반환 (JSON 직렬화 가능해야 함)
{
    "key": "value",
    ...
}
```

### 4단계: runner.py에 파이프라인 등록

`runner.py`의 `PIPELINE_REGISTRY` 딕셔너리에 새 파이프라인을 추가한다.

```python
from pipelines.f003_new_feature.pipeline import F003Pipeline

PIPELINE_REGISTRY: dict[str, type[BasePipeline]] = {
    "F001": F001Pipeline,
    "F002": F002Pipeline,
    "F003": F003Pipeline,  # 여기에 추가
}
```

---

## BasePipeline 제공 유틸 메서드

| 메서드 | 설명 |
|--------|------|
| `update_status(task_id, status, result, error)` | DB의 task 상태를 업데이트 |
| `call_ollama(model, prompt, timeout)` | Ollama /api/generate 동기 호출 |
| `is_cancelled(task_id)` | 해당 task가 CANCELLED 상태인지 확인 |

---

## 작업 상태 값 (status)

| 값 | 설명 |
|----|------|
| `PENDING` | 생성됨, 실행 대기 중 |
| `RUNNING` | 실행 중 |
| `DONE` | 정상 완료 |
| `FAILED` | 오류로 실패 |
| `CANCELLED` | 사용자 취소 |

---

## 주의사항

- 파이프라인 내부에서 `is_cancelled(task_id)`를 주기적으로 호출해 취소 여부를 감지한다
- Ollama 호출 전 헬스체크를 권장한다
- 모든 예외는 반드시 처리하고 `update_status`로 FAILED 기록을 남긴다
- 인코딩 안전 규칙: 파일 상단에 `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` 추가
