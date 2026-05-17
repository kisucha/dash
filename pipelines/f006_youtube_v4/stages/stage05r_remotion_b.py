# 목적: F006 STAGE_05RB - Remotion video_bg 모드 동영상 렌더링 스테이지.
# PNG 슬라이드 없이 slide_json_data(텍스트 JSON)를 props로 사용.
# Remotion 컴포지션 "F006VideoB": 애니메이션 그라디언트 배경 + 텍스트 JSON 렌더링.
# orchestrator에서 render_mode="video_bg" 수신 시 Stage05Edit 대신 이 클래스가 선택된다.
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

# Remotion 컴포지션 ID - video_bg 모드 전용
_COMPOSITION_ID: str = "F006VideoB"

# 출력 파일명 - video_bg 모드 전용
_OUTPUT_VIDEO_NAME: str = "output_videob.mp4"
_OUTPUT_THUMB_NAME: str = "thumbnail_videob.png"


class Stage05rRemotionB(BaseStage, BasePipeline):
    """STAGE_05RB - Remotion video_bg 모드 동영상 렌더링 스테이지.

    처리 흐름:
      1. stage05_auto_skipped=True이면 즉시 SKIPPED
      2. slide_json_data와 오디오 모두 없으면 SKIPPED
      3. 오디오 길이 측정 -> narration 비례 배분으로 슬라이드 duration_sec 계산
         (오디오 없을 때 슬라이드당 5.0초 기본값)
      4. SRT 파일 파싱 -> srt_entries 구성
      5. remotion_props_b.json 파일 생성
      6. npm install (node_modules 없는 경우에만)
      7. remotion render 실행 (컴포지션: F006VideoB) -> output_videob.mp4 생성
      8. remotion still 실행 -> thumbnail_videob.png 생성

    DB 호환성:
      STAGE_ID = "STAGE_05_EDIT" - orchestrator stages 테이블 레코드와 일치
    """

    # DB 호환성: Stage05Edit와 동일한 STAGE_ID 사용
    STAGE_ID: str = "STAGE_05_EDIT"
    STAGE_ORDER: int = 5

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE05RB", "name": "STAGE_05RB_REMOTION_B"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - slide_json_data가 있거나 audio_file_path가 있으면 유효."""
        if data.get("stage05_auto_skipped", False):
            return ValidationResult(is_valid=True)

        slide_json_data = data.get("slide_json_data", [])
        audio_file_path = data.get("audio_file_path")

        # slide_json_data나 오디오 중 하나라도 있으면 유효
        if slide_json_data or audio_file_path:
            return ValidationResult(is_valid=True)

        # 둘 다 없어도 execute에서 SKIPPED 처리하므로 유효 통과
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_05RB 실행 - Remotion video_bg 동영상 렌더링.

        Args:
            job_id: content_jobs.id
            input_data: {
                stage05_auto_skipped (bool): STAGE_04 script_only 체인에 의한 자동 skip
                slide_json_data (list): Stage04bVideoJson이 생성한 슬라이드 텍스트 데이터
                audio_file_path (str or None): STAGE_03 TTS 오디오 파일 경로
                srt_file_path (str or None): STAGE_03 SRT 자막 파일 경로
                channel_name (str): 채널 이름 (Remotion props로 전달)
                remotion_theme (str): 테마 이름 (dark_blue / warm_gray / clean_white)
                remotion_transition (str): 전환 모드 (auto / fade_only / slide_only)
                remotion_concurrency (int): Remotion 렌더링 동시성 (기본 4)
            }

        Returns:
            SKIPPED 시: {stage_id, status="SKIPPED", skip_reason, generated_at}
            COMPLETED 시: {stage_id, status="COMPLETED", video_file_path,
                           subtitle_file_path, duration_sec, resolution,
                           file_size_mb, has_subtitles, generated_at, renderer="remotion_b"}
        """
        logger.info(f"[F006][STAGE_05RB][job_id={job_id}] Remotion video_bg 렌더링 시작")

        # ----------------------------------------------------------------
        # 1. auto_skipped 체크 - STAGE_04 script_only 체인
        # ----------------------------------------------------------------
        if input_data.get("stage05_auto_skipped", False):
            logger.info(
                f"[F006][STAGE_05RB][job_id={job_id}] STAGE_04 script_only로 인해 자동 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "STAGE_04 script_only skip으로 인해 STAGE_05RB 자동 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        slide_json_data: list[dict] = input_data.get("slide_json_data", [])
        audio_file_path: Optional[str] = input_data.get("audio_file_path")

        # ----------------------------------------------------------------
        # 2. slide_json_data와 오디오 모두 없으면 SKIPPED
        # ----------------------------------------------------------------
        if not slide_json_data and not audio_file_path:
            logger.info(
                f"[F006][STAGE_05RB][job_id={job_id}] slide_json_data와 오디오 모두 없어 SKIPPED"
            )
            return {
                "stage_id": "STAGE_05_EDIT",
                "status": "SKIPPED",
                "skip_reason": "slide_json_data와 오디오 파일이 없어 Remotion video_bg 렌더링 건너뜀",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # Remotion 파라미터 추출
        channel_name: str = (
            input_data.get("channel_name") or input_data.get("channel_category", "")
        )
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
                f"[F006][STAGE_05RB][job_id={job_id}] 오디오 길이: {audio_duration:.1f}초"
            )

        # slide_json_data에 duration_sec 배분
        if slide_json_data:
            if audio_duration > 0:
                has_narration = any(s.get("narration") for s in slide_json_data)
                if has_narration:
                    durations = self._distribute_duration_by_narration(
                        slide_json_data, audio_duration
                    )
                    logger.info(
                        f"[F006][STAGE_05RB][job_id={job_id}] narration 비례 배분 - "
                        f"{audio_duration:.1f}초 / {len(slide_json_data)}슬라이드"
                    )
                else:
                    per_slide = audio_duration / len(slide_json_data)
                    durations = {i: per_slide for i in range(len(slide_json_data))}
                    logger.info(
                        f"[F006][STAGE_05RB][job_id={job_id}] 균등 배분 - "
                        f"{per_slide:.1f}초/슬라이드"
                    )
            else:
                # 오디오 없을 때 슬라이드당 5.0초 기본값
                durations = {i: 5.0 for i in range(len(slide_json_data))}
                logger.info(
                    f"[F006][STAGE_05RB][job_id={job_id}] 오디오 없음 - 슬라이드당 5.0초 기본값"
                )
        else:
            durations = {}

        # ----------------------------------------------------------------
        # 4. SRT 파싱
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
                    f"[F006][STAGE_05RB][job_id={job_id}] SRT 파싱 완료 - "
                    f"{len(srt_entries)}개 항목"
                )

        # ----------------------------------------------------------------
        # 5. remotion_props_b.json 구성 및 저장
        # ----------------------------------------------------------------
        job_dir: Path = _PROJECT_ROOT / "storage" / "results" / "f006" / str(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)

        # slides 데이터 구성 - duration_sec 추가
        slides_data: list[dict] = []
        for i, slide in enumerate(slide_json_data):
            duration_sec: float = round(durations.get(i, 5.0), 3)
            slides_data.append({**slide, "duration_sec": duration_sec})

        # 오디오 경로 - job_dir 기준 상대 경로 (staticFile 대응)
        audio_path_normalized: str = ""
        if audio_file_path:
            try:
                audio_rel = Path(audio_file_path).relative_to(job_dir)
                audio_path_normalized = str(audio_rel).replace("\\", "/")
            except ValueError:
                audio_path_normalized = Path(audio_file_path).name

        remotion_props: dict = {
            "slides": slides_data,
            "audio_path": audio_path_normalized,
            "srt_entries": srt_entries,
            "channel_name": channel_name,
            "theme": theme,
            "transition_mode": transition_mode,
        }

        # remotion_props_b.json 저장 (stage05r_remotion.py의 remotion_props.json과 구분)
        props_json_path: Path = job_dir / "remotion_props_b.json"
        with open(props_json_path, "w", encoding="utf-8") as f:
            json.dump(remotion_props, f, ensure_ascii=False, indent=2)
        logger.info(
            f"[F006][STAGE_05RB][job_id={job_id}] remotion_props_b.json 저장: {props_json_path}"
        )

        # ----------------------------------------------------------------
        # 6. npm install (node_modules 없는 경우에만)
        # ----------------------------------------------------------------
        if not (_REMOTION_DIR / "node_modules").exists():
            logger.info(
                f"[F006][STAGE_05RB][job_id={job_id}] node_modules 없음 - npm install 실행"
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
                        f"[F006][STAGE_05RB][job_id={job_id}] npm install 실패: "
                        f"{npm_result.stderr[:300]}"
                    )
                    raise RuntimeError(
                        f"npm install 실패 (exit code {npm_result.returncode}): "
                        f"{npm_result.stderr[:200]}"
                    )
                logger.info(
                    f"[F006][STAGE_05RB][job_id={job_id}] npm install 완료"
                )
            except subprocess.TimeoutExpired as e:
                logger.error(
                    f"[F006][STAGE_05RB][job_id={job_id}] npm install 타임아웃 (300초)"
                )
                raise RuntimeError("npm install 타임아웃 (300초)") from e
        else:
            logger.info(
                f"[F006][STAGE_05RB][job_id={job_id}] node_modules 존재 - npm install 생략"
            )

        # ----------------------------------------------------------------
        # 7. remotion render 실행 (컴포지션: F006VideoB)
        # ----------------------------------------------------------------
        output_final_dir: Path = job_dir / "final"
        output_final_dir.mkdir(parents=True, exist_ok=True)
        output_video_path: str = str(output_final_dir / _OUTPUT_VIDEO_NAME)

        public_dir_str: str = str(job_dir).replace("\\", "/")
        cmd_render: list[str] = [
            "cmd", "/c", "npx", "remotion", "render",
            "--props", str(props_json_path),
            f"--concurrency={concurrency}",
            f"--public-dir={public_dir_str}",
            "src/Root.tsx",
            _COMPOSITION_ID,
            output_video_path,
        ]

        logger.info(
            f"[F006][STAGE_05RB][job_id={job_id}] remotion render 시작 - "
            f"컴포지션={_COMPOSITION_ID}, 출력={output_video_path}"
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
                    f"[F006][STAGE_05RB][job_id={job_id}] remotion render 실패: "
                    f"{render_result.stderr[:400]}"
                )
                raise RuntimeError(
                    f"remotion render 실패 (exit code {render_result.returncode}): "
                    f"{render_result.stderr[:300]}"
                )
            logger.info(
                f"[F006][STAGE_05RB][job_id={job_id}] remotion render 완료: {output_video_path}"
            )
        except subprocess.TimeoutExpired as e:
            logger.error(
                f"[F006][STAGE_05RB][job_id={job_id}] remotion render 타임아웃 (900초)"
            )
            raise RuntimeError("remotion render 타임아웃 (900초)") from e

        # ----------------------------------------------------------------
        # 8. remotion still 실행 - 썸네일 생성
        # ----------------------------------------------------------------
        thumbnails_dir: Path = job_dir / "thumbnails"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_path: str = str(thumbnails_dir / _OUTPUT_THUMB_NAME)

        cmd_still: list[str] = [
            "cmd", "/c", "npx", "remotion", "still",
            "--props", str(props_json_path),
            "--frame=0",
            f"--public-dir={public_dir_str}",
            "src/Root.tsx",
            _COMPOSITION_ID,
            thumbnail_path,
        ]

        logger.info(
            f"[F006][STAGE_05RB][job_id={job_id}] remotion still (썸네일) 시작"
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
                    f"[F006][STAGE_05RB][job_id={job_id}] remotion still 실패 (무시): "
                    f"{still_result.stderr[:200]}"
                )
            else:
                logger.info(
                    f"[F006][STAGE_05RB][job_id={job_id}] remotion still 완료: {thumbnail_path}"
                )
        except subprocess.TimeoutExpired:
            logger.warning(
                f"[F006][STAGE_05RB][job_id={job_id}] remotion still 타임아웃 (180초) - 무시"
            )

        # ----------------------------------------------------------------
        # 9. 결과 메타데이터 수집
        # ----------------------------------------------------------------
        output_file = Path(output_video_path)
        file_size_mb: float = 0.0
        if output_file.exists():
            file_size_mb = round(output_file.stat().st_size / 1024 / 1024, 2)

        # 영상 길이는 슬라이드 duration_sec 합계로 추정
        total_duration: float = round(
            sum(s.get("duration_sec", 5.0) for s in slides_data), 1
        )

        logger.info(
            f"[F006][STAGE_05RB][job_id={job_id}] 렌더링 완료 - "
            f"{file_size_mb}MB, {total_duration}초, 자막: {has_subtitles}"
        )

        return {
            "stage_id": "STAGE_05_EDIT",
            "status": "COMPLETED",
            "video_file_path": output_video_path,
            "subtitle_file_path": subtitle_file_path,
            "duration_sec": total_duration,
            "resolution": "1280x720",
            "file_size_mb": file_size_mb,
            "has_subtitles": has_subtitles,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "renderer": "remotion_b",
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - COMPLETED 시 video_file_path 파일 존재 확인."""
        if output.get("status") == "SKIPPED":
            return ValidationResult(is_valid=True)

        video_path = output.get("video_file_path")
        if not video_path:
            return ValidationResult(
                is_valid=False,
                rejection_reason="STAGE_05RB video_file_path 없음 - Remotion video_bg 렌더링 실패. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        if not Path(video_path).exists():
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"STAGE_05RB 출력 파일 없음: {video_path}. 재시도하세요.",
                rejection_target="STAGE_05_EDIT",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 오디오/자막 헬퍼 메서드 (stage05r_remotion.py와 동일 구현 - 독립 유지)
    # ------------------------------------------------------------------

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
            logger.warning(f"[F006][STAGE_05RB] moviepy 오디오 길이 측정 실패: {e}")
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
            logger.warning(f"[F006][STAGE_05RB] ffprobe 오디오 길이 측정 실패: {e}")
        return 0.0

    def _distribute_duration_by_narration(
        self,
        slides: list[dict],
        audio_duration: float,
    ) -> dict[int, float]:
        """각 슬라이드의 narration 글자 수에 비례해 표시 시간 배분.

        반환값: {슬라이드 인덱스: duration_sec} (인덱스 기반 키)
        2-pass 알고리즘 - stage05r_remotion.py와 동일 로직.
        """
        min_dur = 3.0
        n = len(slides)

        narration_lens = [
            max(10, len(s.get("narration", "") or ""))
            for s in slides
        ]
        total_chars = sum(narration_lens)

        raw = [audio_duration * (n_len / total_chars) for n_len in narration_lens]

        floor_indices = [i for i, d in enumerate(raw) if d < min_dur]
        non_floor_indices = [i for i, d in enumerate(raw) if d >= min_dur]

        floor_total = len(floor_indices) * min_dur

        if floor_total >= audio_duration:
            per_slide = audio_duration / n
            logger.warning(
                f"[F006][STAGE_05RB] min {min_dur}s 보장으로 audio_duration({audio_duration:.1f}s) "
                f"초과 - 균등 배분 폴백 ({per_slide:.1f}s/슬라이드)"
            )
            return {i: per_slide for i in range(n)}

        remaining = audio_duration - floor_total
        non_floor_chars = sum(narration_lens[i] for i in non_floor_indices)

        result: dict[int, float] = {}
        for i in range(n):
            if i in floor_indices:
                result[i] = min_dur
            else:
                result[i] = remaining * (narration_lens[i] / non_floor_chars)

        if floor_indices:
            logger.info(
                f"[F006][STAGE_05RB] min {min_dur}s 클램핑 발동: {len(floor_indices)}개 슬라이드, "
                f"나머지 {len(non_floor_indices)}개에 {remaining:.1f}s 재배분"
            )

        return result

    def _parse_srt(self, srt_path: str) -> list[dict]:
        """SRT 파일을 파싱하여 [{index, start_sec, end_sec, text}] 목록 반환."""
        try:
            with open(srt_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"[F006][STAGE_05RB] SRT 파일 읽기 실패: {srt_path} - {e}")
            return []

        entries: list[dict] = []
        blocks = re.split(r"\n\s*\n", content.strip())

        for block in blocks:
            lines = block.strip().splitlines()
            if len(lines) < 3:
                continue

            try:
                idx = int(lines[0].strip())
            except ValueError:
                continue

            timecode_match = re.match(
                r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
                lines[1].strip(),
            )
            if not timecode_match:
                continue

            start_sec = self._srt_time_to_sec(timecode_match.group(1))
            end_sec = self._srt_time_to_sec(timecode_match.group(2))
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
        """SRT 타임코드 문자열을 초(float)로 변환."""
        time_str = time_str.replace(",", ".")
        parts = time_str.split(":")
        if len(parts) != 3:
            return 0.0
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
