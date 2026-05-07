# 목적: Ollama를 사용하여 SD/AnimateDiff 및 Flux.1 프롬프트를 자동 생성하는 모듈
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import re
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Ollama 기본 엔드포인트
OLLAMA_BASE_URL = "http://localhost:11434"

# 자동 선택 시 우선 순위 폴백 모델 목록 (경량 모델 우선)
_FALLBACK_MODELS = ["exaone3.5:2.4b", "qwen3:4b", "gemma3:4b", "llama3.2:3b"]


def _call_ollama_json(prompt: str, model: str, timeout: int = 60) -> Optional[dict]:
    """Ollama /api/chat에 JSON 포맷 요청을 보내고 파싱 결과를 반환한다.

    JSON 파싱 3단계 폴백 전략:
    1. json.loads() 직접 파싱
    2. ```json ... ``` 코드 블록 정규표현식 추출
    3. { ... } 사이 텍스트 추출

    Args:
        prompt: 사용자 메시지 내용
        model: 사용할 Ollama 모델명
        timeout: 요청 타임아웃 초

    Returns:
        파싱된 dict, 실패 시 None
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
        },
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            # Ollama 응답에서 assistant 메시지 content 추출
            content = resp.json().get("message", {}).get("content", "")
    except Exception as e:
        logger.error(f"Ollama 호출 실패 (model={model}): {e}")
        return None

    # 파싱 시도 1: content를 직접 JSON 파싱
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 파싱 시도 2: ```json ... ``` 마크다운 코드 블록 추출
    match = re.search(r"```json\s*([\s\S]+?)\s*```", content)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 파싱 시도 3: { ... } 사이 첫 번째 JSON 오브젝트 추출
    match = re.search(r"\{[\s\S]+\}", content)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning(f"JSON 파싱 실패 (model={model}) -- 원본 응답 앞부분: {content[:200]}")
    return None


def _get_model(preferred: Optional[str] = None) -> str:
    """사용 가능한 Ollama 모델을 선택한다.

    preferred가 지정된 경우 그대로 사용.
    지정되지 않은 경우 Ollama /api/tags에서 설치된 모델 목록을 조회하여
    _FALLBACK_MODELS 우선순위대로 선택. 조회 실패 시 첫 번째 폴백 모델 반환.

    Args:
        preferred: 명시적으로 지정된 모델명 (None이면 자동 선택)

    Returns:
        선택된 모델명 문자열
    """
    if preferred:
        return preferred

    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                # 설치된 모델 이름 목록
                available = [m["name"] for m in resp.json().get("models", [])]
                for fb in _FALLBACK_MODELS:
                    if fb in available:
                        logger.info(f"자동 선택된 Ollama 모델: {fb}")
                        return fb
    except Exception as e:
        logger.warning(f"Ollama 모델 목록 조회 실패: {e}")

    # 조회 실패 또는 매칭 없을 때 첫 번째 폴백 사용
    logger.warning(f"폴백 모델 사용: {_FALLBACK_MODELS[0]}")
    return _FALLBACK_MODELS[0]


def generate_sd_prompt(
    style_context: dict,
    user_description: str,
    model: Optional[str] = None,
) -> dict:
    """SD/AnimateDiff 경로용 포지티브/네거티브 프롬프트 생성.

    Ollama에게 style_context 키워드와 user_description을 바탕으로
    SD 형식(태그 열거형)의 포지티브/네거티브 프롬프트를 생성하도록 요청한다.

    Args:
        style_context: style_mapper에서 생성한 스타일 키워드 dict.
                       "positive_keywords" 키에 리스트가 있어야 한다.
        user_description: 사용자 입력 추가 설명 (한국어 가능)
        model: 사용할 Ollama 모델명 (None이면 자동 선택)

    Returns:
        {"positive": str, "negative": str}
        Ollama 호출 실패 시 기본값 dict 반환
    """
    # style_context에서 포지티브 키워드 추출
    style_keywords = ", ".join(style_context.get("positive_keywords", []))
    selected_model = _get_model(model)

    logger.info(f"SD 프롬프트 생성 시작 (model={selected_model})")

    prompt_text = f"""You are a Stable Diffusion prompt engineer. Generate a high-quality prompt.

Style keywords: {style_keywords}
User description: {user_description}

Return JSON with exactly these keys:
- "positive": detailed positive prompt in English (start with "masterpiece, best quality,")
- "negative": negative prompt in English (start with "worst quality, low quality,")

Keep each prompt under 200 words."""

    result = _call_ollama_json(prompt_text, selected_model)

    if result and "positive" in result:
        logger.info("SD 프롬프트 생성 성공")
        return {
            "positive": result.get("positive", "masterpiece, best quality, 1girl"),
            "negative": result.get("negative", "worst quality, low quality, nsfw"),
        }

    # 폴백: Ollama 실패 시 style_keywords와 user_description으로 기본 프롬프트 구성
    logger.warning("SD 프롬프트 생성 실패 -- 기본값 사용")
    positive = f"masterpiece, best quality, {style_keywords}"
    if user_description:
        positive += f", {user_description}"
    return {
        "positive": positive,
        "negative": "worst quality, low quality, nsfw, blurry, watermark, text",
    }


def generate_flux_prompt(
    style_context: dict,
    user_description: str,
    model: Optional[str] = None,
) -> str:
    """Flux.1 경로용 단일 자연어 프롬프트 생성.

    Flux.1은 자연어 서술형 프롬프트가 효과적이므로 태그 열거 대신
    2-4문장의 설명형 영어 프롬프트를 생성한다.

    Args:
        style_context: style_mapper에서 생성한 스타일 키워드 dict.
                       "positive_keywords" 키에 리스트가 있어야 한다.
        user_description: 사용자 입력 추가 설명 (한국어 가능)
        model: 사용할 Ollama 모델명 (None이면 자동 선택)

    Returns:
        자연어 프롬프트 문자열
        Ollama 호출 실패 시 기본 문자열 반환
    """
    # style_context에서 포지티브 키워드 추출
    style_keywords = ", ".join(style_context.get("positive_keywords", []))
    selected_model = _get_model(model)

    logger.info(f"Flux 프롬프트 생성 시작 (model={selected_model})")

    prompt_text = f"""You are a Flux.1 image generation prompt engineer. Generate a natural language prompt.

Style keywords: {style_keywords}
User description: {user_description}

Return JSON with exactly one key:
- "prompt": a detailed, natural language description in English for Flux.1 (2-4 sentences, highly descriptive)"""

    result = _call_ollama_json(prompt_text, selected_model)

    if result and "prompt" in result:
        logger.info("Flux 프롬프트 생성 성공")
        return result["prompt"]

    # 폴백: Ollama 실패 시 style_keywords와 user_description으로 기본 프롬프트 구성
    logger.warning("Flux 프롬프트 생성 실패 -- 기본값 사용")
    base = f"A highly detailed, photorealistic image with {style_keywords} aesthetic"
    if user_description:
        base += f". {user_description}"
    return base
