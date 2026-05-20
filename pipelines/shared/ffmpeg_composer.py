# pipelines/shared/ffmpeg_composer.py
# 목적: FFmpeg concat + BGM 믹싱 공통 유틸 - F006/F007 파이프라인 공유
# 슬라이드 PNG 클립 배열 + TTS 오디오 + BGM -> 최종 MP4 합성

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional
import imageio_ffmpeg  # type: ignore[import]

logger = logging.getLogger(__name__)


def get_ffmpeg() -> str:
    """imageio_ffmpeg에서 ffmpeg 실행 파일 경로를 반환한다."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def compose_video(
    clips: list,
    audio_path: Optional[str],
    output_path: str,
    bgm_path: Optional[str] = None,
    bgm_volume: float = 0.15,
    resolution: str = "1280x720",
    timeout: int = 600,
) -> str:
    """슬라이드 PNG 클립 배열 + TTS 오디오 -> MP4 합성.

    Args:
        clips: [{"file_path": str, "duration_sec": float}, ...] 형태의 클립 목록
        audio_path: TTS 나레이션 오디오 파일 경로 (None이면 BGM 전용 또는 무음)
        output_path: 출력 MP4 파일 경로
        bgm_path: 배경 음악 파일 경로 (None이면 BGM 없음)
        bgm_volume: BGM 볼륨 배율 (기본 0.15 = 15%)
        resolution: 출력 해상도 문자열 (현재 미사용, clips의 PNG 크기가 결정)
        timeout: FFmpeg 프로세스 타임아웃(초)

    Returns:
        생성된 MP4 파일의 절대 경로

    Raises:
        RuntimeError: FFmpeg 실패 또는 출력 파일 미생성 시
    """
    ffmpeg = get_ffmpeg()

    # concat demuxer 입력 파일 작성 - 각 PNG + 표시 시간
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        concat_path = f.name
        for clip in clips:
            # 경로에 역슬래시가 있을 경우 슬래시로 통일 (FFmpeg 호환)
            file_path = clip["file_path"].replace("\\", "/")
            duration = clip.get("duration_sec", 5.0)
            f.write(f"file '{file_path}'\n")
            f.write(f"duration {duration}\n")

    try:
        # TTS 오디오 + BGM 둘 다 있는 경우: amix 필터로 믹싱
        if audio_path and bgm_path:
            cmd = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_path,
                "-i", audio_path,
                "-i", bgm_path,
                "-filter_complex",
                (
                    f"[2:a]volume={bgm_volume}[bgm_a];"
                    f"[1:a][bgm_a]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                ),
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_path,
            ]
        # TTS 오디오만 있는 경우: 나레이션 단독
        elif audio_path:
            cmd = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_path,
                "-i", audio_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-shortest",
                output_path,
            ]
        # 오디오 없는 경우: 비디오만 (BGM 처리는 호출자 책임)
        else:
            cmd = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0", "-i", concat_path,
                "-c:v", "libx264",
                output_path,
            ]

        logger.info(f"[ffmpeg_composer] FFmpeg 합성 시작 - 클립 {len(clips)}개 -> {output_path}")
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
        )

        if r.returncode != 0:
            raise RuntimeError(
                f"FFmpeg 합성 실패 (returncode={r.returncode}): {r.stderr[-500:]}"
            )

        if not Path(output_path).exists():
            raise RuntimeError(f"FFmpeg: 출력 파일이 생성되지 않음 - {output_path}")

        logger.info(f"[ffmpeg_composer] 합성 완료 - {output_path}")
        return output_path

    finally:
        # 임시 concat 파일 항상 삭제
        try:
            Path(concat_path).unlink(missing_ok=True)
        except Exception:
            pass
