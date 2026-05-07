# 목적: 사용자 질문의 의도를 파악하고 LLM에 최적화된 구조의 프롬프트를 구성하는 공유 유틸리티
# LLM 추가 호출 없이 키워드 규칙 매칭으로 즉시 의도 판별 (속도·비용 최적화)

import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from typing import Optional

# ── 의도 유형 상수 ─────────────────────────────────────────────────────────────

INTENT_FACTUAL = 'FACTUAL'           # 사실 정보 질문 ("~란?", "설명해줘")
INTENT_HOW_TO = 'HOW_TO'             # 방법·절차 질문 ("어떻게", "단계")
INTENT_COMPARISON = 'COMPARISON'     # 비교 분석 ("차이점", "vs")
INTENT_CREATIVE = 'CREATIVE'         # 창작·생성 요청 ("만들어줘", "써줘")
INTENT_CODING = 'CODING'             # 코드·개발 관련 ("코드", "버그")
INTENT_SUMMARY = 'SUMMARY'           # 요약 요청 ("요약", "정리")
INTENT_SEARCH_ANALYSIS = 'SEARCH_ANALYSIS'  # 검색 결과 컨텍스트 있을 때 자동 적용
INTENT_DEEP_ANALYSIS = 'DEEP_ANALYSIS'      # 멀티 검색 결과 기반 심층 분석
INTENT_GENERAL = 'GENERAL'           # 위 외 일반 대화

# ── 의도별 판별 키워드 (순서대로 매칭 — 앞에 있을수록 우선순위 높음) ─────────────

_INTENT_PATTERNS: list[tuple[str, list[str]]] = [
    (INTENT_CODING, [
        '코드', '함수', '클래스', '메서드', '프로그램', '스크립트',
        '버그', '에러', '오류', '예외', '구현', '디버그',
        'code', 'function', 'class', 'method', 'bug', 'error',
        'exception', 'debug', 'implement',
        '파이썬', 'python', 'javascript', 'typescript',
        'sql', 'css', 'react', 'gradle', 'dockerfile',
    ]),
    (INTENT_HOW_TO, [
        '방법', '어떻게', '하려면', '하는 법', '하는 방법',
        '절차', '순서', '단계', '설치', '설정', '사용법',
        '하면 되', '어떻게 하', 'how to', 'how do', 'steps',
        '따라하', '가이드', '튜토리얼',
    ]),
    (INTENT_COMPARISON, [
        '차이', '비교', ' vs ', 'versus', '장단점', '장점', '단점',
        '다른 점', '낫나요', '뭐가 좋', '어느 것', '어떤 게 나',
        '차이점', '비교해', '어느 쪽',
    ]),
    (INTENT_SUMMARY, [
        '요약', '정리', '간단히', '간략', '핵심만', '핵심',
        '줄여줘', '요점', '짧게', '짧게 말해',
        'summarize', 'summary', 'brief', '한 줄로', '한줄로',
    ]),
    (INTENT_CREATIVE, [
        '만들어줘', '써줘', '작성해줘', '생성해줘', '만들어',
        '기획', '제안해', '아이디어', '초안', '드래프트',
        'write', 'create', 'generate', 'draft',
        '예시 작성', '샘플 작성', '템플릿',
    ]),
    (INTENT_FACTUAL, [
        '이란', '뭐야', '뭔가요', '무엇인가', '무엇인지',
        '알려줘', '설명해줘', '설명해줄', '의미', '정의', '뜻',
        '이란 무엇', '은 무엇', '란?', '은?', '가 뭐',
        'what is', 'define', 'definition', 'explain',
    ]),
]


# ── 공개 인터페이스 ─────────────────────────────────────────────────────────────

def detect_intent(question: str) -> str:
    """
    사용자 질문에서 의도를 파악해 의도 코드를 반환한다.
    키워드 기반 규칙 매칭으로 즉시 판별 — LLM 호출 없음.

    Args:
        question: 사용자 입력 텍스트

    Returns:
        의도 코드 상수 (INTENT_* 중 하나)
    """
    q_lower = question.lower()
    for intent_code, keywords in _INTENT_PATTERNS:
        if any(kw in q_lower for kw in keywords):
            return intent_code
    return INTENT_GENERAL


def _get_intent_instruction(intent: str) -> str:
    """의도 코드에 대응하는 LLM 지시 문장을 반환한다."""
    _instructions: dict[str, str] = {
        INTENT_FACTUAL: (
            "다음 질문에 대해 정확하고 신뢰할 수 있는 정보를 제공하세요. "
            "정의 → 핵심 내용 → 실용적 예시 순서로 명확하게 설명하세요. "
            "불확실한 내용은 그렇다고 명시하세요."
        ),
        INTENT_HOW_TO: (
            "다음 요청에 대해 번호가 매겨진 단계별 절차로 답변하세요. "
            "각 단계는 구체적이고 즉시 실행 가능한 내용을 포함하세요. "
            "필요한 사전 조건이나 준비물이 있으면 먼저 안내하세요."
        ),
        INTENT_COMPARISON: (
            "요청된 항목들을 체계적으로 비교 분석하세요. "
            "가능하면 표 형식으로 주요 차이점을 정리하고, "
            "각 항목이 어떤 상황에 적합한지 구체적인 선택 기준과 결론을 제시하세요."
        ),
        INTENT_CREATIVE: (
            "다음 요청에 대해 창의적이고 완성도 높은 결과물을 작성하세요. "
            "요청 조건을 충실히 반영하고 구체적인 내용으로 채우세요. "
            "필요하면 구조나 형식을 먼저 제안하고 작성하세요."
        ),
        INTENT_CODING: (
            "코드는 반드시 코드 블록(```)으로 감싸 작성하세요. "
            "코드 앞에 목적과 사용 방법을 한두 줄로 설명하고, "
            "핵심 로직에 주석을 달아주세요. "
            "예외 처리가 필요한 부분에는 적절한 에러 핸들링을 포함하세요."
        ),
        INTENT_SUMMARY: (
            "핵심 내용만 간결하게 요약하세요. "
            "불릿 포인트로 중요한 포인트를 나열하고 "
            "마지막에 한 문장으로 결론을 제시하세요. "
            "불필요한 반복이나 부연 설명은 생략하세요."
        ),
        INTENT_SEARCH_ANALYSIS: (
            "제공된 검색 결과를 참고하여 질문에 답변하세요. "
            "검색 결과는 최신 사실·구체적 수치·사례를 보완하는 재료로 활용하고, "
            "부족한 부분은 학습된 지식으로 채워 완성도 높은 답변을 작성하세요. "
            "검색 결과에 배경 설명·맥락·부연 정보가 있으면 본문에 자연스럽게 녹여 서술하세요. "
            "출처 표기 없이 내용만 서술하세요."
        ),
        INTENT_DEEP_ANALYSIS: (
            "제공된 검색 결과와 학습된 지식을 결합하여 심층 분석 답변을 작성하세요.\n\n"
            "검색 결과는 최신 사실·수치·구체적 사례를 보강하는 재료로 활용하고, "
            "검색 결과가 부족한 부분은 학습된 지식으로 채워 완성도를 높이세요.\n\n"
            "답변 구조는 질문의 성격에 맞게 자유롭게 구성하되 다음 원칙을 따르세요:\n"
            "- 단순 나열 금지 — 인과관계와 맥락을 포함한 분석 필수\n"
            "- 검색 결과의 배경 설명·맥락·부연 정보를 본문에 자연스럽게 녹여 서술\n"
            "- 출처 표기 없이 내용만 서술"
        ),
        INTENT_GENERAL: (
            "자연스럽고 도움이 되는 방식으로 질문에 답변하세요."
        ),
    }
    return _instructions.get(intent, _instructions[INTENT_GENERAL])


def build_optimized_prompt(
    question: str,
    history: Optional[list[dict]] = None,
    search_context: Optional[str] = None,
    deep_analysis: bool = False,
) -> str:
    """
    사용자 질문의 의도를 파악하고 LLM에 최적화된 구조의 프롬프트를 구성해 반환한다.

    deep_analysis=True이면 멀티 검색 기반 심층 분석 지시문을 적용한다.
    검색 컨텍스트가 있으면 SEARCH_ANALYSIS 의도를 자동 적용한다.
    대화 이력은 최근 6턴만 포함한다.

    Args:
        question: 사용자 입력 메시지
        history: 이전 대화 이력 [{"role": "user"|"assistant", "content": str}, ...]
        search_context: 인터넷 검색 결과 텍스트 (없으면 None)
        deep_analysis: True이면 심층 분석 구조 지시문 적용

    Returns:
        LLM에 전달할 최종 프롬프트 문자열
    """
    # 의도 결정: deep_analysis > search_context > 키워드 감지
    if deep_analysis and search_context:
        intent = INTENT_DEEP_ANALYSIS
    elif search_context:
        intent = INTENT_SEARCH_ANALYSIS
    else:
        intent = detect_intent(question)
    instruction = _get_intent_instruction(intent)

    parts: list[str] = []

    # 지시문 섹션
    parts.append(f"[지시문]\n{instruction}")

    # 이전 대화 이력 섹션 (최근 6턴)
    if history:
        recent = history[-6:]
        lines: list[str] = []
        for turn in recent:
            prefix = "사용자" if turn.get("role") == "user" else "어시스턴트"
            lines.append(f"{prefix}: {turn.get('content', '')}")
        if lines:
            parts.append("[이전 대화]\n" + "\n".join(lines))

    # 현재 질문 섹션 — 검색 결과보다 먼저 배치하여 LLM이 질문 중심으로 답변하도록 유도
    parts.append(f"[질문]\n{question}")

    # 검색 결과 컨텍스트 섹션 — 5000자로 제한하여 컨텍스트 윈도우 오버플로 방지
    if search_context:
        ctx = search_context[:5000] if len(search_context) > 5000 else search_context
        parts.append(
            "[참고 검색 결과]\n"
            "아래는 인터넷에서 수집한 최신 정보입니다. "
            "부족한 부분은 학습된 지식으로 채워 완성도 높은 답변을 작성하세요.\n\n"
            f"{ctx}"
        )

    parts.append("[답변]")

    return "\n\n".join(parts)
