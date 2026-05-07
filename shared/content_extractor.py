# 목적: URL을 크롤링하고 본문을 추출·정제하는 공유 유틸리티
# 파싱 전략: trafilatura 1순위 → BeautifulSoup 폴백
# 동기(파이프라인 독립 프로세스용)와 비동기(FastAPI 라우터용) 두 가지 인터페이스 제공

import sys
import re
import asyncio

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import httpx
import trafilatura
from bs4 import BeautifulSoup

# ── 설정 상수 ──────────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT: float = 8.0
_DEFAULT_MAX_CHARS: int = 3000

# trafilatura 결과가 이 글자 수 미만이면 BeautifulSoup 폴백 시도
_TRAFILATURA_MIN_CHARS: int = 300

# 병렬 크롤링 최대 URL 수
_MAX_CONCURRENT: int = 5

# BeautifulSoup 폴백용 — 제거할 HTML 태그
_NOISE_TAGS: list[str] = [
    'script', 'style', 'nav', 'header', 'footer', 'aside',
    'iframe', 'form', 'button', 'noscript', 'figure', 'figcaption',
    'meta', 'link', 'head',
]

# BeautifulSoup 폴백용 — 제거할 class/id 키워드
_NOISE_KEYWORDS: list[str] = [
    'ad', 'ads', 'advert', 'advertisement', 'advertorial',
    'sidebar', 'side-bar', 'sidenav', 'menu', 'nav', 'navigation',
    'header', 'footer', 'topbar', 'cookie', 'popup', 'modal',
    'banner', 'widget', 'related', 'recommend', 'share', 'sharing',
    'comment', 'social', 'follow', 'subscribe', 'newsletter',
    'promo', 'promotion', 'sponsor', 'sponsored',
]

# BeautifulSoup 폴백용 — 본문 후보 클래스 패턴
_CONTENT_CLASS_PATTERNS: list[str] = [
    r'article', r'post[-_]?content', r'entry[-_]?content',
    r'article[-_]?body', r'main[-_]?content', r'story[-_]?body',
    r'post[-_]?body', r'article[-_]?text', r'body[-_]?text',
    r'news[-_]?content', r'page[-_]?content',
]

# 크롤링 요청 헤더
_HEADERS: dict[str, str] = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

# 파서 이름 상수 — body_parser 필드에 기록됨
PARSER_TRAFILATURA = "trafilatura"
PARSER_BEAUTIFULSOUP = "BeautifulSoup"


# ── BeautifulSoup 폴백 내부 함수 ──────────────────────────────────────────────

def _bs_remove_noise(soup: BeautifulSoup) -> None:
    for tag_name in _NOISE_TAGS:
        for el in soup.find_all(tag_name):
            el.decompose()
    for el in soup.find_all(True):
        el_class = ' '.join(el.get('class', [])).lower()
        el_id = el.get('id', '').lower()
        combined = el_class + ' ' + el_id
        if any(kw in combined for kw in _NOISE_KEYWORDS):
            el.decompose()


def _bs_find_content(soup: BeautifulSoup):
    el = soup.find('article')
    if el:
        return el
    el = soup.find('main')
    if el:
        return el
    for pattern in _CONTENT_CLASS_PATTERNS:
        el = soup.find(class_=re.compile(pattern, re.I))
        if el:
            return el
    return soup.find('body') or soup


def _bs_clean_text(raw: str) -> str:
    lines = [l.strip() for l in raw.splitlines() if len(l.strip()) >= 20]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def _bs_extract(html: str, max_chars: int) -> str:
    """BeautifulSoup으로 본문을 추출한다."""
    soup = BeautifulSoup(html, 'lxml')
    _bs_remove_noise(soup)
    content_el = _bs_find_content(soup)
    raw = content_el.get_text(separator='\n')
    return _bs_clean_text(raw)[:max_chars]


# ── 핵심 파싱 함수 — trafilatura 1순위, BeautifulSoup 폴백 ──────────────────────

def _extract_from_html(html: str, max_chars: int) -> tuple[str, str]:
    """
    HTML에서 본문을 추출하고 (텍스트, 파서명) 튜플을 반환한다.

    trafilatura가 300자 이상 추출하면 trafilatura 결과를 사용한다.
    미달하거나 실패하면 BeautifulSoup으로 폴백한다.
    둘 다 실패하면 ('', '') 반환.
    """
    # ── 1순위: trafilatura ────────────────────────────────────────────────────
    try:
        result = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )
        if result and len(result.strip()) >= _TRAFILATURA_MIN_CHARS:
            return result.strip()[:max_chars], PARSER_TRAFILATURA
    except Exception:
        pass

    # ── 2순위: BeautifulSoup 폴백 ─────────────────────────────────────────────
    try:
        text = _bs_extract(html, max_chars)
        if text:
            return text, PARSER_BEAUTIFULSOUP
    except Exception:
        pass

    return '', ''


# ── 공개 인터페이스 ─────────────────────────────────────────────────────────────

def extract_article_text(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """
    동기 버전 — 파이프라인(독립 프로세스)에서 사용.
    크롤링 후 정제된 본문 텍스트만 반환한다 (파서 정보 불필요 시).
    실패 시 빈 문자열 반환.
    """
    try:
        with httpx.Client(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            text, _ = _extract_from_html(resp.text, max_chars)
            return text
    except Exception:
        return ''


async def extract_article_text_async(
    url: str,
    timeout: float = _DEFAULT_TIMEOUT,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """
    비동기 버전 — FastAPI 라우터에서 사용.
    크롤링 후 정제된 본문 텍스트만 반환한다 (파서 정보 불필요 시).
    실패 시 빈 문자열 반환.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text, _ = _extract_from_html(resp.text, max_chars)
            return text
    except Exception:
        return ''


def enrich_search_results(
    results: list[dict],
    max_per_result: int = _DEFAULT_MAX_CHARS,
) -> list[dict]:
    """
    동기 버전 — 파이프라인에서 사용.
    각 URL을 크롤링하여 body_text와 body_parser 필드를 추가한다.
    실패 항목은 snippet/content를 body_text로, body_parser는 빈 문자열로 설정한다.
    """
    enriched: list[dict] = []

    for i, r in enumerate(results):
        fallback_text = r.get('content', r.get('snippet', ''))
        if i < _MAX_CONCURRENT:
            try:
                with httpx.Client(
                    timeout=_DEFAULT_TIMEOUT,
                    headers=_HEADERS,
                    follow_redirects=True,
                ) as client:
                    resp = client.get(r.get('url', ''))
                    resp.raise_for_status()
                    text, parser = _extract_from_html(resp.text, max_per_result)
            except Exception:
                text, parser = '', ''
        else:
            text, parser = '', ''

        enriched.append({
            **r,
            'body_text': text if text else fallback_text,
            'body_parser': parser,
        })

    return enriched


async def enrich_search_results_async(
    results: list[dict],
    max_per_result: int = _DEFAULT_MAX_CHARS,
) -> list[dict]:
    """
    비동기 버전 — FastAPI 라우터에서 사용.
    상위 _MAX_CONCURRENT개 URL을 asyncio.gather로 병렬 크롤링하여
    body_text와 body_parser 필드를 추가한다.
    """
    async def _fetch_one(r: dict) -> tuple[str, str]:
        try:
            async with httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT,
                headers=_HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(r.get('url', ''))
                resp.raise_for_status()
                return _extract_from_html(resp.text, max_per_result)
        except Exception:
            return '', ''

    to_crawl = results[:_MAX_CONCURRENT]
    rest = results[_MAX_CONCURRENT:]

    pairs = await asyncio.gather(*[_fetch_one(r) for r in to_crawl], return_exceptions=True)

    enriched: list[dict] = []
    for r, pair in zip(to_crawl, pairs):
        fallback = r.get('content', r.get('snippet', ''))
        if isinstance(pair, Exception) or not pair[0]:
            text, parser = fallback, ''
        else:
            text, parser = pair
            if not text:
                text = fallback
        enriched.append({**r, 'body_text': text, 'body_parser': parser})

    for r in rest:
        fallback = r.get('content', r.get('snippet', ''))
        enriched.append({**r, 'body_text': fallback, 'body_parser': ''})

    return enriched
