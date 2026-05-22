# 목적: STAGE_03 — TTS 보이스오버 생성 스테이지.
# Coqui/ElevenLabs/OpenAI/Edge TTS/gTTS를 지원하며 skip 처리도 가능하다.
# tts_skip=True이면 즉시 SKIPPED 상태를 반환한다.

import sys
import os
import re
import json
import logging
import subprocess

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f001_youtube.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트 (call_ollama 등)
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage03TTS(BaseStage, BasePipeline):
    """STAGE_03 — TTS 보이스오버 생성 스테이지.

    지원 프로바이더:
      - edge_tts: Microsoft Edge TTS (무료, 인터넷 필요, 한국어 고품질)
      - gtts: Google TTS (무료, 인터넷 필요, 한국어 지원)
      - coqui: TTS CLI subprocess 호출 (한국어 모델: tts_models/ko/css10/vits)
      - elevenlabs: ElevenLabs REST API (ELEVENLABS_API_KEY 환경변수 필요)
      - openai: OpenAI TTS API (OPENAI_API_KEY 환경변수 필요)

    tts_skip=True이면 보이스오버 없이 다음 스테이지로 진행한다.
    """

    STAGE_ID: str = "STAGE_03_TTS"
    STAGE_ORDER: int = 3

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F001_STAGE03", "name": "STAGE_03_TTS"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_03 실행 — TTS 보이스오버 생성.

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
        # skip 처리 — 사용자가 TTS를 건너뛰기로 선택한 경우
        tts_skip: bool = bool(input_data.get("tts_skip", False))
        if tts_skip:
            logger.info(f"[STAGE_03][job_id={job_id}] TTS 건너뜀 (사용자 선택)")
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

        # script_text가 JSON이면 slides.narration 추출
        if script_text.strip().startswith("{"):
            try:
                _parsed = json.loads(script_text)
                _parts = [s.get("narration", "").strip() for s in _parsed.get("slides", []) if s.get("narration", "").strip()]
                if _parts:
                    script_text = " ".join(_parts)
                    logger.info(f"[STAGE_03][job_id={job_id}] script_text JSON → narration 추출 ({len(script_text)}자)")
            except Exception:
                pass

        # 스크립트 텍스트 없으면 skip 처리
        if not script_text.strip():
            logger.warning(
                f"[STAGE_03][job_id={job_id}] 스크립트 텍스트가 비어 있어 TTS 건너뜀"
            )
            return {
                "stage_id": "STAGE_03_TTS",
                "status": "SKIPPED",
                "skip_reason": "스크립트 텍스트가 없어 TTS 생략",
                "audio_file_path": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 출력 경로 설정 — 절대 경로 (ERR-007: 상대 경로는 backend 기준으로 저장됨)
        # voicebox는 WAV 출력, 나머지 프로바이더는 MP3
        _project_root = Path(__file__).parent.parent.parent.parent
        _audio_ext = "wav" if provider == "voicebox" else "mp3"
        output_path: str = str(_project_root / "storage" / "results" / "f001" / str(job_id) / f"voiceover.{_audio_ext}")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[STAGE_03][job_id={job_id}] TTS 시작 — "
            f"프로바이더: {provider}, 출력: {output_path}"
        )

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

            else:
                raise ValueError(f"알 수 없는 TTS 프로바이더: {provider}")

        except Exception as e:
            logger.error(f"[STAGE_03][job_id={job_id}] TTS 실패: {e}")
            raise RuntimeError(f"STAGE_03 TTS 생성 실패: {e}") from e

        # 파일 존재 확인
        output_file = Path(output_path)
        if not output_file.exists():
            raise RuntimeError(f"TTS 출력 파일이 생성되지 않음: {output_path}")

        # 오디오 길이 추정 (파일 크기 기반 — 실제 duration은 ffprobe로 정확히 계산 가능)
        file_size_bytes: int = output_file.stat().st_size
        file_size_kb: int = file_size_bytes // 1024
        # mp3 128kbps 기준 추정: bytes / (128 * 1024 / 8)
        audio_duration: float = round(file_size_bytes / 16000, 1)

        logger.info(
            f"[STAGE_03][job_id={job_id}] TTS 완료 — "
            f"{file_size_kb}KB, 추정 {audio_duration}초"
        )

        # SRT 자막 파일 생성 — TTS 성공 시 항상 생성
        output_dir: str = str(Path(output_path).parent)
        srt_file_path: Optional[str] = None
        srt_content: str = ""
        try:
            srt_file_path, srt_content = self._generate_srt(
                script_text, audio_duration, output_dir, job_id
            )
        except Exception as e:
            # SRT 생성 실패는 경고만 — TTS 성공 자체는 유지
            logger.warning(f"[STAGE_03][job_id={job_id}] SRT 생성 실패 (무시): {e}")

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
            f"[STAGE_03][job_id={job_id}] VoiceBox TTS 시작 - "
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

            logger.info(f"[STAGE_03][job_id={job_id}] VoiceBox 비동기 생성 대기 (gen_id={gen_id})")
            _DONE_STATUS = {"done", "completed", "success", "finished", "complete"}
            audio_bytes = None
            for attempt in range(300):  # 최대 15분
                _time.sleep(3)
                is_done = False
                try:
                    with _urllib_req.urlopen(f"{base_url}/generate/{gen_id}/status", timeout=10) as sr:
                        status_info = _json_mod.loads(sr.read())
                        if attempt == 0:
                            logger.info(f"[STAGE_03] VoiceBox status: {str(status_info)[:300]}")
                        is_done = str(status_info.get("status", "")).lower() in _DONE_STATUS
                except Exception:
                    pass
                if is_done or attempt % 10 == 9:
                    try:
                        with _urllib_req.urlopen(f"{base_url}/audio/{gen_id}", timeout=30) as ar:
                            candidate = ar.read()
                            if _is_wav(candidate):
                                audio_bytes = candidate
                    except Exception:
                        pass
                if audio_bytes:
                    logger.info(f"[STAGE_03][job_id={job_id}] VoiceBox 생성 완료 (시도 {attempt + 1}회)")
                    break
            if not audio_bytes:
                raise RuntimeError(f"VoiceBox 오디오 생성 타임아웃 15분 초과 (gen_id={gen_id})")

        from pathlib import Path as _Path
        _Path(output_path).write_bytes(audio_bytes)
        logger.info(f"[STAGE_03][job_id={job_id}] VoiceBox TTS 완료")

    def _run_coqui_tts(self, script_text: str, output_path: str, job_id: int) -> None:
        """Coqui TTS CLI subprocess 호출.

        'tts_models/ko/css10/vits' 한국어 모델을 사용한다.
        모델은 첫 실행 시 자동 다운로드된다 (약 80~100MB).

        Args:
            script_text: TTS 변환할 텍스트 (최대 5000자로 잘라 사용)
            output_path: 출력 mp3 파일 경로
            job_id: 로그 식별용

        Raises:
            RuntimeError: Coqui TTS 프로세스 비정상 종료 시
        """
        logger.info(f"[STAGE_03][job_id={job_id}] Coqui TTS subprocess 실행 시작")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "TTS",
                "--text",
                script_text[:5000],  # 스크립트 최대 5000자 사용
                "--model_name",
                "tts_models/ko/css10/vits",
                "--out_path",
                output_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,  # 600초 타임아웃 (긴 텍스트 고려)
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Coqui TTS 실패 (exit code {result.returncode}): "
                f"{result.stderr[:300]}"
            )

        logger.info(f"[STAGE_03][job_id={job_id}] Coqui TTS 완료")

    def _run_edge_tts(
        self,
        script_text: str,
        output_path: str,
        job_id: int,
        voice: str = "",
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ) -> None:
        """Microsoft Edge TTS 실행 (edge-tts 패키지 사용, 무료, API 키 불필요).

        한국어 음성: ko-KR-SunHiNeural (여성) / ko-KR-InJoonNeural (남성)
        rate 예시: "+0%"(기본), "+20%"(1.2배속), "-20%"(0.8배속)
        pitch 예시: "+0Hz"(기본), "+10Hz"(높게), "-10Hz"(낮게)

        Args:
            script_text: TTS 변환할 텍스트
            output_path: 출력 mp3 파일 경로
            job_id: 로그 식별용
            voice: Edge TTS 음성 ID (기본 ko-KR-SunHiNeural)
            rate: 발화 속도 (기본 "+0%", 범위 -100%~+100%)
            pitch: 음성 피치 (기본 "+0Hz", 범위 -100Hz~+100Hz)

        Raises:
            RuntimeError: edge-tts 미설치 또는 실행 실패 시
        """
        _voice = voice or "ko-KR-SunHiNeural"
        logger.info(
            f"[STAGE_03][job_id={job_id}] Edge TTS 실행 시작 — "
            f"voice={_voice}, rate={rate}, pitch={pitch}"
        )
        try:
            import asyncio
            import edge_tts  # type: ignore[import]
        except ImportError as e:
            raise RuntimeError(
                f"edge-tts 패키지가 설치되지 않았습니다. "
                f"pip install edge-tts 실행 후 재시도하세요. ({e})"
            ) from e

        async def _synthesize() -> None:
            communicate = edge_tts.Communicate(
                text=script_text[:5000],
                voice=_voice,
                rate=rate,
                pitch=pitch,
            )
            await communicate.save(output_path)

        try:
            asyncio.run(_synthesize())
            logger.info(f"[STAGE_03][job_id={job_id}] Edge TTS 완료")
        except Exception as e:
            raise RuntimeError(f"Edge TTS 실행 실패: {e}") from e

    def _run_gtts(self, script_text: str, output_path: str, job_id: int) -> None:
        """Google TTS 실행 (gTTS 패키지, 무료, API 키 불필요).

        pip install gtts 가 필요하다.
        한국어 고정 (lang='ko').

        Args:
            script_text: TTS 변환할 텍스트
            output_path: 출력 mp3 파일 경로
            job_id: 로그 식별용

        Raises:
            RuntimeError: gtts 미설치 또는 실행 실패 시
        """
        logger.info(f"[STAGE_03][job_id={job_id}] Google TTS 실행 시작")
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
            logger.info(f"[STAGE_03][job_id={job_id}] Google TTS 완료")
        except Exception as e:
            raise RuntimeError(f"Google TTS 실행 실패: {e}") from e

    def _run_elevenlabs_tts(
        self, script_text: str, output_path: str, job_id: int, voice: str = ""
    ) -> None:
        """ElevenLabs REST API 호출 TTS.

        ELEVENLABS_API_KEY 환경변수가 필요하다.
        기본 음성 ID (Rachel: 21m00Tcm4TlvDq8ikWAM)를 사용한다.

        Args:
            script_text: TTS 변환할 텍스트
            output_path: 출력 mp3 파일 경로
            job_id: 로그 식별용
            voice: ElevenLabs 음성 ID (기본 Rachel)

        Raises:
            RuntimeError: API 키 미설정 또는 API 호출 실패 시
        """
        import httpx

        api_key: str = os.getenv("ELEVENLABS_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 ELEVENLABS_API_KEY=... 추가 후 재시도하세요."
            )

        # 음성 ID — 미지정 시 Rachel 기본값
        voice_id = voice or "21m00Tcm4TlvDq8ikWAM"
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        logger.info(f"[STAGE_03][job_id={job_id}] ElevenLabs TTS API 호출 시작 — voice={voice_id}")
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
                        "text": script_text[:4500],  # ElevenLabs 5000자 제한
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

            logger.info(f"[STAGE_03][job_id={job_id}] ElevenLabs TTS 완료")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"ElevenLabs API 오류: HTTP {e.response.status_code}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"ElevenLabs TTS 호출 실패: {e}") from e

    def _run_openai_tts(
        self, script_text: str, output_path: str, job_id: int, voice: str = ""
    ) -> None:
        """OpenAI TTS API 호출.

        OPENAI_API_KEY 환경변수가 필요하다.
        지원 음성: alloy, echo, fable, onyx, nova, shimmer

        Args:
            script_text: TTS 변환할 텍스트
            output_path: 출력 mp3 파일 경로
            job_id: 로그 식별용
            voice: OpenAI 음성 이름 (기본 alloy)

        Raises:
            RuntimeError: API 키 미설정 또는 API 호출 실패 시
        """
        import httpx

        api_key: str = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                ".env 파일에 OPENAI_API_KEY=... 추가 후 재시도하세요."
            )

        _voice = voice or "alloy"
        logger.info(f"[STAGE_03][job_id={job_id}] OpenAI TTS API 호출 시작 — voice={_voice}")
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
                        "input": script_text[:4096],  # OpenAI TTS 4096자 제한
                        "voice": _voice,
                        "response_format": "mp3",
                    },
                )
                resp.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(resp.content)

            logger.info(f"[STAGE_03][job_id={job_id}] OpenAI TTS 완료")

        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"OpenAI TTS API 오류: HTTP {e.response.status_code}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"OpenAI TTS 호출 실패: {e}") from e

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

        Args:
            script_text: TTS에 사용한 전체 스크립트 텍스트
            audio_duration: 실제 오디오 길이(초) — 스케일 보정에 사용
            output_dir: SRT 파일을 저장할 디렉토리
            job_id: 로그 식별용

        Returns:
            (srt_file_path, srt_content) 튜플
        """
        # 문장 분할 — 한국어/영어 구두점 기준 (. ! ? 。 ！ ？)
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
            f"[STAGE_03][job_id={job_id}] SRT 생성 완료 — "
            f"{len(sentences)}개 자막 항목, {srt_path}"
        )
        return srt_path, srt_content
