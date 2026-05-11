# 목적: F003 영상제작 파이프라인 — ComfyUI + Ollama로 이미지/동영상 자동 생성
import sys
import json
import logging
import random
from pathlib import Path
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 프로젝트 루트를 sys.path에 추가 (독립 프로세스 실행 환경)
_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipelines.base import BasePipeline
from pipelines.f003_video_creation.comfyui_client import ComfyUIClient
from pipelines.f003_video_creation.model_manager import ModelManager
from pipelines.f003_video_creation.prompt_generator import generate_sd_prompt, generate_flux_prompt
from pipelines.f003_video_creation import style_mapper

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent / "config.json"


def _collect_missing_loras(
    art_style: str,
    params: dict,
    config: dict,
    base_model: str,
    available_loras: list[str],
) -> list[dict]:
    """ComfyUI에 미설치된 LoRA 중 다운로드 소스가 설정된 항목을 수집한다.

    style_loras는 config에 다운로드 소스 정보가 없으므로 경고만 출력.
    detail_loras는 civitai_version_id 또는 hf_repo_id가 있으면 다운로드 대상에 추가.

    Returns:
        [{"filename": str, "model_type": "lora", "source": str, "source_id": str}, ...]
    """
    required: list[dict] = []

    # 스타일 LoRA 미설치 확인 (다운로드 소스 없으면 경고만)
    style_info = config.get("style_mapping", {}).get(art_style, {})
    for lora in style_info.get("style_loras", []):
        if lora["name"] not in available_loras:
            logger.warning(
                f"스타일 LoRA '{lora['name']}' ComfyUI 미설치 — "
                "config에 다운로드 소스 미등록, 건너뜀"
            )

    # 디테일 LoRA 미설치 확인 (source 정보 있으면 다운로드 대상 추가)
    raw_items = style_mapper._parse_detail_loras(params.get("detail_loras", ""))
    detail_keys = [
        item if isinstance(item, str) else item.get("key", "")
        for item in raw_items
        if item
    ]

    detail_map = config.get("detail_lora_mapping", {})
    for key in detail_keys:
        if key not in detail_map:
            continue
        info = detail_map[key]
        if base_model not in info.get("base_models", []):
            continue
        filename = info["filename"]
        if filename in available_loras:
            continue
        # 다운로드 소스 확인
        civitai_id = info.get("civitai_version_id")
        hf_repo = info.get("hf_repo_id")
        if civitai_id:
            required.append({
                "filename": filename,
                "model_type": "lora",
                "source": "civitai",
                "source_id": str(civitai_id),
            })
        elif hf_repo:
            required.append({
                "filename": filename,
                "model_type": "lora",
                "source": "huggingface",
                "source_id": hf_repo,
            })
        else:
            logger.warning(
                f"디테일 LoRA '{key}' ({filename}) ComfyUI 미설치 — "
                "다운로드 소스 미등록, 건너뜀"
            )

    return required


# 출력 디렉토리 — config.json의 output_dir이 우선, 없으면 프로젝트 루트 기준 상대 경로 사용
_OUTPUT_DIR = Path(__file__).parent.parent.parent / "storage" / "results" / "f003"


def _load_config() -> dict:
    """config.json을 로드해 딕셔너리로 반환한다."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


class F003Pipeline(BasePipeline):
    """F003 영상제작 파이프라인 — ComfyUI + Ollama 기반 이미지/동영상 생성."""

    def get_metadata(self) -> dict:
        """파이프라인 메타데이터를 반환한다."""
        return {
            "feature_id": "F003",
            "name": "영상제작",
            "description": "ComfyUI와 Ollama를 활용하여 동영상(AnimateDiff) 또는 그림(Flux.1/SD)을 자동 생성합니다.",
            "supports_schedule": False,
            "input_schema": {},
        }

    def run(self, task_id: int, params: dict) -> dict:
        """파이프라인 메인 실행 로직.

        실행 순서:
        1. RUNNING 상태 업데이트
        2. config.json 로드
        3. ComfyUI 헬스체크
        4. 스타일 파라미터 해석
        5. 프롬프트 생성 (Ollama)
        6. 시드 처리
        7. 워크플로우 JSON 조립
        8. ComfyUI 워크플로우 제출
        9. 완료 대기 (WebSocket)
        10. 결과 파일 다운로드 및 저장
        11. DONE 상태 업데이트
        """
        # [1] RUNNING 상태 업데이트
        self.update_status(task_id, "RUNNING")
        logger.info(f"[F003][task_id={task_id}] 파이프라인 시작 — params: {params}")

        try:
            # [2] config 로드
            config = _load_config()
            comfyui_url = config.get("comfyui_url", "http://localhost:8188")
            output_dir = Path(config.get("output_dir", str(_OUTPUT_DIR)))
            output_dir.mkdir(parents=True, exist_ok=True)

            # [3] ComfyUI 헬스체크
            client = ComfyUIClient(comfyui_url)
            if not client.health_check():
                raise RuntimeError(f"ComfyUI 서버에 연결할 수 없습니다. ({comfyui_url})")
            logger.info(f"[F003][task_id={task_id}] ComfyUI 헬스체크 통과")

            if self.is_cancelled(task_id):
                self.update_status(task_id, "CANCELLED")
                return {}

            # [4] 스타일 파라미터 해석
            generation_type = params.get("generation_type", "image")
            art_style = params.get("art_style", "realistic")
            base_model = style_mapper.resolve_base_model(art_style, config)
            logger.info(
                f"[F003][task_id={task_id}] 생성 유형: {generation_type}, "
                f"스타일: {art_style}, 기반 모델: {base_model}"
            )

            # [4.5] 모델 가용성 확인 및 자동 다운로드
            # /object_info 단일 호출로 checkpoints·loras·vaes를 한꺼번에 조회 (중복 요청 방지)
            _model_lists = client.get_all_model_lists()
            available_checkpoints: list[str] = _model_lists["checkpoints"]
            available_loras: list[str] = _model_lists["loras"]
            _available_vaes: list[str] = _model_lists["vaes"]
            logger.info(
                f"[F003][task_id={task_id}] ComfyUI 가용 체크포인트 {len(available_checkpoints)}개, "
                f"LoRA {len(available_loras)}개, VAE {len(_available_vaes)}개"
            )

            # 체크포인트 존재 여부 사전 검증 (Flux.1 제외 — UNETLoader 경로 사용)
            if base_model != "Flux.1":
                custom_cp = params.get("custom_checkpoint", "").strip()
                required_checkpoint = custom_cp if custom_cp else style_mapper.resolve_checkpoint(art_style, config)
                if available_checkpoints and required_checkpoint not in available_checkpoints:
                    raise RuntimeError(
                        f"필요한 체크포인트 '{required_checkpoint}'이(가) ComfyUI에 설치되어 있지 않습니다. "
                        f"설치된 체크포인트: {available_checkpoints}"
                    )

            # custom_vae 설치 여부 사전 검증 — 이미 조회된 목록 재사용
            custom_vae = params.get("custom_vae", "").strip()
            if custom_vae and _available_vaes and custom_vae not in _available_vaes:
                raise RuntimeError(
                    f"선택한 VAE '{custom_vae}'이(가) ComfyUI에 설치되어 있지 않습니다. "
                    f"설치된 VAE: {_available_vaes}"
                )

            # 필요한 LoRA 중 미설치 항목을 자동 다운로드 시도
            mm = ModelManager(config.get("comfyui_path", r"C:\ComfyUI"))
            mm.scan_local_models()
            required_lora_models = _collect_missing_loras(
                art_style=art_style,
                params=params,
                config=config,
                base_model=base_model,
                available_loras=available_loras,
            )
            if required_lora_models:
                logger.info(
                    f"[F003][task_id={task_id}] 미설치 LoRA {len(required_lora_models)}개 "
                    f"자동 다운로드 시작: {[m['filename'] for m in required_lora_models]}"
                )
                ok = mm.ensure_models(
                    required_models=required_lora_models,
                    comfyui_client=client,
                    manager_url=config.get("comfyui_manager_url"),
                )
                if ok:
                    # 다운로드 완료 후 가용 목록 갱신
                    available_loras = client.get_available_loras()
                    logger.info(f"[F003][task_id={task_id}] 다운로드 완료, LoRA 목록 갱신")

            if self.is_cancelled(task_id):
                self.update_status(task_id, "CANCELLED")
                return {}

            # [5] 프롬프트 생성 (Ollama)
            style_context = style_mapper.build_prompt_keywords(params, config)
            user_description = params.get("user_description", "")
            logger.info(f"[F003][task_id={task_id}] 프롬프트 생성 시작")

            if base_model == "Flux.1":
                # Flux.1 모델: 단일 텍스트 프롬프트 구조
                flux_text = generate_flux_prompt(style_context, user_description)
                prompt = {"positive": flux_text, "negative": "", "flux_prompt": flux_text}
            else:
                # SD 계열 모델: positive/negative 분리 구조
                prompt = generate_sd_prompt(style_context, user_description)
            logger.info(f"[F003][task_id={task_id}] 프롬프트 생성 완료")

            if self.is_cancelled(task_id):
                self.update_status(task_id, "CANCELLED")
                return {}

            # [5.5] LoRA 트리거 워드를 포지티브 프롬프트에 주입
            # detail_loras 파라미터를 파싱해 키 목록으로 변환
            _raw = style_mapper._parse_detail_loras(params.get("detail_loras", ""))
            _detail_keys_for_trigger = [
                item if isinstance(item, str) else item.get("key", "")
                for item in _raw if item
            ]

            trigger_words = style_mapper.collect_trigger_words(
                art_style=art_style,
                detail_lora_keys=_detail_keys_for_trigger,
                base_model=base_model,
                config=config,
                available_loras=available_loras,
            )
            if trigger_words:
                tw_str = ", ".join(trigger_words)
                current_positive = prompt.get("positive") or prompt.get("flux_prompt", "")
                # 이미 주입된 트리거 워드는 중복 추가하지 않음
                if tw_str not in current_positive:
                    new_positive = f"{tw_str}, {current_positive}" if current_positive else tw_str
                    if "flux_prompt" in prompt:
                        prompt = {**prompt, "positive": new_positive, "flux_prompt": new_positive}
                    else:
                        prompt = {**prompt, "positive": new_positive}
                logger.info(f"[F003][task_id={task_id}] 트리거 워드 주입: {trigger_words}")

            # [6] 시드 처리 (-1이면 무작위 생성)
            seed = int(params.get("seed", -1))
            if seed == -1:
                seed = random.randint(0, 2**32 - 1)
            params_with_seed = {**params, "seed": seed}

            # [6.5] 입력 이미지 처리 (img2img 모드)
            # params에 input_image(base64)가 있으면 ComfyUI에 업로드하고 파일명을 얻는다
            import base64 as _base64
            input_image_b64 = params.get("input_image", "")
            comfyui_image_filename = None
            if input_image_b64:
                # data:image/xxx;base64, 헤더가 있으면 제거하고 순수 base64만 추출
                if "," in input_image_b64:
                    input_image_b64 = input_image_b64.split(",", 1)[1]
                image_bytes = _base64.b64decode(input_image_b64)
                comfyui_image_filename = client.upload_image(
                    image_bytes, f"task_{task_id}_input.png"
                )
                logger.info(
                    f"[F003][task_id={task_id}] 입력 이미지 업로드: {comfyui_image_filename}"
                )

            # [7] 워크플로우 JSON 조립 — ComfyUI 가용 목록 기준으로 LoRA 필터링
            workflow = style_mapper.build_workflow(
                generation_type=generation_type,
                art_style=art_style,
                prompt=prompt,
                params=params_with_seed,
                config=config,
                available_loras=available_loras,
                input_image_filename=comfyui_image_filename,
            )
            logger.info(
                f"[F003][task_id={task_id}] 워크플로우 조립 완료 (노드 수: {len(workflow)})"
            )

            # [8] ComfyUI 워크플로우 제출
            prompt_id = client.submit_workflow(workflow)
            logger.info(f"[F003][task_id={task_id}] 워크플로우 제출 완료: prompt_id={prompt_id}")

            if self.is_cancelled(task_id):
                self.update_status(task_id, "CANCELLED")
                return {}

            # [9] 완료 대기 (WebSocket, 최대 10분)
            timeout = 600
            logger.info(f"[F003][task_id={task_id}] 완료 대기 시작 (timeout={timeout}s)")
            client.wait_for_completion(
                prompt_id=prompt_id,
                timeout=timeout,
                cancel_check_fn=self.is_cancelled,
                task_id=task_id,
            )

            if self.is_cancelled(task_id):
                self.update_status(task_id, "CANCELLED")
                return {}

            # [10] 결과 파일 목록 조회
            output_files = client.get_output_files(prompt_id)
            if not output_files:
                raise RuntimeError("ComfyUI 결과 파일이 없습니다.")
            logger.info(f"[F003][task_id={task_id}] 결과 파일: {output_files}")

            # 첫 번째 파일 다운로드
            first_file = output_files[0]
            file_bytes = client.download_output(
                filename=first_file["filename"],
                subfolder=first_file.get("subfolder", ""),
                file_type=first_file.get("type", "output"),
            )

            # 확장자 결정 — 원본 파일명 기준, 없으면 생성 유형으로 추론
            original_name = first_file["filename"]
            ext = Path(original_name).suffix or (".mp4" if generation_type == "video" else ".png")
            save_filename = f"{task_id}_{generation_type}{ext}"
            save_path = output_dir / save_filename

            save_path.write_bytes(file_bytes)
            logger.info(
                f"[F003][task_id={task_id}] 파일 저장 완료: {save_path} ({len(file_bytes)} bytes)"
            )

            # [11] DONE 상태 업데이트
            result = {
                "generation_type": generation_type,
                "art_style": art_style,
                "base_model": base_model,
                "file_name": save_filename,
                "file_path": str(save_path),
                "file_size_bytes": len(file_bytes),
                "seed": seed,
                "prompt_positive": prompt.get("positive", "")[:300],
                "prompt_negative": prompt.get("negative", "")[:300],
            }
            self.update_status(task_id, "DONE", result=result)
            logger.info(f"[F003][task_id={task_id}] 파이프라인 완료")
            return result

        except Exception as exc:
            logger.error(f"[F003][task_id={task_id}] 파이프라인 실패: {exc}", exc_info=True)
            self.update_status(task_id, "FAILED", error=str(exc)[:2000])
            raise
