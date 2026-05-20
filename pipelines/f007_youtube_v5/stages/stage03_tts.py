# pipelines/f007_youtube_v5/stages/stage03_tts.py
# 목적: F007 STAGE_03 - shared/tts.py TTSChain 위임
# finance 채널: 기본 voice F1 (낮고 신뢰감 있는 음성)
# language 채널: 기본 voice F3 (밝고 친근한 음성)

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
from datetime import datetime, timezone
from pathlib import Path

from pipelines.f007_youtube_v5.stages import BaseStage, ValidationResult
from pipelines.base import BasePipeline
from pipelines.shared.tts import TTSChain

logger = logging.getLogger(__name__)


class Stage03TTS(BaseStage, BasePipeline):
    """STAGE_03 - TTSChain으로 TTS 합성.

    shared/tts.py의 TTSChain에 완전히 위임한다.
    tts_skip=True이면 TTS를 건너뛰고 audio_file_path=None으로 반환한다.
    channel_type에 따라 기본 voice가 다르다 (finance=F1, language=F3).
    """
    STAGE_ID: str = "STAGE_03_TTS"
    STAGE_ORDER: int = 3

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE03", "name": "STAGE_03_TTS"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - tts_skip=True이면 script_text 없어도 통과."""
        if data.get("tts_skip"):
            return ValidationResult(is_valid=True)
        if not data.get("script_text", "").strip():
            return ValidationResult(
                is_valid=False,
                rejection_reason="script_text 없음. STAGE_02에서 스크립트를 생성하세요.",
                rejection_target="STAGE_02_SCRIPT",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_03 실행 - TTS 합성.

        Args:
            job_id: content_jobs.id
            input_data: {
                script_text (str): TTS 합성할 텍스트 (tts_skip=False 시 필수)
                tts_skip (bool, 기본 False): True이면 TTS 건너뜀
                tts_provider (str, 기본 "supertone3"): TTS 프로바이더
                tts_voice (str, 기본 ""): 음성 ID (빈 문자열이면 channel_type 기본값 적용)
                channel_type (str, 기본 "finance"): 채널 유형 (기본 voice 결정에 사용)
            }

        Returns:
            {
                stage_id, status,
                audio_file_path (str|None): 생성된 오디오 파일 경로,
                srt_file_path (str|None): 자막 파일 경로 (F007 Stage03은 미생성),
                tts_provider (str): 사용된 프로바이더,
                duration_sec (float): 오디오 길이(초),
                generated_at (str)
            }
        """
        tts_skip: bool = input_data.get("tts_skip", False)
        script_text: str = input_data.get("script_text", "")
        tts_provider: str = input_data.get("tts_provider", "supertone3")
        tts_voice: str = input_data.get("tts_voice", "")
        channel_type: str = input_data.get("channel_type", "finance")

        # 출력 디렉토리 생성 - storage/results/f007/{job_id}/audio/
        project_root = Path(__file__).parent.parent.parent.parent
        audio_dir = project_root / "storage" / "results" / "f007" / str(job_id) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        # TTS skip 모드
        if tts_skip:
            logger.info(f"[F007][STAGE_03][job_id={job_id}] TTS skip 모드 - 오디오 없이 진행")
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "COMPLETED",
                "audio_file_path": None,
                "srt_file_path": None,
                "tts_provider": "skip",
                "duration_sec": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # channel_type별 기본 voice 적용 (사용자가 명시하지 않은 경우)
        if not tts_voice or tts_voice == "F1":
            # language 채널은 F3(밝고 친근한), finance 채널은 F1(신뢰감 있는)
            tts_voice = "F3" if channel_type == "language" else "F1"

        logger.info(
            f"[F007][STAGE_03][job_id={job_id}] TTS 합성 시작 - "
            f"provider={tts_provider}, voice={tts_voice}, "
            f"channel={channel_type}, 텍스트 {len(script_text)}자"
        )

        audio_path = str(audio_dir / "tts_output.mp3")

        # 프로바이더 순서 결정 - auto이면 전체 폴백 체인, 아니면 지정 프로바이더 우선
        provider_order: list
        if tts_provider == "auto":
            provider_order = ["supertone3", "coqui", "pyttsx3"]
        else:
            # 지정 프로바이더 우선, 실패 시 coqui -> pyttsx3 순서로 폴백
            fallback = ["coqui", "pyttsx3"]
            provider_order = [tts_provider] + [p for p in fallback if p != tts_provider]

        chain = TTSChain(provider_order=provider_order)
        try:
            result = chain.synthesize(
                text=script_text,
                output_path=audio_path,
                voice=tts_voice,
            )
            logger.info(
                f"[F007][STAGE_03][job_id={job_id}] TTS 완료 - "
                f"provider={result.provider}, duration={result.duration_sec:.1f}초"
            )
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "COMPLETED",
                "audio_file_path": result.audio_path,
                "srt_file_path": None,  # F007 Stage03은 SRT 미생성 (Stage05에서 선택적 Whisper)
                "tts_provider": result.provider,
                "duration_sec": result.duration_sec,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            # TTS 전체 실패 시 - 오디오 없이 계속 진행 (영상 생성 자체는 허용)
            logger.error(
                f"[F007][STAGE_03][job_id={job_id}] TTS 전체 실패: {e}"
            )
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "COMPLETED",
                "audio_file_path": None,
                "srt_file_path": None,
                "tts_provider": "failed",
                "duration_sec": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - TTS는 실패해도 파이프라인 계속 진행 허용 (오디오 없이도 영상 생성 가능)."""
        return ValidationResult(is_valid=True)
