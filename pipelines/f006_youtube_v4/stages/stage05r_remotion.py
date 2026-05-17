# 목적: F006 STAGE_05R - Remotion 기반 동영상 렌더링 스테이지.
# FFmpeg concat 대신 Remotion(React)으로 자연스러운 전환/애니메이션 MP4를 생성한다.
# orchestrator에서 use_remotion=True 파라미터 수신 시 Stage05Edit 대신 이 클래스가 선택된다.
# STAGE_ID는 DB 호환성을 위해 Stage05Edit와 동일하게 "STAGE_05_EDIT"를 사용한다.

import sys
import json
import logging
import subprocess
import os
import re

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# imageio-ffmpeg 번들 FFmpeg 경로 - ffprobe 폴백용
import imageio_ffmpeg as _imageio_ffmpeg

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# 프로젝트 루트 경로 - 이 파일 기준 4단계 상위 (stages -> f006_youtube_v4 -> pipelines -> Dash)
_PROJECT_ROOT: Path = Path(__file__).parent.parent.parent.parent

# Remotion 프로젝트 디렉토리 경로 (절대 경로)
_REMOTION_DIR: Path = Path(__file__).parent.parent / "remotion"


class Stage05rRemotion(BaseStage, BasePipeline):
    """STAGE_05R - Remotion 기반 동영상 렌더링 스테이지.

    처리 흐름:
      1. stage05_auto_skipped=True이면 즉시 SKIPPED (STAGE_04 script_only 체인)
      2. 클립(PNG)과 오디오(mp3)가 모두 없으면 SKIPPED
      3. 오디오 길이 측정 -> narration 비례 배분으로 슬라이드 duration_sec 계산
      4. SRT 파일 파싱 -> srt_entries 구성
      5. remotion_props.json 파일 생성
      6. npm install (node_modules 없는 경우에만)
      7. remotion render 실행 -> output_remotion.mp4 생성
      8. remotion still 실행 -> thumbnail_remotion.png 생성

    DB 호환성:
      STAGE_ID = "STAGE_05_EDIT" - orchestrator stages 테이블 레코드와 일치
    """

    # DB 호환성: Stage05Edit와 동일한 STAGE_ID 사용
    STAGE_ID: str = "STAGE_05_EDIT"
    STAGE_ORDER: int = 5

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE05R", "name": "STAGE_05R_REMOTION"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - clips가 있거나 audio_file_path가 있으면 유효."""
        # auto_skipped 체인은 execute에서 처리
        if data.get("stage05_auto_skipped", False):
            return ValidationResult(is_valid=True)

        clips = data.get("clips", [])
        audio_file_path = data.get("audio_file_path")

        # 클립이나 오디오 중 하나라도 있으면 유효 (Stage05Edit와 동일 기준)
        if clips or audio_file_path:
            return ValidationResult(is_valid=True)

        # 둘 다 없으면 SKIPPED 처리를 execute에서 할 것이므로 유효로 통과
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_05R 실행 - Remotion 동영상 렌더링.

        Args:
            job_id: content_jobs.id
            input_data: {
                stage05_auto_skipped (bool): STAGE_04 script_only 체인에 의한 자동 skip
                clips (list): [{slide_no, file_path, duration_sec, narration, type}]
                audio_file_path (str or None): STAGE_03 TTS 오디오 파일 경로
                srt_file_path (str or None): STAGE_03 SRT 자막 파일 경로
                use_remotion (bool): True이면 Remotion 경로 사용
                remotion_theme (str): 테마 이름 (dark_blue / warm_gray / clean_white)
                remotion_transition (str): 전환 모드 (auto / fade_only / slide_only)
                remotion_concurrency (int): Remotion 렌더링 동시성 (기본 4)
            }

        Returns:
            SKIPPED 시: {stage_id, status="SKIPPED", skip_reason, generated_at}
            COMPLETED 시: {stage_id, status="COMPLETED", video_file_path,
                           subtitle_file_path, duration_sec, resolution,
                           file_size_mb, has_subtitles, generated_at, renderer="remotion"}
        """
        logger.info(f"[F006][STAGE_05R][job_id={job_id}] Remotion 렌더링 시작")

        # ----------------------------------------------------------------
        # 1. auto_skipped 체크 - STAGE_04 script_only 체인
        # ----------------------------------------------------------------
        if input_data.get("stage05_auto_skipped", False):
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] STAGE_04 script_only로 인해 자동 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "STAGE_04 script_only skip으로 인해 STAGE_05R 자동 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        clips: list[dict] = input_data.get("clips", [])
        audio_file_path: Optional[str] = input_data.get("audio_file_path")

        # ----------------------------------------------------------------
        # 2. 클립/오디오 모두 없으면 SKIPPED
        # ----------------------------------------------------------------
        if not clips and not audio_file_path:
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] 클립과 오디오 모두 없어 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "클립과 오디오 파일이 없어 Remotion 렌더링 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Remotion 파라미터 추출
        theme: str = input_data.get("remotion_theme", "dark_blue")
        transition_mode: str = input_data.get("remotion_transition", "auto")
        concurrency: int = int(input_data.get("remotion_concurrency", 4))
        srt_file_path: Optional[str] = input_data.get("srt_file_path")

        # ----------------------------------------------------------------
        # 3. 오디오 길이 측정 및 슬라이드 duration_sec 계산
        # ----------------------------------------------------------------
        audio_duration: float = 0.0
        if audio_file_path and Path(audio_file_path).exists():
            audio_duration = self._get_audio_duration_sec(audio_file_path)
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] 오디오 길이: {audio_duration:.1f}초"
            )

        # 유효한 클립만 필터링 (파일 존재 확인)
        valid_clips: list[dict] = [
            c for c in clips if Path(c.get("file_path", "")).exists()
        ]
        if not valid_clips and not audio_file_path:
            logger.warning(
                f"[F006][STAGE_05R][job_id={job_id}] 유효한 클립 없음 - SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "유효한 클립 파일이 없어 Remotion 렌더링 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # narration 비례 배분으로 슬라이드별 duration_sec 결정
        clip_durations: dict[str, float] = {}
        if audio_duration > 0 and valid_clips:
            has_narration = any(c.get("narration") for c in valid_clips)
            if has_narration:
                clip_durations = self._distribute_duration_by_narration(
                    valid_clips, audio_duration
                )
                logger.info(
                    f"[F006][STAGE_05R][job_id={job_id}] narration 비례 배분 적용 - "
                    f"오디오 {audio_duration:.1f}초 / {len(valid_clips)}클립"
                )
            else:
                per_clip_sec: float = audio_duration / len(valid_clips)
                for c in valid_clips:
                    clip_durations[c["file_path"]] = per_clip_sec
                logger.info(
                    f"[F006][STAGE_05R][job_id={job_id}] 균등 배분 - "
                    f"{per_clip_sec:.1f}초/클립"
                )
        else:
            # 오디오 없거나 duration 0인 경우 클립 자체 duration_sec 사용
            for c in valid_clips:
                clip_durations[c["file_path"]] = float(c.get("duration_sec", 5))

        # ----------------------------------------------------------------
        # 4. SRT 파싱 - srt_file_path가 있으면 파싱, 없으면 빈 목록
        # ----------------------------------------------------------------
        srt_entries: list[dict] = []
        has_subtitles: bool = False
        subtitle_file_path: Optional[str] = None
        if srt_file_path and Path(srt_file_path).exists():
            srt_entries = self._parse_srt(srt_file_path)
            if srt_entries:
                has_subtitles = True
                subtitle_file_path = srt_file_path
                logger.info(
                    f"[F006][STAGE_05R][job_id={job_id}] SRT 파싱 완료 - "
                    f"{len(srt_entries)}개 항목"
                )

        # ----------------------------------------------------------------
        # 5. remotion_props.json 구성 및 저장
        # ----------------------------------------------------------------
        # 슬라이드 데이터 구성 (type 필드 정규화 포함)
        slides_data: list[dict] = []
        for clip in valid_clips:
            raw_type: str = clip.get("type", "content")
            # 허용 타입 목록 - 벗어나면 "content"로 폴백
            allowed_types = {"title", "content", "summary", "quote"}
            slide_type: str = raw_type if raw_type in allowed_types else "content"
            file_path_normalized: str = clip["file_path"].replace("\\", "/")
            duration_sec: float = clip_durations.get(clip["file_path"], 5.0)
            slides_data.append({
                "slide_no": clip.get("slide_no", len(slides_data) + 1),
                "type": slide_type,
                "file_path": file_path_normalized,
                "duration_sec": round(duration_sec, 3),
            })

        # 오디오 경로 정규화
        audio_path_normalized: str = ""
        if audio_file_path:
            audio_path_normalized = audio_file_path.replace("\\", "/")

        remotion_props: dict = {
            "slides": slides_data,
            "audio_path": audio_path_normalized,
            "srt_entries": srt_entries,
            "theme": theme,
            "transition_mode": transition_mode,
        }

        # remotion_props.json 저장 경로
        props_dir: Path = (
            _PROJECT_ROOT / "storage" / "results" / "f006" / str(job_id)
        )
        props_dir.mkdir(parents=True, exist_ok=True)
        props_json_path: Path = props_dir / "remotion_props.json"
        with open(props_json_path, "w", encoding="utf-8") as f:
            json.dump(remotion_props, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[F006][STAGE_05R][job_id={job_id}] remotion_props.json 저장: {props_json_path}"
        )

        # ----------------------------------------------------------------
        # 6. npm install (node_modules 없는 경우에만)
        # ----------------------------------------------------------------
        if not (_REMOTION_DIR / "node_modules").exists():
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] node_modules 없음 - npm install 실행"
            )
            try:
                npm_result = subprocess.run(
                    ["cmd", "/c", "npm", "install"],
                    cwd=str(_REMOTION_DIR),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=300,
                )
                if npm_result.returncode != 0:
                    logger.error(
                        f"[F006][STAGE_05R][job_id={job_id}] npm install 실패: "
                        f"{npm_result.stderr[:300]}"
                    )
                    raise RuntimeError(
                        f"npm install 실패 (exit code {npm_result.returncode}): "
                        f"{npm_result.stderr[:200]}"
                    )
                logger.info(
                    f"[F006][STAGE_05R][job_id={job_id}] npm install 완료"
                )
            except subprocess.TimeoutExpired as e:
                logger.error(
                    f"[F006][STAGE_05R][job_id={job_id}] npm install 타임아웃 (300초)"
                )
                raise RuntimeError("npm install 타임아웃 (300초)") from e
        else:
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] node_modules 존재 - npm install 생략"
            )

        # ----------------------------------------------------------------
        # 7. remotion render 실행
        # ----------------------------------------------------------------
        output_final_dir: Path = (
            _PROJECT_ROOT / "storage" / "results" / "f006" / str(job_id) / "final"
        )
        output_final_dir.mkdir(parents=True, exist_ok=True)
        output_video_path: str = str(output_final_dir / "output_remotion.mp4")

        cmd_render: list[str] = [
            "cmd", "/c", "npx", "remotion", "render",
            "--props", str(props_json_path),
            f"--concurrency={concurrency}",
            "src/Root.tsx",
            "F006Video",
            output_video_path,
        ]

        logger.info(
            f"[F006][STAGE_05R][job_id={job_id}] remotion render 시작 - "
            f"출력: {output_video_path}"
        )
        try:
            render_result = subprocess.run(
                cmd_render,
                cwd=str(_REMOTION_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
            )
            if render_result.returncode != 0:
                logger.error(
                    f"[F006][STAGE_05R][job_id={job_id}] remotion render 실패: "
                    f"{render_result.stderr[:400]}"
                )
                raise RuntimeError(
                    f"remotion render 실패 (exit code {render_result.returncode}): "
                    f"{render_result.stderr[:300]}"
                )
            logger.info(
                f"[F006][STAGE_05R][job_id={job_id}] remotion render 완료: {output_video_path}"
            )
        except subprocess.TimeoutExpired as e:
            logger.error(
                f"[F006][STAGE_05R][job_id={job_id}] remotion render 타임아웃 (900초)"
            )
            raise RuntimeError("remotion render 타임아웃 (900초)") from e

        # ----------------------------------------------------------------
        # 8. remotion still 실행 - 썸네일 생성
        # ----------------------------------------------------------------
        thumbnails_dir: Path = (
            _PROJECT_ROOT / "storage" / "results" / "f006" / str(job_id) / "thumbnails"
        )
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_path: str = str(thumbnails_dir / "thumbnail_remotion.png")

        cmd_still: list[str] = [
            "cmd", "/c", "npx", "remotion", "still",
            "--props", str(props_json_path),
            "--frame=0",
            "src/Root.tsx",
            "F006Video",
            thumbnail_path,
        ]

        logger.info(
            f"[F006][STAGE_05R][job_id={job_id}] remotion still (썸네일) 시작"
        )
        try:
            still_result = subprocess.run(
                cmd_still,
                cwd=str(_REMOTION_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if still_result.returncode != 0:
                # 썸네일 실패는 치명적이지 않음 - 경고 후 계속 진행
                logger.warning(
                    f"[F006][STAGE_05R][job_id={job_id}] remotion still 실패 (무시): "
                    f"{still_result.stderr[:200]}"
                )
            else:
                logger.info(
                    f"[F006][STAGE_05R][job_id={job_id}] remotion still 완료: {thumbnail_path}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"[F006][STAGE_05R][job_id={job_id}] remotion still 타임아웃 (180초) - 무시"
            )

        # ----------------------------------------------------------------
        # 9. 결과 메타데이터 수집
        # ----------------------------------------------------------------
        output_file = Path(output_video_path)
        file_size_mb: float = 0.0
        if output_file.exists():
            file_size_mb = round(output_file.stat().st_size / 1024 / 1024, 2)

        # 영상 길이는 슬라이드 duration_sec 합계로 추정 (render 완료 후 파일에서 읽기 어려움)
        duration_sec: float = round(sum(s["duration_sec"] for s in slides_data), 1)

        logger.info(
            f"[F006][STAGE_05R][job_id={job_id}] 렌더링 완료 - "
            f"{file_size_mb}MB, {duration_sec}초, 자막: {has_subtitles}"
        )

        return {
            "stage_id": "STAGE_05_EDIT",
            "status": "COMPLETED",
            "video_file_path": output_video_path,
            "subtitle_file_path": subtitle_file_path,
            "duration_sec": duration_sec,
            "resolution": "1280x720",
            "file_size_mb": file_size_mb,
            "has_subtitles": has_subtitles,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "renderer": "remotion",
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - COMPLETED 시 video_file_path 파일 존재 확인."""
        if output.get("status") == "SKIPPED":
            return ValidationResult(is_valid=True)

        video_path = output.get("video_file_path")
        if not video_path:
            return ValidationResult(
                is_valid=False,
                rejection_reason="STAGE_05R video_file_path 없음 - Remotion 렌더링 실패. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        if not Path(video_path).exists():
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"STAGE_05R 출력 파일 없음: {video_path}. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 오디오/자막 헬퍼 메서드
    # ------------------------------------------------------------------

    def _get_audio_duration_sec(self, audio_path: str) -> float:
        """오디오 파일 실제 재생 길이(초)를 반환.

        moviepy AudioFileClip으로 측정하며 실패 시 ffprobe로 폴백.
        둘 다 실패하면 0.0 반환.
        (Stage05Edit._get_audio_duration_sec와 동일 구현)
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
            logger.warning(f"[F006][STAGE_05R] moviepy 오디오 길이 측정 실패: {e}")
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
            logger.warning(f"[F006][STAGE_05R] ffprobe 오디오 길이 측정 실패: {e}")
        return 0.0

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
        (Stage05Edit._distribute_duration_by_narration과 동일 구현)
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
                f"[F006][STAGE_05R] min {min_dur}s 보장으로 audio_duration({audio_duration:.1f}s) "
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
                f"[F006][STAGE_05R] min {min_dur}s 클램핑 발동: {len(floor_indices)}개 클립, "
                f"나머지 {len(non_floor_indices)}개에 {remaining:.1f}s 재배분"
            )

        return result

    def _parse_srt(self, srt_path: str) -> list[dict]:
        """SRT 파일을 파싱하여 [{index, start_sec, end_sec, text}] 목록 반환.

        SRT 형식:
          1
          00:00:00,000 --> 00:00:03,500
          자막 텍스트

        Args:
            srt_path: SRT 파일 절대 경로

        Returns:
            srt_entries 목록 (파싱 실패 시 빈 목록)
        """
        try:
            with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"[F006][STAGE_05R] SRT 파일 읽기 실패: {srt_path} - {e}")
            return []

        entries: list[dict] = []
        # SRT 블록 분리 - 빈 줄로 구분
        blocks = re.split(r"\n\s*\n", content.strip())

        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                # 인덱스 + 타임코드 + 텍스트 최소 3줄 필요
                continue

            # 첫 줄: 인덱스 (정수)
            try:
                idx = int(lines[0].strip())
            except ValueError:
                continue

            # 두 번째 줄: 타임코드 "HH:MM:SS,mmm --> HH:MM:SS,mmm"
            timecode_match = re.match(
                r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
                lines[1].strip(),
            )
            if not timecode_match:
                continue

            start_sec = self._srt_time_to_sec(timecode_match.group(1))
            end_sec = self._srt_time_to_sec(timecode_match.group(2))

            # 나머지 줄: 자막 텍스트 (다중 줄 지원)
            text = " ".join(line.strip() for line in lines[2:] if line.strip())

            if text:
                entries.append({
                    "index": idx,
                    "start_sec": round(start_sec, 3),
                    "end_sec": round(end_sec, 3),
                    "text": text,
                })

        return entries

    @staticmethod
    def _srt_time_to_sec(time_str: str) -> float:
        """SRT 타임코드 문자열을 초(float)로 변환.

        입력 형식: "HH:MM:SS,mmm" 또는 "HH:MM:SS.mmm"
        """
        # 콤마/점 모두 허용
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        if len(parts) != 3:
            return 0.0
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
