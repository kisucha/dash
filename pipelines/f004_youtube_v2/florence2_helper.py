# 목적: F004 Florence-2 비전 모델 래퍼 — 이미지 캡션/분석으로 img2img 프롬프트 품질 향상
# MiaoshouAI/Florence-2-base-PromptGen-v2.0 (로컬 HuggingFace 캐시 사용)
# 모델은 첫 호출 시 로드 후 모듈 수준 싱글턴으로 캐시된다.

import sys
import logging
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)

# 모델 ID — HuggingFace 캐시에서 확인된 정확한 ID
FLORENCE2_MODEL_ID = "MiaoshouAI/Florence-2-base-PromptGen-v2.0"

# 모듈 수준 싱글턴 — 최초 호출 시 로드, 이후 재사용
_model = None
_processor = None


def _load_model():
    """Florence-2 모델과 프로세서를 로드하여 싱글턴 캐시에 저장.

    GPU 사용 가능 시 자동으로 cuda 디바이스를 선택한다.
    처음 호출 시에만 로드하고 이후 캐시된 인스턴스를 반환한다.

    Raises:
        ImportError: transformers 미설치 시
        RuntimeError: 모델 로드 실패 시
    """
    global _model, _processor
    if _model is not None:
        return _model, _processor

    try:
        import torch
        from transformers import AutoProcessor, AutoModelForCausalLM
    except ImportError as e:
        raise ImportError(
            f"transformers 패키지가 필요합니다. "
            f"pip install transformers torch 실행 후 재시도하세요. ({e})"
        ) from e

    logger.info(f"Florence-2 모델 로드 시작: {FLORENCE2_MODEL_ID}")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        _processor = AutoProcessor.from_pretrained(
            FLORENCE2_MODEL_ID, trust_remote_code=True
        )
        _model = AutoModelForCausalLM.from_pretrained(
            FLORENCE2_MODEL_ID,
            trust_remote_code=True,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        ).to(device).eval()
        logger.info(f"Florence-2 모델 로드 완료 (device={device})")
    except Exception as e:
        _model = None
        _processor = None
        raise RuntimeError(f"Florence-2 모델 로드 실패: {e}") from e

    return _model, _processor


def get_detailed_caption(image_path: str) -> Optional[str]:
    """이미지 파일에서 상세 캡션(DETAILED_CAPTION)을 추출.

    img2img SD 프롬프트 보강에 사용된다.
    실패 시 None을 반환하여 호출부에서 폴백 처리할 수 있게 한다.

    Args:
        image_path: 분석할 이미지 파일 절대 경로

    Returns:
        상세 캡션 문자열 또는 None (실패 시)
    """
    try:
        from PIL import Image as _PIL_Image
        model, processor = _load_model()

        import torch
        device = next(model.parameters()).device

        image = _PIL_Image.open(image_path).convert("RGB")
        task_prompt = "<DETAILED_CAPTION>"

        inputs = processor(
            text=task_prompt,
            images=image,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=256,
                do_sample=False,
            )

        generated_text = processor.batch_decode(
            generated_ids, skip_special_tokens=False
        )[0]
        parsed = processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height),
        )
        caption = parsed.get(task_prompt, "")
        logger.info(f"Florence-2 DETAILED_CAPTION: {caption[:100]}")
        return caption.strip() if caption else None

    except Exception as e:
        logger.warning(f"Florence-2 캡션 추출 실패 (폴백): {e}")
        return None


def get_caption(image_path: str) -> Optional[str]:
    """이미지 파일에서 기본 캡션(CAPTION)을 추출.

    생성된 클립 품질 검수에 사용된다.

    Args:
        image_path: 분석할 이미지 파일 절대 경로

    Returns:
        캡션 문자열 또는 None
    """
    try:
        from PIL import Image as _PIL_Image
        model, processor = _load_model()

        import torch
        device = next(model.parameters()).device

        image = _PIL_Image.open(image_path).convert("RGB")
        task_prompt = "<CAPTION>"

        inputs = processor(
            text=task_prompt,
            images=image,
            return_tensors="pt",
        )
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            generated_ids = model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=128,
                do_sample=False,
            )

        generated_text = processor.batch_decode(
            generated_ids, skip_special_tokens=False
        )[0]
        parsed = processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(image.width, image.height),
        )
        caption = parsed.get(task_prompt, "")
        return caption.strip() if caption else None

    except Exception as e:
        logger.warning(f"Florence-2 CAPTION 추출 실패: {e}")
        return None
