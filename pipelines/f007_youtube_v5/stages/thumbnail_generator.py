# pipelines/f007_youtube_v5/stages/thumbnail_generator.py
# 목적: F007 썸네일 생성 유틸 - Pillow로 1280x720 유튜브 썸네일 생성
# STAGE_04_VISUAL에서 첫 번째 슬라이드를 썸네일로 사용하는 것과 달리
# 이 모듈은 주제 제목과 채널 브랜딩을 강조한 별도 썸네일을 생성한다.

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 썸네일 캔버스 크기 (유튜브 권장: 1280x720)
_TW, _TH = 1280, 720

# channel_type별 썸네일 배경색 팔레트
_THUMBNAIL_PALETTES = {
    "finance": {
        "bg_top": (8, 15, 35),      # 짙은 네이비 (상단)
        "bg_bottom": (20, 40, 80),   # 미드나잇 블루 (하단)
        "accent": (0, 160, 255),     # 밝은 파란색
        "text_primary": (255, 255, 255),
        "text_secondary": (160, 210, 255),
        "badge_bg": (0, 100, 200),
        "badge_text": (255, 255, 255),
    },
    "language": {
        "bg_top": (20, 12, 40),      # 짙은 보라 (상단)
        "bg_bottom": (45, 25, 80),   # 퍼플 (하단)
        "accent": (160, 100, 255),   # 밝은 보라색
        "text_primary": (255, 255, 255),
        "text_secondary": (220, 190, 255),
        "badge_bg": (120, 60, 220),
        "badge_text": (255, 255, 255),
    },
}
_DEFAULT_PALETTE = _THUMBNAIL_PALETTES["finance"]


def generate_thumbnail(
    topic: str,
    output_path: str,
    channel_type: str = "finance",
    channel_name: str = "",
    badge_text: str = "",
    custom_font_path: str = "",
) -> Optional[str]:
    """유튜브 썸네일 PNG를 생성한다.

    레이아웃:
      - 상단 -> 하단 그라디언트 배경
      - 중앙: 주제 텍스트 (크고 굵게)
      - 하단 왼쪽: 채널 브랜딩 바
      - 하단 오른쪽: badge_text (예: "오늘의 이슈", "5가지 표현")
      - 좌측 6px accent 세로 바

    Args:
        topic: 유튜브 영상 주제 제목 (썸네일 메인 텍스트)
        output_path: 저장할 PNG 파일 경로
        channel_type: "finance" 또는 "language" (팔레트 선택)
        channel_name: 채널명 (하단 브랜딩 바에 표시, 빈 문자열이면 생략)
        badge_text: 우측 상단 뱃지 텍스트 (빈 문자열이면 생략)
        custom_font_path: 사용자 지정 폰트 경로 (빈 문자열이면 시스템 폰트 사용)

    Returns:
        성공 시 output_path, 실패 시 None
    """
    try:
        from PIL import Image, ImageDraw

        # shared slide_renderer의 _load_font 재사용
        from pipelines.shared.slide_renderer import _load_font

        palette = _THUMBNAIL_PALETTES.get(channel_type, _DEFAULT_PALETTE)
        extra = [custom_font_path] if custom_font_path else []

        # 1. 배경 - 수직 그라디언트 (상단 -> 하단)
        img = Image.new("RGB", (_TW, _TH), palette["bg_top"])
        draw = ImageDraw.Draw(img)
        top_c = palette["bg_top"]
        bot_c = palette["bg_bottom"]
        strip = max(1, _TH // 180)
        for y_start in range(0, _TH, strip):
            t = y_start / _TH
            r = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
            g = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
            b = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
            draw.rectangle(
                [0, y_start, _TW, min(y_start + strip - 1, _TH - 1)],
                fill=(r, g, b),
            )

        # 2. 좌측 accent 세로 바 (8px)
        draw.rectangle([0, 0, 8, _TH], fill=palette["accent"])

        # 3. 뱃지 (우측 상단, badge_text가 있을 때만)
        if badge_text:
            badge_font = _load_font(22, bold=True, extra_candidates=extra)
            badge_padding = 16
            try:
                bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
                badge_w = bbox[2] - bbox[0] + badge_padding * 2
            except Exception:
                badge_w = len(badge_text) * 14 + badge_padding * 2
            badge_h = 44
            badge_x = _TW - badge_w - 40
            badge_y = 40
            # 뱃지 배경 (둥근 모서리 없이 직사각형)
            draw.rectangle(
                [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                fill=palette["badge_bg"],
            )
            # 뱃지 텍스트 중앙 정렬
            draw.text(
                (badge_x + badge_padding, badge_y + badge_h // 2),
                badge_text,
                font=badge_font,
                fill=palette["badge_text"],
                anchor="lm",
            )

        # 4. 주제 텍스트 (중앙, 크고 굵게, 최대 3줄)
        topic_font = _load_font(72, bold=True, extra_candidates=extra)
        max_topic_w = _TW - 100  # 좌측 accent 바 + 여백
        topic_lines = _wrap_text_thumbnail(draw, topic, topic_font, max_topic_w)[:3]

        line_h = 86
        total_topic_h = len(topic_lines) * line_h
        # 채널바 높이(60px) + 상단 여백 - 중앙보다 약간 위로
        topic_y_start = (_TH - 60) // 2 - total_topic_h // 2 - 20

        for i, line in enumerate(topic_lines):
            try:
                bbox = draw.textbbox((0, 0), line, font=topic_font)
                text_w = bbox[2] - bbox[0]
                x = max(40, (_TW - text_w) // 2)  # 왼쪽 accent 바 우측으로 보정
            except Exception:
                x = 60
            draw.text(
                (x, topic_y_start + i * line_h),
                line,
                font=topic_font,
                fill=palette["text_primary"],
            )

        # 주제 텍스트 하단 accent 언더라인
        underline_y = topic_y_start + total_topic_h + 12
        underline_center_x = _TW // 2
        draw.rectangle(
            [underline_center_x - 100, underline_y, underline_center_x + 100, underline_y + 4],
            fill=palette["accent"],
        )

        # 5. 하단 채널 브랜딩 바 (60px)
        bar_h = 60
        bar_y = _TH - bar_h
        draw.rectangle([0, bar_y, _TW, _TH], fill=(8, 12, 24))
        draw.rectangle([0, bar_y, _TW, bar_y + 2], fill=palette["accent"])

        if channel_name:
            ch_font = _load_font(26, bold=True, extra_candidates=extra)
            draw.text(
                (40, bar_y + bar_h // 2),
                channel_name[:50],
                font=ch_font,
                fill=palette["text_secondary"],
                anchor="lm",
            )

        # 저장
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        logger.info(f"[thumbnail_generator] 썸네일 생성 완료: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"[thumbnail_generator] 썸네일 생성 실패: {e}")
        return None


def _wrap_text_thumbnail(draw, text: str, font, max_width: int) -> list[str]:
    """썸네일 텍스트를 max_width 픽셀에 맞게 단어 단위로 줄바꿈한다.

    한글은 글자 단위로 분리하고, 영문은 단어 단위로 분리한다.
    """
    # 단어 단위 줄바꿈 시도
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        try:
            bbox = draw.textbbox((0, 0), test, font=font)
            w = bbox[2] - bbox[0]
        except Exception:
            w = len(test) * 40  # 폰트 크기 72 기준 대략 추정
        if w > max_width and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines if lines else [text]
