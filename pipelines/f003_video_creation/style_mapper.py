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


def resolve_style_loras(
    art_style: str,
    config: Optional[dict] = None,
    available_loras: Optional[list] = None,
) -> list[dict]:
    """아트 스타일에 해당하는 스타일 LoRA 목록을 반환한다.

    available_loras가 지정되면 ComfyUI에 실제 설치된 LoRA만 반환한다.
    """
    cfg = config or _load_config()
    style_info = cfg["style_mapping"].get(art_style, cfg["style_mapping"]["realistic"])
    loras = style_info.get("style_loras", [])
    if available_loras is not None:
        filtered = [l for l in loras if l["name"] in available_loras]
        skipped = [l["name"] for l in loras if l["name"] not in available_loras]
        if skipped:
            logger.warning(f"스타일 LoRA ComfyUI 미설치로 건너뜀: {skipped}")
        return filtered
    return loras


def resolve_detail_loras(
    items: list,
    base_model: str,
    config: Optional[dict] = None,
    available_loras: Optional[list] = None,
) -> list[dict]:
    """기반 모델과 호환되며 ComfyUI에 설치된 디테일 향상 LoRA 목록만 반환한다.

    items 형식:
      - 문자열 리스트 ["key1", "key2"] -> config.json default_weight 사용 (하위 호환)
      - 객체 리스트 [{"key": "k1", "strength": 1.2}] -> 사용자 지정 strength 우선
    """
    cfg = config or _load_config()
    detail_map = cfg["detail_lora_mapping"]
    result = []
    for item in items:
        if isinstance(item, str):
            key = item.strip()
            user_strength = None
        else:
            key = item.get("key", "").strip()
            user_strength = item.get("strength")

        if not key:
            continue
        if key not in detail_map:
            logger.warning(f"알 수 없는 디테일 LoRA 키: {key}")
            continue
        lora_info = detail_map[key]
        if base_model not in lora_info["base_models"]:
            logger.info(f"디테일 LoRA '{key}' - 기반 모델 {base_model} 미지원, 건너뜀")
            continue
        if available_loras is not None and lora_info["filename"] not in available_loras:
            logger.info(f"디테일 LoRA '{key}' ({lora_info['filename']}) - ComfyUI 미설치, 건너뜀")
            continue
        weight = user_strength if user_strength is not None else lora_info["default_weight"]
        result.append({
            "name": lora_info["filename"],
            "strength_model": weight,
            "strength_clip": weight,
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


def _parse_detail_loras(raw) -> list:
    """detail_loras 파라미터를 아이템 리스트로 파싱한다.

    지원 형식:
      - 빈 문자열/None -> []
      - 쉼표 구분 문자열 "k1,k2" -> ["k1", "k2"]  (하위 호환)
      - JSON 배열 문자열 '[{"key":"k1","strength":1.2}]' -> [{"key":"k1","strength":1.2}]
      - 이미 리스트인 경우 그대로 반환
    """
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        return [k.strip() for k in stripped.split(",") if k.strip()]
    return []


def _insert_vae_node(workflow: dict, vae_name: str) -> tuple[dict, str]:
    """워크플로우에 VAELoader 노드를 삽입하고 새 노드 ID를 반환한다.

    VAEDecode/VAEEncode 노드의 vae 입력 교체는 호출 측에서 처리한다.
    LoRA 노드 삽입 이후 호출해야 ID 충돌이 없다.

    Returns:
        (수정된 workflow, 새 VAELoader 노드 ID 문자열)
    """
    existing_ids = [int(k) for k in workflow.keys() if k.isdigit()]
    new_id = str(max(existing_ids) + 1 if existing_ids else 100)
    workflow[new_id] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": vae_name},
    }
    return workflow, new_id


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


def collect_trigger_words(
    art_style: str,
    detail_lora_keys: list[str],
    base_model: str,
    config: Optional[dict] = None,
    available_loras: Optional[list] = None,
) -> list[str]:
    """활성화된 LoRA들의 트리거 워드를 수집해 반환한다.

    style_loras와 detail_loras 중 실제 사용되는(available_loras에 있는) 것만 수집.
    Flux.1 모델은 trigger_words_flux 우선 사용.
    """
    cfg = config or _load_config()
    triggers: list[str] = []

    # 스타일 LoRA 트리거 워드 수집
    style_info = cfg["style_mapping"].get(art_style, {})
    for lora in style_info.get("style_loras", []):
        # available_loras가 지정된 경우 실제 설치된 LoRA만 처리
        if available_loras is not None and lora["name"] not in available_loras:
            continue
        for tw in lora.get("trigger_words", []):
            if tw and tw not in triggers:
                triggers.append(tw)

    # 디테일 LoRA 트리거 워드 수집
    detail_map = cfg.get("detail_lora_mapping", {})
    for key in detail_lora_keys:
        if key not in detail_map:
            continue
        info = detail_map[key]
        # 기반 모델 호환성 확인
        if base_model not in info.get("base_models", []):
            continue
        filename = info["filename"]
        # available_loras가 지정된 경우 실제 설치된 LoRA만 처리
        if available_loras is not None and filename not in available_loras:
            continue
        # Flux.1 모델은 trigger_words_flux 우선 사용
        if base_model == "Flux.1" and info.get("trigger_words_flux"):
            word_list = info["trigger_words_flux"]
        else:
            word_list = info.get("trigger_words", [])
        for tw in word_list:
            if tw and tw not in triggers:
                triggers.append(tw)

    return triggers


def build_workflow(
    generation_type: str,
    art_style: str,
    prompt: dict,
    params: dict,
    config: Optional[dict] = None,
    available_loras: Optional[list] = None,
    input_image_filename: Optional[str] = None,
) -> dict:
    """완성된 ComfyUI 워크플로우 dict를 반환한다.

    Args:
        generation_type: "image" 또는 "video"
        art_style: 아트 스타일 키 (예: "anime")
        prompt: {"positive": str, "negative": str} 또는 {"flux_prompt": str}
        params: 사용자 입력 파라미터 전체 (denoise, width, height 등 포함)
        config: config.json dict (None이면 파일에서 로드)
        available_loras: ComfyUI에 설치된 LoRA 파일명 목록
        input_image_filename: img2img 모드 시 ComfyUI 서버의 입력 이미지 파일명.
                              None이면 txt2img 경로, 지정 시 img2img 워크플로우 사용.
                              비디오 경로(generation_type="video")에서는 무시됨.

    Returns:
        ComfyUI API 포맷 워크플로우 dict
    """
    cfg = config or _load_config()
    base_model = resolve_base_model(art_style, cfg)
    checkpoint = resolve_checkpoint(art_style, cfg)
    style_loras = resolve_style_loras(art_style, cfg, available_loras)

    # 사용자 커스텀 체크포인트 우선 적용
    custom_checkpoint = params.get("custom_checkpoint", "").strip()
    custom_vae = params.get("custom_vae", "").strip()
    if custom_checkpoint:
        checkpoint = custom_checkpoint
        logger.info(f"커스텀 체크포인트 적용: {checkpoint}")

    # 디테일 향상 LoRA 파싱 (문자열/JSON 배열/리스트 모두 지원)
    detail_lora_items = _parse_detail_loras(params.get("detail_loras", ""))
    detail_loras = resolve_detail_loras(detail_lora_items, base_model, cfg, available_loras)
    all_loras = style_loras + detail_loras

    # 공통 파라미터
    width = int(params.get("width", 512))
    height = int(params.get("height", 768))
    steps = int(params.get("steps", 20))
    cfg_scale = float(params.get("cfg_scale", 7))
    seed = int(params.get("seed", -1))

    # --- Flux.1 이미지 생성 경로 ---
    if base_model == "Flux.1" or art_style == "flux":
        flux_prompt = prompt.get("flux_prompt") or prompt.get("positive", "")

        if input_image_filename:
            # img2img 경로: VAEEncode 기반 워크플로우 사용
            wf = copy.deepcopy(_load_workflow("img2img_flux_base.json"))
            # UNETLoader 노드 1 — diffusion 모델 파일명 설정
            cfg_flux = cfg.get("flux_model", {})
            if "1" in wf:
                wf["1"]["inputs"]["unet_name"] = cfg_flux.get(
                    "diffusion_model", "flux1-schnell.safetensors"
                )
            # LoadImage 노드 4 — 업로드된 입력 이미지 참조
            if "4" in wf:
                wf["4"]["inputs"]["image"] = input_image_filename
            # ImageScale 노드 12 — 출력 해상도 설정
            if "12" in wf:
                wf["12"]["inputs"].update({"width": width, "height": height})
            # CLIPTextEncode 노드 6 — 프롬프트 텍스트
            if "6" in wf:
                wf["6"]["inputs"]["text"] = flux_prompt
            # KSampler 노드 8 — 시드/스텝/denoise 설정
            denoise_val = float(params.get("denoise", 0.75))
            if "8" in wf:
                wf["8"]["inputs"].update({
                    "seed": seed,
                    "steps": steps,
                    "cfg": 1.0,
                    "denoise": denoise_val,
                })
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
            # custom_vae 적용 — class_type 탐색으로 VAELoader 노드 위치를 찾아 교체
            # 노드 ID "2" 하드코딩 대신 탐색하여 워크플로우 구조 변경에 대응
            if custom_vae:
                flux_vae_nodes = [k for k, v in wf.items() if v.get("class_type") == "VAELoader"]
                if flux_vae_nodes:
                    for n in flux_vae_nodes:
                        wf[n]["inputs"]["vae_name"] = custom_vae
                else:
                    # VAELoader 노드가 없는 워크플로우 변형에 대비해 새로 삽입
                    wf, _ = _insert_vae_node(wf, custom_vae)
                    logger.info("Flux img2img: VAELoader 노드 미발견, 새 노드 삽입")
            return wf
        else:
            # txt2img 경로: EmptyLatentImage 기반 워크플로우 사용
            wf = copy.deepcopy(_load_workflow("flux_base.json"))
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
            # custom_vae 적용 — class_type 탐색으로 VAELoader 노드 위치를 찾아 교체
            if custom_vae:
                flux_vae_nodes = [k for k, v in wf.items() if v.get("class_type") == "VAELoader"]
                if flux_vae_nodes:
                    for n in flux_vae_nodes:
                        wf[n]["inputs"]["vae_name"] = custom_vae
                else:
                    wf, _ = _insert_vae_node(wf, custom_vae)
                    logger.info("Flux txt2img: VAELoader 노드 미발견, 새 노드 삽입")
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
        # custom_vae 적용 — LoRA 삽입 이후 VAE 노드 삽입 (ID 충돌 방지)
        if custom_vae:
            wf, vae_node_id = _insert_vae_node(wf, custom_vae)
            vae_decode_nodes = [k for k, v in wf.items() if v.get("class_type") == "VAEDecode"]
            if not vae_decode_nodes:
                # 워크플로우 구조 변경으로 VAEDecode 노드가 없는 경우 — silent 무시 방지
                logger.warning("custom_vae 적용 불완전: animatediff 워크플로우에 VAEDecode 노드 없음")
            for n in vae_decode_nodes:
                wf[n]["inputs"]["vae"] = [vae_node_id, 0]
        return wf

    # --- SD 이미지 생성 경로 ---
    else:
        if input_image_filename:
            # img2img 경로: VAEEncode 기반 전용 워크플로우 사용
            wf = copy.deepcopy(_load_workflow("img2img_sd_base.json"))
            # 체크포인트 노드 1
            if "1" in wf:
                wf["1"]["inputs"]["ckpt_name"] = checkpoint
            # 긍정 프롬프트 노드 2
            if "2" in wf:
                wf["2"]["inputs"]["text"] = prompt.get("positive", "masterpiece, best quality")
            # 부정 프롬프트 노드 3
            if "3" in wf:
                wf["3"]["inputs"]["text"] = prompt.get("negative", "worst quality, low quality")
            # LoadImage 노드 4 — 업로드된 입력 이미지 참조
            if "4" in wf:
                wf["4"]["inputs"]["image"] = input_image_filename
            # ImageScale 노드 12 — 출력 해상도 설정
            if "12" in wf:
                wf["12"]["inputs"].update({"width": width, "height": height})
            # KSampler 노드 6 — 시드/스텝/cfg/denoise 설정
            denoise_val = float(params.get("denoise", 0.75))
            if "6" in wf:
                wf["6"]["inputs"].update({
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg_scale,
                    "denoise": denoise_val,
                })
            # LoRA 체인 삽입 — 체크포인트 노드 1 뒤에 연결, KSampler/CLIP 업데이트
            if all_loras:
                wf, model_ref, clip_ref = _insert_lora_nodes(
                    wf, all_loras,
                    model_input_ref=["1", 0],
                    clip_input_ref=["1", 1],
                )
                if "6" in wf:
                    wf["6"]["inputs"]["model"] = model_ref
                if "2" in wf:
                    wf["2"]["inputs"]["clip"] = clip_ref
                if "3" in wf:
                    wf["3"]["inputs"]["clip"] = clip_ref
            # custom_vae 적용 — LoRA 삽입 이후 VAE 노드 삽입 (ID 충돌 방지)
            if custom_vae:
                wf, vae_node_id = _insert_vae_node(wf, custom_vae)
                # img2img_sd_base.json: VAEEncode 노드5, VAEDecode 노드7
                if "5" in wf:
                    wf["5"]["inputs"]["vae"] = [vae_node_id, 0]
                if "7" in wf:
                    wf["7"]["inputs"]["vae"] = [vae_node_id, 0]
            return wf
        else:
            # txt2img 경로: 전용 image_sd_base.json 사용 (SD1.5/SDXL 공용)
            wf = copy.deepcopy(_load_workflow("image_sd_base.json"))
            # 체크포인트 노드 1
            if "1" in wf:
                wf["1"]["inputs"]["ckpt_name"] = checkpoint
            # 긍정 프롬프트 노드 2
            if "2" in wf:
                wf["2"]["inputs"]["text"] = prompt.get("positive", "masterpiece, best quality")
            # 부정 프롬프트 노드 3
            if "3" in wf:
                wf["3"]["inputs"]["text"] = prompt.get("negative", "worst quality, low quality")
            # EmptyLatentImage 노드 4 — 해상도 설정
            if "4" in wf:
                wf["4"]["inputs"].update({"width": width, "height": height, "batch_size": 1})
            # KSampler 노드 5 — 샘플링 파라미터
            if "5" in wf:
                wf["5"]["inputs"].update({"seed": seed, "steps": steps, "cfg": cfg_scale})
            # LoRA 체인 삽입 — 체크포인트 노드 1 뒤에 연결, KSampler/CLIP 업데이트
            if all_loras:
                wf, model_ref, clip_ref = _insert_lora_nodes(
                    wf, all_loras,
                    model_input_ref=["1", 0],
                    clip_input_ref=["1", 1],
                )
                if "5" in wf:
                    wf["5"]["inputs"]["model"] = model_ref
                if "2" in wf:
                    wf["2"]["inputs"]["clip"] = clip_ref
                if "3" in wf:
                    wf["3"]["inputs"]["clip"] = clip_ref
            # custom_vae 적용 — LoRA 삽입 이후 VAE 노드 삽입 (ID 충돌 방지)
            if custom_vae:
                wf, vae_node_id = _insert_vae_node(wf, custom_vae)
                # image_sd_base.json: VAEDecode 노드6
                if "6" in wf:
                    wf["6"]["inputs"]["vae"] = [vae_node_id, 0]
            return wf
