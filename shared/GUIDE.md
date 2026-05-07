# shared 패키지 가이드

| 필드 | 내용 |
|------|------|
| 문서명 | shared 패키지 GUIDE |
| 버전 | V1 |
| 날짜 | 2026-05-06 |
| 작성자 | Claude (kisuc 승인) |
| 문서 유형 | 패키지 가이드 |

---

## 목적

백엔드(FastAPI)와 파이프라인(독립 프로세스) 양쪽에서 공통으로 사용하는 유틸리티 모음.
프로젝트 루트(`C:\Develop\Dash\`)가 sys.path에 등록되어 있으면 어디서든 임포트 가능.

---

## 모듈 목록

| 모듈 | 역할 |
|------|------|
| `content_extractor.py` | URL 크롤링 + trafilatura/BeautifulSoup 본문 추출 + 텍스트 정제 |
| `prompt_builder.py` | 질문 의도 파악 + LLM 최적화 프롬프트 구성 (deep_analysis 모드 포함) |
| `query_expander.py` | 분석/전망/투자/트렌드 의도 감지 + 멀티 검색 쿼리 확장 |

---

## content_extractor.py — 주요 함수

| 함수 | 방식 | 설명 |
|------|------|------|
| `extract_article_text(url)` | 동기 | 단건 URL 크롤링·정제 (파이프라인용) |
| `extract_article_text_async(url)` | 비동기 | 단건 URL 크롤링·정제 (FastAPI용) |
| `enrich_search_results(results)` | 동기 | 검색 결과 배치 크롤링 (파이프라인용) |
| `enrich_search_results_async(results)` | 비동기 | 검색 결과 병렬 크롤링 (FastAPI용) |

### 입력 results 형식
```
[{"title": str, "url": str, "snippet": str, ...}, ...]
```

### 출력 results 형식 (body_text 추가됨)
```
[{"title": str, "url": str, "snippet": str, "body_text": str, ...}, ...]
```

---

## prompt_builder.py — 주요 함수

| 함수 | 반환값 | 설명 |
|------|--------|------|
| `detect_intent(question)` | 의도 코드 문자열 | 키워드 매칭으로 즉시 판별 |
| `build_optimized_prompt(question, history, search_context)` | 프롬프트 문자열 | 의도별 최적 구조 생성 |

### 의도 코드 상수

| 상수 | 설명 |
|------|------|
| `INTENT_FACTUAL` | 사실 정보 질문 |
| `INTENT_HOW_TO` | 방법·절차 질문 |
| `INTENT_COMPARISON` | 비교 분석 |
| `INTENT_CREATIVE` | 창작·생성 요청 |
| `INTENT_CODING` | 코드·개발 관련 |
| `INTENT_SUMMARY` | 요약 요청 |
| `INTENT_SEARCH_ANALYSIS` | 검색 결과 있을 때 자동 적용 |
| `INTENT_DEEP_ANALYSIS` | 멀티 검색 + deep_analysis=True 일 때 적용 |
| `INTENT_GENERAL` | 일반 대화 |

---

## query_expander.py — 주요 함수

| 함수 | 반환값 | 설명 |
|------|--------|------|
| `detect_expansion_type(question)` | 확장 유형 코드 | 분석/전망/투자/트렌드/원인 감지 |
| `needs_expansion(question)` | bool | 멀티 검색 필요 여부 |
| `expand_query(question)` | list[str] | [원본, 서브쿼리1, 서브쿼리2, 서브쿼리3] |

### 확장 유형 상수

| 상수 | 트리거 예시 |
|------|------------|
| `EXPANSION_NONE` | 확장 불필요 |
| `EXPANSION_ANALYSIS` | "분석해줘", "검토해줘" |
| `EXPANSION_FORECAST` | "전망", "예측", "향후" |
| `EXPANSION_INVESTMENT` | "투자", "주식", "수익률" |
| `EXPANSION_TREND` | "트렌드", "동향" |
| `EXPANSION_CAUSAL` | "왜", "원인이", "이유가" |

---

## 사용 예시

### FastAPI 라우터에서
```python
from shared.content_extractor import enrich_search_results_async
from shared.prompt_builder import build_optimized_prompt
```

### 파이프라인에서 (BasePipeline 상속 시 래퍼 사용)
```python
# BasePipeline.enrich_results() 래퍼 메서드 사용
enriched = self.enrich_results(search_results)

# BasePipeline.build_prompt() 래퍼 메서드 사용
prompt = self.build_prompt(question, search_context=context_text)
response = self.call_ollama(prompt=prompt)
```

---

## sys.path 등록 위치

| 진입점 | 등록 코드 위치 |
|--------|--------------|
| `backend/main.py` | 파일 상단 (자동 등록) |
| `pipelines/runner.py` | 파일 상단 `_PROJECT_ROOT` 등록 |
