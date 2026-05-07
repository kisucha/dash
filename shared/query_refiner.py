# 목적: 대화 이력 기반 LLM 검색 쿼리 정제 유틸리티
# "해당", "그", "이" 같은 지시대명사를 감지하면 이력에서 실제 대상을 파악해 구체적 쿼리 생성
# FastAPI(비동기 refine_query_async)와 파이프라인(동기 refine_query) 양쪽 지원

import sys
import asyncio

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import httpx

# ── 정제 필요성 판단 기준 ───────────────────────────────────────────────────────

# 이전 대화를 가리키는 지시대명사/참조어 — 이 단어가 있고 이력이 존재하면 정제 수행
_REFERENCE_WORDS: list[str] = [
    "해당", "그 영화", "이 영화", "그 제품", "이 제품", "그 회사", "이 회사",
    "그 사람", "이 사람", "그 책", "이 책", "그 게임", "이 게임",
    "그것", "이것", "저것", "그거", "이거", "저거",
    "위의", "위에서", "앞서", "앞에서", "방금", "아까",
    "위에서 말한", "앞서 말한", "방금 말한", "아까 말한",
]

# 이력 없어도 보강 검색이 유리한 패턴 (대화 흐름 연속)
_CONTINUATION_PATTERNS: list[str] = [
    "자세히", "자세하게", "더 자세하게", "좀 더",
    "더 알려줘", "더 알려주세요", "추가로 알려",
    "계속해서", "이어서", "그 외에도",
]


def needs_refinement(question: str, history: list[dict]) -> bool:
    """
    현재 질문이 이전 대화를 참조하고 있어 쿼리 정제가 필요한지 판단한다.

    Args:
        question: 현재 사용자 질문
        history: 이전 대화 이력 [{"role": str, "content": str}, ...]

    Returns:
        True면 정제 필요 (이전 대화를 참조하는 표현 발견)
    """
    if not history:
        return False

    for word in _REFERENCE_WORDS:
        if word in question:
            return True

    for pattern in _CONTINUATION_PATTERNS:
        if pattern in question:
            return True

    return False


# ── 정제 프롬프트 ──────────────────────────────────────────────────────────────

def _build_refine_prompt(question: str, history: list[dict]) -> str:
    """
    LLM에게 쿼리 정제를 지시하는 프롬프트를 생성한다.
    최근 8개 메시지만 포함해 컨텍스트를 제한한다.
    """
    # 최근 8개 메시지만 사용 — 너무 길면 소형 모델의 응답 품질 저하
    recent = history[-8:] if len(history) > 8 else history

    history_lines: list[str] = []
    for msg in recent:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))[:400]  # 메시지당 최대 400자
        if role == "user":
            history_lines.append(f"사용자: {content}")
        elif role == "assistant":
            history_lines.append(f"AI: {content}")

    history_text = "\n".join(history_lines)

    return (
        "아래는 사용자와 AI의 최근 대화입니다.\n\n"
        f"{history_text}\n\n"
        f"현재 사용자 질문: {question}\n\n"
        "위 대화를 참고하여, 현재 질문에서 '해당', '그', '이', '위', '방금' 같은 "
        "지시대명사나 참조어가 실제로 무엇을 가리키는지 파악한 뒤, "
        "인터넷 검색엔진에 입력할 최적의 검색어를 한 줄로만 작성해라.\n\n"
        "규칙:\n"
        "- 검색어만 출력하고 다른 설명·문장은 절대 쓰지 마라\n"
        "- 검색어는 구체적이어야 한다 (제품명·작품명·인물명·브랜드명 포함)\n"
        "- 예시: 질문이 '해당 영화 스토리 알려줘'이고 대화에서 '브루탈리스트'가 언급됐다면\n"
        "  → 출력: 브루탈리스트 영화 줄거리 스토리 감독\n"
        "검색어:"
    )


# ── 정제 실행 ──────────────────────────────────────────────────────────────────

async def refine_query_async(
    question: str,
    history: list[dict],
    ollama_url: str = "http://localhost:11434",
    model: str = "exaone3.5:2.4b",
    timeout: float = 15.0,
) -> str:
    """
    대화 이력을 참고해 검색에 최적화된 쿼리를 LLM으로 생성한다. (비동기)

    실패하거나 결과가 불적절하면 원본 질문을 그대로 반환한다.

    Args:
        question: 현재 사용자 질문 (원본)
        history: 이전 대화 이력
        ollama_url: Ollama 서버 주소
        model: 사용할 Ollama 모델
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        정제된 검색 쿼리 (실패 시 원본 question)
    """
    prompt = _build_refine_prompt(question, history)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            refined = data.get("response", "").strip()

            # 빈 응답 또는 비정상적으로 긴 응답은 원본 반환
            if not refined or len(refined) > 300:
                return question

            # "검색어:" 레이블이 그대로 출력된 경우 제거
            for prefix in ("검색어:", "검색어 :", "Search:", "Query:", "검색 쿼리:"):
                if refined.lower().startswith(prefix.lower()):
                    refined = refined[len(prefix):].strip()

            # 첫 줄만 사용 (여러 줄 출력 방지)
            refined = refined.splitlines()[0].strip()

            return refined if refined else question

    except Exception:
        return question


def refine_query(
    question: str,
    history: list[dict],
    ollama_url: str = "http://localhost:11434",
    model: str = "exaone3.5:2.4b",
    timeout: float = 15.0,
) -> str:
    """
    refine_query_async의 동기 래퍼.
    파이프라인(독립 프로세스)에서 사용한다.
    이미 실행 중인 이벤트 루프가 있는 환경(FastAPI 내부)에서는 호출하면 안 된다.
    """
    return asyncio.run(
        refine_query_async(
            question=question,
            history=history,
            ollama_url=ollama_url,
            model=model,
            timeout=timeout,
        )
    )
