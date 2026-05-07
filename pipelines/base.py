# 파이프라인 베이스 클래스 — 모든 파이프라인이 상속받는 추상 기반 클래스.
# DB 상태 업데이트, Ollama 동기 호출, Tavily 검색, 취소 감지 유틸 메서드를 제공한다.
# shared 패키지의 content_extractor, prompt_builder 래퍼 메서드도 포함한다.

import sys
import os
import sqlite3
import json
import httpx
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 파이프라인은 독립 프로세스로 실행되므로 직접 .env 로드
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / '.env')
except ImportError:
    pass

# shared 패키지 임포트 — 프로젝트 루트가 sys.path에 등록되어 있으므로 직접 임포트 가능
try:
    from shared.content_extractor import enrich_search_results
    from shared.prompt_builder import build_optimized_prompt, detect_intent
    _SHARED_AVAILABLE = True
except ImportError:
    _SHARED_AVAILABLE = False

# 로거 설정
logger = logging.getLogger(__name__)

# DB 경로 상수
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"

# Ollama 기본 엔드포인트
OLLAMA_BASE_URL: str = "http://localhost:11434"

# Ollama 모델 우선순위 (앞에서부터 순서대로 시도)
OLLAMA_MODEL_FALLBACK: list[str] = ["exaone3.5:2.4b", "qwen3.5:4b", "gemma4:e4b"]

# Tavily REST API 엔드포인트
TAVILY_API_URL: str = "https://api.tavily.com/search"

# SearXNG 로컬 인스턴스 주소
SEARXNG_BASE_URL: str = "http://192.168.20.80:8888"

# F002 등 이슈 발굴에 사용할 고품질 소스 도메인
TAVILY_ISSUE_DOMAINS: list[str] = [
    "reddit.com",
    "news.ycombinator.com",
    "techcrunch.com",
    "arxiv.org",
    "huggingface.co",
    "wired.com",
    "theverge.com",
    "dev.to",
    "producthunt.com",
]


class BasePipeline(ABC):
    """
    모든 업무 파이프라인의 추상 베이스 클래스.

    하위 클래스는 반드시 get_metadata()와 run() 두 메서드를 구현해야 한다.
    DB 연결은 동기 sqlite3를 사용한다 (독립 프로세스이므로 비동기 불필요).
    """

    # ------------------------------------------------------------------
    # 추상 메서드 — 하위 클래스에서 반드시 구현
    # ------------------------------------------------------------------

    @abstractmethod
    def get_metadata(self) -> dict:
        """
        파이프라인 메타데이터를 반환한다.

        반환 형식:
        {
            "feature_id": str,        # 예: "F001"
            "name": str,              # 업무 이름
            "description": str,       # 업무 설명
            "input_schema": dict,     # 입력 파라미터 스키마
            "supports_schedule": bool # 스케줄 자동 실행 지원 여부
        }
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, task_id: int, params: dict) -> dict:
        """
        파이프라인 실제 실행 메서드.

        Args:
            task_id: DB의 tasks 테이블 PK
            params: 실행 파라미터 딕셔너리 (DB에서 JSON 파싱된 값)

        Returns:
            실행 결과 딕셔너리 (JSON 직렬화 가능해야 함)

        Raises:
            Exception: 실행 실패 시 예외를 발생시키면 runner.py가 FAILED 처리
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # 유틸 메서드 — DB 상태 업데이트
    # ------------------------------------------------------------------

    def update_status(
        self,
        task_id: int,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> None:
        """
        DB의 tasks 테이블에서 해당 task의 상태를 업데이트한다.

        Args:
            task_id: 업데이트할 task의 ID
            status: 새 상태값 (RUNNING, DONE, FAILED, CANCELLED)
            result: 성공 시 결과 딕셔너리 (JSON으로 직렬화됨)
            error: 실패 시 오류 메시지
        """
        # 현재 시각 (UTC, ISO 형식)
        now: str = datetime.now(timezone.utc).isoformat()

        # SQL 파라미터 구성
        set_clauses: list[str] = ["status = ?"]
        values: list = [status]

        # RUNNING 상태 전환 시 started_at 기록
        if status == "RUNNING":
            set_clauses.append("started_at = ?")
            values.append(now)

        # 최종 상태(DONE, FAILED, CANCELLED) 전환 시 finished_at 기록
        if status in ("DONE", "FAILED", "CANCELLED"):
            set_clauses.append("finished_at = ?")
            values.append(now)

        # 결과 저장 (JSON 직렬화)
        if result is not None:
            set_clauses.append("result = ?")
            values.append(json.dumps(result, ensure_ascii=False))

        # 오류 메시지 저장
        if error is not None:
            set_clauses.append("error_message = ?")
            values.append(error)

        # task_id를 WHERE 조건으로 추가
        values.append(task_id)

        sql: str = f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?"

        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                conn.execute(sql, values)
                conn.commit()
                logger.info(f"[task_id={task_id}] 상태 업데이트: {status}")
            finally:
                conn.close()
        except sqlite3.Error as e:
            # DB 업데이트 실패는 로그만 기록하고 파이프라인 실행은 계속
            logger.error(f"[task_id={task_id}] DB 상태 업데이트 실패: {e}")

    # ------------------------------------------------------------------
    # 유틸 메서드 — DB 선택 모델 조회
    # ------------------------------------------------------------------

    def _get_selected_model(self) -> Optional[str]:
        """DB settings 테이블에서 사용자가 선택한 모델명을 읽는다."""
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                cursor = conn.execute(
                    "SELECT value FROM settings WHERE key = 'selected_model'"
                )
                row = cursor.fetchone()
                return row[0] if row else None
            finally:
                conn.close()
        except sqlite3.Error:
            return None

    # ------------------------------------------------------------------
    # 유틸 메서드 — Ollama 동기 호출
    # ------------------------------------------------------------------

    def call_ollama(
        self,
        prompt: str,
        timeout: int = 120,
        model: Optional[str] = None,
        num_ctx: int = 8192,
        num_predict: int = 4096,
    ) -> str:
        """
        Ollama /api/generate 엔드포인트를 동기적으로 호출하고 응답 텍스트를 반환한다.

        Args:
            model: 사용할 Ollama 모델명 (예: "llama3.2")
            prompt: LLM에 전달할 프롬프트 문자열
            timeout: HTTP 요청 타임아웃 초 (기본 120초)
            num_ctx: Ollama 컨텍스트 윈도우 크기 (기본 8192 토큰)
            num_predict: 최대 생성 토큰 수 (기본 4096)

        Returns:
            LLM이 생성한 텍스트 응답

        Raises:
            RuntimeError: Ollama 호출 실패 또는 모든 폴백 모델이 실패한 경우
        """
        # 시도할 모델 목록 구성 — DB 선택 모델 → 인자 모델 → 폴백 순서
        models_to_try: list[str] = []
        selected = self._get_selected_model()
        if selected:
            models_to_try.append(selected)
        if model and model not in models_to_try:
            models_to_try.append(model)
        for fallback in OLLAMA_MODEL_FALLBACK:
            if fallback not in models_to_try:
                models_to_try.append(fallback)

        last_error: Optional[Exception] = None

        for current_model in models_to_try:
            try:
                logger.info(f"Ollama 호출 시작 — 모델: {current_model}")

                # httpx 동기 클라이언트로 Ollama API 호출
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": current_model,
                            "prompt": prompt,
                            "stream": False,  # 스트리밍 비활성화 (동기 단순 호출)
                            "options": {
                                "num_ctx": num_ctx,
                                "num_predict": num_predict,
                                "temperature": 0.7,
                            },
                        },
                    )
                    response.raise_for_status()

                # 응답 파싱
                data: dict = response.json()
                generated_text: str = data.get("response", "")

                if not generated_text:
                    raise RuntimeError(f"Ollama 응답이 비어 있음 — 모델: {current_model}")

                logger.info(f"Ollama 호출 성공 — 모델: {current_model}, 응답 길이: {len(generated_text)}자")
                return generated_text

            except httpx.HTTPStatusError as e:
                # 404 = 모델 없음 → 다음 폴백 모델 시도
                if e.response.status_code == 404:
                    logger.warning(f"모델 '{current_model}' 없음 — 다음 모델 시도")
                    last_error = e
                    continue
                else:
                    last_error = e
                    logger.error(f"Ollama HTTP 오류 — 모델: {current_model}, 상태: {e.response.status_code}")
                    continue

            except httpx.TimeoutException as e:
                last_error = e
                logger.error(f"Ollama 타임아웃 — 모델: {current_model}, 제한: {timeout}초")
                continue

            except httpx.ConnectError as e:
                # Ollama 서버 미실행 → 즉시 실패 (다른 모델 시도해도 동일)
                raise RuntimeError(
                    f"Ollama 서버에 연결할 수 없음. "
                    f"Ollama가 실행 중인지 확인하세요. (주소: {OLLAMA_BASE_URL})"
                ) from e

            except Exception as e:
                last_error = e
                logger.error(f"Ollama 호출 예외 — 모델: {current_model}: {e}")
                continue

        # 모든 모델 시도 실패
        raise RuntimeError(
            f"모든 Ollama 모델 호출 실패. 시도한 모델: {models_to_try}. "
            f"마지막 오류: {last_error}"
        )

    # ------------------------------------------------------------------
    # 유틸 메서드 — Tavily 검색 (동기)
    # ------------------------------------------------------------------

    def call_tavily(
        self,
        query: str,
        max_results: int = 20,
        days: int = 2,
        include_domains: Optional[list[str]] = None,
        search_depth: str = "basic",
    ) -> list[dict]:
        """
        Tavily REST API로 인터넷 검색을 수행하고 결과 리스트를 반환한다.

        Args:
            query: 검색어
            max_results: 최대 결과 수 (기본 20, 최대 20)
            days: 검색 기간 (최근 N일, 기본 2일)
            include_domains: 검색 대상 도메인 필터 (None이면 전체)
            search_depth: "basic"(1크레딧) 또는 "advanced"(2크레딧)

        Returns:
            [{"title": str, "url": str, "content": str, "score": float}, ...]

        Raises:
            RuntimeError: API 키 미설정 또는 Tavily 호출 실패
        """
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY 환경변수가 설정되지 않았습니다.")

        payload: dict = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "days": days,
        }
        if include_domains:
            payload["include_domains"] = include_domains

        logger.info(f"Tavily 검색 시작 — query: {query!r}, days: {days}, domains: {include_domains}")

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(TAVILY_API_URL, json=payload)
                resp.raise_for_status()
                results = resp.json().get("results", [])
                logger.info(f"Tavily 검색 완료 — {len(results)}건 수신")
                return results
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Tavily API 오류: HTTP {e.response.status_code}") from e
        except Exception as e:
            raise RuntimeError(f"Tavily 검색 실패: {e}") from e

    # ------------------------------------------------------------------
    # 유틸 메서드 — SearXNG 검색 (동기)
    # ------------------------------------------------------------------

    def call_searxng(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[dict]:
        """
        SearXNG 로컬 인스턴스에서 검색하고 결과 리스트를 반환한다.

        결과는 Tavily 형식과 동일한 dict 구조를 사용해 파이프라인 코드 공용화를 유지한다.
        단, content 필드는 SearXNG 스니펫이므로 enrich_results()로 본문 보강을 권장한다.

        Args:
            query: 검색어
            max_results: 최대 결과 수 (기본 20)

        Returns:
            [{"title": str, "url": str, "content": str}, ...]

        Raises:
            RuntimeError: SearXNG 서버 연결 실패 또는 검색 오류
        """
        params = {
            "q": query,
            "format": "json",
            "categories": "general",
        }
        logger.info(f"SearXNG 검색 시작 — query: {query!r}, max_results: {max_results}")
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(f"{SEARXNG_BASE_URL}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])[:max_results]
            ]
            logger.info(f"SearXNG 검색 완료 — {len(results)}건 수신")
            return results

        except httpx.ConnectError as e:
            raise RuntimeError(
                f"SearXNG 서버에 연결할 수 없음. (주소: {SEARXNG_BASE_URL})"
            ) from e
        except Exception as e:
            raise RuntimeError(f"SearXNG 검색 실패: {e}") from e

    # ------------------------------------------------------------------
    # 유틸 메서드 — 취소 감지
    # ------------------------------------------------------------------

    def is_cancelled(self, task_id: int) -> bool:
        """
        DB에서 해당 task의 status가 'CANCELLED'인지 확인한다.
        파이프라인 실행 중 주기적으로 호출하여 중단 여부를 감지한다.

        Args:
            task_id: 확인할 task의 ID

        Returns:
            CANCELLED 상태이면 True, 아니면 False
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                cursor = conn.execute(
                    "SELECT status FROM tasks WHERE id = ?", (task_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    logger.warning(f"[task_id={task_id}] task를 찾을 수 없음")
                    return False
                return row[0] == "CANCELLED"
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"[task_id={task_id}] 취소 상태 확인 실패: {e}")
            return False

    # ------------------------------------------------------------------
    # 유틸 메서드 — shared.content_extractor 래퍼
    # ------------------------------------------------------------------

    def enrich_results(
        self,
        results: list[dict],
        max_per_result: int = 3000,
    ) -> list[dict]:
        """
        검색 결과 리스트를 URL 크롤링으로 본문 보강한다.
        shared.content_extractor를 임포트할 수 없으면 원본 리스트를 그대로 반환한다.

        Args:
            results: [{"title", "url", "snippet"|"content", ...}, ...] 형태의 검색 결과
            max_per_result: 항목당 최대 본문 길이 (문자)

        Returns:
            body_text 필드가 추가된 동일 구조의 리스트
        """
        if not _SHARED_AVAILABLE:
            logger.warning("shared.content_extractor 사용 불가 — 크롤링 생략")
            return results
        return enrich_search_results(results, max_per_result=max_per_result)

    # ------------------------------------------------------------------
    # 유틸 메서드 — shared.multihop_search 래퍼
    # ------------------------------------------------------------------

    def multihop_search(
        self,
        query: str,
        provider: str = "searxng",
        max_hops: int = 2,
        results_per_hop: int = 10,
        subqueries_per_hop: int = 3,
        enrich: bool = True,
        days: int = 0,
        categories: str = "general",
    ):
        """
        멀티 홉 검색을 수행하고 MultiHopResult를 반환한다.
        shared.multihop_search를 사용하며, 사용 불가 시 단순 검색으로 폴백한다.

        Args:
            query: 검색어
            provider: 'searxng' | 'tavily'
            max_hops: 최대 홉 수 (기본 2, 1이면 단순 1회 검색)
            results_per_hop: 홉당 수집 결과 수 (기본 10)
            subqueries_per_hop: 홉당 생성할 서브쿼리 수 (기본 3)
            enrich: URL 크롤링 본문 보강 여부
            days: 최근 N일 이내 결과만 수집 (0이면 날짜 필터 없음)
            categories: SearXNG 카테고리 (general/news). Tavily는 무시.
        """
        if not _SHARED_AVAILABLE:
            logger.warning("shared 사용 불가 — 단순 검색으로 폴백")
            return self._multihop_fallback(query, provider, results_per_hop, enrich)

        try:
            from shared.multihop_search import multihop_search as _mh
            return _mh(
                query=query,
                provider=provider,
                max_hops=max_hops,
                results_per_hop=results_per_hop,
                subqueries_per_hop=subqueries_per_hop,
                enrich=enrich,
                days=days,
                categories=categories,
            )
        except Exception as e:
            logger.error(f"multihop_search 실패 — 단순 검색으로 폴백: {e}")
            return self._multihop_fallback(query, provider, results_per_hop, enrich)

    def _multihop_fallback(
        self,
        query: str,
        provider: str,
        results_per_hop: int,
        enrich: bool,
    ):
        """multihop_search 실패 시 단순 검색 결과를 MultiHopResult 형태로 반환."""
        try:
            from shared.multihop_search import MultiHopResult, build_context_text
        except ImportError:
            # shared 완전 불가 — 최소 duck-typing 객체 반환
            class _Dummy:
                results: list = []
                context_text: str = ""
                hops_executed: int = 1
            return _Dummy()

        if provider == "tavily":
            raw = self.call_tavily(query=query, max_results=results_per_hop)
        else:
            raw = self.call_searxng(query=query, max_results=results_per_hop)

        if enrich and provider == "searxng":
            raw = self.enrich_results(raw)

        # hop 정보 태깅
        for r in raw:
            r.setdefault("hop", 1)
            r.setdefault("hop_query", "")

        return MultiHopResult(
            query=query,
            provider=provider,
            hops_executed=1,
            results=raw,
            context_text=build_context_text(query, raw),
        )

    # ------------------------------------------------------------------
    # 유틸 메서드 — shared.prompt_builder 래퍼
    # ------------------------------------------------------------------

    def build_prompt(
        self,
        question: str,
        search_context: Optional[str] = None,
        history: Optional[list[dict]] = None,
    ) -> str:
        """
        질문 의도를 파악하고 최적화된 프롬프트를 구성해 반환한다.
        shared.prompt_builder를 임포트할 수 없으면 question을 그대로 반환한다.

        Args:
            question: LLM에 전달할 질문 텍스트
            search_context: 검색 결과 컨텍스트 텍스트 (없으면 None)
            history: 이전 대화 이력 [{"role", "content"}, ...] (없으면 None)

        Returns:
            LLM에 전달할 최종 프롬프트 문자열
        """
        if not _SHARED_AVAILABLE:
            logger.warning("shared.prompt_builder 사용 불가 — 원본 질문 사용")
            return question
        return build_optimized_prompt(
            question=question,
            history=history,
            search_context=search_context,
        )
