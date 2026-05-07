# 목적: 범용 멀티 홉 검색 엔진
# 1차 검색 결과 제목에서 서브쿼리를 자동 생성해 N차까지 재귀 검색한다.
# FastAPI(비동기 multihop_search_async)와 파이프라인(동기 multihop_search) 양쪽 지원.
# 채팅/파이프라인 등 어느 레이어에서든 import하여 동일하게 사용한다.

import sys
import os
import re
import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import httpx

try:
    from shared.content_extractor import enrich_search_results_async
    _ENRICH_AVAILABLE = True
except ImportError:
    _ENRICH_AVAILABLE = False

# ── 설정 — 환경변수 우선, 없으면 기본값 ───────────────────────────────────────
SEARXNG_BASE_URL: str = os.getenv("SEARXNG_BASE_URL", "http://192.168.20.80:8888")
TAVILY_API_URL: str = "https://api.tavily.com/search"

# 검색 요청 타임아웃 (초)
_SEARCH_TIMEOUT: float = 10.0

# 조기 종료 — 새 결과 수가 이 미만이면 다음 hop 중단
_MIN_NEW_RESULTS: int = 2

# 조기 종료 — 새 결과 중 이미 수집한 URL 비율이 이 이상이면 중단
_DUPLICATE_THRESHOLD: float = 0.7


# ── 반환 타입 ──────────────────────────────────────────────────────────────────

@dataclass
class MultiHopResult:
    """멀티 홉 검색 결과 컨테이너."""
    query: str
    provider: str
    hops_executed: int
    results: list[dict] = field(default_factory=list)
    context_text: str = ""


# ── 내부 검색 함수 ─────────────────────────────────────────────────────────────

def _days_to_time_range(days: int) -> str:
    """
    정수 days → SearXNG time_range 문자열 변환.
    0 이하면 빈 문자열 반환 (날짜 필터 없음).
    """
    if days <= 0:
        return ""
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "year"


async def _search_searxng_async(
    query: str,
    max_results: int,
    time_range: str = "",
    categories: str = "general",
) -> list[dict]:
    """SearXNG 비동기 검색 — 실패 시 빈 리스트 반환.

    Args:
        time_range: 날짜 필터 (day/week/month/year). 빈 문자열이면 필터 없음.
        categories: SearXNG 검색 카테고리 (general/news/images 등).
            news는 뉴스 소스만 조회하므로 publishedDate가 포함되어 최신성 보장에 유리.
    """
    params: dict = {"q": query, "format": "json", "categories": categories}
    if time_range:
        params["time_range"] = time_range
    try:
        async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
            resp = await client.get(f"{SEARXNG_BASE_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in data.get("results", [])[:max_results]
            ]
    except Exception:
        return []


async def _search_tavily_async(query: str, max_results: int, days: int = 0) -> list[dict]:
    """Tavily 비동기 검색 — API 키 미설정 또는 실패 시 빈 리스트 반환.

    Args:
        days: 최근 N일 이내 결과만 반환. 0이면 필터 없음.
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return []
    payload: dict = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    if days > 0:
        payload["days"] = days
    try:
        async with httpx.AsyncClient(timeout=_SEARCH_TIMEOUT) as client:
            resp = await client.post(TAVILY_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                }
                for r in data.get("results", [])
            ]
    except Exception:
        return []


# ── 서브쿼리 생성 ──────────────────────────────────────────────────────────────

def _extract_next_queries(
    results: list[dict],
    original_query: str,
    seen_queries: set[str],
    n: int = 3,
) -> list[str]:
    """
    결과 제목에서 다음 hop 서브쿼리를 생성한다.

    - 각 제목의 앞 5단어를 원본 쿼리와 결합해 구체적인 쿼리를 만든다.
    - 이미 검색한 쿼리(seen_queries)와 중복되는 것은 건너뛴다.
    - 최대 n개 반환.
    """
    candidates: list[str] = []
    seen_titles: set[str] = set()

    for r in results:
        title = r.get("title", "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        # 제목이 6단어 초과면 앞 5단어만 사용
        words = title.split()
        short_title = " ".join(words[:5]) if len(words) > 5 else title

        candidate = f"{short_title} {original_query}".strip()
        if candidate not in seen_queries:
            candidates.append(candidate)
            seen_queries.add(candidate)

        if len(candidates) >= n:
            break

    return candidates


async def _generate_subqueries_llm_async(
    results: list[dict],
    original_query: str,
    n: int = 3,
    ollama_url: str = "http://localhost:11434",
    model: str = "exaone3.5:2.4b",
    timeout: float = 30.0,
) -> list[str]:
    """
    LLM으로 현재 hop 결과를 분석해 심층 탐색 서브쿼리를 생성한다.

    hop 1에서 발견한 핵심 엔티티(영화명·인물·제품 등)를 파악하고,
    원래 질문에 더 완전히 답하기 위한 구체적 심층 검색어를 생성한다.
    실패 시 빈 리스트 반환 → 호출부에서 _extract_next_queries로 폴백.
    """
    # 상위 5개 결과의 제목+스니펫으로 컨텍스트 구성 (프롬프트 크기 절약)
    result_lines: list[str] = []
    for r in results[:5]:
        title = r.get("title", "").strip()
        snippet = (r.get("body_text") or r.get("snippet", "")).strip()[:200]
        if title:
            result_lines.append(f"- {title}: {snippet}")

    if not result_lines:
        return []

    result_text = "\n".join(result_lines)
    prompt = (
        f"아래는 인터넷 검색 결과 요약이다.\n\n"
        f"{result_text}\n\n"
        f"원래 질문: {original_query}\n\n"
        f"위 결과를 토대로, 원래 질문에 더 완전하게 답하기 위해 추가로 검색해야 할 "
        f"구체적인 검색어 {n}개를 한 줄씩만 출력하라.\n\n"
        f"규칙:\n"
        f"- 검색어만 출력하고 다른 설명은 절대 쓰지 마라\n"
        f"- 결과에서 발견된 구체적 고유명사(영화명·인물·제품·브랜드)를 포함\n"
        f"- 이미 알게 된 사실을 보완하는 심층 정보를 얻기 위한 검색어\n"
        f"- 예: 'Anora'가 발견됐다면 → 'Anora 영화 줄거리 감독 출연진'\n"
        f"검색어:"
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()

        queries: list[str] = []
        for line in raw.splitlines():
            line = re.sub(r'^[\d]+[.)]\s*', '', line.strip()).strip()
            line = re.sub(r'^[-*]\s*', '', line).strip()
            if line and len(line) > 2:
                queries.append(line)
            if len(queries) >= n:
                break

        return queries

    except Exception as e:
        logger.warning("LLM 서브쿼리 생성 실패 (%s) — breadth-first 폴백 사용", e)
        return []


# ── 본문 보강 ──────────────────────────────────────────────────────────────────

async def _enrich_async(results: list[dict]) -> list[dict]:
    """URL 크롤링으로 body_text 보강 — content_extractor 사용 불가 시 원본 반환."""
    if not _ENRICH_AVAILABLE:
        return results
    try:
        return await enrich_search_results_async(results)
    except Exception:
        return results


# ── 컨텍스트 텍스트 빌더 ───────────────────────────────────────────────────────

def build_context_text(initial_query: str, all_results: list[dict]) -> str:
    """
    모든 hop 결과를 LLM 프롬프트용 텍스트로 변환한다.
    hop 구분선을 포함해 각 차수의 검색 쿼리와 결과를 구조화해서 표시한다.
    """
    if not all_results:
        return f'"{initial_query}"에 대한 검색 결과가 없습니다.'

    lines: list[str] = [f"검색어: {initial_query}", ""]
    current_hop = -1

    for r in all_results:
        hop = r.get("hop", 1)
        if hop != current_hop:
            if current_hop != -1:
                lines.append("")
            hop_query = r.get("hop_query", "")
            if hop == 1:
                lines.append("[1차 검색 결과]")
            else:
                lines.append(f"[{hop}차 심층 검색: {hop_query}]")
            current_hop = hop

        title = r.get("title", "")
        # body_text(크롤링 본문) 우선, 없으면 snippet 사용
        content = r.get("body_text") or r.get("snippet", "")

        lines.append(f"- {title}")
        if content:
            lines.append(f"  {content}")

    return "\n".join(lines)


# ── 메인 멀티 홉 함수 (비동기) ────────────────────────────────────────────────

async def multihop_search_async(
    query: str,
    provider: str = "searxng",
    max_hops: int = 3,
    results_per_hop: int = 5,
    subqueries_per_hop: int = 3,
    enrich: bool = True,
    days: int = 0,
    categories: str = "general",
    use_llm_subqueries: bool = False,
    ollama_url: str = "http://localhost:11434",
    model: str = "exaone3.5:2.4b",
) -> MultiHopResult:
    """
    범용 멀티 홉 검색 (비동기).

    흐름:
        1차: search(query)
        → 결과 제목에서 서브쿼리 subqueries_per_hop개 생성
        → 2차: 서브쿼리 병렬 검색
        → ... max_hops까지 반복

    조기 종료 조건 (둘 중 하나 충족 시):
        - 새 결과 수 < _MIN_NEW_RESULTS (2개)
        - 새 결과 중 중복 URL 비율 >= _DUPLICATE_THRESHOLD (70%)

    Args:
        query: 초기 검색어
        provider: 'searxng' | 'tavily'
        max_hops: 최대 홉 수 (기본 3, 1이면 단순 1회 검색)
        results_per_hop: 홉당 수집 결과 수 (기본 5)
        subqueries_per_hop: 홉당 생성할 서브쿼리 수 (기본 3)
        enrich: URL 크롤링 본문 보강 여부
        days: 최근 N일 이내 결과만 수집 (0이면 날짜 필터 없음)
            SearXNG: days→time_range 자동 변환 (2→week, 8→month 등)
            Tavily: days 값을 API에 직접 전달
        categories: SearXNG 검색 카테고리 (general/news). Tavily는 무시.
            news — 뉴스 소스만 조회, publishedDate 포함, 최신성 보장
            general — 일반 웹 전체, 블로그/튜토리얼 포함 (기본)
        use_llm_subqueries: True이면 각 hop 후 LLM이 심층 서브쿼리를 생성한다.
            발견된 핵심 엔티티를 파고드는 depth-first 탐색.
            False이면 결과 제목 앞 5단어 조합으로 breadth-first 탐색 (기본).
        ollama_url: LLM 서브쿼리 생성에 사용할 Ollama 서버 주소.
        model: LLM 서브쿼리 생성에 사용할 모델명.

    Returns:
        MultiHopResult — 모든 hop 결과 합산
    """
    # days/categories를 각 검색 엔진에 맞는 형태로 고정한 검색 함수를 클로저로 생성
    if provider == "tavily":
        async def search_fn(q: str, n: int) -> list[dict]:
            return await _search_tavily_async(q, n, days=days)
    else:
        time_range = _days_to_time_range(days)
        async def search_fn(q: str, n: int) -> list[dict]:
            return await _search_searxng_async(q, n, time_range=time_range, categories=categories)

    all_results: list[dict] = []
    seen_urls: set[str] = set()
    seen_queries: set[str] = {query}
    current_queries: list[str] = [query]
    hops_executed: int = 0

    for hop in range(1, max_hops + 1):
        hops_executed = hop

        # 현재 hop의 모든 쿼리를 병렬 검색
        tasks = [search_fn(q, results_per_hop) for q in current_queries]
        results_by_query = await asyncio.gather(*tasks, return_exceptions=True)

        # 새 결과 수집 — 중복 URL 제거하고 hop 정보 태깅
        new_results: list[dict] = []
        duplicate_count: int = 0

        for q, results in zip(current_queries, results_by_query):
            if isinstance(results, Exception) or not results:
                continue
            for r in results:
                url = r.get("url", "")
                if url and url in seen_urls:
                    duplicate_count += 1
                    continue
                if url:
                    seen_urls.add(url)
                r_copy = dict(r)
                r_copy["hop"] = hop
                # 1차 검색(원본 쿼리)이면 hop_query 비워 컨텍스트에서 헤더를 단순하게 유지
                r_copy["hop_query"] = q if q != query else ""
                new_results.append(r_copy)

        # URL 크롤링으로 본문 보강
        if enrich and new_results:
            new_results = await _enrich_async(new_results)

        all_results.extend(new_results)

        # 조기 종료 판단 1: 새 결과가 너무 적음
        if len(new_results) < _MIN_NEW_RESULTS:
            break

        # 조기 종료 판단 2: 중복 URL이 너무 많음
        total_checked = len(new_results) + duplicate_count
        if total_checked > 0 and duplicate_count / total_checked >= _DUPLICATE_THRESHOLD:
            break

        if hop >= max_hops:
            break

        # 다음 hop 쿼리 생성
        if use_llm_subqueries:
            # LLM으로 심층 서브쿼리 생성 — 발견된 핵심 엔티티를 파고드는 depth-first
            llm_queries = await _generate_subqueries_llm_async(
                results=new_results,
                original_query=query,
                n=subqueries_per_hop,
                ollama_url=ollama_url,
                model=model,
            )
            # seen_queries 필터링
            next_queries = [q for q in llm_queries if q not in seen_queries]
            for q in next_queries:
                seen_queries.add(q)
            if next_queries:
                logger.debug("hop %d LLM 서브쿼리 생성 성공: %s", hop, next_queries)
            else:
                # LLM 실패·중복 소진 시 breadth-first로 폴백
                logger.info("hop %d LLM 서브쿼리 없음 — breadth-first 폴백", hop)
                next_queries = _extract_next_queries(new_results, query, seen_queries, n=subqueries_per_hop)
        else:
            # 기존 breadth-first: 결과 제목 앞 5단어 + 원본 쿼리 조합
            next_queries = _extract_next_queries(new_results, query, seen_queries, n=subqueries_per_hop)

        if not next_queries:
            break

        current_queries = next_queries

    context = build_context_text(query, all_results)
    return MultiHopResult(
        query=query,
        provider=provider,
        hops_executed=hops_executed,
        results=all_results,
        context_text=context,
    )


# ── 동기 래퍼 — 파이프라인(독립 프로세스)에서 사용 ────────────────────────────

def multihop_search(
    query: str,
    provider: str = "searxng",
    max_hops: int = 3,
    results_per_hop: int = 5,
    subqueries_per_hop: int = 3,
    enrich: bool = True,
    days: int = 0,
    categories: str = "general",
    use_llm_subqueries: bool = False,
    ollama_url: str = "http://localhost:11434",
    model: str = "exaone3.5:2.4b",
) -> MultiHopResult:
    """
    multihop_search_async의 동기 래퍼.
    파이프라인(독립 프로세스)에서 사용한다.
    이미 실행 중인 이벤트 루프가 있는 환경(FastAPI 내부)에서는 호출하면 안 된다.
    """
    return asyncio.run(
        multihop_search_async(
            query=query,
            provider=provider,
            max_hops=max_hops,
            results_per_hop=results_per_hop,
            subqueries_per_hop=subqueries_per_hop,
            enrich=enrich,
            days=days,
            categories=categories,
            use_llm_subqueries=use_llm_subqueries,
            ollama_url=ollama_url,
            model=model,
        )
    )
