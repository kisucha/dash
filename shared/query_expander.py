# 목적: 사용자 질문의 분석/전망/투자/트렌드 의도를 감지하고 멀티 검색 쿼리로 확장
# 키워드 기반 즉시 판별 — LLM 호출 없음 (속도 최적화)

import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ── 확장 유형 상수 ─────────────────────────────────────────────────────────────

EXPANSION_NONE = 'NONE'
EXPANSION_ANALYSIS = 'ANALYSIS'       # 분석 요청
EXPANSION_FORECAST = 'FORECAST'       # 전망/예측 요청
EXPANSION_INVESTMENT = 'INVESTMENT'   # 투자/시장 평가 요청
EXPANSION_TREND = 'TREND'             # 트렌드/동향 요청
EXPANSION_CAUSAL = 'CAUSAL'           # 원인/이유 요청

# ── 확장 유형별 트리거 키워드 (순서 = 우선순위) ────────────────────────────────

_EXPANSION_PATTERNS: list[tuple[str, list[str]]] = [
    (EXPANSION_INVESTMENT, [
        '투자', '매수', '매도', '포트폴리오', '주식', '코인', '암호화폐',
        '수익률', '리스크', '위험도', '가치평가', '밸류에이션',
        'invest', 'portfolio', 'stock', 'crypto',
    ]),
    (EXPANSION_FORECAST, [
        '전망', '예측', '예상', '앞으로', '미래', '향후', '내년',
        '올 하반기', '올 상반기', '하반기', '상반기', '분기',
        'forecast', 'predict', 'outlook', 'future',
    ]),
    (EXPANSION_TREND, [
        '트렌드', '동향', '흐름', '최신 동향', '최신 트렌드',
        'trend', 'trending',
    ]),
    (EXPANSION_CAUSAL, [
        '왜 ', '왜냐', '이유가', '원인이', '때문에',
        '어째서', 'why', 'reason', 'cause',
    ]),
    (EXPANSION_ANALYSIS, [
        '분석해줘', '분석해 줘', '분석해주세요', '분석 해줘',
        '살펴봐줘', '검토해줘', '평가해줘', '비교 분석',
        '어떻게 봐', '어떻게봐', '어떤가요', '어떻게 생각',
        'analyze', 'analysis', 'review', 'evaluate',
    ]),
]

# 주제 추출 시 제거할 트리거 구문 목록 (긴 구문 먼저)
_TRIGGER_PHRASES: list[str] = [
    '분석해줘', '분석해 줘', '분석해주세요', '분석 해줘', '분석해줘요',
    '전망해줘', '전망해 줘', '전망해주세요',
    '예측해줘', '예측해 줘', '예측해주세요',
    '검토해줘', '검토해 줘', '검토해주세요',
    '평가해줘', '평가해 줘', '평가해주세요',
    '살펴봐줘', '살펴봐 줘', '살펴봐주세요',
    '알려줘', '알려 줘', '알려주세요',
    '설명해줘', '설명해 줘', '설명해주세요',
    '어떻게 봐', '어떻게봐', '어떻게 생각',
    '어떤가요', '어때요', '어때',
    '최신', '오늘자', '오늘', '요즘', '최근에', '최근', '지금',
]


# ── 공개 인터페이스 ─────────────────────────────────────────────────────────────

def detect_expansion_type(question: str) -> str:
    """
    질문에서 쿼리 확장 유형을 감지한다.
    확장이 필요 없으면 EXPANSION_NONE 반환.
    """
    q_lower = question.lower()
    for expansion_type, keywords in _EXPANSION_PATTERNS:
        if any(kw in q_lower for kw in keywords):
            return expansion_type
    return EXPANSION_NONE


def needs_expansion(question: str) -> bool:
    """쿼리 확장이 필요한 질문인지 판별한다."""
    return detect_expansion_type(question) != EXPANSION_NONE


def _extract_topic(question: str) -> str:
    """
    질문에서 트리거 구문을 제거하고 핵심 주제어만 추출한다.
    예: "삼성전자 주가 분석해줘" -> "삼성전자 주가"
    """
    topic = question.strip()
    for phrase in sorted(_TRIGGER_PHRASES, key=len, reverse=True):
        topic = topic.replace(phrase, ' ')
    topic = re.sub(r'\s+', ' ', topic).strip()
    topic = topic.rstrip('?!.')
    return topic if topic else question.strip()


def expand_query(question: str) -> list[str]:
    """
    질문을 분석해 멀티 검색 쿼리 목록을 반환한다.
    반환: [원본 질문, 서브쿼리1, 서브쿼리2, 서브쿼리3]
    확장 불필요 시 [원본 질문]만 반환.
    """
    expansion_type = detect_expansion_type(question)
    if expansion_type == EXPANSION_NONE:
        return [question]

    topic = _extract_topic(question)

    if expansion_type == EXPANSION_INVESTMENT:
        return [
            question,
            f"{topic} 최근 시장 현황 데이터 수치",
            f"{topic} 리스크 위험 요인 분석",
            f"{topic} 투자 전망 수익 가능성",
        ]
    elif expansion_type == EXPANSION_FORECAST:
        return [
            question,
            f"{topic} 최신 현황 통계 데이터",
            f"{topic} 주요 변수 영향 요인",
            f"{topic} 전문가 전망 시나리오",
        ]
    elif expansion_type == EXPANSION_TREND:
        return [
            question,
            f"{topic} 최신 트렌드 통계 현황",
            f"{topic} 주요 사례 활용 현황",
            f"{topic} 향후 방향 변화 전망",
        ]
    elif expansion_type == EXPANSION_CAUSAL:
        return [
            question,
            f"{topic} 원인 배경 분석",
            f"{topic} 관련 데이터 근거 사례",
            f"{topic} 영향 결과 파급효과",
        ]
    else:  # EXPANSION_ANALYSIS
        return [
            question,
            f"{topic} 현황 최신 데이터 수치",
            f"{topic} 원인 배경 주요 요인",
            f"{topic} 전망 영향 향후 변화",
        ]
