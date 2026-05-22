# 목적: F006 STAGE_03 - TTS 보이스오버 생성 스테이지.
# Coqui/ElevenLabs/OpenAI/Edge TTS/gTTS를 지원하며 skip 처리도 가능하다.
# tts_skip=True이면 즉시 SKIPPED 상태를 반환한다.

import sys
import os
import re
import json
import logging
import subprocess

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트 (call_ollama 등)
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage03TTS(BaseStage, BasePipeline):
    """STAGE_03 - TTS 보이스오버 생성 스테이지.

    지원 프로바이더:
      - edge_tts: Microsoft Edge TTS (무료, 인터넷 필요, 한국어 고품질)
      - gtts: Google TTS (무료, 인터넷 필요, 한국어 지원)
      - coqui: TTS CLI subprocess 호출 (한국어 모델: tts_models/ko/css10/vits)
      - elevenlabs: ElevenLabs REST API (ELEVENLABS_API_KEY 환경변수 필요)
      - openai: OpenAI TTS API (OPENAI_API_KEY 환경변수 필요)

    tts_skip=True이면 보이스오버 없이 다음 스테이지로 진행한다.
    edge_tts 사용 시 SubMaker로 정확한 WordBoundary 기반 SRT를 생성한다.
    """

    STAGE_ID: str = "STAGE_03_TTS"
    STAGE_ORDER: int = 3

    # edge_tts SubMaker가 생성한 SRT 경로 (execute 중 _run_edge_tts가 설정)
    _edge_tts_srt_path: Optional[str] = None

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE03", "name": "STAGE_03_TTS"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_03 실행 - TTS 보이스오버 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                tts_skip (bool, 기본 False): TTS 건너뛰기 여부
                tts_provider (str, 기본 "coqui"): TTS 엔진
                script_text (str): STAGE_02 출력 전체 스크립트 텍스트
            }

        Returns:
            SKIPPED 시: {stage_id, status="SKIPPED", skip_reason, audio_file_path=None, generated_at}
            COMPLETED 시: {stage_id, status="COMPLETED", tts_provider, audio_file_path,
                           duration_sec, file_size_kb, generated_at}
        """
        # skip 처리 - 사용자가 TTS를 건너뛰기로 선택한 경우
        tts_skip: bool = bool(input_data.get("tts_skip", False))
        if tts_skip:
            logger.info(f"[F006][STAGE_03][job_id={job_id}] TTS 건너뜀 (사용자 선택)")
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "SKIPPED",
                "skip_reason": "사용자 선택으로 TTS 건너뜀",
                "audio_file_path": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 프로바이더, 목소리, 속도, 피치, 스크립트 추출
        provider: str = input_data.get("tts_provider", "edge_tts")
        tts_voice: str = input_data.get("tts_voice") or ""
        tts_rate: str = input_data.get("tts_rate") or "+0%"
        tts_pitch: str = input_data.get("tts_pitch") or "+0Hz"
        script_text: str = input_data.get("script_text", "")

        # 숫자 읽기 전처리: 천 단위 쉼표 제거, 소수점 "점" 변환
        script_text = self._preprocess_script_for_tts(script_text)

        # 스크립트 텍스트 없으면 skip 처리
        if not script_text.strip():
            logger.warning(
                f"[F006][STAGE_03][job_id={job_id}] 스크립트 텍스트가 비어 있어 TTS 건너뜀"
            )
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "SKIPPED",
                "skip_reason": "스크립트 텍스트가 없어 TTS 생략",
                "audio_file_path": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 출력 경로 설정 - 절대 경로 (ERR-007: 상대 경로는 backend 기준으로 저장됨)
        _project_root = Path(__file__).parent.parent.parent.parent
        # supertonic/voicebox는 WAV 출력 — 나머지는 MP3
        _audio_ext = "wav" if provider in ("supertonic", "voicebox") else "mp3"
        output_path: str = str(
            _project_root / "storage" / "results" / "f006" / str(job_id) / f"voiceover.{_audio_ext}"
        )
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] TTS 시작 - "
            f"프로바이더: {provider}, 출력: {output_path}"
        )

        # SubMaker SRT 경로 초기화 (execute 실행마다 리셋)
        self._edge_tts_srt_path = None

        # 프로바이더별 TTS 실행
        try:
            if provider == "voicebox":
                self._run_voicebox_tts(script_text, output_path, job_id, tts_voice)

            elif provider == "coqui":
                self._run_coqui_tts(script_text, output_path, job_id)

            elif provider == "edge_tts":
                self._run_edge_tts(script_text, output_path, job_id, tts_voice, tts_rate, tts_pitch)

            elif provider == "gtts":
                self._run_gtts(script_text, output_path, job_id)

            elif provider == "elevenlabs":
                self._run_elevenlabs_tts(script_text, output_path, job_id, tts_voice)

            elif provider == "openai":
                self._run_openai_tts(script_text, output_path, job_id, tts_voice)

            elif provider == "supertonic":
                self._run_supertonic_tts(script_text, output_path, job_id, tts_voice, tts_rate)

            else:
                raise ValueError(f"알 수 없는 TTS 프로바이더: {provider}")

        except Exception as e:
            logger.error(f"[F006][STAGE_03][job_id={job_id}] TTS 실패: {e}")
            raise RuntimeError(f"STAGE_03 TTS 생성 실패: {e}") from e

        # 파일 존재 확인
        output_file = Path(output_path)
        if not output_file.exists():
            raise RuntimeError(f"TTS 출력 파일이 생성되지 않음: {output_path}")

        # 파일 크기 (폴백 추정용으로 유지)
        file_size_bytes: int = output_file.stat().st_size
        file_size_kb: int = file_size_bytes // 1024
        # mp3 128kbps 기준 파일 크기 추정값 (ffprobe 폴백용)
        audio_duration_estimate: float = round(file_size_bytes / 16000, 1)

        # ffprobe로 실제 오디오 길이 측정 (더 정확)
        actual_duration: Optional[float] = self._get_actual_audio_duration(output_path)
        audio_duration: float = actual_duration if actual_duration else audio_duration_estimate

        if actual_duration:
            logger.info(
                f"[F006][STAGE_03][job_id={job_id}] TTS 완료 - "
                f"{file_size_kb}KB, ffprobe 실제 길이: {actual_duration:.2f}초"
            )
        else:
            logger.info(
                f"[F006][STAGE_03][job_id={job_id}] TTS 완료 - "
                f"{file_size_kb}KB, 파일 크기 추정: {audio_duration_estimate:.1f}초 (ffprobe 실패)"
            )

        # SRT 자막 파일 결정
        # subtitle_enabled=False이면 자막 생성 건너뜀
        subtitle_enabled: bool = bool(input_data.get("subtitle_enabled", True))
        output_dir: str = str(Path(output_path).parent)
        srt_file_path: Optional[str] = None
        srt_content: str = ""

        if subtitle_enabled:
            # edge_tts SubMaker SRT 우선 사용 (WordBoundary 기반, 정확한 타임코드)
            if (
                provider == "edge_tts"
                and self._edge_tts_srt_path
                and Path(self._edge_tts_srt_path).exists()
            ):
                srt_file_path = self._edge_tts_srt_path
                try:
                    srt_content = Path(srt_file_path).read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning(f"[F006][STAGE_03][job_id={job_id}] SubMaker SRT 읽기 실패: {e}")
                    srt_content = ""
                logger.info(
                    f"[F006][STAGE_03][job_id={job_id}] SubMaker SRT 사용 (정확한 타임코드)"
                )
            else:
                # 다른 프로바이더: ffprobe 실제 duration 기반 char 비례 SRT
                try:
                    srt_file_path, srt_content = self._generate_srt(
                        script_text, audio_duration, output_dir, job_id
                    )
                except Exception as e:
                    logger.warning(f"[F006][STAGE_03][job_id={job_id}] SRT 생성 실패 (무시): {e}")
        else:
            logger.info(f"[F006][STAGE_03][job_id={job_id}] 자막 비활성화 - SRT 생성 건너뜀")

        return {
            "stage_id": "STAGE_03_TTS",
            "status": "COMPLETED",
            "tts_provider": provider,
            "audio_file_path": output_path,
            "srt_file_path": srt_file_path,
            "srt_content": srt_content,
            "duration_sec": audio_duration,
            "file_size_kb": file_size_kb,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # TTS 프로바이더별 구현
    # ------------------------------------------------------------------

    def _run_voicebox_tts(
        self, script_text: str, output_path: str, job_id: int, voice: str = ""
    ) -> None:
        """VoiceBox 로컬 REST API (http://127.0.0.1:17493/generate) TTS.

        VoiceBox API는 비동기: POST /generate → job JSON 즉시 반환 → 폴링으로 WAV 획득.
        """
        import json as _json_mod
        import time as _time
        import urllib.request as _urllib_req

        base_url = os.getenv("VOICEBOX_BASE_URL", "http://127.0.0.1:17493")
        profile_id = voice or os.getenv("VOICEBOX_PROFILE_ID", "")
        language = os.getenv("VOICEBOX_LANGUAGE", "ko")

        if not profile_id:
            raise RuntimeError(
                "VOICEBOX_PROFILE_ID 환경변수가 설정되지 않았습니다. "
                ".env 파일에 VOICEBOX_PROFILE_ID=... 추가 후 재시도하세요."
            )

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] VoiceBox TTS 시작 - "
            f"profile={profile_id}, language={language}"
        )

        payload = _json_mod.dumps({
            "text": script_text[:5000],
            "profile_id": profile_id,
            "language": language,
        }).encode("utf-8")

        req = _urllib_req.Request(
            f"{base_url}/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with _urllib_req.urlopen(req, timeout=60) as resp:
                resp_bytes = resp.read()
        except Exception as e:
            raise RuntimeError(f"VoiceBox API 호출 실패 ({base_url}): {e}") from e

        def _is_wav(data: bytes) -> bool:
            return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"

        if _is_wav(resp_bytes):
            audio_bytes = resp_bytes
        else:
            try:
                job_info = _json_mod.loads(resp_bytes)
                gen_id = job_info.get("id")
            except Exception:
                gen_id = None

            if not gen_id:
                preview = resp_bytes[:300].decode("utf-8", errors="replace")
                raise RuntimeError(f"VoiceBox 응답이 WAV도 아니고 id도 없음: {preview}")

            logger.info(f"[F006][STAGE_03][job_id={job_id}] VoiceBox 비동기 생성 대기 (gen_id={gen_id})")
            poll_urls = [
                f"{base_url}/generate/{gen_id}/audio",
                f"{base_url}/audio/{gen_id}",
                f"{base_url}/generate/{gen_id}",
            ]

            audio_bytes = None
            for attempt in range(120):
                _time.sleep(3)
                for poll_url in poll_urls:
                    try:
                        with _urllib_req.urlopen(poll_url, timeout=30) as poll_resp:
                            data = poll_resp.read()
                            if _is_wav(data):
                                audio_bytes = data
                                break
                    except Exception:
                        continue
                if audio_bytes:
                    logger.info(f"[F006][STAGE_03][job_id={job_id}] VoiceBox 생성 완료 (시도 {attempt + 1}회)")
                    break

            if not audio_bytes:
                raise RuntimeError(f"VoiceBox 오디오 생성 타임아웃 6분 초과 (gen_id={gen_id})")

        from pathlib import Path as _Path
        _Path(output_path).write_bytes(audio_bytes)
        logger.info(f"[F006][STAGE_03][job_id={job_id}] VoiceBox TTS 완료")

    def _run_coqui_tts(self, script_text: str, output_path: str, job_id: int) -> None:
        """Coqui TTS CLI subprocess 호출.

        'tts_models/ko/css10/vits' 한국어 모델을 사용한다.
        모델은 첫 실행 시 자동 다운로드된다 (약 80~100MB).
        """
        logger.info(f"[F006][STAGE_03][job_id={job_id}] Coqui TTS subprocess 실행 시작")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "TTS",
                "--text",
                script_text[:5000],
                "--model_name",
                "tts_models/ko/css10/vits",
                "--out_path",
                output_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Coqui TTS 실패 (exit code {result.returncode}): "
                f"{result.stderr[:300]}"
            )

        logger.info(f"[F006][STAGE_03][job_id={job_id}] Coqui TTS 완료")

    def _get_actual_audio_duration(self, audio_path: str) -> Optional[float]:
        """ffprobe로 실제 오디오 길이(초)를 측정한다. 실패 시 None 반환.

        시스템 ffprobe 먼저 시도, 없으면 imageio_ffmpeg 번들 경로로 폴백.
        """
        # 시스템 PATH의 ffprobe 시도
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True, text=True, timeout=30, encoding="utf-8"
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass

        # imageio_ffmpeg 번들 ffprobe 경로 시도
        try:
            import imageio_ffmpeg as _ff
            ffmpeg_exe = _ff.get_ffmpeg_exe()
            ffprobe_path = (
                ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
            )
            result = subprocess.run(
                [
                    ffprobe_path, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True, text=True, timeout=30, encoding="utf-8"
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass

        return None

    def _run_edge_tts(
        self,
        script_text: str,
        output_path: str,
        job_id: int,
        voice: str = "",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        """edge_tts + SubMaker: 음성 파일과 정확한 SRT 자막을 동시 생성.

        SubMaker는 WordBoundary 이벤트를 캡처해 단어 단위 타임코드를 만든다.
        SRT 저장 경로는 self._edge_tts_srt_path에 기록해 execute()에서 참조한다.
        """
        try:
            import asyncio
            import edge_tts  # type: ignore[import]
        except ImportError as e:
            raise RuntimeError(
                f"edge-tts 패키지가 설치되지 않았습니다. "
                f"pip install edge-tts 실행 후 재시도하세요. ({e})"
            ) from e

        _voice = voice or "ko-KR-SunHiNeural"
        srt_path = str(Path(output_path).parent / "voiceover.srt")

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] Edge TTS+SubMaker 실행 시작 - "
            f"voice={_voice}, rate={rate}, pitch={pitch}"
        )

        async def _synthesize():
            """스트리밍으로 오디오 저장 + WordBoundary 수집."""
            subs = edge_tts.SubMaker()
            communicate = edge_tts.Communicate(
                text=script_text[:5000],
                voice=_voice,
                rate=rate,
                pitch=pitch,
            )
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        subs.create_sub(
                            chunk["offset"], chunk["duration"], chunk["text"]
                        )
            return subs

        try:
            subs = asyncio.run(_synthesize())
            self._save_submaker_srt(subs, srt_path, job_id)
            self._edge_tts_srt_path = srt_path
            logger.info(f"[F006][STAGE_03][job_id={job_id}] Edge TTS+SubMaker 완료")
        except Exception as e:
            self._edge_tts_srt_path = None
            raise RuntimeError(f"Edge TTS 실행 실패: {e}") from e

    def _save_submaker_srt(self, subs, srt_path: str, job_id: int) -> None:
        """SubMaker 출력을 SRT 형식으로 변환 저장.

        edge_tts.SubMaker.generate_subs()는 VTT 형식을 반환한다.
        타임코드 구분자를 콤마로 바꾸고 인덱스를 붙여 SRT로 저장한다.
        """
        import re as _re

        # generate_subs() 반환은 VTT 형식 (WEBVTT\n\n타임코드\n텍스트...)
        vtt_content = ""
        try:
            vtt_content = subs.generate_subs()
        except Exception:
            # 구버전 edge_tts: words_in_cue 파라미터 지원
            try:
                vtt_content = subs.generate_subs(words_in_cue=10)
            except Exception as e:
                logger.warning(
                    f"[F006][STAGE_03][job_id={job_id}] SubMaker generate_subs 실패: {e}"
                )
                return

        if not vtt_content:
            logger.warning(
                f"[F006][STAGE_03][job_id={job_id}] SubMaker 빈 VTT 출력 - SRT 저장 건너뜀"
            )
            return

        lines = vtt_content.strip().splitlines()
        srt_lines: list[str] = []
        idx = 1
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # WEBVTT 헤더 및 빈 줄, NOTE 블록 건너뜀
            if line in ("WEBVTT", "") or line.startswith("NOTE"):
                i += 1
                continue
            # 타임코드 라인 (00:00:00.000 --> 00:00:01.000)
            tc_match = _re.match(
                r"(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})",
                line
            )
            if tc_match:
                # 점(.) -> 콤마(,) 변환 (SRT 형식)
                start = tc_match.group(1).replace(".", ",")
                end = tc_match.group(2).replace(".", ",")
                i += 1
                text_parts: list[str] = []
                while i < len(lines) and lines[i].strip():
                    text_parts.append(lines[i].strip())
                    i += 1
                if text_parts:
                    srt_lines.extend([
                        str(idx),
                        f"{start} --> {end}",
                        " ".join(text_parts),
                        "",
                    ])
                    idx += 1
            else:
                i += 1

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] SubMaker SRT 저장 완료: "
            f"{srt_path} ({idx - 1}개 항목)"
        )

    def _run_gtts(self, script_text: str, output_path: str, job_id: int) -> None:
        """Google TTS 실행 (gTTS 패키지, 무료, API 키 불필요)."""
        logger.info(f"[F006][STAGE_03][job_id={job_id}] Google TTS 실행 시작")
        try:
            from gtts import gTTS  # type: ignore[import]
        except ImportError as e:
            raise RuntimeError(
                f"gtts 패키지가 설치되지 않았습니다. "
                f"pip install gtts 실행 후 재시도하세요. ({e})"
            ) from e

        try:
            tts = gTTS(text=script_text[:5000], lang="ko", slow=False)
            tts.save(output_path)
            logger.info(f"[F006][STAGE_03][job_id={job_id}] Google TTS 완료")
        except Exception as e:
            raise RuntimeError(f"Google TTS 실행 실패: {e}") from e

    def _run_elevenlabs_tts(
        self, script_text: str, output_path: str, job_id: int, voice: str = ""
    ) -> None:
        """ElevenLabs REST API 호출 TTS. ELEVENLABS_API_KEY 환경변수 필요."""
        import httpx

        api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 ELEVENLABS_API_KEY=... 추가 후 재시도하세요."
            )

        voice_id = voice or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        logger.info(f"[F006][STAGE_03][job_id={job_id}] ElevenLabs TTS API 호출 시작 - voice={voice_id}")
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    url,
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                    json={
                        "text": script_text[:4500],
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.8,
                        },
                    },
                )
                resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"[F006][STAGE_03][job_id={job_id}] ElevenLabs TTS 완료")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"ElevenLabs API 오류: HTTP {e.response.status_code}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS 호출 실패: {e}") from e

    def _run_openai_tts(
        self, script_text: str, output_path: str, job_id: int, voice: str = ""
    ) -> None:
        """OpenAI TTS API 호출. OPENAI_API_KEY 환경변수 필요."""
        import httpx

        api_key: str = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 OPENAI_API_KEY=... 추가 후 재시도하세요."
            )

        _voice = voice or "alloy"
        logger.info(f"[F006][STAGE_03][job_id={job_id}] OpenAI TTS API 호출 시작 - voice={_voice}")
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "tts-1",
                        "input": script_text[:4096],
                        "voice": _voice,
                        "response_format": "mp3",
                    },
                )
                resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"[F006][STAGE_03][job_id={job_id}] OpenAI TTS 완료")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"OpenAI TTS API 오류: HTTP {e.response.status_code}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"OpenAI TTS 호출 실패: {e}") from e

    def _run_supertonic_tts(
        self,
        script_text: str,
        output_path: str,
        job_id: int,
        voice: str = "",
        rate: str = "+0%",
    ) -> None:
        """Supertone TTS 로컬 실행. pip install supertonic 필요.

        음성: M1-M5(남성), F1-F5(여성), 기본값 F1.
        출력: 16-bit WAV.
        total_steps=8 고정 (품질/속도 균형).
        tts_rate("+10%" 형식) → speed float 변환.
        """
        try:
            from supertonic import TTS  # type: ignore[import]
        except ImportError as e:
            raise RuntimeError(
                f"supertonic 패키지가 설치되지 않았습니다. "
                f"pip install supertonic 실행 후 재시도하세요. ({e})"
            ) from e

        _voice = voice or "F1"

        # "+10%" → 1.1, "-5%" → 0.95, "+0%" → 1.0
        _speed = 1.05
        try:
            rate_stripped = rate.strip().replace("%", "")
            rate_int = int(rate_stripped)
            _speed = max(0.7, min(2.0, 1.0 + rate_int / 100.0))
        except Exception:
            pass

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] Supertone TTS 시작 - "
            f"voice={_voice}, speed={_speed:.2f}"
        )

        try:
            tts = TTS(auto_download=True)
            style = tts.get_voice_style(voice_name=_voice)
            wav, _ = tts.synthesize(
                text=script_text[:5000],
                lang="ko",
                voice_style=style,
                total_steps=8,
                speed=_speed,
            )
            tts.save_audio(wav, output_path)
            logger.info(f"[F006][STAGE_03][job_id={job_id}] Supertone TTS 완료")
        except Exception as e:
            raise RuntimeError(f"Supertone TTS 실행 실패: {e}") from e

    @staticmethod
    def _num_to_korean(n: int) -> str:
        """정수를 한국어 숫자 읽기 텍스트로 변환.

        한국어는 만(10,000) 단위 체계. 십/백/천/만/억/조 단위로 분해.
        각 자리에서 1인 경우 '일' 생략 (단, 일의 자리는 명시).
        예: 281000 -> 이십팔만천, 1110 -> 천백십, 7516 -> 칠천오백십육
        """
        if n == 0:
            return "영"
        if n < 0:
            return "마이너스" + Stage03TTS._num_to_korean(-n)

        # 자리값 단위 (만 단위 체계)
        UNITS = ["", "만", "억", "조"]
        DIGITS = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
        PLACES = ["", "십", "백", "천"]

        def _chunk_to_korean(chunk: int) -> str:
            """0-9999 범위의 정수를 한국어 문자열로 변환."""
            if chunk == 0:
                return ""
            result = ""
            for place_idx, place_name in enumerate(PLACES):
                digit = (chunk // (10 ** place_idx)) % 10
                if digit == 0:
                    continue
                # 십/백/천 자리에서 digit==1이면 '일' 생략 (ex: 천, 백십, 십)
                digit_str = "" if (digit == 1 and place_idx > 0) else DIGITS[digit]
                result = digit_str + place_name + result
            return result

        result = ""
        for unit_idx, unit_name in enumerate(UNITS):
            chunk = (n // (10000 ** unit_idx)) % 10000
            if chunk == 0:
                continue
            chunk_str = _chunk_to_korean(chunk)
            result = chunk_str + unit_name + result

        return result

    def _preprocess_script_for_tts(self, text: str) -> str:
        """TTS 전송 전 숫자 표기 전처리.

        1. 천 단위 쉼표가 포함된 숫자를 한국어 텍스트로 변환
           예: 281,000 -> 이십팔만천, 1,110 -> 천백십
        2. 소수점 '점'으로 변환: 0.361 -> 0점361
           (TTS가 '.'를 '콤마'로 읽는 문제 방지)
        3. 쉼표 없는 단독 큰 숫자(5자리 이상)도 한국어 변환
           예: 281000 -> 이십팔만천
        """
        import re as _re

        def _replace_comma_num(m: "re.Match[str]") -> str:
            # 쉼표 제거 후 정수 변환 → 한국어
            raw = m.group(0).replace(",", "")
            try:
                return Stage03TTS._num_to_korean(int(raw))
            except ValueError:
                return raw

        # 1단계: 천 단위 쉼표 포함 숫자 -> 한국어 (1,234,567 등 모두 처리)
        text = _re.sub(r'\d{1,3}(?:,\d{3})+', _replace_comma_num, text)

        # 2단계: 쉼표 없는 5자리 이상 숫자 -> 한국어 (ex: 281000)
        text = _re.sub(r'\b(\d{5,})\b', lambda m: Stage03TTS._num_to_korean(int(m.group(1))), text)

        # 3단계: 숫자 사이 소수점 -> '점' (문장 마침표 등 비숫자 맥락은 건드리지 않음)
        text = _re.sub(r'(\d)\.(\d)', r'\1점\2', text)

        return text

    def _generate_srt(
        self,
        script_text: str,
        audio_duration: float,
        output_dir: str,
        job_id: int,
    ) -> Tuple[str, str]:
        """스크립트 텍스트에서 SRT 자막 파일 생성.

        한국어 평균 발화 속도(350자/분 = 5.8자/초) 기준으로 문장별 타임코드를 추정하고
        실제 오디오 duration으로 전체 타임라인을 스케일 보정한다.
        """
        # 문장 분할 - 한국어/영어 구두점 기준
        raw_sentences: list[str] = re.split(
            r'(?<=[.!?。！？])\s+', script_text.strip()
        )
        sentences: list[str] = [s.strip() for s in raw_sentences if s.strip()]
        if not sentences:
            sentences = [script_text.strip()]

        # 한국어 발화 속도 기준 문장별 예상 길이(초) 계산
        CHARS_PER_SEC: float = 5.8
        raw_durations: list[float] = [
            max(0.5, len(s) / CHARS_PER_SEC) for s in sentences
        ]
        raw_total: float = sum(raw_durations)

        # 실제 오디오 duration으로 전체 타임라인 스케일 보정
        scale: float = (
            audio_duration / raw_total
            if raw_total > 0 and audio_duration > 0
            else 1.0
        )
        durations: list[float] = [d * scale for d in raw_durations]

        def _fmt_time(sec: float) -> str:
            """초 단위 float를 SRT 타임코드(HH:MM:SS,mmm)로 변환."""
            h: int = int(sec // 3600)
            m: int = int((sec % 3600) // 60)
            s: int = int(sec % 60)
            ms: int = int(round((sec - int(sec)) * 1000))
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        # SRT 본문 조합
        srt_lines: list[str] = []
        current: float = 0.0
        for i, (sentence, dur) in enumerate(zip(sentences, durations), start=1):
            start_tc: str = _fmt_time(current)
            end_tc: str = _fmt_time(current + dur)
            srt_lines.extend([str(i), f"{start_tc} --> {end_tc}", sentence, ""])
            current += dur

        srt_content: str = "\n".join(srt_lines)
        srt_path: str = str(Path(output_dir) / "voiceover.srt")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        logger.info(
            f"[F006][STAGE_03][job_id={job_id}] SRT 생성 완료 - "
            f"{len(sentences)}개 자막 항목, {srt_path}"
        )
        return srt_path, srt_content
