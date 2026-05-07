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
    "F003": {
        "feature_id": "F003",
        "name": "영상제작",
        "description": "ComfyUI와 Ollama를 활용하여 동영상(AnimateDiff) 또는 그림(Flux.1/SD)을 자동 생성합니다.",
        "supports_schedule": False,
        "input_schema": [
            {
                "name": "generation_type",
                "title": "생성 유형",
                "type": "select",
                "required": True,
                "default": "image",
                "options": ["image", "video"],
                "description": "동영상(AnimateDiff) 또는 그림(Flux.1/SD) 중 선택",
            },
            {
                "name": "art_style",
                "title": "아트 스타일",
                "type": "select",
                "required": False,
                "default": "realistic",
                "options": ["anime", "realistic", "fantasy", "cyberpunk", "watercolor", "3d_render", "pixel_art", "flux"],
                "description": "생성할 이미지의 아트 스타일",
            },
            {
                "name": "character_face",
                "title": "캐릭터 얼굴형",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "western", "asian", "mixed"],
                "description": "캐릭터 얼굴형 (비워두면 기본값 사용)",
            },
            {
                "name": "character_hair_style",
                "title": "헤어스타일",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "long_hair", "short_hair", "twin_tails", "ponytail", "bob_with_bangs"],
                "description": "캐릭터 헤어스타일",
            },
            {
                "name": "character_hair_color",
                "title": "헤어 색상",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "blonde", "brown", "black", "pink", "silver", "gradient"],
                "description": "캐릭터 헤어 색상",
            },
            {
                "name": "character_eyes",
                "title": "눈매",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "large_eyes", "sharp_eyes", "upturned", "downturned"],
                "description": "캐릭터 눈매",
            },
            {
                "name": "character_outfit",
                "title": "의상",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "casual", "fantasy", "school_uniform", "sportswear", "dress", "cyberpunk"],
                "description": "캐릭터 의상",
            },
            {
                "name": "camera_angle",
                "title": "카메라 앵글",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "front", "side", "from_above", "from_below", "dramatic_low"],
                "description": "카메라 앵글",
            },
            {
                "name": "camera_composition",
                "title": "화면 구도",
                "type": "select",
                "required": False,
                "default": "close_up",
                "options": ["close_up", "upper_body", "full_body", "wide_shot"],
                "description": "화면 구도",
            },
            {
                "name": "depth_of_field",
                "title": "심도",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "bokeh", "pan_focus"],
                "description": "심도 효과",
            },
            {
                "name": "lighting",
                "title": "조명",
                "type": "select",
                "required": False,
                "default": "natural_day",
                "options": ["natural_day", "golden_hour", "night", "indoor", "dramatic", "soft", "backlit", "studio", "neon"],
                "description": "조명 환경",
            },
            {
                "name": "background",
                "title": "배경",
                "type": "select",
                "required": False,
                "default": "",
                "options": ["", "classroom", "cafe", "bedroom", "office", "city_street", "nature_park", "beach", "mountain_forest", "castle", "magical_realm", "otherworldly", "plain_background", "abstract"],
                "description": "배경 환경",
            },
            {
                "name": "motion_intensity",
                "title": "모션 강도",
                "type": "select",
                "required": False,
                "default": "subtle",
                "options": ["subtle", "moderate", "dynamic"],
                "description": "동영상 모션 강도 (동영상 선택 시만 적용)",
            },
            {
                "name": "motion_type",
                "title": "모션 유형",
                "type": "select",
                "required": False,
                "default": "camera_movement",
                "options": ["camera_movement", "character_movement", "particle_environment"],
                "description": "동영상 모션 유형 (동영상 선택 시만 적용)",
            },
            {
                "name": "loop_animation",
                "title": "루프 애니메이션",
                "type": "select",
                "required": False,
                "default": "false",
                "options": ["true", "false"],
                "description": "동영상 루프 여부 (동영상 선택 시만 적용)",
            },
            {
                "name": "detail_loras",
                "title": "디테일 향상 LoRA",
                "type": "list",
                "required": False,
                "default": "",
                "options": ["detail_tweaker", "detail_tweaker_xl", "add_more_details", "flux_image_upgrader", "detailifier"],
                "description": "쉼표 구분 다중 선택 (예: detail_tweaker,add_more_details). 선택된 아트 스타일의 기반 모델과 호환 LoRA만 적용됨",
            },
            {
                "name": "user_description",
                "title": "추가 설명",
                "type": "textarea",
                "required": False,
                "default": "",
                "options": [],
                "description": "생성할 이미지/동영상에 대한 추가 설명 (한국어 가능)",
            },
            {
                "name": "width",
                "title": "가로 크기",
                "type": "integer",
                "required": False,
                "default": 512,
                "options": [],
                "description": "이미지 가로 크기 (픽셀, 기본: 512)",
            },
            {
                "name": "height",
                "title": "세로 크기",
                "type": "integer",
                "required": False,
                "default": 768,
                "options": [],
                "description": "이미지 세로 크기 (픽셀, 기본: 768)",
            },
            {
                "name": "steps",
                "title": "샘플링 스텝",
                "type": "integer",
                "required": False,
                "default": 20,
                "options": [],
                "description": "샘플링 스텝 수 (기본: 20, 많을수록 품질 향상 but 느림)",
            },
            {
                "name": "cfg_scale",
                "title": "CFG 스케일",
                "type": "integer",
                "required": False,
                "default": 7,
                "options": [],
                "description": "프롬프트 충실도 (기본: 7, 높을수록 프롬프트에 충실)",
            },
            {
                "name": "seed",
                "title": "시드",
                "type": "integer",
                "required": False,
                "default": -1,
                "options": [],
                "description": "랜덤 시드 (-1이면 무작위)",
            },
            {
                "name": "video_length",
                "title": "동영상 프레임 수",
                "type": "integer",
                "required": False,
                "default": 16,
                "options": [],
                "description": "생성할 동영상 프레임 수 (동영상 선택 시만 적용, 기본: 16)",
            },
            {
                "name": "fps",
                "title": "초당 프레임",
                "type": "integer",
                "required": False,
                "default": 8,
                "options": [],
                "description": "동영상 FPS (동영상 선택 시만 적용, 기본: 8)",
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
