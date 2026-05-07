# 목적: 사용자 스타일 선택을 ComfyUI 워크플로우 파라미터로 매핑하는 모듈
import sys
import json
import copy
import logging
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)

# config.json 및 workflows 디렉토리 경로
_CONFIG_PATH = Path(__file__).parent / "config.json"
_WORKFLOWS_DIR = Path(__file__).parent / "workflows"


def _load_config() -> dict:
    """config.json을 로드한다."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_workflow(name: str) -> dict:
    """workflows/ 디렉토리에서 워크플로우 JSON을 로드한다."""
    path = _WORKFLOWS_DIR / name
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def resolve_checkpoint(art_style: str, config: Optional[dict] = None) -> str:
    """아트 스타일에 해당하는 체크포인트 파일명을 반환한다."""
    cfg = config or _load_config()
    style_info = cfg["style_mapping"].get(art_style, cfg["style_mapping"]["realistic"])
    return style_info["checkpoint"]


def resolve_base_model(art_style: str, config: Optional[dict] = None) -> str:
    """아트 스타일에 해당하는 기반 모델(SD1.5/SDXL/Flux.1)을 반환한다."""
    cfg = config or _load_config()
    style_info = cfg["style_mapping"].get(art_style, cfg["style_mapping"]["realistic"])
    return style_info["base_model"]


def resolve_style_loras(art_style: str, config: Optional[dict] = None) -> list[dict]:
    """아트 스타일에 해당하는 스타일 LoRA 목록을 반환한다."""
    cfg = config or _load_config()
    style_info = cfg["style_mapping"].get(art_style, cfg["style_mapping"]["realistic"])
    return style_info.get("style_loras", [])


def resolve_detail_loras(keys: list[str], base_model: str, config: Optional[dict] = None) -> list[dict]:
    """기반 모델과 호환되는 디테일 향상 LoRA 목록만 필터링해서 반환한다."""
    cfg = config or _load_config()
    detail_map = cfg["detail_lora_mapping"]
    result = []
    for key in keys:
        if not key.strip():
            continue
        key = key.strip()
        if key not in detail_map:
            logger.warning(f"알 수 없는 디테일 LoRA 키: {key}")
            continue
        lora_info = detail_map[key]
        if not lora_info.get("installed", True):
            logger.info(f"디테일 LoRA '{key}' - 미설치 (config.json installed=false), 건너뜀")
            continue
        if base_model not in lora_info["base_models"]:
            logger.info(f"디테일 LoRA '{key}' - 기반 모델 {base_model} 미지원, 건너뜀")
            continue
        result.append({
            "name": lora_info["filename"],
            "strength_model": lora_info["default_weight"],
            "strength_clip": lora_info["default_weight"],
        })
    return result


def resolve_motion_module(base_model: str, config: Optional[dict] = None) -> str:
    """기반 모델에 해당하는 AnimateDiff 모션 모듈 파일명을 반환한다."""
    cfg = config or _load_config()
    mapping = cfg["motion_module_mapping"]
    return mapping.get(base_model, cfg["default_motion_module"])


def build_prompt_keywords(params: dict, config: Optional[dict] = None) -> dict:
    """파라미터에서 프롬프트 키워드 딕셔너리를 구성한다.

    Returns:
        {"positive_keywords": [...], "negative_keywords": [...]}
    """
    cfg = config or _load_config()
    art_style = params.get("art_style", "realistic")
    style_info = cfg["style_mapping"].get(art_style, cfg["style_mapping"]["realistic"])
    keywords = list(style_info.get("prompt_keywords", []))

    # 캐릭터 키워드 매핑 (얼굴형, 헤어스타일, 헤어색상, 눈, 의상)
    char_map = cfg.get("character_keyword_map", {})
    for field in ["character_face", "character_hair_style", "character_hair_color", "character_eyes", "character_outfit"]:
        val = params.get(field, "")
        if val and val in char_map:
            keywords.append(char_map[val])

    # 카메라 키워드 매핑 (앵글, 구도, 심도)
    cam_map = cfg.get("camera_keyword_map", {})
    for field in ["camera_angle", "camera_composition", "depth_of_field"]:
        val = params.get(field, "")
        if val and val in cam_map:
            keywords.append(cam_map[val])

    # 조명 키워드
    lighting_map = cfg.get("lighting_keyword_map", {})
    lighting = params.get("lighting", "")
    if lighting and lighting in lighting_map:
        keywords.append(lighting_map[lighting])

    # 배경 키워드
    bg_map = cfg.get("background_keyword_map", {})
    background = params.get("background", "")
    if background and background in bg_map:
        keywords.append(bg_map[background])

    return {"positive_keywords": keywords, "negative_keywords": []}


def _insert_lora_nodes(
    workflow: dict,
    loras: list[dict],
    model_input_ref: list,
    clip_input_ref: list,
) -> tuple[dict, list, list]:
    """워크플로우에 LoRA 노드를 체인으로 삽입한다.

    Args:
        workflow: 수정할 워크플로우 dict (deepcopy 권장)
        loras: [{"name": str, "strength_model": float, "strength_clip": float}, ...]
        model_input_ref: 현재 model 입력 참조 [node_id, output_idx]
        clip_input_ref: 현재 clip 입력 참조 [node_id, output_idx]

    Returns:
        (수정된 workflow, 마지막 model 참조, 마지막 clip 참조)
    """
    if not loras:
        return workflow, model_input_ref, clip_input_ref

    # 새 노드 ID: 기존 최대 정수 ID + 1부터 순차 부여
    existing_ids = [int(k) for k in workflow.keys() if k.isdigit()]
    next_id = max(existing_ids) + 1 if existing_ids else 100

    current_model = model_input_ref
    current_clip = clip_input_ref

    for lora in loras:
        node_id = str(next_id)
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": current_model,
                "clip": current_clip,
                "lora_name": lora["name"],
                "strength_model": lora["strength_model"],
                "strength_clip": lora["strength_clip"],
            }
        }
        current_model = [node_id, 0]
        current_clip = [node_id, 1]
        next_id += 1

    return workflow, current_model, current_clip


def build_workflow(
    generation_type: str,
    art_style: str,
    prompt: dict,
    params: dict,
    config: Optional[dict] = None,
) -> dict:
    """완성된 ComfyUI 워크플로우 dict를 반환한다.

    Args:
        generation_type: "image" 또는 "video"
        art_style: 아트 스타일 키 (예: "anime")
        prompt: {"positive": str, "negative": str} 또는 {"flux_prompt": str}
        params: 사용자 입력 파라미터 전체
        config: config.json dict (None이면 파일에서 로드)

    Returns:
        ComfyUI API 포맷 워크플로우 dict
    """
    cfg = config or _load_config()
    base_model = resolve_base_model(art_style, cfg)
    checkpoint = resolve_checkpoint(art_style, cfg)
    style_loras = resolve_style_loras(art_style, cfg)

    # 디테일 향상 LoRA 키 파싱 (쉼표 구분 문자열 또는 리스트)
    detail_lora_raw = params.get("detail_loras", "")
    if isinstance(detail_lora_raw, str):
        detail_lora_keys = [k.strip() for k in detail_lora_raw.split(",") if k.strip()]
    else:
        detail_lora_keys = list(detail_lora_raw) if detail_lora_raw else []
    detail_loras = resolve_detail_loras(detail_lora_keys, base_model, cfg)
    all_loras = style_loras + detail_loras

    # 공통 파라미터
    width = int(params.get("width", 512))
    height = int(params.get("height", 768))
    steps = int(params.get("steps", 20))
    cfg_scale = float(params.get("cfg_scale", 7))
    seed = int(params.get("seed", -1))

    # --- Flux.1 이미지 생성 경로 ---
    if base_model == "Flux.1" or art_style == "flux":
        wf = copy.deepcopy(_load_workflow("flux_base.json"))
        flux_prompt = prompt.get("flux_prompt") or prompt.get("positive", "")
        # 텍스트 인코딩 노드 6 업데이트
        if "6" in wf:
            wf["6"]["inputs"]["text"] = flux_prompt
        # 이미지 크기 노드 7 업데이트
        if "7" in wf:
            wf["7"]["inputs"].update({"width": width, "height": height})
        # KSampler 노드 8 업데이트
        if "8" in wf:
            wf["8"]["inputs"].update({"seed": seed, "steps": steps, "cfg": 1.0})
        # Flux LoRA 삽입 (LoraLoaderModelOnly — clip 출력 없음)
        if all_loras and "1" in wf:
            existing_ids = [int(k) for k in wf.keys() if k.isdigit()]
            next_id = max(existing_ids) + 1
            current_model = ["1", 0]
            for lora in all_loras:
                node_id = str(next_id)
                wf[node_id] = {
                    "class_type": "LoraLoaderModelOnly",
                    "inputs": {
                        "model": current_model,
                        "lora_name": lora["name"],
                        "strength_model": lora["strength_model"],
                    }
                }
                current_model = [node_id, 0]
                next_id += 1
            # KSampler의 model 입력을 마지막 LoRA 노드로 연결
            if "8" in wf:
                wf["8"]["inputs"]["model"] = current_model
        return wf

    # --- AnimateDiff 비디오 생성 경로 ---
    if generation_type == "video":
        wf = copy.deepcopy(_load_workflow("animatediff_base.json"))
        motion_module = resolve_motion_module(base_model, cfg)
        # 체크포인트 노드 1
        if "1" in wf:
            wf["1"]["inputs"]["ckpt_name"] = checkpoint
        # 긍정/부정 프롬프트 노드 2, 3
        if "2" in wf:
            wf["2"]["inputs"]["text"] = prompt.get("positive", "masterpiece, best quality")
        if "3" in wf:
            wf["3"]["inputs"]["text"] = prompt.get("negative", "worst quality, low quality")
        # AnimateDiff 모션 모듈 노드 4
        if "4" in wf:
            wf["4"]["inputs"]["model_name"] = motion_module
        # AnimateDiff 설정 노드 5 (프레임 수, 시드, 루프)
        video_length = int(params.get("video_length", 16))
        loop = params.get("loop_animation", "false") == "true"
        if "5" in wf:
            wf["5"]["inputs"].update({
                "batch_size": video_length,
                "seed_gen_override": seed,
                "closed_loop": "R" if loop else "N",
            })
        # EmptyLatentImage 노드 8
        if "8" in wf:
            wf["8"]["inputs"].update({"width": width, "height": height, "batch_size": 1})
        # KSampler 노드 7
        if "7" in wf:
            wf["7"]["inputs"].update({"seed": seed, "steps": steps, "cfg": cfg_scale})
        # FPS 노드 10
        fps = int(params.get("fps", 8))
        if "10" in wf:
            wf["10"]["inputs"]["frame_rate"] = fps
        # LoRA 체인 삽입 - 체크포인트 노드 1 뒤에 연결
        if all_loras:
            wf, model_ref, clip_ref = _insert_lora_nodes(
                wf, all_loras,
                model_input_ref=["1", 0],
                clip_input_ref=["1", 1],
            )
            # AnimateDiff Apply 노드 6의 unet 입력 업데이트
            if "6" in wf:
                wf["6"]["inputs"]["unet"] = model_ref
            # 텍스트 인코딩 노드 2, 3의 clip 입력 업데이트
            if "2" in wf:
                wf["2"]["inputs"]["clip"] = clip_ref
            if "3" in wf:
                wf["3"]["inputs"]["clip"] = clip_ref
        return wf

    # --- SD 이미지 생성 경로 ---
    else:
        wf = copy.deepcopy(_load_workflow("animatediff_base.json"))
        # 체크포인트 노드 1
        if "1" in wf:
            wf["1"]["inputs"]["ckpt_name"] = checkpoint
        # 프롬프트 노드 2, 3
        if "2" in wf:
            wf["2"]["inputs"]["text"] = prompt.get("positive", "masterpiece, best quality")
        if "3" in wf:
            wf["3"]["inputs"]["text"] = prompt.get("negative", "worst quality, low quality")
        # 이미지 크기 노드 8
        if "8" in wf:
            wf["8"]["inputs"].update({"width": width, "height": height, "batch_size": 1})
        # KSampler 노드 7 - AnimateDiff 노드 없이 체크포인트 직결
        if "7" in wf:
            wf["7"]["inputs"].update({
                "model": ["1", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg_scale,
            })
        # VHS_VideoCombine 노드 10을 SaveImage로 교체
        if "10" in wf:
            wf["10"] = {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["9", 0],
                    "filename_prefix": "SD_image",
                }
            }
        # LoRA 체인 삽입
        if all_loras:
            wf, model_ref, clip_ref = _insert_lora_nodes(
                wf, all_loras,
                model_input_ref=["1", 0],
                clip_input_ref=["1", 1],
            )
            if "7" in wf:
                wf["7"]["inputs"]["model"] = model_ref
            if "2" in wf:
                wf["2"]["inputs"]["clip"] = clip_ref
            if "3" in wf:
                wf["3"]["inputs"]["clip"] = clip_ref
        # AnimateDiff 전용 노드(모션 모듈, 설정, Apply) 제거
        for node_id in ["4", "5", "6"]:
            wf.pop(node_id, None)
        return wf
