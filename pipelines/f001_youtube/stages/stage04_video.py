# 목적: STAGE_04 — 씬별 영상/이미지 클립 생성 스테이지.
# ComfyUI 또는 text_slide(텍스트 슬라이드 PNG) 두 가지 경로를 지원한다.
# generation_backend=="skip"이면 skip_mode에 따라 처리한다.

import sys
import io
import json
import logging
import subprocess

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f001_youtube.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# config.json 경로 — 이 파일 기준 상위 디렉토리
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class Stage04VideoGen(BaseStage, BasePipeline):
    """STAGE_04 — 씬별 영상/이미지 클립 생성 스테이지.

    처리 흐름:
      skip + script_only: 즉시 SKIPPED 반환 (클립 없음)
      skip + text_slide: FFmpeg/PIL로 텍스트 슬라이드 PNG 생성 후 SKIPPED 반환
      ComfyUI: STAGE_02 씬 목록을 영어 프롬프트로 변환 → ComfyUI 이미지 생성

    ComfyUIClient는 F003에서 공유하며 import를 통해 재활용한다.
    """

    STAGE_ID: str = "STAGE_04_VIDEO_GEN"
    STAGE_ORDER: int = 4

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F001_STAGE04", "name": "STAGE_04_VIDEO_GEN"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_04 실행 — 씬별 클립 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                generation_backend (str): "comfyui" 또는 "skip"
                skip_mode (str, optional): "script_only" 또는 "text_slide"
                scenes (list): STAGE_02 씬 목록 [{scene_no, description, duration_sec}]
            }

        Returns:
            SKIPPED(script_only): {stage_id, status="SKIPPED", skip_mode, clips=[], generated_at}
            SKIPPED(text_slide): {stage_id, status="SKIPPED", skip_mode, clips=[...], generated_at}
            COMPLETED: {stage_id, status="COMPLETED", generation_backend, clips=[...],
                        thumbnail_candidates, total_clips, generated_at}
        """
        # skip 여부 및 모드 판단
        skip: bool = input_data.get("generation_backend", "comfyui") == "skip"
        skip_mode: Optional[str] = input_data.get("skip_mode")
        scenes: list[dict] = input_data.get("scenes", [])

        # 클립 저장 디렉토리 — 절대 경로 (ERR-007: 상대 경로는 backend 기준으로 저장됨)
        _project_root = Path(__file__).parent.parent.parent.parent
        output_dir = _project_root / "storage" / "results" / "f001" / str(job_id) / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)

        # ----------------------------------------------------------------
        # skip + script_only: 클립 생성 없이 즉시 SKIPPED
        # ----------------------------------------------------------------
        if skip and skip_mode == "script_only":
            logger.info(
                f"[STAGE_04][job_id={job_id}] script_only 모드 — 클립 생성 없이 SKIPPED"
            )
            return {
                "stage_id": "STAGE_04_VIDEO_GEN",
                "status": "SKIPPED",
                "skip_mode": "script_only",
                "clips": [],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # ----------------------------------------------------------------
        # skip + text_slide: 텍스트 슬라이드 PNG 생성 후 SKIPPED
        # ----------------------------------------------------------------
        if skip and skip_mode == "text_slide":
            logger.info(
                f"[STAGE_04][job_id={job_id}] text_slide 모드 — "
                f"텍스트 슬라이드 {len(scenes)}개 생성"
            )
            clips = self._generate_text_slides(scenes, output_dir, job_id)
            return {
                "stage_id": "STAGE_04_VIDEO_GEN",
                "status": "SKIPPED",
                "skip_mode": "text_slide",
                "clips": clips,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # ----------------------------------------------------------------
        # ComfyUI 연동 — 씬별 이미지 생성
        # ----------------------------------------------------------------
        logger.info(
            f"[STAGE_04][job_id={job_id}] ComfyUI 모드 — "
            f"{len(scenes)}개 씬 이미지 생성 시작"
        )

        config = self._load_config()
        comfyui_url: str = config.get("comfyui_url", "http://localhost:8188")

        # F003 ComfyUIClient 임포트 재활용
        try:
            from pipelines.f003_video_creation.comfyui_client import ComfyUIClient
        except ImportError as e:
            raise RuntimeError(
                f"ComfyUIClient 임포트 실패. "
                f"F003 파이프라인이 설치되어 있는지 확인하세요. ({e})"
            ) from e

        client = ComfyUIClient(comfyui_url)

        # ComfyUI 서버 헬스체크
        try:
            health_ok = client.health_check()
        except Exception as e:
            health_ok = False

        if not health_ok:
            comfyui_path = config.get("comfyui_path", r"D:\comfyui\ComfyUI")
            raise RuntimeError(
                f"ComfyUI 서버 연결 실패 ({comfyui_url}). "
                f"ComfyUI를 먼저 실행하세요: {comfyui_path}"
            )

        # 사용 가능한 체크포인트 자동 선택
        checkpoints = client.get_available_checkpoints()
        if not checkpoints:
            raise RuntimeError("ComfyUI에 설치된 체크포인트가 없습니다.")
        # config에 지정된 체크포인트가 있으면 우선 사용, 없으면 첫 번째
        default_ckpt: str = config.get("comfyui_default_checkpoint", checkpoints[0])
        if default_ckpt not in checkpoints:
            default_ckpt = checkpoints[0]
        logger.info(f"[STAGE_04][job_id={job_id}] 사용 체크포인트: {default_ckpt}")

        # 썸네일 디렉토리 — 절대 경로
        thumbnail_dir = _project_root / "storage" / "results" / "f001" / str(job_id) / "thumbnails"
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        clips: list[dict] = []
        thumbnail_candidates: list[str] = []

        import random
        import shutil

        # 이미지 다운로드용 임시 디렉토리
        download_dir = _project_root / "storage" / "results" / "f001" / str(job_id) / "raw_downloads"
        download_dir.mkdir(parents=True, exist_ok=True)

        for scene in scenes:
            scene_no: int = scene.get("scene_no", 0)
            scene_desc: str = scene.get("description", "")
            duration_sec: int = scene.get("duration_sec", 5)

            # Ollama: 씬 설명을 영어 이미지 프롬프트 + 검색 키워드로 변환
            try:
                ollama_resp: str = self.call_ollama(
                    prompt=(
                        f"Convert the following Korean scene description into:\n"
                        f"1. A short English image search query (max 8 words, comma-separated keywords)\n"
                        f"2. An English Stable Diffusion prompt (max 80 words)\n\n"
                        f"Output format (JSON only):\n"
                        f"{{\"search_query\": \"...\", \"sd_prompt\": \"...\"}}\n\n"
                        f"Scene: {scene_desc}"
                    ),
                    timeout=60,
                    num_predict=300,
                )
                import re as _re
                _json_match = _re.search(r'\{.*\}', ollama_resp, _re.DOTALL)
                if _json_match:
                    _parsed = json.loads(_json_match.group())
                    search_query: str = _parsed.get("search_query", scene_desc[:80])
                    english_prompt: str = _parsed.get("sd_prompt", scene_desc[:300])
                else:
                    raise ValueError("JSON not found in Ollama response")
            except Exception as e:
                logger.warning(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} Ollama 변환 실패 — "
                    f"원본 사용: {e}"
                )
                search_query = scene_desc[:80]
                english_prompt = scene_desc[:300]

            output_image_path = str(output_dir / f"scene_{scene_no:02d}.png")
            result_path: Optional[str] = None

            # ── 1단계: 관련 이미지 검색 & 다운로드 ──────────────────────
            raw_image_path: Optional[str] = self._search_and_download_image(
                search_query=search_query,
                save_path=str(download_dir / f"raw_{scene_no:02d}.jpg"),
                job_id=job_id,
                scene_no=scene_no,
                config=config,
            )

            # ── 1.5단계: Florence-2로 다운로드 이미지 분석 → SD 프롬프트 보강 ──
            if raw_image_path:
                enhanced_prompt = self._enhance_prompt_with_florence2(
                    raw_image_path, english_prompt, job_id, scene_no
                )
            else:
                enhanced_prompt = english_prompt

            # ── 2단계: img2img or PIL 처리 ──────────────────────────────
            if raw_image_path:
                # img2img 시도 (ComfyUI)
                result_path = self._run_img2img(
                    client=client,
                    raw_image_path=raw_image_path,
                    prompt=enhanced_prompt,
                    checkpoint=default_ckpt,
                    output_path=output_image_path,
                    job_id=job_id,
                    scene_no=scene_no,
                    denoise=float(config.get("img2img_denoise", 0.4)),
                    seed=random.randint(0, 2**32 - 1),
                )

                # img2img 실패 → PIL로 원본 이미지 처리 (리사이즈 + 배경 최적화)
                if not result_path:
                    result_path = self._process_image_as_bg(
                        raw_image_path, output_image_path, job_id, scene_no
                    )

            # ── 3단계: 이미지 검색 실패 → txt2img 폴백 ─────────────────
            if not result_path:
                logger.info(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} — "
                    f"이미지 검색 실패, txt2img 폴백"
                )
                result_path = self._run_txt2img(
                    client=client,
                    prompt=english_prompt,
                    checkpoint=default_ckpt,
                    output_path=output_image_path,
                    job_id=job_id,
                    scene_no=scene_no,
                    seed=random.randint(0, 2**32 - 1),
                )

            # ── 결과 수집 ────────────────────────────────────────────────
            if result_path and Path(result_path).exists():
                # Florence-2 품질 검수 — 생성 클립 캡션 vs 씬 설명 비교 (로그만)
                clip_caption = self._quality_check_with_florence2(
                    result_path, scene_desc, job_id, scene_no
                )
                clips.append({
                    "scene_no": scene_no,
                    "file_path": result_path,
                    "duration_sec": duration_sec,
                    "source": "img2img" if raw_image_path else "txt2img",
                    "caption": clip_caption or "",
                })
                if scene_no == 1:
                    thumb_path = str(thumbnail_dir / "thumb_01.png")
                    shutil.copy2(result_path, thumb_path)
                    thumbnail_candidates.append(thumb_path)
                logger.info(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} 완료: {result_path}"
                )
            else:
                logger.warning(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} 이미지 생성 전체 실패 — 건너뜀"
                )

        logger.info(
            f"[STAGE_04][job_id={job_id}] ComfyUI 이미지 생성 완료 — "
            f"{len(clips)}/{len(scenes)}개 성공"
        )

        # 썸네일 자동 생성 — 첫 클립 + 주제 텍스트 오버레이
        selected_topic: str = input_data.get("selected_topic", "")
        thumbnail_path: Optional[str] = self._generate_thumbnail(
            base_image_path=clips[0]["file_path"] if clips else None,
            title_text=selected_topic,
            output_path=str(thumbnail_dir / "thumbnail.png"),
            job_id=job_id,
        )
        if thumbnail_path:
            thumbnail_candidates.insert(0, thumbnail_path)

        return {
            "stage_id": "STAGE_04_VIDEO_GEN",
            "status": "COMPLETED",
            "generation_backend": "comfyui",
            "comfyui_path": config.get("comfyui_path", r"D:\comfyui\ComfyUI"),
            "clips": clips,
            "thumbnail_path": thumbnail_path,
            "thumbnail_candidates": thumbnail_candidates,
            "total_clips": len(clips),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _search_and_download_image(
        self,
        search_query: str,
        save_path: str,
        job_id: int,
        scene_no: int,
        config: dict,
    ) -> Optional[str]:
        """씬 키워드로 관련 이미지를 검색하고 다운로드한다.

        검색 우선순위:
          1. Pexels API (config에 pexels_api_key가 있을 때)
          2. SearXNG 이미지 검색 (fallback)

        Args:
            search_query: 영어 검색 키워드
            save_path: 다운로드 저장 경로
            job_id: 로그 식별용
            scene_no: 씬 번호
            config: config.json 로드 결과

        Returns:
            저장된 이미지 파일 경로 또는 None (실패 시)
        """
        import httpx as _httpx

        pexels_key: str = config.get("pexels_api_key", "")

        # ── Pexels API 시도 ──────────────────────────────────────────────
        if pexels_key:
            try:
                with _httpx.Client(timeout=15.0) as hc:
                    resp = hc.get(
                        "https://api.pexels.com/v1/search",
                        headers={"Authorization": pexels_key},
                        params={"query": search_query, "per_page": 5, "orientation": "landscape"},
                    )
                    resp.raise_for_status()
                    photos = resp.json().get("photos", [])
                    if photos:
                        # 첫 번째 사진의 large2x URL 다운로드
                        img_url: str = photos[0].get("src", {}).get("large2x", "")
                        if img_url:
                            img_resp = hc.get(img_url, timeout=30.0)
                            img_resp.raise_for_status()
                            Path(save_path).write_bytes(img_resp.content)
                            logger.info(
                                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} "
                                f"Pexels 이미지 다운로드 완료: {search_query!r}"
                            )
                            return save_path
            except Exception as e:
                logger.warning(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} Pexels 검색 실패: {e}"
                )

        # ── SearXNG 이미지 검색 시도 ────────────────────────────────────
        try:
            image_results = self.call_searxng_images(search_query, max_results=5)
            for item in image_results:
                img_url = item.get("img_src", "")
                if not img_url or not img_url.startswith("http"):
                    continue
                try:
                    with _httpx.Client(timeout=20.0) as hc:
                        img_resp = hc.get(img_url, follow_redirects=True, timeout=20.0)
                        img_resp.raise_for_status()
                        content_type = img_resp.headers.get("content-type", "")
                        if "image" not in content_type:
                            continue
                        Path(save_path).write_bytes(img_resp.content)
                    logger.info(
                        f"[STAGE_04][job_id={job_id}] 씬 {scene_no} "
                        f"SearXNG 이미지 다운로드 완료: {img_url[:60]}"
                    )
                    return save_path
                except Exception:
                    continue  # 개별 URL 실패 → 다음 URL 시도
        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} SearXNG 이미지 검색 실패: {e}"
            )

        return None

    def _process_image_as_bg(
        self,
        raw_image_path: str,
        output_path: str,
        job_id: int,
        scene_no: int,
    ) -> Optional[str]:
        """다운로드된 원본 이미지를 배경용으로 PIL 처리.

        1280x720 리사이즈 + 채도 1.15 + 밝기 0.9 조정.
        PIL 미설치 시 원본 파일을 복사만 한다.

        Returns:
            처리된 이미지 경로 또는 None
        """
        try:
            from PIL import Image, ImageEnhance
            img = Image.open(raw_image_path).convert("RGB")
            # 1280x720에 맞게 crop-resize (cover 방식)
            target_w, target_h = 1280, 720
            orig_w, orig_h = img.size
            scale = max(target_w / orig_w, target_h / orig_h)
            new_w = int(orig_w * scale)
            new_h = int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            img = img.crop((left, top, left + target_w, top + target_h))
            # 채도 + 밝기 조정 (배경 분위기 최적화)
            img = ImageEnhance.Color(img).enhance(1.15)
            img = ImageEnhance.Brightness(img).enhance(0.88)
            img.save(output_path, "PNG")
            logger.info(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} PIL 배경 처리 완료"
            )
            return output_path
        except ImportError:
            # PIL 없으면 원본 그대로 복사
            import shutil
            shutil.copy2(raw_image_path, output_path)
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} PIL 미설치 — 원본 복사"
            )
            return output_path
        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} PIL 처리 실패: {e}"
            )
            return None

    def _run_img2img(
        self,
        client,
        raw_image_path: str,
        prompt: str,
        checkpoint: str,
        output_path: str,
        job_id: int,
        scene_no: int,
        denoise: float = 0.4,
        seed: int = 0,
    ) -> Optional[str]:
        """ComfyUI img2img 워크플로우 실행.

        다운로드된 원본 이미지를 ComfyUI에 업로드한 뒤 KSampler(denoise<1.0)로
        스타일 변환한다. 실패 시 None 반환.

        Args:
            client: ComfyUIClient 인스턴스
            raw_image_path: 입력 이미지 파일 경로
            prompt: 영어 SD 프롬프트
            checkpoint: 사용할 체크포인트 이름
            output_path: 결과 저장 경로
            job_id: 로그 식별용
            scene_no: 씬 번호
            denoise: KSampler denoise 강도 (0.3~0.5 권장)
            seed: KSampler 시드값

        Returns:
            저장된 이미지 경로 또는 None
        """
        try:
            # 입력 이미지를 PNG로 변환 후 ComfyUI에 업로드
            from PIL import Image as _PIL_Image
            img = _PIL_Image.open(raw_image_path).convert("RGB")
            img = img.resize((1280, 720), _PIL_Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            upload_filename = f"f001_s04_input_{job_id}_{scene_no}.png"
            comfyui_name = client.upload_image(img_bytes, upload_filename)

            workflow = self._build_img2img_workflow(
                input_image_name=comfyui_name,
                prompt=prompt,
                checkpoint=checkpoint,
                denoise=denoise,
                seed=seed,
            )
            prompt_id = client.submit_workflow(workflow)
            client.wait_for_completion(prompt_id, timeout=300)
            output_files = client.get_output_files(prompt_id)
            if not output_files:
                raise RuntimeError("img2img 결과 파일 없음")

            file_bytes = client.download_output(
                filename=output_files[0]["filename"],
                subfolder=output_files[0].get("subfolder", ""),
            )
            Path(output_path).write_bytes(file_bytes)
            logger.info(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} img2img 완료"
            )
            return output_path

        except ImportError:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} PIL 미설치 — img2img 불가"
            )
            return None
        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} img2img 실패: {e}"
            )
            return None

    def _run_txt2img(
        self,
        client,
        prompt: str,
        checkpoint: str,
        output_path: str,
        job_id: int,
        scene_no: int,
        seed: int = 0,
    ) -> Optional[str]:
        """ComfyUI txt2img 워크플로우 실행 (img2img 폴백용).

        Returns:
            저장된 이미지 경로 또는 None
        """
        try:
            import random
            workflow = self._build_txt2img_workflow(
                prompt=prompt,
                checkpoint=checkpoint,
                width=1280,
                height=720,
                seed=seed,
            )
            prompt_id = client.submit_workflow(workflow)
            client.wait_for_completion(prompt_id, timeout=300)
            output_files = client.get_output_files(prompt_id)
            if not output_files:
                return None
            file_bytes = client.download_output(
                filename=output_files[0]["filename"],
                subfolder=output_files[0].get("subfolder", ""),
            )
            Path(output_path).write_bytes(file_bytes)
            logger.info(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} txt2img 완료"
            )
            return output_path
        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} txt2img 실패: {e}"
            )
            return None

    def _build_img2img_workflow(
        self,
        input_image_name: str,
        prompt: str,
        checkpoint: str,
        denoise: float = 0.4,
        seed: int = 0,
        steps: int = 20,
        cfg: float = 7.0,
    ) -> dict:
        """ComfyUI img2img KSampler 워크플로우 JSON 구성.

        ComfyUI의 LoadImage → VAEEncode → KSampler(denoise<1) → VAEDecode → SaveImage 흐름.
        """
        return {
            "1": {
                "inputs": {"image": input_image_name, "upload": "image"},
                "class_type": "LoadImage",
            },
            "4": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple",
            },
            "5": {
                "inputs": {"pixels": ["1", 0], "vae": ["4", 2]},
                "class_type": "VAEEncode",
            },
            "6": {
                "inputs": {"text": prompt, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
            },
            "7": {
                "inputs": {
                    "text": "ugly, blurry, low quality, watermark, text, signature, worst quality, deformed",
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "3": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": denoise,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "8": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode",
            },
            "9": {
                "inputs": {"filename_prefix": "f001_s04_img2img", "images": ["8", 0]},
                "class_type": "SaveImage",
            },
        }

    def _enhance_prompt_with_florence2(
        self,
        image_path: str,
        base_prompt: str,
        job_id: int,
        scene_no: int,
    ) -> str:
        """Florence-2 DETAILED_CAPTION으로 다운로드 이미지를 분석하여 SD 프롬프트를 보강.

        원본 이미지의 실제 내용(색상, 구도, 요소)을 SD 프롬프트에 추가해
        img2img 결과가 원본 이미지와 더 일관성 있게 생성되도록 한다.

        Args:
            image_path: 다운로드된 원본 이미지 경로
            base_prompt: Ollama가 생성한 기본 SD 프롬프트
            job_id: 로그 식별용
            scene_no: 씬 번호

        Returns:
            보강된 프롬프트 문자열 (Florence-2 실패 시 base_prompt 반환)
        """
        try:
            from pipelines.f001_youtube.florence2_helper import get_detailed_caption
            caption = get_detailed_caption(image_path)
            if caption:
                # 캡션을 base_prompt 앞에 결합 — 구조적 정보 우선
                enhanced = f"{caption[:200]}, {base_prompt}"
                logger.info(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} "
                    f"Florence-2 프롬프트 보강 완료"
                )
                return enhanced[:700]
        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] 씬 {scene_no} Florence-2 보강 실패: {e}"
            )
        return base_prompt

    def _quality_check_with_florence2(
        self,
        clip_path: str,
        scene_desc: str,
        job_id: int,
        scene_no: int,
    ) -> Optional[str]:
        """Florence-2 CAPTION으로 생성된 클립 품질을 검수하고 캡션을 반환.

        씬 설명과 생성 이미지의 캡션을 비교해 관련성을 로그로 기록한다.
        현재는 로그만 남기며 자동 재생성은 수행하지 않는다.

        Returns:
            생성된 캡션 문자열 또는 None
        """
        try:
            from pipelines.f001_youtube.florence2_helper import get_caption
            caption = get_caption(clip_path)
            if caption:
                # 간단한 키워드 겹침으로 관련성 추정
                scene_words = set(scene_desc.lower().split())
                caption_words = set(caption.lower().split())
                overlap = len(scene_words & caption_words)
                logger.info(
                    f"[STAGE_04][job_id={job_id}] 씬 {scene_no} 품질 검수 — "
                    f"캡션: '{caption[:80]}' | 키워드 겹침: {overlap}개"
                )
                return caption
        except Exception as e:
            logger.debug(f"[STAGE_04][job_id={job_id}] 씬 {scene_no} 품질 검수 생략: {e}")
        return None

    def _generate_thumbnail(
        self,
        base_image_path: Optional[str],
        title_text: str,
        output_path: str,
        job_id: int,
    ) -> Optional[str]:
        """YouTube 썸네일 자동 생성 (1280x720).

        첫 클립 이미지를 배경으로 사용하고 주제 텍스트를 하단에 오버레이한다.
        PIL 미설치 시 None 반환.

        썸네일 구성:
          - 배경: 첫 클립 이미지 (없으면 다크 그라디언트)
          - 하단 1/3: 반투명 어두운 오버레이 (텍스트 가독성)
          - 텍스트: 흰색 굵은 폰트, 최대 2줄

        Args:
            base_image_path: 배경으로 사용할 이미지 경로 (None 가능)
            title_text: 썸네일에 표시할 주제 제목
            output_path: 저장 경로
            job_id: 로그 식별용

        Returns:
            저장된 썸네일 경로 또는 None
        """
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageFilter
        except ImportError:
            logger.warning(f"[STAGE_04][job_id={job_id}] PIL 미설치 — 썸네일 생성 불가")
            return None

        try:
            W, H = 1280, 720

            # 배경 이미지 준비
            if base_image_path and Path(base_image_path).exists():
                bg = Image.open(base_image_path).convert("RGB")
                # cover 리사이즈
                scale = max(W / bg.width, H / bg.height)
                nw, nh = int(bg.width * scale), int(bg.height * scale)
                bg = bg.resize((nw, nh), Image.LANCZOS)
                left = (nw - W) // 2
                top = (nh - H) // 2
                bg = bg.crop((left, top, left + W, top + H))
                # 배경 약간 어둡게
                bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), alpha=0.25)
            else:
                # 다크 그라디언트 배경
                bg = Image.new("RGB", (W, H), (20, 20, 40))

            draw = ImageDraw.Draw(bg)

            # 하단 그라디언트 오버레이 (텍스트 가독성 확보)
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ov_draw = ImageDraw.Draw(overlay)
            for y in range(H // 2, H):
                alpha = int(180 * ((y - H // 2) / (H // 2)))
                ov_draw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
            bg = bg.convert("RGBA")
            bg = Image.alpha_composite(bg, overlay).convert("RGB")
            draw = ImageDraw.Draw(bg)

            # 폰트 로드 (한글 지원)
            font_size = 56
            font: ImageFont.FreeTypeFont
            for font_name in ["malgunbd.ttf", "malgun.ttf", "arialbd.ttf", "arial.ttf"]:
                try:
                    font = ImageFont.truetype(font_name, size=font_size)
                    break
                except Exception:
                    continue
            else:
                font = ImageFont.load_default()

            # 제목 텍스트 줄바꿈 (최대 22자/줄, 2줄)
            text = title_text[:80] if title_text else "YouTube 영상"
            lines: list[str] = []
            for i in range(0, len(text), 22):
                lines.append(text[i : i + 22])
                if len(lines) >= 2:
                    break

            # 텍스트 하단 중앙 배치
            line_h = font_size + 10
            total_h = len(lines) * line_h
            y_start = H - total_h - 48
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                tw = bbox[2] - bbox[0]
                x = (W - tw) // 2
                # 그림자 효과
                draw.text((x + 2, y_start + 2), line, font=font, fill=(0, 0, 0, 180))
                draw.text((x, y_start), line, font=font, fill=(255, 255, 255))
                y_start += line_h

            bg.save(output_path, "PNG")
            logger.info(f"[STAGE_04][job_id={job_id}] 썸네일 생성 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.warning(f"[STAGE_04][job_id={job_id}] 썸네일 생성 실패: {e}")
            return None

    def _build_txt2img_workflow(
        self,
        prompt: str,
        checkpoint: str,
        width: int = 1280,
        height: int = 720,
        seed: int = 0,
        steps: int = 20,
        cfg: float = 7.0,
    ) -> dict:
        """기본 KSampler txt2img 워크플로우 JSON 구성."""
        return {
            "4": {"inputs": {"ckpt_name": checkpoint}, "class_type": "CheckpointLoaderSimple"},
            "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
            "6": {"inputs": {"text": prompt, "clip": ["4", 1]}, "class_type": "CLIPTextEncode"},
            "7": {
                "inputs": {
                    "text": "ugly, blurry, low quality, watermark, text, signature, worst quality",
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "3": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": "euler",
                    "scheduler": "karras",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "8": {"inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "class_type": "VAEDecode"},
            "9": {
                "inputs": {"filename_prefix": "f001_s04", "images": ["8", 0]},
                "class_type": "SaveImage",
            },
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 — COMPLETED 상태인데 clips가 비어 있으면 반송."""
        status: str = output.get("status", "")
        clips: list = output.get("clips", [])
        # SKIPPED 상태는 검증 통과 (skip 모드에서 clips가 없어도 정상)
        if status == "COMPLETED" and not clips:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    "클립 생성 실패. ComfyUI 연결 상태를 확인하고 재시도하세요. "
                    "또는 skip_mode=text_slide로 변경하세요."
                ),
                rejection_target="STAGE_04_VIDEO_GEN",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        """config.json 로드.

        파일이 없거나 파싱 실패 시 빈 딕셔너리를 반환한다.
        """
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"config.json 로드 실패 ({e}), 기본값 사용")
            return {}

    def _generate_text_slides(
        self,
        scenes: list[dict],
        output_dir: Path,
        job_id: int,
    ) -> list[dict]:
        """텍스트 슬라이드 PNG 파일 생성.

        PIL이 설치되어 있으면 PIL로, 없으면 FFmpeg drawtext 필터로 생성한다.
        1280x720 검정 배경에 흰색 텍스트 슬라이드.

        Args:
            scenes: [{scene_no, description, duration_sec}]
            output_dir: 출력 디렉토리 Path
            job_id: 로그 식별용

        Returns:
            [{scene_no, file_path, duration_sec}] 목록
        """
        clips: list[dict] = []

        for scene in scenes:
            scene_no: int = scene.get("scene_no", 0)
            description: str = scene.get("description", f"장면 {scene_no}")
            duration_sec: int = scene.get("duration_sec", 5)

            slide_path = str(output_dir / f"slide_{scene_no:02d}.png")

            # PIL 시도
            generated = self._generate_slide_with_pil(description, slide_path, job_id, scene_no)

            # PIL 실패 시 FFmpeg 시도
            if not generated:
                generated = self._generate_slide_with_ffmpeg(
                    description, slide_path, job_id, scene_no
                )

            if generated:
                clips.append({
                    "scene_no": scene_no,
                    "file_path": slide_path,
                    "duration_sec": duration_sec,
                })
            else:
                logger.warning(
                    f"[STAGE_04][job_id={job_id}] 슬라이드 {scene_no} 생성 실패 — 건너뜀"
                )

        logger.info(
            f"[STAGE_04][job_id={job_id}] 텍스트 슬라이드 생성 완료 — "
            f"{len(clips)}/{len(scenes)}개"
        )
        return clips

    def _generate_slide_with_pil(
        self,
        text: str,
        output_path: str,
        job_id: int,
        scene_no: int,
    ) -> bool:
        """PIL(Pillow)로 텍스트 슬라이드 PNG 생성.

        Returns:
            True: 성공, False: PIL 미설치 또는 실패
        """
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            return False

        try:
            # 1280x720 검정 배경 이미지 생성
            img = Image.new("RGB", (1280, 720), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)

            # 기본 폰트 (크기 40) — 시스템 폰트 로드 시도
            try:
                font = ImageFont.truetype("malgun.ttf", size=40)
            except Exception:
                try:
                    font = ImageFont.truetype("arial.ttf", size=40)
                except Exception:
                    font = ImageFont.load_default()

            # 텍스트를 60자 단위로 줄바꿈
            wrapped_text = "\n".join(
                text[i : i + 60] for i in range(0, len(text), 60)
            )[:300]

            # 텍스트 중앙 배치
            draw.multiline_text(
                (640, 360),
                wrapped_text,
                font=font,
                fill=(255, 255, 255),
                anchor="mm",
                align="center",
            )

            img.save(output_path, "PNG")
            logger.info(
                f"[STAGE_04][job_id={job_id}] PIL 슬라이드 생성 완료: {output_path}"
            )
            return True

        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] PIL 슬라이드 {scene_no} 생성 실패: {e}"
            )
            return False

    def _generate_slide_with_ffmpeg(
        self,
        text: str,
        output_path: str,
        job_id: int,
        scene_no: int,
    ) -> bool:
        """FFmpeg drawtext 필터로 텍스트 슬라이드 PNG 생성.

        PIL 대안. FFmpeg가 PATH에 있어야 한다.

        Returns:
            True: 성공, False: FFmpeg 실패
        """
        # 텍스트 특수문자 이스케이프 (FFmpeg drawtext 문법)
        safe_text = text[:200].replace("'", "\\'").replace(":", r"\:")
        safe_text = safe_text.replace("\n", " ")

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:size=1280x720:rate=1",
                    "-vframes",
                    "1",
                    "-vf",
                    (
                        f"drawtext=text='{safe_text}'"
                        ":fontcolor=white:fontsize=36"
                        ":x=(w-text_w)/2:y=(h-text_h)/2"
                        ":line_spacing=8"
                    ),
                    output_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0 and Path(output_path).exists():
                logger.info(
                    f"[STAGE_04][job_id={job_id}] FFmpeg 슬라이드 생성 완료: {output_path}"
                )
                return True
            else:
                logger.warning(
                    f"[STAGE_04][job_id={job_id}] FFmpeg 슬라이드 {scene_no} 실패: "
                    f"{result.stderr[:200]}"
                )
                return False

        except Exception as e:
            logger.warning(
                f"[STAGE_04][job_id={job_id}] FFmpeg 슬라이드 {scene_no} 예외: {e}"
            )
            return False
