# 목적: F006 STAGE_05 - FFmpeg 기반 영상 편집 및 Whisper 자막 생성 스테이지.
# STAGE_03(TTS 오디오) + STAGE_04(클립 목록)를 합쳐 최종 MP4를 생성한다.
# imageio-ffmpeg 번들 FFmpeg 사용 - 시스템 FFmpeg 설치 불필요.
# 출력 경로: storage/results/f006/{job_id}/final/

import sys
import json
import logging
import subprocess
import tempfile
import os
import shutil

# imageio-ffmpeg 번들 FFmpeg 경로 - 시스템 PATH에 ffmpeg 없어도 동작
import imageio_ffmpeg as _imageio_ffmpeg

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage05Edit(BaseStage, BasePipeline):
    """STAGE_05 - FFmpeg 영상 편집 + Whisper 자막 생성 스테이지.

    처리 흐름:
      1. stage05_auto_skipped=True이면 즉시 SKIPPED (STAGE_04 script_only 체인)
      2. 클립(PNG/MP4)과 오디오(mp3)가 모두 없으면 SKIPPED
      3. FFmpeg로 클립을 정지 영상으로 concat + 오디오 합성
      4. Whisper로 오디오 -> SRT 자막 생성 (openai-whisper 패키지 필요)
      5. 최종 output.mp4 및 subtitles.srt 저장 (f006 경로 사용)
    """

    STAGE_ID: str = "STAGE_05_EDIT"
    STAGE_ORDER: int = 5

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE05", "name": "STAGE_05_EDIT"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_05 실행 - FFmpeg 영상 편집 + Whisper 자막.

        Args:
            job_id: content_jobs.id
            input_data: {
                stage05_auto_skipped (bool): STAGE_04 script_only 체인에 의한 자동 skip
                clips (list): [{slide_no, file_path, duration_sec, narration, type}]
                audio_file_path (str or None): STAGE_03 TTS 오디오 파일 경로
            }

        Returns:
            SKIPPED 시: {stage_id, status="SKIPPED", skip_reason, generated_at}
            COMPLETED 시: {stage_id, status="COMPLETED", video_file_path,
                           subtitle_file_path, duration_sec, resolution,
                           file_size_mb, has_subtitles, generated_at}
        """
        # auto_skipped: STAGE_04 script_only 체인에 의한 자동 SKIP
        if input_data.get("stage05_auto_skipped", False):
            logger.info(
                f"[F006][STAGE_05][job_id={job_id}] STAGE_04 script_only로 인해 자동 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "STAGE_04 script_only skip으로 인해 STAGE_05 자동 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        clips: list[dict] = input_data.get("clips", [])
        audio_file_path: Optional[str] = input_data.get("audio_file_path")

        # 클립도 없고 오디오도 없으면 SKIP
        if not clips and not audio_file_path:
            logger.info(
                f"[F006][STAGE_05][job_id={job_id}] 클립과 오디오 모두 없어 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "클립과 오디오 파일이 없어 편집 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # 출력 디렉토리 - f006 경로 사용 (절대 경로, ERR-007 방지)
        _project_root = Path(__file__).parent.parent.parent.parent
        output_dir = _project_root / "storage" / "results" / "f006" / str(job_id) / "final"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_video: str = str(output_dir / "output.mp4")
        output_srt: str = str(output_dir / "subtitles.srt")

        logger.info(
            f"[F006][STAGE_05][job_id={job_id}] FFmpeg 편집 시작 - "
            f"클립: {len(clips)}개, 오디오: {'있음' if audio_file_path else '없음'}"
        )

        # FFmpeg concat 실행
        try:
            self._run_ffmpeg_concat(clips, audio_file_path, output_video, job_id)
        except Exception as e:
            logger.error(f"[F006][STAGE_05][job_id={job_id}] FFmpeg 실패: {e}")
            raise RuntimeError(f"STAGE_05 FFmpeg 편집 실패: {e}") from e

        # 자막 생성 - subtitle_enabled=False이면 건너뜀
        subtitle_enabled: bool = bool(input_data.get("subtitle_enabled", True))
        # stage03에서 SubMaker가 생성한 SRT 경로 (WordBoundary 기반, 정확한 타임코드)
        srt_from_stage03: Optional[str] = input_data.get("srt_file_path")
        has_subtitles: bool = False

        if subtitle_enabled:
            if srt_from_stage03 and Path(srt_from_stage03).exists():
                # SubMaker SRT 직접 복사 — Whisper 건너뜀 (이미 정확한 타임코드)
                shutil.copy2(srt_from_stage03, output_srt)
                has_subtitles = True
                logger.info(
                    f"[F006][STAGE_05][job_id={job_id}] SubMaker SRT 복사 사용: "
                    f"{srt_from_stage03}"
                )
            elif audio_file_path and Path(audio_file_path).exists():
                # Whisper 폴백 (SubMaker SRT 없는 경우 — edge_tts 외 프로바이더)
                has_subtitles = self._run_whisper_transcribe(
                    audio_file_path, output_srt, job_id
                )
        else:
            logger.info(f"[F006][STAGE_05][job_id={job_id}] 자막 비활성화 - 건너뜀")

        # 자막 번인 — SRT 파일이 준비된 경우 FFmpeg subtitles 필터로 영상에 번인
        if has_subtitles and Path(output_srt).exists():
            output_video_burned: str = str(output_dir / "output_burned.mp4")
            burned_ok: bool = self._burn_subtitles(
                output_video, output_srt, output_video_burned, job_id
            )
            if burned_ok and Path(output_video_burned).exists():
                output_video = output_video_burned

        # 결과 메타데이터 수집
        output_file = Path(output_video)
        if output_file.exists():
            file_size_mb: float = round(output_file.stat().st_size / 1024 / 1024, 2)
        else:
            file_size_mb = 0.0

        duration_sec: float = self._get_video_duration(output_video)

        logger.info(
            f"[F006][STAGE_05][job_id={job_id}] 편집 완료 - "
            f"{file_size_mb}MB, {duration_sec}초, 자막: {has_subtitles}"
        )

        return {
            "stage_id": "STAGE_05_EDIT",
            "status": "COMPLETED",
            "video_file_path": output_video,
            "subtitle_file_path": output_srt if has_subtitles else None,
            "duration_sec": duration_sec,
            "resolution": "1280x720",
            "file_size_mb": file_size_mb,
            "has_subtitles": has_subtitles,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - COMPLETED 시 video_file_path 파일 존재 확인."""
        if output.get("status") == "SKIPPED":
            return ValidationResult(is_valid=True)

        video_path = output.get("video_file_path")
        if not video_path:
            return ValidationResult(
                is_valid=False,
                rejection_reason="STAGE_05 video_file_path 없음 - FFmpeg 편집 실패. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        if not Path(video_path).exists():
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"STAGE_05 출력 파일 없음: {video_path}. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # FFmpeg 편집 헬퍼
    # ------------------------------------------------------------------

    def _distribute_duration_by_narration(
        self,
        clips: list[dict],
        audio_duration: float,
    ) -> dict[str, float]:
        """각 클립의 narration 글자 수에 비례해 표시 시간 배분.

        2-pass 알고리즘:
          1차: 비례 배분 계산
          2차: floor 3.0초 미달 클립을 3.0초로 올리고, 남은 시간을 나머지 클립에 재배분.
        전체 합 = audio_duration 보장.
        """
        min_dur = 3.0
        n = len(clips)

        narration_lens = [
            max(10, len(c.get("narration", "") or ""))
            for c in clips
        ]
        total_chars = sum(narration_lens)

        raw = [audio_duration * (n_len / total_chars) for n_len in narration_lens]

        floor_indices = [i for i, d in enumerate(raw) if d < min_dur]
        non_floor_indices = [i for i, d in enumerate(raw) if d >= min_dur]

        floor_total = len(floor_indices) * min_dur

        if floor_total >= audio_duration:
            per_clip = audio_duration / n
            logger.warning(
                f"[F006][STAGE_05] min {min_dur}s 보장으로 audio_duration({audio_duration:.1f}s) "
                f"초과 - 균등 배분 폴백 ({per_clip:.1f}s/클립)"
            )
            return {c["file_path"]: per_clip for c in clips}

        remaining = audio_duration - floor_total
        non_floor_chars = sum(narration_lens[i] for i in non_floor_indices)

        result: dict[str, float] = {}
        for i, clip in enumerate(clips):
            if i in floor_indices:
                result[clip["file_path"]] = min_dur
            else:
                result[clip["file_path"]] = remaining * (narration_lens[i] / non_floor_chars)

        if floor_indices:
            logger.info(
                f"[F006][STAGE_05] min {min_dur}s 클램핑 발동: {len(floor_indices)}개 클립, "
                f"나머지 {len(non_floor_indices)}개에 {remaining:.1f}s 재배분"
            )

        return result

    def _get_audio_duration_sec(self, audio_path: str) -> float:
        """오디오 파일 실제 재생 길이(초)를 반환.

        moviepy AudioFileClip으로 측정하며 실패 시 ffprobe로 폴백.
        둘 다 실패하면 0.0 반환.
        """
        if not Path(audio_path).exists():
            return 0.0
        try:
            from moviepy import AudioFileClip
            ac = AudioFileClip(audio_path)
            dur = float(ac.duration)
            ac.close()
            return dur
        except Exception as e:
            logger.warning(f"[F006][STAGE_05] moviepy 오디오 길이 측정 실패: {e}")
        try:
            ffmpeg_exe: str = _imageio_ffmpeg.get_ffmpeg_exe()
            ffprobe_exe: str = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe").replace(
                "ffmpeg", "ffprobe"
            )
            res = subprocess.run(
                [
                    ffprobe_exe, "-v", "quiet",
                    "-print_format", "json",
                    "-show_format", audio_path,
                ],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
            data = json.loads(res.stdout)
            dur = float(data.get("format", {}).get("duration", 0))
            return dur
        except Exception as e:
            logger.warning(f"[F006][STAGE_05] ffprobe 오디오 길이 측정 실패: {e}")
        return 0.0

    def _run_ffmpeg_concat(
        self,
        clips: list[dict],
        audio_file_path: Optional[str],
        output_video: str,
        job_id: int,
    ) -> None:
        """FFmpeg로 클립(PNG/MP4)을 concat하고 오디오를 합성."""
        if not clips:
            self._generate_black_video_with_audio(audio_file_path, output_video, job_id)
            return

        _ffmpeg_exe: str = _imageio_ffmpeg.get_ffmpeg_exe()

        valid_clips: list[dict] = [
            c for c in clips if Path(c.get("file_path", "")).exists()
        ]
        clip_durations: dict[str, float] = {}

        has_audio: bool = bool(audio_file_path and Path(audio_file_path).exists())
        audio_duration: float = 0.0

        if has_audio:
            audio_duration = self._get_audio_duration_sec(audio_file_path)

        if has_audio and audio_duration > 0 and valid_clips:
            has_narration = any(c.get("narration") for c in valid_clips)
            if has_narration:
                clip_durations = self._distribute_duration_by_narration(
                    valid_clips, audio_duration
                )
                logger.info(
                    f"[F006][STAGE_05][job_id={job_id}] narration 비례 배분 적용 - "
                    f"오디오 {audio_duration:.1f}초 / {len(valid_clips)}클립"
                )
            else:
                per_clip_sec: float = audio_duration / len(valid_clips)
                for c in valid_clips:
                    clip_durations[c["file_path"]] = per_clip_sec
                logger.info(
                    f"[F006][STAGE_05][job_id={job_id}] 오디오 기준 균등 배분 - "
                    f"오디오 {audio_duration:.1f}초 / {len(valid_clips)}클립 "
                    f"= {per_clip_sec:.1f}초/클립"
                )
        else:
            for c in clips:
                clip_durations[c["file_path"]] = float(c.get("duration_sec", 5))

        input_args: list[str] = []
        n_clips: int = 0
        for clip in clips:
            file_path: str = clip.get("file_path", "")

            if not Path(file_path).exists():
                logger.warning(
                    f"[F006][STAGE_05][job_id={job_id}] 클립 파일 없음 건너뜀: {file_path}"
                )
                continue

            duration_sec: float = clip_durations.get(file_path, float(clip.get("duration_sec", 5)))

            if file_path.lower().endswith(".png"):
                input_args.extend([
                    "-loop", "1",
                    "-t", f"{duration_sec:.3f}",
                    "-i", file_path,
                ])
            else:
                input_args.extend(["-i", file_path])
            n_clips += 1

        if n_clips == 0:
            self._generate_black_video_with_audio(audio_file_path, output_video, job_id)
            return

        filter_inputs = "".join(f"[{i}:v]" for i in range(n_clips))
        filter_complex = f"{filter_inputs}concat=n={n_clips}:v=1:a=0[outv]"

        ffmpeg_cmd: list[str] = [_ffmpeg_exe, "-y"]
        ffmpeg_cmd.extend(input_args)

        if has_audio:
            ffmpeg_cmd.extend(["-i", audio_file_path])
            audio_idx = n_clips
            ffmpeg_cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", f"{audio_idx}:a",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-s", "1280x720",
                "-r", "24",
                output_video,
            ])
        else:
            ffmpeg_cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-s", "1280x720",
                "-r", "24",
                output_video,
            ])

        logger.info(
            f"[F006][STAGE_05][job_id={job_id}] FFmpeg 실행 - "
            f"클립 {n_clips}개 concat"
        )

        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg concat 실패 (exit code {result.returncode}): "
                f"{result.stderr[:300]}"
            )

        logger.info(f"[F006][STAGE_05][job_id={job_id}] FFmpeg concat 완료: {output_video}")

    def _generate_black_video_with_audio(
        self,
        audio_file_path: Optional[str],
        output_video: str,
        job_id: int,
    ) -> None:
        """클립 없을 때 검정 배경 영상 + 오디오로 MP4 생성."""
        _ffmpeg_exe: str = _imageio_ffmpeg.get_ffmpeg_exe()
        if audio_file_path and Path(audio_file_path).exists():
            cmd = [
                _ffmpeg_exe, "-y",
                "-f", "lavfi",
                "-i", "color=c=black:size=1280x720:rate=24",
                "-i", audio_file_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_video,
            ]
        else:
            cmd = [
                _ffmpeg_exe, "-y",
                "-f", "lavfi",
                "-i", "color=c=black:size=1280x720:rate=24:duration=5",
                "-c:v", "libx264",
                output_video,
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"검정 영상 생성 실패: {result.stderr[:200]}"
            )
        logger.info(f"[F006][STAGE_05][job_id={job_id}] 검정 배경 영상 생성 완료")

    # ------------------------------------------------------------------
    # 자막 번인 헬퍼
    # ------------------------------------------------------------------

    def _burn_subtitles(
        self,
        video_path: str,
        srt_path: str,
        output_path: str,
        job_id: int,
    ) -> bool:
        """FFmpeg subtitles 필터로 자막을 영상에 번인. 실패 시 False 반환.

        Windows 경로 이슈: 백슬래시를 슬래시로, 드라이브 콜론을 이스케이프.
        번인 실패는 치명적이지 않음 — 경고 후 원본 영상 유지.
        """
        _ffmpeg_exe: str = _imageio_ffmpeg.get_ffmpeg_exe()

        # Windows 경로 → FFmpeg subtitles 필터 형식 변환
        # E:\path\file.srt → E\:/path/file.srt
        srt_for_filter: str = (
            srt_path.replace("\\", "/").replace(":/", "\\:/")
        )

        # 자막 스타일: 흰색, 28pt, 외곽선+배경 - 한국어 가독성 최적화
        vf_filter: str = (
            f"subtitles='{srt_for_filter}':"
            "force_style='FontSize=28,PrimaryColour=&HFFFFFF,"
            "BorderStyle=3,Outline=2,Shadow=1,MarginV=40'"
        )

        cmd: list[str] = [
            _ffmpeg_exe, "-y",
            "-i", video_path,
            "-vf", vf_filter,
            "-c:a", "copy",
            output_path,
        ]

        logger.info(f"[F006][STAGE_05][job_id={job_id}] 자막 번인 시작: {srt_path}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
            )
            if result.returncode != 0:
                logger.warning(
                    f"[F006][STAGE_05][job_id={job_id}] 자막 번인 실패 (원본 영상 유지): "
                    f"{result.stderr[:300]}"
                )
                return False
            logger.info(
                f"[F006][STAGE_05][job_id={job_id}] 자막 번인 완료: {output_path}"
            )
            return True
        except subprocess.TimeoutExpired:
            logger.warning(
                f"[F006][STAGE_05][job_id={job_id}] 자막 번인 타임아웃 (600초) - 원본 영상 유지"
            )
            return False
        except Exception as e:
            logger.warning(
                f"[F006][STAGE_05][job_id={job_id}] 자막 번인 오류 (원본 영상 유지): {e}"
            )
            return False

    # ------------------------------------------------------------------
    # Whisper 자막 헬퍼
    # ------------------------------------------------------------------

    def _run_whisper_transcribe(
        self,
        audio_file_path: str,
        output_srt: str,
        job_id: int,
    ) -> bool:
        """Whisper로 오디오를 SRT 자막으로 변환. openai-whisper 패키지 필요."""
        try:
            import whisper  # type: ignore[import]
        except ImportError:
            logger.warning(
                f"[F006][STAGE_05][job_id={job_id}] openai-whisper 미설치 - 자막 생성 건너뜀. "
                f"pip install openai-whisper 실행 후 재시도 가능"
            )
            return False

        try:
            logger.info(
                f"[F006][STAGE_05][job_id={job_id}] Whisper 자막 생성 시작: {audio_file_path}"
            )
            model = whisper.load_model("medium")
            result = model.transcribe(audio_file_path, language="ko")
            segments: list[dict] = result.get("segments", [])

            if not segments:
                logger.warning(
                    f"[F006][STAGE_05][job_id={job_id}] Whisper 세그먼트 없음 - 자막 없음"
                )
                return False

            self._write_srt(segments, output_srt)
            logger.info(
                f"[F006][STAGE_05][job_id={job_id}] Whisper 자막 생성 완료: {output_srt}"
            )
            return True

        except Exception as e:
            logger.warning(
                f"[F006][STAGE_05][job_id={job_id}] Whisper 실패 - 자막 없이 계속: {e}"
            )
            return False

    def _write_srt(self, segments: list[dict], output_path: str) -> None:
        """Whisper 세그먼트 목록을 SRT 파일로 저장."""
        srt_lines: list[str] = []
        for i, seg in enumerate(segments, start=1):
            start: float = float(seg.get("start", 0))
            end: float = float(seg.get("end", start + 1))
            text: str = seg.get("text", "").strip()

            srt_lines.append(str(i))
            srt_lines.append(
                f"{self._sec_to_srt_time(start)} --> {self._sec_to_srt_time(end)}"
            )
            srt_lines.append(text)
            srt_lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))

    @staticmethod
    def _sec_to_srt_time(sec: float) -> str:
        """초(float)를 SRT 타임코드 형식 문자열로 변환. 예: 65.5 -> '00:01:05,500'"""
        hours: int = int(sec // 3600)
        minutes: int = int((sec % 3600) // 60)
        seconds: int = int(sec % 60)
        millis: int = int((sec - int(sec)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    # ------------------------------------------------------------------
    # 영상 정보 조회 헬퍼
    # ------------------------------------------------------------------

    def _get_video_duration(self, video_path: str) -> float:
        """moviepy로 영상 길이(초)를 조회. 실패 시 0 반환."""
        if not Path(video_path).exists():
            return 0.0
        clip = None
        try:
            from moviepy import VideoFileClip  # type: ignore[import]
            clip = VideoFileClip(video_path)
            return round(float(clip.duration), 1)
        except Exception as e:
            logger.warning(f"moviepy duration 조회 실패: {e}")
            return 0.0
        finally:
            if clip is not None:
                clip.close()
