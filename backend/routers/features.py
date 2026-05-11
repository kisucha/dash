# 목적: /api/features 엔드포인트 라우터 — 하드코딩된 업무 목록 제공
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException

from schemas.task import FeatureResponse

logger = logging.getLogger(__name__)

# F003 config.json 경로 — 프로젝트 루트 기준 절대 경로
F003_CONFIG_PATH = Path(__file__).parent.parent.parent / "pipelines" / "f003_video_creation" / "config.json"

# LoRA 카테고리 표시 순서 정의
LORA_CATEGORY_ORDER = ["enhancement", "character", "style", "background"]

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


# 주의: /f003/models, /f003/loras, /f003/loras/predownload 는 반드시 /{feature_id} 보다 먼저 선언해야 한다.
# FastAPI는 라우트 등록 순서대로 매칭하므로, path parameter 라우트보다 고정 경로를 앞에 두어야 한다.

def _check_checkpoint_has_clip(ckpt_dir: str, filename: str) -> bool:
    """safetensors 헤더만 빠르게 읽어 CLIP 텐서 포함 여부를 반환한다.

    safetensors 형식은 파일 앞쪽 8+N 바이트에 텐서 이름 목록이 JSON으로 저장되므로
    전체 파일을 읽지 않아도 된다. 읽기 실패 시 True(경고 안 함)를 반환한다.
    """
    import struct
    # CLIP 관련 텐서 키워드 — 이 중 하나라도 있으면 CLIP 포함으로 판정
    CLIP_KEYWORDS = ("text_model", "clip_l", "clip_g", "cond_stage_model", "text_encoder")
    filepath = Path(ckpt_dir) / filename
    try:
        with open(filepath, "rb") as f:
            # 처음 8바이트: 헤더 JSON 길이 (little-endian uint64)
            raw_len = f.read(8)
            if len(raw_len) < 8:
                return True
            header_len = struct.unpack("<Q", raw_len)[0]
            header_bytes = f.read(header_len)
        header = json.loads(header_bytes)
        return any(any(kw in key for kw in CLIP_KEYWORDS) for key in header)
    except Exception:
        return True  # 판정 불가 시 경고 표시 안 함 (오탐 방지)


@router.get("/f003/models")
async def get_f003_models() -> dict:
    """F003 파이프라인용 ComfyUI 설치 모델 목록을 반환한다.

    checkpoints, vaes, loras, clips 네 가지 목록을 한 번에 반환한다.
    no_clip_checkpoints: CLIP 텐서가 없는 체크포인트 파일명 목록 (UI 경고용).
    ComfyUI 연결 실패 시 빈 목록으로 처리하며 예외는 발생시키지 않는다.
    """
    import sys as _sys
    project_root = str(Path(__file__).parent.parent.parent)
    if project_root not in _sys.path:
        _sys.path.insert(0, project_root)

    comfyui_url = "http://localhost:8188"
    comfyui_path = r"C:\ComfyUI\ComfyUI"
    if F003_CONFIG_PATH.exists():
        try:
            with open(F003_CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            comfyui_url  = cfg.get("comfyui_url", comfyui_url)
            comfyui_path = cfg.get("comfyui_path", comfyui_path)
        except Exception:
            pass

    checkpoints: list = []
    vaes: list = []
    loras: list = []
    clips: list = []
    no_clip_checkpoints: list = []

    try:
        from pipelines.f003_video_creation.comfyui_client import ComfyUIClient
        client = ComfyUIClient(comfyui_url)
        # /object_info 단일 호출로 4개 목록을 한꺼번에 조회 (중복 네트워크 요청 방지)
        model_lists = client.get_all_model_lists()
        checkpoints = model_lists["checkpoints"]
        vaes        = model_lists["vaes"]
        loras       = model_lists["loras"]
        clips       = model_lists["clips"]
        logger.info(
            f"ComfyUI 모델 목록: 체크포인트 {len(checkpoints)}개, "
            f"VAE {len(vaes)}개, LoRA {len(loras)}개, CLIP {len(clips)}개"
        )

        # 각 체크포인트의 CLIP 포함 여부를 safetensors 헤더로 확인
        ckpt_dir = str(Path(comfyui_path) / "models" / "checkpoints")
        for ckpt_name in checkpoints:
            if ckpt_name.endswith(".safetensors"):
                if not _check_checkpoint_has_clip(ckpt_dir, ckpt_name):
                    no_clip_checkpoints.append(ckpt_name)
        if no_clip_checkpoints:
            logger.info(f"CLIP 없는 체크포인트: {no_clip_checkpoints}")
    except Exception as e:
        logger.warning(f"ComfyUI 모델 목록 조회 실패: {e}")

    return {
        "checkpoints": checkpoints,
        "vaes": vaes,
        "loras": loras,
        "clips": clips,
        "no_clip_checkpoints": no_clip_checkpoints,
    }


@router.get("/f003/loras")
async def get_f003_loras() -> dict:
    """F003 파이프라인의 LoRA 목록을 카테고리별로 분류하여 반환한다.

    ComfyUI /object_info/LoraLoader API를 통해 각 LoRA의 설치 여부를 확인한다.
    ComfyUI 연결 실패 시 installed=False로 처리하며 예외는 발생시키지 않는다.
    """
    # config.json 로드
    if not F003_CONFIG_PATH.exists():
        raise HTTPException(status_code=500, detail="F003 config.json 파일을 찾을 수 없습니다.")

    with open(F003_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    lora_mapping: dict = config.get("detail_lora_mapping", {})
    comfyui_url: str = config.get("comfyui_url", "http://localhost:8188")

    # ComfyUI에서 설치된 LoRA 파일명 목록 조회 — 실패 시 빈 목록으로 처리
    installed_filenames: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)) as client:
            resp = await client.get(f"{comfyui_url}/object_info/LoraLoader")
            if resp.status_code == 200:
                data = resp.json()
                # LoraLoader 노드의 lora_name 입력 위젯에서 설치된 LoRA 파일명 목록 추출
                lora_names = (
                    data.get("LoraLoader", {})
                    .get("input", {})
                    .get("required", {})
                    .get("lora_name", [None])[0]
                )
                if isinstance(lora_names, list):
                    installed_filenames = set(lora_names)
                logger.info(f"ComfyUI LoRA 목록 조회 완료: {len(installed_filenames)}개 설치됨")
    except Exception as e:
        # ComfyUI 미실행 또는 연결 오류 시 설치 여부를 False로 처리
        logger.warning(f"ComfyUI 연결 실패 - LoRA 설치 여부 확인 불가: {e}")

    # 카테고리별로 LoRA 항목을 분류
    categories: dict[str, list] = {cat: [] for cat in LORA_CATEGORY_ORDER}
    total_count = 0
    installed_count = 0

    for key, lora in lora_mapping.items():
        category = lora.get("category", "enhancement")
        filename = lora.get("filename", "")
        is_installed = filename in installed_filenames
        # civitai_version_id 또는 hf_repo_id 중 하나라도 있으면 다운로드 가능
        is_downloadable = (
            lora.get("civitai_version_id") is not None
            or lora.get("hf_repo_id") is not None
        )

        entry = {
            "key": key,
            "display_name": lora.get("display_name", key),
            "category": category,
            "description": lora.get("description", ""),
            "base_models": lora.get("base_models", []),
            "default_weight": lora.get("default_weight", 1.0),
            "installed": is_installed,
            "downloadable": is_downloadable,
            "trigger_words": lora.get("trigger_words", []),
        }

        # 알려지지 않은 카테고리는 enhancement로 fallback
        if category not in categories:
            categories.setdefault(category, [])
        categories[category].append(entry)

        total_count += 1
        if is_installed:
            installed_count += 1

    return {
        "categories": categories,
        "installed_count": installed_count,
        "total_count": total_count,
    }


async def _run_lora_predownload(loras: list[dict]) -> None:
    """미설치 LoRA를 백그라운드에서 다운로드한다.

    ModelManager.ensure_models()를 통해 CivitAI에서 직접 다운로드한다.
    이 함수는 BackgroundTasks로 실행되므로 예외가 발생해도 API 응답에 영향을 주지 않는다.
    """
    import sys as _sys

    # 프로젝트 루트를 sys.path에 추가하여 pipelines 패키지를 임포트 가능하게 한다
    project_root = str(Path(__file__).parent.parent.parent)
    if project_root not in _sys.path:
        _sys.path.insert(0, project_root)

    try:
        from pipelines.f003_video_creation.model_manager import ModelManager
        from pipelines.f003_video_creation.comfyui_client import ComfyUIClient

        # config에서 comfyui_path 조회
        with open(F003_CONFIG_PATH, encoding="utf-8") as f:
            config = json.load(f)
        comfyui_path: str = config.get("comfyui_path", r"C:\ComfyUI\ComfyUI")
        comfyui_url: str = config.get("comfyui_url", "http://localhost:8188")

        manager = ModelManager(comfyui_path)
        comfyui_client = ComfyUIClient(comfyui_url)

        # ensure_models 형식으로 변환 — LoRA 타입, CivitAI 소스 명시
        required_models = []
        for lora in loras:
            civitai_id = lora.get("civitai_version_id")
            hf_repo = lora.get("hf_repo_id")
            if civitai_id:
                source = "civitai"
                source_id = str(civitai_id)
            elif hf_repo:
                source = "huggingface"
                source_id = hf_repo
            else:
                # 다운로드 소스가 없는 항목은 건너뜀
                continue
            required_models.append({
                "filename": lora["filename"],
                "model_type": "lora",
                "source": source,
                "source_id": source_id,
            })

        logger.info(f"LoRA 사전 다운로드 시작: {len(required_models)}개")
        manager.ensure_models(required_models, comfyui_client)
        logger.info("LoRA 사전 다운로드 완료")
    except Exception as e:
        logger.error(f"LoRA 사전 다운로드 실패: {e}")


@router.post("/f003/loras/predownload")
async def predownload_f003_loras(background_tasks: BackgroundTasks) -> dict:
    """downloadable=True이고 installed=False인 LoRA를 백그라운드로 다운로드한다.

    ComfyUI 연결 여부와 무관하게 즉시 응답을 반환하며,
    실제 다운로드는 BackgroundTasks로 비동기 처리된다.
    """
    if not F003_CONFIG_PATH.exists():
        raise HTTPException(status_code=500, detail="F003 config.json 파일을 찾을 수 없습니다.")

    with open(F003_CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    lora_mapping: dict = config.get("detail_lora_mapping", {})
    comfyui_url: str = config.get("comfyui_url", "http://localhost:8188")

    # ComfyUI에서 현재 설치된 LoRA 목록 조회
    installed_filenames: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)) as client:
            resp = await client.get(f"{comfyui_url}/object_info/LoraLoader")
            if resp.status_code == 200:
                data = resp.json()
                lora_names = (
                    data.get("LoraLoader", {})
                    .get("input", {})
                    .get("required", {})
                    .get("lora_name", [None])[0]
                )
                if isinstance(lora_names, list):
                    installed_filenames = set(lora_names)
    except Exception as e:
        logger.warning(f"ComfyUI 연결 실패 - 설치 여부 미확인 상태로 다운로드 진행: {e}")

    # downloadable=True이고 installed=False인 항목만 선별
    queued_loras = []
    queued_keys = []
    for key, lora in lora_mapping.items():
        filename = lora.get("filename", "")
        civitai_id = lora.get("civitai_version_id")
        hf_repo = lora.get("hf_repo_id")
        is_downloadable = civitai_id is not None or hf_repo is not None
        is_installed = filename in installed_filenames

        if is_downloadable and not is_installed:
            queued_loras.append({
                "key": key,
                "filename": filename,
                "civitai_version_id": civitai_id,
                "hf_repo_id": hf_repo,
            })
            queued_keys.append(key)

    if queued_loras:
        # 백그라운드로 다운로드 실행 — API 응답은 즉시 반환
        background_tasks.add_task(_run_lora_predownload, queued_loras)
        logger.info(f"LoRA 다운로드 백그라운드 작업 등록: {queued_keys}")
    else:
        logger.info("다운로드할 LoRA 없음 - 모두 설치됨")

    return {
        "status": "started",
        "queued_count": len(queued_loras),
        "queued": queued_keys,
    }


# /{feature_id} 는 가장 마지막에 선언 — 위 고정 경로 라우트를 가로채지 않도록 한다
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
