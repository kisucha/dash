# 목적: /api/search 인터넷 검색 엔드포인트
# provider: searxng(기본, 로컬 SearXNG 인스턴스) | tavily(유료, LLM 최적화)
# enrich=True(기본) 시 각 URL을 크롤링해 본문 텍스트를 추출·정제해서 반환
import sys
import os

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import httpx
import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from shared.content_extractor import enrich_search_results_async
from core.config import OLLAMA_BASE_URL, DB_PATH

router = APIRouter(prefix="/api/search", tags=["search"])

# SearXNG 로컬 인스턴스 주소
SEARXNG_BASE_URL = "http://192.168.20.80:8888"

# Tavily REST API 주소
TAVILY_API_URL = "https://api.tavily.com/search"


class SearchRequest(BaseModel):
    """POST /api/search 요청 바디."""
    query: str = Field(..., description="검색어")
    max_results: int = Field(default=20, ge=1, le=20, description="최대 결과 수")
    provider: str = Field(
        default="searxng",
        description="검색 엔진: searxng(기본) | tavily",
    )
    # 각 URL을 크롤링해 본문을 추출할지 여부 (기본 True)
    enrich: bool = Field(default=True, description="URL 크롤링으로 본문 보강 여부")
    # 멀티 홉 검색 여부 — True이면 1차 결과 제목으로 추가 검색을 N차까지 수행
    multihop: bool = Field(default=False, description="멀티 홉 심층 검색 여부")
    # 최대 홉 수 (multihop=True일 때 사용, 기본 3)
    max_hops: int = Field(default=3, ge=1, le=5, description="최대 홉 수 (1~5)")
    # 최근 N일 이내 결과만 수집 (0이면 날짜 필터 없음)
    days: int = Field(default=0, ge=0, description="최근 N일 이내 결과 필터 (0=전체)")
    # LLM 심층 서브쿼리 생성 여부 — True이면 각 hop 후 Ollama로 depth-first 쿼리 생성
    use_llm_subqueries: bool = Field(default=False, description="LLM 기반 심층 서브쿼리 생성")


class SearchResult(BaseModel):
    """검색 결과 단건."""
    title: str
    url: str
    snippet: str
    # 크롤링으로 추출한 정제 본문 (enrich=True일 때 채워짐, 실패 시 snippet과 동일)
    body_text: str = ""


class SearchResponse(BaseModel):
    """POST /api/search 응답."""
    query: str
    provider: str
    results: list[SearchResult]
    context_text: str
    # 실제 수행된 홉 수 (multihop=False이면 항상 1)
    hops_executed: int = 1


def _build_context_text(query: str, results: list[SearchResult]) -> str:
    """
    검색 결과를 LLM 프롬프트에 삽입할 형태로 변환한다.
    body_text가 있으면 body_text를, 없으면 snippet을 내용으로 사용한다.
    """
    if not results:
        return f'"{query}"에 대한 검색 결과가 없습니다.'
    lines: list[str] = [f'검색어: {query}', '']
    for i, r in enumerate(results, 1):
        # 크롤링 본문 우선, 없으면 스니펫 사용
        content = r.body_text if r.body_text else r.snippet
        lines.append(f"{i}. {r.title}")
        lines.append(f"   출처: {r.url}")
        lines.append(f"   내용: {content}")
        lines.append('')
    return '\n'.join(lines)


# ── SearXNG ───────────────────────────────────────────────────────────────────

async def _search_searxng(query: str, max_results: int) -> list[SearchResult]:
    """SearXNG JSON API로 검색한다."""
    params = {
        "q": query,
        "format": "json",
        "categories": "general",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{SEARXNG_BASE_URL}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=f"SearXNG 서버에 연결할 수 없습니다. ({SEARXNG_BASE_URL})",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"SearXNG 오류: HTTP {e.response.status_code}",
        )

    results: list[SearchResult] = []
    for item in data.get("results", [])[:max_results]:
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
        ))
    return results


# ── Tavily ────────────────────────────────────────────────────────────────────

async def _search_tavily(query: str, max_results: int) -> list[SearchResult]:
    """Tavily REST API로 검색한다."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="TAVILY_API_KEY 환경변수가 설정되지 않았습니다.",
        )
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(TAVILY_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Tavily API 오류: HTTP {e.response.status_code}",
        )

    return [
        SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
        )
        for item in data.get("results", [])
    ]


# ── 보강(enrich) 처리 ─────────────────────────────────────────────────────────

async def _enrich(results: list[SearchResult]) -> list[SearchResult]:
    """
    SearchResult 리스트를 dict로 변환 → 크롤링 보강 → SearchResult로 재변환한다.
    크롤링 실패 항목은 snippet이 body_text로 그대로 사용된다.
    """
    raw_dicts = [
        {"title": r.title, "url": r.url, "snippet": r.snippet}
        for r in results
    ]
    enriched_dicts = await enrich_search_results_async(raw_dicts)
    return [
        SearchResult(
            title=d["title"],
            url=d["url"],
            snippet=d["snippet"],
            body_text=d.get("body_text", ""),
        )
        for d in enriched_dicts
    ]


# ── 엔드포인트 ────────────────────────────────────────────────────────────────

@router.post("", response_model=SearchResponse)
async def search_web(request: SearchRequest) -> SearchResponse:
    """
    인터넷 검색을 수행하고 결과를 반환한다.

    provider=searxng : 로컬 SearXNG 인스턴스 — 무제한, 빠름 (기본)
    provider=tavily  : Tavily API — 1크레딧/호출, LLM 최적화
    enrich=True      : 각 URL을 크롤링해 본문 텍스트를 추출·정제 (기본)
    enrich=False     : 스니펫만 사용 (빠름)
    multihop=True    : 1차 결과 제목으로 서브쿼리 생성 후 N차까지 심층 검색
    max_hops         : 멀티 홉 최대 홉 수 (기본 3)
    """
    # 멀티 홉 검색 — shared.multihop_search 엔진 사용
    if request.multihop:
        from shared.multihop_search import multihop_search_async

        # LLM 서브쿼리 사용 시 DB에서 선택 모델을 조회
        llm_model = "exaone3.5:2.4b"
        if request.use_llm_subqueries:
            async with aiosqlite.connect(DB_PATH) as conn:
                cur = await conn.execute("SELECT value FROM settings WHERE key='selected_model'")
                row = await cur.fetchone()
                if row and row[0]:
                    llm_model = row[0]

        mh = await multihop_search_async(
            query=request.query,
            provider=request.provider,
            max_hops=request.max_hops,
            results_per_hop=min(5, request.max_results),
            enrich=request.enrich,
            days=request.days,
            use_llm_subqueries=request.use_llm_subqueries,
            ollama_url=OLLAMA_BASE_URL,
            model=llm_model,
        )
        results = [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("snippet", ""),
                body_text=r.get("body_text", ""),
            )
            for r in mh.results
        ]
        return SearchResponse(
            query=request.query,
            provider=request.provider,
            results=results,
            context_text=mh.context_text,
            hops_executed=mh.hops_executed,
        )

    # 단순 1회 검색 (기존 방식)
    if request.provider == "tavily":
        results = await _search_tavily(request.query, request.max_results)
    else:
        results = await _search_searxng(request.query, request.max_results)

    if request.enrich and results:
        results = await _enrich(results)

    return SearchResponse(
        query=request.query,
        provider=request.provider,
        results=results,
        context_text=_build_context_text(request.query, results),
        hops_executed=1,
    )
