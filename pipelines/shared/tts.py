# pipelines/shared/tts.py
# 목적: TTS 폴백 체인 - Supertone3 > Coqui > pyttsx3
# F006/F007 등 여러 파이프라인에서 공유하는 공통 TTS 유틸리티

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import subprocess
import logging
import json as _json
from pathlib import Path
from typing import Optional
import importlib.util

logger = logging.getLogger(__name__)

# 기본 프로바이더 시도 순서 - Supertone3(고품질) > Coqui(오픈소스) > pyttsx3(로컬 폴백)
DEFAULT_PROVIDER_ORDER = ["supertone3", "coqui", "pyttsx3"]


class TTSResult:
    """TTS 합성 결과 - 오디오 파일 경로, 사용된 프로바이더, 길이 정보."""

    def __init__(self, audio_path: str, provider: str, duration_sec: float = 0.0):
        # 생성된 오디오 파일의 절대 경로
        self.audio_path = audio_path
        # 실제로 사용된 TTS 프로바이더 이름 (supertone3/coqui/pyttsx3)
        self.provider = provider
        # 오디오 길이(초) - ffprobe로 측정, 실패 시 0.0
        self.duration_sec = duration_sec


class TTSChain:
    """TTS 프로바이더 폴백 체인 - provider_order 순서대로 시도.

    앞 프로바이더 실패 시 다음 프로바이더로 자동 전환한다.
    모든 프로바이더 실패 시 RuntimeError를 발생시킨다.
    """

    def __init__(self, provider_order: list = None):
        # 시도할 프로바이더 순서 목록
        self.provider_order = provider_order or DEFAULT_PROVIDER_ORDER

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: str = "F1",
        rate: float = 1.0,
        timeout: int = 300,
    ) -> TTSResult:
        """텍스트를 오디오로 합성한다.

        Args:
            text: 합성할 텍스트
            output_path: 출력 오디오 파일 경로
            voice: 음성 ID (Supertone3 기준: F1/F3 등)
            rate: 말하기 속도 배율 (1.0 = 표준)
            timeout: 외부 프로세스 타임아웃(초)

        Returns:
            TTSResult - 성공한 프로바이더와 오디오 경로 포함

        Raises:
            RuntimeError: 모든 프로바이더 실패 시
        """
        last_error = None
        for provider in self.provider_order:
            try:
                if provider == "supertone3":
                    result = self._supertone3(text, output_path, voice, rate, timeout)
                elif provider == "coqui":
                    result = self._coqui(text, output_path, timeout)
                elif provider == "pyttsx3":
                    result = self._pyttsx3(text, output_path)
                else:
                    logger.warning(f"[TTSChain] 알 수 없는 프로바이더: {provider}")
                    continue
                # 파일이 실제로 생성됐는지 확인
                if result and Path(result.audio_path).exists():
                    logger.info(f"[TTSChain] {provider} 합성 성공 - {result.audio_path}")
                    return result
            except Exception as e:
                last_error = e
                logger.warning(f"[TTSChain] {provider} 실패 - 다음 프로바이더 시도: {e}")
        raise RuntimeError(f"모든 TTS 프로바이더 실패. 마지막 오류: {last_error}")

    def _supertone3(self, text: str, output_path: str, voice: str, rate: float, timeout: int) -> TTSResult:
        """Supertone3(supertonic) 패키지로 TTS 합성.

        supertonic 패키지가 설치되지 않으면 ImportError 발생 -> 폴백 처리.
        """
        if not importlib.util.find_spec("supertonic"):
            raise ImportError("supertonic 패키지 미설치 - pip install supertonic 필요")
        from supertonic import TTS as SupertonicTTS  # type: ignore[import]
        engine = SupertonicTTS(auto_download=True)
        style = engine.get_voice_style(voice_name=voice)
        # synthesize()는 (wav_array, sample_rate) 튜플 반환
        wav, _ = engine.synthesize(
            text=text[:5000],
            lang="ko",
            voice_style=style,
            total_steps=8,
            speed=rate,
        )
        engine.save_audio(wav, output_path)
        return TTSResult(output_path, "supertone3", self._get_duration(output_path))

    def _coqui(self, text: str, output_path: str, timeout: int) -> TTSResult:
        """Coqui TTS CLI로 한국어 합성.

        tts_models/ko/css10/vits 모델 사용. 모델 미설치 시 자동 다운로드.
        """
        cmd = [
            sys.executable, "-m", "TTS",
            "--model_name", "tts_models/ko/css10/vits",
            "--text", text,
            "--out_path", output_path,
        ]
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )
        if r.returncode != 0:
            raise RuntimeError(f"Coqui TTS 실패 (returncode={r.returncode}): {r.stderr[:200]}")
        if not Path(output_path).exists():
            raise RuntimeError("Coqui TTS: 출력 파일이 생성되지 않음")
        return TTSResult(output_path, "coqui", self._get_duration(output_path))

    def _pyttsx3(self, text: str, output_path: str) -> TTSResult:
        """pyttsx3(로컬 TTS 엔진)로 합성 - 품질 낮지만 외부 의존성 없음."""
        import pyttsx3  # type: ignore[import]
        engine = pyttsx3.init()
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        if not Path(output_path).exists():
            raise RuntimeError("pyttsx3: 출력 파일이 생성되지 않음")
        return TTSResult(output_path, "pyttsx3", self._get_duration(output_path))

    def _get_duration(self, audio_path: str) -> float:
        """ffprobe로 오디오 파일 길이(초)를 측정한다.

        imageio_ffmpeg를 통해 ffprobe 경로를 찾고, 실패 시 시스템 ffprobe로 폴백.
        """
        try:
            import imageio_ffmpeg  # type: ignore[import]
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            # ffmpeg.exe -> ffprobe.exe 경로 치환
            ffprobe = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        except Exception:
            ffprobe = "ffprobe"

        try:
            r = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_streams",
                    audio_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
            )
            data = _json.loads(r.stdout)
            streams = data.get("streams", [])
            if streams:
                return float(streams[0].get("duration", 0))
        except Exception as e:
            logger.debug(f"[TTSChain] ffprobe 길이 측정 실패: {e}")
        return 0.0
