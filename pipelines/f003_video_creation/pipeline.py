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

            # [6] 시드 처리 (-1이면 무작위 생성)
            seed = int(params.get("seed", -1))
            if seed == -1:
                seed = random.randint(0, 2**32 - 1)
            params_with_seed = {**params, "seed": seed}

            # [7] 워크플로우 JSON 조립
            workflow = style_mapper.build_workflow(
                generation_type=generation_type,
                art_style=art_style,
                prompt=prompt,
                params=params_with_seed,
                config=config,
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
            }
            self.update_status(task_id, "DONE", result=result)
            logger.info(f"[F003][task_id={task_id}] 파이프라인 완료")
            return result

        except Exception as exc:
            logger.error(f"[F003][task_id={task_id}] 파이프라인 실패: {exc}", exc_info=True)
            self.update_status(task_id, "FAILED", error=str(exc)[:2000])
            raise
