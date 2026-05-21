# pipelines/f007_youtube_v5/stages/stage05_video.py
# 목적: F007 STAGE_05 - shared/ffmpeg_composer.py 위임 + narration 비례 duration 계산
# clips의 각 슬라이드 표시 시간을 narration 길이 비례로 계산한다.

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import random as _random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipelines.f007_youtube_v5.stages import BaseStage, ValidationResult
from pipelines.base import BasePipeline
from pipelines.shared.ffmpeg_composer import compose_video

logger = logging.getLogger(__name__)

# 슬라이드 표시 최소 시간(초) - narration이 없어도 이 시간 이상 유지
_MIN_CLIP_DURATION = 2.0

# narration 없는 슬라이드 기본 표시 시간(초)
_DEFAULT_CLIP_DURATION = 3.0

# narration 기준 초당 글자 수 (한국어 기준 약 8자/초)
_CHARS_PER_SECOND = 8.0


class Stage05Video(BaseStage, BasePipeline):
    """STAGE_05 - FFmpeg 영상 합성.

    shared/ffmpeg_composer.py의 compose_video()에 위임한다.
    각 슬라이드 표시 시간은 narration 길이 비례 또는 TTS duration 비례로 결정한다.
    """
    STAGE_ID: str = "STAGE_05_VIDEO"
    STAGE_ORDER: int = 5

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE05", "name": "STAGE_05_VIDEO"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - clips 없으면 STAGE_04_VISUAL로 반송."""
        if not data.get("clips"):
            return ValidationResult(
                is_valid=False,
                rejection_reason="clips 없음. STAGE_04에서 슬라이드 이미지를 생성하세요.",
                rejection_target="STAGE_04_VISUAL",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_05 실행 - FFmpeg 영상 합성.

        Args:
            job_id: content_jobs.id
            input_data: {
                clips (list): STAGE_04 출력 클립 목록
                audio_file_path (str|None): TTS 오디오 파일 경로
                srt_file_path (str|None): 자막 파일 경로 (현재 미사용)
                duration_sec (float, 기본 0): TTS 오디오 총 길이(초)
                bgm_path (str, 기본 "random"): BGM 경로 또는 "random"/"" 특수값
                bgm_volume (float, 기본 0.15): BGM 볼륨 배율
                channel_type (str, 기본 "finance"): BGM 디렉토리 선택에 사용
            }

        Returns:
            {
                stage_id, status,
                video_file_path (str): 생성된 MP4 파일 경로,
                generated_at (str)
            }
        """
        clips: list = input_data.get("clips", [])
        audio_path: Optional[str] = input_data.get("audio_file_path")
        bgm_path_input: str = input_data.get("bgm_path", "random")
        bgm_volume: float = float(input_data.get("bgm_volume", 0.15))
        channel_type: str = input_data.get("channel_type", "finance")
        total_duration: float = float(input_data.get("duration_sec", 0) or 0)

        # 출력 디렉토리 생성
        project_root = Path(__file__).parent.parent.parent.parent
        output_dir = project_root / "storage" / "results" / "f007" / str(job_id) / "final"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / "final_video.mp4")

        logger.info(
            f"[F007][STAGE_05][job_id={job_id}] 시작 - "
            f"clips={len(clips)}, audio={'있음' if audio_path else '없음'}, "
            f"total_duration={total_duration:.1f}초"
        )

        # 1. narration 비례 duration 계산
        clips = [dict(c) for c in clips]  # 원본 dict 수정 방지 (shallow copy)
        self._assign_durations(clips, total_duration)

        # 2. BGM 경로 결정
        bgm_path = self._resolve_bgm_path(
            bgm_path_input, project_root, channel_type
        )

        # 3. 오디오 파일 존재 확인 (없으면 None으로)
        audio_file = None
        if audio_path and Path(audio_path).exists():
            audio_file = audio_path
        elif audio_path:
            logger.warning(
                f"[F007][STAGE_05][job_id={job_id}] "
                f"오디오 파일 없음: {audio_path} - 오디오 없이 합성"
            )

        # 4. FFmpeg 영상 합성
        logger.info(
            f"[F007][STAGE_05][job_id={job_id}] FFmpeg 합성 시작 - "
            f"bgm={'있음' if bgm_path else '없음'}"
        )
        try:
            result_path = compose_video(
                clips=clips,
                audio_path=audio_file,
                output_path=output_path,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
            )
        except Exception as e:
            logger.error(f"[F007][STAGE_05][job_id={job_id}] FFmpeg 합성 실패: {e}")
            raise

        logger.info(f"[F007][STAGE_05][job_id={job_id}] 완료 - {result_path}")

        return {
            "stage_id": "STAGE_05_VIDEO",
            "status": "COMPLETED",
            "video_file_path": result_path,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - video_file_path가 실제로 존재해야 통과."""
        vp = output.get("video_file_path")
        if not vp or not Path(vp).exists():
            return ValidationResult(
                is_valid=False,
                rejection_reason="video_file_path 없거나 파일 미존재. 영상 합성을 재시도합니다.",
                rejection_target="STAGE_05_VIDEO",
            )
        return ValidationResult(is_valid=True)

    def _assign_durations(self, clips: list, total_duration: float) -> None:
        """각 클립의 duration_sec을 narration 길이 비례로 설정한다.

        total_duration > 0이면 2-pass 알고리즘으로 합계 = total_duration 보장.
        없으면 narration 길이 기반 추정.

        2-pass 알고리즘:
          1차: 비례 배분 계산
          2차: MIN 미달 클립을 MIN으로 올리고 남은 시간을 나머지에 재배분.
          전체 합 = total_duration 항상 보장 (FFmpeg -shortest 싱크 오류 방지).
        """
        # 빈 narration도 최소 10자로 취급해 극단적 비율 방지
        narration_lengths = [max(10, len(c.get("narration", "") or "")) for c in clips]
        total_chars = sum(narration_lengths) or 1
        n = len(clips)

        if total_duration > 0:
            # 1차: 비례 배분
            raw = [total_duration * nar / total_chars for nar in narration_lengths]

            floor_indices = [i for i, d in enumerate(raw) if d < _MIN_CLIP_DURATION]
            non_floor_indices = [i for i, d in enumerate(raw) if d >= _MIN_CLIP_DURATION]
            floor_total = len(floor_indices) * _MIN_CLIP_DURATION

            if floor_total >= total_duration:
                # MIN 보장만으로 total_duration 초과 시 균등 분배
                per_clip = total_duration / n
                logger.warning(
                    f"[F007][STAGE_05] min {_MIN_CLIP_DURATION}s 보장으로 "
                    f"audio_duration({total_duration:.1f}s) 초과 - "
                    f"균등 배분 ({per_clip:.1f}s/클립)"
                )
                for clip in clips:
                    clip["duration_sec"] = per_clip
            else:
                # 2차: MIN 미달 클립 = MIN, 나머지에 잔여 시간 재배분
                remaining = total_duration - floor_total
                non_floor_chars = sum(narration_lengths[i] for i in non_floor_indices) or 1
                for i, clip in enumerate(clips):
                    if i in floor_indices:
                        clip["duration_sec"] = _MIN_CLIP_DURATION
                    else:
                        clip["duration_sec"] = remaining * (narration_lengths[i] / non_floor_chars)
        else:
            # TTS 없는 경우: narration 길이를 초당 글자 수로 나눠 추정
            for clip, nar_len in zip(clips, narration_lengths):
                if nar_len > 0:
                    estimated = nar_len / _CHARS_PER_SECOND
                    clip["duration_sec"] = max(_MIN_CLIP_DURATION, estimated)
                else:
                    clip["duration_sec"] = _DEFAULT_CLIP_DURATION

    def _resolve_bgm_path(
        self,
        bgm_path_input: str,
        project_root: Path,
        channel_type: str,
    ) -> Optional[str]:
        """BGM 경로 특수값 처리.

        - "random": storage/bgm/{channel_type}/ 에서 랜덤 선택
        - "" (빈 문자열): BGM 없음 (None 반환)
        - 실제 경로: 그대로 사용 (파일 존재 확인 후)
        """
        if bgm_path_input == "" or bgm_path_input is None:
            return None

        if bgm_path_input == "random":
            bgm_dir = project_root / "storage" / "bgm" / channel_type
            if not bgm_dir.exists():
                # 채널 타입별 디렉토리가 없으면 공통 BGM 디렉토리 시도
                bgm_dir = project_root / "storage" / "bgm"
            bgm_files = list(bgm_dir.glob("*.mp3")) + list(bgm_dir.glob("*.wav"))
            if bgm_files:
                chosen = str(_random.choice(bgm_files))
                logger.info(f"[F007][STAGE_05] BGM 랜덤 선택: {chosen}")
                return chosen
            else:
                logger.info(
                    f"[F007][STAGE_05] BGM 파일 없음 ({bgm_dir}) - BGM 없이 진행"
                )
                return None

        # 실제 경로 지정 시 - 파일 존재 확인
        if Path(bgm_path_input).exists():
            return bgm_path_input
        else:
            logger.warning(
                f"[F007][STAGE_05] BGM 파일 없음: {bgm_path_input} - BGM 없이 진행"
            )
            return None
