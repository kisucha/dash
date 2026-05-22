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

# 기본 프로바이더 시도 순서 - VoiceBox(로컬 REST) > Supertone3(고품질) > Coqui(오픈소스) > pyttsx3(로컬 폴백)
DEFAULT_PROVIDER_ORDER = ["voicebox", "supertone3", "coqui", "pyttsx3"]


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
                if provider == "voicebox":
                    result = self._voicebox(text, output_path, voice, timeout)
                elif provider == "supertone3":
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

    def _voicebox(self, text: str, output_path: str, voice: str, timeout: int) -> TTSResult:
        """VoiceBox 로컬 REST API (http://127.0.0.1:17493/generate) TTS.

        VoiceBox가 로컬에서 실행 중이어야 한다 (MSI 설치 후 실행).
        환경변수:
            VOICEBOX_BASE_URL: 기본값 http://127.0.0.1:17493
            VOICEBOX_PROFILE_ID: 생성한 음성 프로파일 ID (필수)
            VOICEBOX_LANGUAGE: 언어 코드 (기본 ko)
        """
        import os
        import json as _json_mod
        import urllib.request

        base_url = os.environ.get("VOICEBOX_BASE_URL", "http://127.0.0.1:17493")
        profile_id = voice or os.environ.get("VOICEBOX_PROFILE_ID", "")
        language = os.environ.get("VOICEBOX_LANGUAGE", "ko")

        if not profile_id:
            raise ImportError("VOICEBOX_PROFILE_ID 미설정 - VoiceBox 프로파일 ID를 .env에 추가하세요")

        # VoiceBox는 WAV 출력 - 확장자 강제 .wav
        wav_path = (
            output_path
            if output_path.lower().endswith(".wav")
            else output_path.rsplit(".", 1)[0] + ".wav"
        )

        payload = _json_mod.dumps({
            "text": text[:5000],
            "profile_id": profile_id,
            "language": language,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp_bytes = resp.read()
        except Exception as e:
            raise RuntimeError(f"VoiceBox API 호출 실패 ({base_url}/generate): {e}") from e

        def _is_wav(data: bytes) -> bool:
            return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"

        if _is_wav(resp_bytes):
            audio_bytes = resp_bytes
        else:
            import time as _time
            try:
                job_info = json.loads(resp_bytes)
                gen_id = job_info.get("id")
            except Exception:
                gen_id = None

            if not gen_id:
                preview = resp_bytes[:300].decode("utf-8", errors="replace")
                raise RuntimeError(f"VoiceBox 응답이 WAV도 아니고 id도 없음: {preview}")

            logger.info(f"[TTSChain] VoiceBox 비동기 생성 대기 (gen_id={gen_id})")
            _DONE_STATUS = {"done", "completed", "success", "finished", "complete"}
            audio_bytes = None
            for attempt in range(300):
                _time.sleep(3)
                is_done = False
                try:
                    with urllib.request.urlopen(f"{base_url}/generate/{gen_id}/status", timeout=10) as sr:
                        status_info = json.loads(sr.read())
                        if attempt == 0:
                            logger.info(f"[TTSChain] VoiceBox status: {str(status_info)[:300]}")
                        is_done = str(status_info.get("status", "")).lower() in _DONE_STATUS
                except Exception:
                    pass
                if is_done or attempt % 10 == 9:
                    try:
                        with urllib.request.urlopen(f"{base_url}/audio/{gen_id}", timeout=30) as ar:
                            candidate = ar.read()
                            if _is_wav(candidate):
                                audio_bytes = candidate
                    except Exception:
                        pass
                if audio_bytes:
                    logger.info(f"[TTSChain] VoiceBox 생성 완료 (시도 {attempt + 1}회)")
                    break
            if not audio_bytes:
                raise RuntimeError(f"VoiceBox 오디오 생성 타임아웃 15분 초과 (gen_id={gen_id})")

        Path(wav_path).write_bytes(audio_bytes)
        return TTSResult(wav_path, "voicebox", self._get_duration(wav_path))

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
        """오디오 파일 길이(초)를 측정한다.

        WAV 파일은 Python 내장 wave 모듈로 측정 (ffprobe 불필요).
        그 외 포맷(mp3 등)은 imageio_ffmpeg를 통해 ffprobe 경로를 찾고, 실패 시 시스템 ffprobe로 폴백.
        """
        # WAV 파일은 Python 내장 wave 모듈로 측정 (ffprobe 경로 해석 오류 방지)
        if audio_path.lower().endswith(".wav"):
            try:
                import wave
                with wave.open(audio_path, "rb") as wf:
                    return wf.getnframes() / float(wf.getframerate())
            except Exception as e:
                logger.debug(f"[TTSChain] wave 모듈 측정 실패: {e}")

        # 그 외 포맷(mp3 등): ffprobe 사용
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
