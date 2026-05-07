# 목적: /api/features 엔드포인트 라우터 — 하드코딩된 업무 목록 제공
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from fastapi import APIRouter, HTTPException

from schemas.task import FeatureResponse

router = APIRouter(prefix="/api/features", tags=["features"])

# 업무 목록 하드코딩 — DB 없이 코드에서 관리
# 새 업무 추가 시 이 딕셔너리에만 항목을 추가하면 된다
FEATURES: dict[str, dict] = {
    "F001": {
        "feature_id": "F001",
        "name": "유튜브 컨텐츠 제작",
        "description": "주제를 입력하면 유튜브 스크립트, 제목, 설명을 생성합니다.",
        "supports_schedule": False,
        "input_schema": [
            {
                "name": "topic",
                "title": "영상 주제",
                "type": "string",
                "required": True,
                "default": "",
                "description": "제작할 유튜브 영상의 주제를 입력하세요",
            },
            {
                "name": "style",
                "title": "영상 스타일",
                "type": "string",
                "required": False,
                "default": "정보전달",
                "description": "영상 스타일 (예: 정보전달, 브이로그, 리뷰)",
            },
            {
                "name": "duration_min",
                "title": "목표 길이(분)",
                "type": "integer",
                "required": False,
                "default": 10,
                "description": "목표 영상 길이 (분 단위, 기본: 10)",
            },
        ],
    },
    "F002": {
        "feature_id": "F002",
        "name": "매일 아침 주요 이슈 발굴",
        "description": "검색(SearXNG/Tavily)으로 최신 뉴스를 수집하고 Ollama LLM이 주요 이슈를 분석·요약합니다.",
        "supports_schedule": True,
        "input_schema": [
            {
                "name": "search_provider",
                "title": "검색 엔진",
                "type": "select",
                "required": False,
                "default": "searxng",
                "options": ["searxng", "tavily"],
                "description": "SearXNG(로컬·무료·기본) 또는 Tavily(클라우드·API 키 필요)",
            },
            {
                "name": "keywords",
                "title": "검색 키워드",
                "type": "list",
                "required": False,
                "default": "AI, tech, startup",
                "description": "쉼표로 구분 (기본: AI, tech, startup)",
            },
            {
                "name": "max_issues",
                "title": "최대 이슈 수",
                "type": "integer",
                "required": False,
                "default": 5,
                "description": "발굴할 이슈 최대 개수 (1~20, 기본: 5)",
            },
            {
                "name": "days",
                "title": "검색 기간(일)",
                "type": "integer",
                "required": False,
                "default": 2,
                "description": "최근 N일 내 뉴스 검색 — Tavily 선택 시만 적용 (기본: 2)",
            },
            {
                "name": "date",
                "title": "기준일",
                "type": "string",
                "required": False,
                "default": "",
                "description": "분석 기준일 YYYY-MM-DD (비우면 오늘 날짜 자동 사용)",
            },
            {
                "name": "max_hops",
                "title": "검색 깊이 (홉)",
                "type": "integer",
                "required": False,
                "default": 2,
                "description": "멀티 홉 검색 깊이 — 1차 결과 제목으로 재검색하는 횟수 (1~5, 기본: 2)",
            },
            {
                "name": "prompt_template",
                "title": "분석 프롬프트",
                "type": "textarea",
                "required": False,
                "default": (
                    "위 실제 검색 결과를 바탕으로 '{keywords}' 관련 주요 이슈 {max_issues}개를 아래 형식으로 정리해줘.\n"
                    "반드시 실제 검색 결과에 있는 내용만 사용하고, 없는 내용을 만들지 마.\n\n"
                    "각 이슈는 반드시 아래 형식으로 작성:\n"
                    "---\n"
                    "[이슈 번호]. [이슈 제목]\n"
                    "요약: [이슈 내용을 2~4문장으로 요약]\n"
                    "중요도: [높음 / 보통 / 낮음 중 하나만 선택]\n"
                    "---\n\n"
                    "조건:\n"
                    "- 이슈 제목에 반드시 구체적인 제품명·모델명·브랜드명을 포함할 것\n"
                    "  나쁜 예: 'AI 가전 혁신', '스마트 헬스 웨어러블'\n"
                    "  좋은 예: '삼성 갤럭시 S25 엣지 보더리스 공개', '로지텍 MX Keys S Pro 한국 출시'\n"
                    "- 이슈 제목은 40자 이내\n"
                    "- 요약은 검색 결과에서 발췌한 구체적 수치·제품명·사건을 포함\n"
                    "- 중요도는 반드시 '높음', '보통', '낮음' 중 하나\n"
                    "- {max_issues}개 이슈만 출력 (추가 설명 없이)\n"
                    "- 한국어로 작성"
                ),
                "description": "LLM 분석 지시 프롬프트 — {keywords}와 {max_issues}는 실행 시 자동 치환됩니다",
            },
        ],
    },
}


@router.get("", response_model=list[FeatureResponse])
async def list_features() -> list[FeatureResponse]:
    """등록된 모든 업무 목록을 반환한다."""
    return [FeatureResponse(**feat) for feat in FEATURES.values()]


@router.get("/{feature_id}", response_model=FeatureResponse)
async def get_feature(feature_id: str) -> FeatureResponse:
    """feature_id로 업무 상세 정보를 반환한다."""
    feature = FEATURES.get(feature_id)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{feature_id}' 를 찾을 수 없습니다.",
        )
    return FeatureResponse(**feature)
