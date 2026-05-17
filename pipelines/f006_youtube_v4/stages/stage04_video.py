# 목적: F006 STAGE_04 - Pillow 기반 PPT 슬라이드 PNG 이미지 생성.
# ComfyUI 없이 로컬에서 1280x720 슬라이드 이미지를 생성한다.

import sys

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# -- 캔버스 상수 --
W, H = 1280, 720
MARGIN_X = 80
HEADER_H = 90
CONTENT_Y = HEADER_H + 20
FOOTER_H = 60

# -- 차트 패널 레이아웃 상수 --
CHART_PANEL_X = 768          # 텍스트 영역 끝 (W * 0.6)
CHART_PANEL_W = 492          # 차트 패널 너비 (W - CHART_PANEL_X - 20)
CHART_PANEL_Y = HEADER_H + 10
CHART_PANEL_H = 540          # H - HEADER_H - FOOTER_H - 10
TEXT_AREA_W = CHART_PANEL_X - MARGIN_X - 20  # 차트 있을 때 텍스트 영역 너비

# -- 색상 테마 --
SLIDE_THEMES = {
    "dark_blue": {
        "bg": (15, 25, 50),
        "accent": (0, 122, 255),
        "accent_light": (100, 180, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (180, 200, 220),
        "bullet_dot": (0, 122, 255),
        "divider": (40, 60, 100),
        "header_bg": (0, 50, 120),
        "source_bg": (10, 20, 40),
    },
    "dark_green": {
        "bg": (10, 30, 20),
        "accent": (0, 200, 100),
        "accent_light": (80, 230, 150),
        "text_primary": (255, 255, 255),
        "text_secondary": (160, 210, 180),
        "bullet_dot": (0, 200, 100),
        "divider": (20, 70, 40),
        "header_bg": (0, 80, 40),
        "source_bg": (5, 20, 12),
    },
    "corporate": {
        "bg": (240, 244, 248),
        "accent": (30, 90, 200),
        "accent_light": (80, 140, 240),
        "text_primary": (20, 30, 50),
        "text_secondary": (80, 100, 130),
        "bullet_dot": (30, 90, 200),
        "divider": (200, 210, 230),
        "header_bg": (30, 90, 200),
        "source_bg": (220, 230, 245),
    },
}
DEFAULT_THEME = "dark_blue"

# -- 폰트 캐시 - 동일 크기/굵기 반복 로드 방지 --
_FONT_CACHE: dict = {}

# -- 텍스트 정규화 유틸 --

import re as _re

def _normalize_text(text: str) -> str:
    """슬라이드 텍스트 정규화 - 인코딩 아티팩트 제거, 특수문자 교체.

    LLM이 placeholder로 삽입하는 □/■ 계열 문자를 제거하고,
    ₩ 기호를 '원'으로 교체한다.
    """
    if not text:
        return text
    # U+25A0-U+25FF(기하 도형), U+FFFD(대체 문자), U+2610-U+2612(체크박스) 제거
    text = _re.sub(r'[■-◿�☐☒]', '', text)
    # ₩X원 -> X원 (₩와 원 동시 존재 시 ₩만 제거)
    text = _re.sub(r'₩([\d,]+)원', lambda m: f"{m.group(1)}원", text)
    # ₩X -> X원 (₩가 숫자 앞에 오고 원 없는 경우)
    text = _re.sub(r'₩([\d,]+)', lambda m: f"{m.group(1)}원", text)
    # 나머지 고립된 ₩ -> 원
    text = text.replace('₩', '원')
    # 연속 공백 정리
    text = _re.sub(r'  +', ' ', text).strip()
    return text


def _unify_amount(text: str) -> str:
    """금액 표현을 만원 단위로 통일한다.

    규칙:
    - 10,000원 이상 -> 만원 단위 (예: 260,000원 -> 26만원, 2,600,000원 -> 260만원)
    - 100,000,000원 이상 -> 억원 단위
    - 'Xk원' / 'Xk' (k=천) -> 만원 변환
    - 10,000 미만 -> 그대로 X원
    """

    def _to_man(m: "_re.Match") -> str:
        raw = m.group(1).replace(',', '').replace(' ', '')
        try:
            n = int(raw)
        except ValueError:
            return m.group(0)
        if n >= 100_000_000:
            eok = n // 100_000_000
            rem = (n % 100_000_000) // 10_000
            return f"{eok}억원" if rem == 0 else f"{eok}억 {rem}만원"
        elif n >= 10_000:
            man = n // 10_000
            rem = n % 10_000
            return f"{man}만원" if rem == 0 else f"{man}만 {rem}원"
        else:
            return f"{n:,}원"

    # 쉼표 포함 숫자 + 원 패턴 (최소 5자리 숫자부터 변환)
    text = _re.sub(r'([\d,]{5,})원', _to_man, text)

    # Xk원 패턴 (예: 260k원 -> 26만원)
    def _k_to_man(m: "_re.Match") -> str:
        n = int(m.group(1)) * 1000
        if n >= 10_000:
            man = n // 10_000
            rem = n % 10_000
            return f"{man}만원" if rem == 0 else f"{man}만 {rem}원"
        return f"{n:,}원"

    text = _re.sub(r'(\d+)[kK]원', _k_to_man, text)
    return text


def _clean_slide(slide: dict) -> dict:
    """슬라이드 딕셔너리 텍스트 필드를 정규화해 복사본을 반환한다."""
    result = dict(slide)
    result['title'] = _unify_amount(_normalize_text(slide.get('title', '')))
    result['bullets'] = [
        _unify_amount(_normalize_text(b)) for b in slide.get('bullets', [])
    ]
    if 'narration' in slide:
        result['narration'] = _unify_amount(_normalize_text(slide['narration']))
    if 'source' in slide:
        result['source'] = _normalize_text(slide.get('source', ''))
    return result

# 한글 폰트 후보 - 절대 경로(Bold) 우선, 이후 Regular, 이후 영문 폴백
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\malgunbd.ttf",       # 맑은 고딕 Bold (절대 경로 우선)
    r"C:\Windows\Fonts\malgun.ttf",         # 맑은 고딕 Regular
    r"C:\Windows\Fonts\NanumGothicBold.ttf",
    r"C:\Windows\Fonts\NanumGothic.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "malgunbd.ttf",
    "malgun.ttf",
]


def _load_font(
    size: int,
    bold: bool = False,
    extra_candidates: list[str] | None = None,
) -> "ImageFont.FreeTypeFont":
    """폰트를 크기/굵기 키로 캐싱해 반환한다."""
    from PIL import ImageFont

    extra = extra_candidates or []
    cache_key = (size, bold, tuple(extra))
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]

    base = FONT_CANDIDATES if bold else [FONT_CANDIDATES[1]] + FONT_CANDIDATES
    candidates = extra + base

    for path in candidates:
        try:
            font = ImageFont.truetype(path, size=size)
            _FONT_CACHE[cache_key] = font
            return font
        except Exception:
            continue

    logger.warning(f"한글 폰트 로드 실패. 기본 폰트 사용 (size={size})")
    font = ImageFont.load_default()
    _FONT_CACHE[cache_key] = font
    return font


class SlideRenderer:
    """Pillow 기반 PPT 슬라이드 렌더러.

    슬라이드 타입별(title, content, summary, quote) render 메서드를 제공한다.
    테마 딕셔너리를 주입받아 색상 일관성을 유지한다.
    """

    def __init__(self, theme: dict, custom_font_path: str = "", channel_name: str = ""):
        # 테마 딕셔너리 - 색상 참조에 사용
        self.theme = theme
        # 사용자 지정 폰트 경로 - 전역 FONT_CANDIDATES 변경 없이 우선 탐색
        self._extra: list[str] = [custom_font_path] if custom_font_path else []
        # 채널 이름 - 슬라이드 헤더 브랜딩에 표시 (미입력 시 빈 문자열)
        self.channel_name: str = channel_name

    def _font(self, size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
        """self._extra를 추가해 _load_font를 호출하는 헬퍼."""
        return _load_font(size, bold=bold, extra_candidates=self._extra)

    # -- 테마별 그라디언트 2색 정의 (상단색 -> 하단색) --
    # SLIDE_THEMES 키와 동일 이름으로 맵핑; 없으면 bg 단색 폴백
    _GRADIENT_MAP: dict = {
        "dark_blue":  ((10, 22, 40),   (15, 36, 84)),   # #0a1628 -> #0f2454
        "dark_green": ((10, 30, 20),   (15, 55, 35)),
        "corporate":  ((240, 244, 248), (232, 244, 253)), # #f0f4f8 -> #e8f4fd
    }

    def _make_base_image(self, gradient: bool = False):
        """배경 이미지와 Draw 객체를 생성해 반환한다.

        gradient=True 시 2색 수직 그라디언트 배경을 그린다.
        numpy 없이 ImageDraw rect 반복으로 구현 (호환성 우선).
        """
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (W, H), self.theme["bg"])

        if gradient:
            # 테마 이름 탐색 - SLIDE_THEMES 역방향 검색
            theme_name = next(
                (k for k, v in SLIDE_THEMES.items() if v is self.theme),
                None,
            )
            grad_colors = self._GRADIENT_MAP.get(theme_name)
            if grad_colors:
                top_c, bot_c = grad_colors
                draw_tmp = ImageDraw.Draw(img)
                # 수직 그라디언트: 한 줄씩 색상 보간 (strip 단위로 블록 채워 성능 최적화)
                strip = max(1, H // 180)  # 약 180 스텝으로 분할
                for y_start in range(0, H, strip):
                    t = y_start / H
                    r = int(top_c[0] + (bot_c[0] - top_c[0]) * t)
                    g = int(top_c[1] + (bot_c[1] - top_c[1]) * t)
                    b = int(top_c[2] + (bot_c[2] - top_c[2]) * t)
                    draw_tmp.rectangle(
                        [0, y_start, W, min(y_start + strip - 1, H - 1)],
                        fill=(r, g, b),
                    )

        draw = ImageDraw.Draw(img)
        return img, draw

    def _draw_header(self, draw, slide_title: str, is_title_page: bool = False) -> None:
        """헤더 영역(배경 + accent 라인 + 채널명/제목)을 그린다.

        페이지 번호 없음.
        - 타이틀 페이지: 채널명만 표시 (없으면 빈 헤더)
        - 일반 페이지: '채널명  |  슬라이드 제목' 표시
        """
        draw.rectangle([0, 0, W, HEADER_H], fill=self.theme["header_bg"])
        draw.rectangle([0, HEADER_H - 3, W, HEADER_H], fill=self.theme["accent"])

        if is_title_page:
            # 타이틀 페이지 - 채널명만 크게
            header_text = self.channel_name
            font = self._font(34, bold=True)
        else:
            # 일반 페이지 - 채널명 | 슬라이드 제목
            if self.channel_name and slide_title:
                header_text = f"{self.channel_name}  |  {slide_title}"
            elif self.channel_name:
                header_text = self.channel_name
            else:
                header_text = slide_title
            font = self._font(28, bold=True)

        if header_text:
            draw.text(
                (MARGIN_X, HEADER_H // 2),
                header_text[:70],
                font=font,
                fill=self.theme["text_primary"],
                anchor="lm",
            )

    def _draw_footer(self, draw, source: str, page: int, total: int) -> None:
        """푸터 영역(출처 텍스트)을 그린다."""
        fy = H - FOOTER_H
        draw.rectangle([0, fy, W, H], fill=self.theme.get("source_bg", self.theme["bg"]))
        if source:
            sfont = self._font(22)
            draw.text(
                (MARGIN_X, fy + FOOTER_H // 2),
                f"출처: {source[:60]}",
                font=sfont,
                fill=self.theme["text_secondary"],
                anchor="lm",
            )

    def _draw_branding_bar(self, img, draw) -> None:
        """하단 브랜딩 바 - 하단 60px에 반투명 오버레이 + 채널명 텍스트.

        채널명이 없으면 아무것도 그리지 않는다.
        Image 객체가 필요한 이유: ImageDraw는 RGBA alpha 합성 불가 -> 별도 레이어 paste.
        """
        if not self.channel_name:
            return
        from PIL import Image, ImageDraw as _ID

        bar_h = 60
        bar_y = H - bar_h

        # 반투명 레이어 생성 (알파 128 = 50% 불투명)
        overlay = Image.new("RGBA", (W, bar_h), (0, 0, 0, 128))
        # 원본 이미지를 RGBA로 변환하지 않고 paste로 합성 (mask 사용)
        img.paste(overlay, (0, bar_y), overlay)

        # 합성 후 draw 객체로 채널명 텍스트 출력
        bfont = self._font(24, bold=True)
        draw.text(
            (MARGIN_X, bar_y + bar_h // 2),
            self.channel_name[:50],
            font=bfont,
            fill=(255, 255, 255),
            anchor="lm",
        )

    def _wrap_text(self, draw, text: str, font, max_width: int) -> list:
        """한글/영문 혼용 텍스트를 max_width 픽셀 기준으로 줄바꿈한다."""
        lines = []
        current = ""
        for ch in text:
            test = current + ch
            try:
                bbox = draw.textbbox((0, 0), test, font=font)
                w = bbox[2] - bbox[0]
            except Exception:
                w = len(test) * (font.size if hasattr(font, "size") else 12)
            if w > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def render_title(self, slide: dict, page: int, total: int) -> "Image.Image":
        """타이틀 슬라이드 렌더링.

        헤더 강조: 타이틀 슬라이드의 헤더 폰트 크기를 10% 키우고 하단에 3px 밑줄 라인 추가.
        """
        img, draw = self._make_base_image(gradient=True)
        title = slide.get("title", "")
        subtitle = slide.get("subtitle", "")

        # 타이틀 페이지 헤더 - 폰트 10% 증가 (34 -> 38), 3px 밑줄 라인
        draw.rectangle([0, 0, W, HEADER_H], fill=self.theme["header_bg"])
        draw.rectangle([0, HEADER_H - 3, W, HEADER_H], fill=self.theme["accent"])
        if self.channel_name:
            header_font_title = self._font(38, bold=True)  # 34 * 1.10 ~ 38
            draw.text(
                (MARGIN_X, HEADER_H // 2),
                self.channel_name[:70],
                font=header_font_title,
                fill=self.theme["text_primary"],
                anchor="lm",
            )
        # 헤더 하단 3px 강조 라인 (accent 라인 위에 추가 강조)
        draw.rectangle([0, HEADER_H, W, HEADER_H + 3], fill=self.theme["accent_light"])

        tfont = self._font(68, bold=True)
        lines = self._wrap_text(draw, title, tfont, W - MARGIN_X * 2)
        y_start = H // 2 - len(lines) * 75 // 2 - 40
        for line in lines[:3]:
            try:
                bbox = draw.textbbox((0, 0), line, font=tfont)
                x = (W - (bbox[2] - bbox[0])) // 2
            except Exception:
                x = MARGIN_X
            draw.text((x, y_start), line, font=tfont, fill=self.theme["text_primary"])
            y_start += 80

        draw.rectangle(
            [W // 2 - 120, y_start + 8, W // 2 + 120, y_start + 12],
            fill=self.theme["accent"],
        )

        if subtitle:
            sfont = self._font(34)
            slines = self._wrap_text(draw, subtitle, sfont, W - MARGIN_X * 2)
            y2 = y_start + 28
            for sline in slines[:2]:
                try:
                    bbox = draw.textbbox((0, 0), sline, font=sfont)
                    x = (W - (bbox[2] - bbox[0])) // 2
                except Exception:
                    x = MARGIN_X
                draw.text((x, y2), sline, font=sfont, fill=self.theme["text_secondary"])
                y2 += 42

        # 하단 브랜딩 바 추가
        self._draw_branding_bar(img, draw)
        return img

    def render_content(self, slide: dict, page: int, total: int) -> "Image.Image":
        """일반 콘텐츠 슬라이드 렌더링."""
        img, draw = self._make_base_image()
        self._draw_header(draw, slide.get("title", ""))
        self._draw_footer(draw, slide.get("source", ""), page, total)

        bullets = slide.get("bullets", [])
        bfont = self._font(34)
        footer_y = H - FOOTER_H
        avail_h = footer_y - CONTENT_Y - 10
        spacing = min(95, avail_h // max(1, len(bullets)))
        y = CONTENT_Y + 15

        for bullet in bullets[:5]:
            draw.ellipse(
                [MARGIN_X, y + 14, MARGIN_X + 14, y + 28],
                fill=self.theme["bullet_dot"],
            )
            lines = self._wrap_text(draw, bullet, bfont, W - MARGIN_X * 2 - 30)
            for i, line in enumerate(lines[:2]):
                color = (
                    self.theme["text_primary"] if i == 0 else self.theme["text_secondary"]
                )
                draw.text((MARGIN_X + 25, y + i * 38), line, font=bfont, fill=color)
            y += spacing

        # 하단 브랜딩 바 추가
        self._draw_branding_bar(img, draw)
        return img

    def render_summary(self, slide: dict, page: int, total: int) -> "Image.Image":
        """핵심 요약 슬라이드 렌더링."""
        img, draw = self._make_base_image()
        self._draw_header(draw, slide.get("title", "핵심 요약"))

        bullets = slide.get("bullets", [])
        nfont = self._font(50, bold=True)
        tfont = self._font(32)
        avail_h = (H - FOOTER_H) - CONTENT_Y - 10
        spacing = avail_h // max(1, len(bullets))
        y = CONTENT_Y + 10

        for i, bullet in enumerate(bullets[:4], start=1):
            draw.text((MARGIN_X, y), f"{i:02d}", font=nfont, fill=self.theme["accent"])
            lines = self._wrap_text(draw, bullet, tfont, W - MARGIN_X * 2 - 80)
            for j, line in enumerate(lines[:2]):
                draw.text(
                    (MARGIN_X + 80, y + j * 36),
                    line,
                    font=tfont,
                    fill=self.theme["text_primary"],
                )
            y += spacing
            if i < len(bullets):
                draw.rectangle(
                    [MARGIN_X, y - 5, W - MARGIN_X, y - 4],
                    fill=self.theme["divider"],
                )

        # 하단 브랜딩 바 추가
        self._draw_branding_bar(img, draw)
        return img

    def render_content_with_chart(
        self,
        slide: dict,
        chart_img_path: str,
        page: int,
        total: int,
    ) -> "Image.Image":
        """텍스트(좌 60%) + 차트 이미지(우 40%) 레이아웃 슬라이드 렌더링.

        차트 이미지 로드 실패 시 render_content 폴백.
        """
        from PIL import Image

        img, draw = self._make_base_image()
        self._draw_header(draw, slide.get("title", ""))
        self._draw_footer(draw, slide.get("source", ""), page, total)

        # 텍스트 영역 - 좌측 60%에 bullets 렌더링
        bullets = slide.get("bullets", [])
        bfont = self._font(30)
        footer_y = H - FOOTER_H
        avail_h = footer_y - CONTENT_Y - 10
        spacing = min(90, avail_h // max(1, len(bullets)))
        y = CONTENT_Y + 15

        for bullet in bullets[:5]:
            draw.ellipse(
                [MARGIN_X, y + 12, MARGIN_X + 12, y + 24],
                fill=self.theme["bullet_dot"],
            )
            lines = self._wrap_text(draw, bullet, bfont, TEXT_AREA_W - 25)
            for i, line in enumerate(lines[:2]):
                color = (
                    self.theme["text_primary"] if i == 0 else self.theme["text_secondary"]
                )
                draw.text((MARGIN_X + 22, y + i * 35), line, font=bfont, fill=color)
            y += spacing

        # 구분선 - 텍스트/차트 경계
        draw.rectangle(
            [CHART_PANEL_X, HEADER_H, CHART_PANEL_X + 1, H - FOOTER_H],
            fill=self.theme["divider"],
        )

        # 차트 이미지 붙이기
        try:
            chart_img = Image.open(chart_img_path).convert("RGB")
            chart_img = chart_img.resize(
                (CHART_PANEL_W, CHART_PANEL_H), Image.LANCZOS
            )
            img.paste(chart_img, (CHART_PANEL_X + 10, CHART_PANEL_Y))
        except Exception as e:
            logger.warning(f"[SlideRenderer] 차트 이미지 로드 실패 - 폴백: {e}")
            return self.render_content(slide, page, total)

        # 하단 브랜딩 바 추가
        self._draw_branding_bar(img, draw)
        return img

    def render_quote(self, slide: dict, page: int, total: int) -> "Image.Image":
        """인용/수치 슬라이드 렌더링 (type=="quote")."""
        img, draw = self._make_base_image()
        self._draw_header(draw, slide.get("title", ""))

        quote = slide.get(
            "quote",
            slide.get("bullets", [""])[0] if slide.get("bullets") else "",
        )
        qfont = self._font(52, bold=True)
        lines = self._wrap_text(draw, quote, qfont, W - MARGIN_X * 2)
        y = H // 2 - len(lines) * 60 // 2

        for line in lines[:3]:
            try:
                bbox = draw.textbbox((0, 0), line, font=qfont)
                x = (W - (bbox[2] - bbox[0])) // 2
            except Exception:
                x = MARGIN_X
            draw.text((x, y), line, font=qfont, fill=self.theme["accent_light"])
            y += 65

        self._draw_footer(draw, slide.get("source", ""), page, total)
        # 하단 브랜딩 바 추가
        self._draw_branding_bar(img, draw)
        return img


# -- 카드뉴스 테마 상수 --
CARDNEWS_THEMES = {
    "dark_blue": {
        "bg":             (10, 22, 40),
        "accent":         (74, 159, 212),    # #4a9fd4
        "accent_dark":    (14, 36, 84),      # 헤더 블록
        "text_primary":   (255, 255, 255),
        "text_secondary": (160, 200, 230),
        "number_bg":      (74, 159, 212),
        "number_text":    (255, 255, 255),
        "check_color":    (74, 159, 212),
        "divider":        (40, 80, 130),
        "channel_bar":    (8, 16, 32),
    },
    "warm_gray": {
        "bg":             (26, 22, 20),
        "accent":         (232, 165, 75),    # #e8a54b
        "accent_dark":    (45, 35, 25),
        "text_primary":   (245, 237, 224),
        "text_secondary": (180, 155, 120),
        "number_bg":      (232, 165, 75),
        "number_text":    (26, 22, 20),
        "check_color":    (232, 165, 75),
        "divider":        (70, 55, 40),
        "channel_bar":    (15, 12, 10),
    },
    "clean_white": {
        "bg":             (248, 249, 250),
        "accent":         (37, 99, 235),     # #2563eb
        "accent_dark":    (30, 64, 175),
        "text_primary":   (15, 23, 42),
        "text_secondary": (71, 85, 105),
        "number_bg":      (37, 99, 235),
        "number_text":    (255, 255, 255),
        "check_color":    (37, 99, 235),
        "divider":        (203, 213, 225),
        "channel_bar":    (15, 23, 42),
    },
}


class CardNewsRenderer:
    """카드뉴스 스타일 슬라이드 렌더러.

    슬라이드 타입별로 완전히 다른 레이아웃을 사용한다.
    페이지 번호 없음.
    SlideRenderer와 독립적으로 동작하며 CARDNEWS_THEMES를 사용한다.
    """

    W, H = 1280, 720

    def __init__(self, theme_name: str = "dark_blue", channel_name: str = ""):
        # CARDNEWS_THEMES에서 테마 딕셔너리를 가져온다. 없으면 dark_blue 폴백.
        self.theme = CARDNEWS_THEMES.get(theme_name, CARDNEWS_THEMES["dark_blue"])
        # 하단 채널 브랜딩 바에 표시할 채널명
        self.channel_name = channel_name
        # 사용자 지정 폰트 경로 목록 (빈 리스트면 기본 FONT_CANDIDATES 사용)
        self._extra: list[str] = []

    def set_custom_font(self, font_path: str) -> None:
        """사용자 지정 폰트 경로를 설정한다."""
        self._extra = [font_path] if font_path else []

    def _font(self, size: int, bold: bool = False) -> "ImageFont.FreeTypeFont":
        """self._extra를 추가해 _load_font를 호출하는 헬퍼."""
        return _load_font(size, bold=bold, extra_candidates=self._extra)

    def _base_image(self):
        """단색 배경 이미지와 Draw 객체를 반환한다."""
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (self.W, self.H), self.theme["bg"])
        draw = ImageDraw.Draw(img)
        return img, draw

    def _draw_channel_bar(self, img, draw) -> None:
        """하단 48px 채널 브랜딩 바를 그린다.

        바 상단에 2px accent 라인을 추가하고 채널명을 표시한다.
        채널명이 없어도 바 자체는 그린다.
        """
        bar_h = 48
        y = self.H - bar_h
        draw.rectangle([0, y, self.W, self.H], fill=self.theme["channel_bar"])
        # 상단 2px accent 라인
        draw.rectangle([0, y, self.W, y + 2], fill=self.theme["accent"])
        if self.channel_name:
            font = self._font(18, bold=False)
            draw.text((40, y + 14), self.channel_name, font=font, fill=self.theme["text_secondary"])

    def render_title(self, slide: dict) -> "Image.Image":
        """title 슬라이드: 상단 채널 바 + 중앙 accent 세로 바 + 대형 주제 텍스트."""
        from PIL import Image, ImageDraw
        img, draw = self._base_image()
        t = self.theme

        title_text = _normalize_text(slide.get("title", slide.get("header", "")))
        subtitle = _normalize_text(slide.get("subtitle", ""))
        if not subtitle:
            # bullets 첫 항목을 서브타이틀로 사용
            bullets = slide.get("bullets", [])
            subtitle = _normalize_text(bullets[0]) if bullets else ""

        # 상단 채널 바 (60px) - accent_dark 배경 + 하단 2px accent 라인
        draw.rectangle([0, 0, self.W, 60], fill=t["channel_bar"])
        draw.rectangle([0, 58, self.W, 60], fill=t["accent"])
        if self.channel_name:
            ch_font = self._font(20, bold=False)
            draw.text((40, 18), self.channel_name, font=ch_font, fill=t["text_secondary"])

        # 중앙 컨텐츠 영역: Y 80 ~ H-60
        content_y_start = 80
        content_y_end = self.H - 60

        # 제목 텍스트 (최대 2줄, 크게)
        title_font = self._font(62, bold=True)
        side_bar_x = 100
        title_x = side_bar_x + 20
        title_max_w = self.W - title_x - 80
        title_lines = self._wrap_text(title_text, title_font, title_max_w)[:2]

        line_h = 72
        total_title_h = len(title_lines) * line_h
        title_y = (content_y_start + content_y_end) // 2 - total_title_h // 2 - 20

        # accent 세로 바 (좌측 6px, 제목 높이만큼)
        draw.rectangle(
            [side_bar_x, title_y - 8, side_bar_x + 6, title_y + total_title_h + 8],
            fill=t["accent"]
        )

        # 제목 텍스트 출력
        for i, line in enumerate(title_lines):
            draw.text((title_x, title_y + i * line_h), line, font=title_font, fill=t["text_primary"])

        # 서브타이틀 (제목 아래 1줄)
        if subtitle:
            sub_font = self._font(24, bold=False)
            sub_y = title_y + total_title_h + 20
            sub_lines = self._wrap_text(subtitle, sub_font, title_max_w)[:1]
            for line in sub_lines:
                draw.text((title_x, sub_y), line, font=sub_font, fill=t["text_secondary"])

        self._draw_channel_bar(img, draw)
        return img

    def render_content(self, slide: dict) -> "Image.Image":
        """content 슬라이드: accent_dark 헤더 + 번호 박스 + 항목 목록."""
        from PIL import Image, ImageDraw
        img, draw = self._base_image()
        t = self.theme

        header_text = _normalize_text(slide.get("title", slide.get("header", "")))
        bullets = [_normalize_text(b) for b in slide.get("bullets", [])]

        # 헤더 영역 (80px) - accent_dark 배경 + 좌측 6px accent 바
        draw.rectangle([0, 0, self.W, 80], fill=t["accent_dark"])
        draw.rectangle([0, 0, 6, 80], fill=t["accent"])
        header_font = self._font(32, bold=True)
        draw.text((30, 22), header_text, font=header_font, fill=t["text_primary"])

        # 항목 목록 - Y=105부터 시작
        item_y = 105
        item_max_w = self.W - 200  # 번호 박스(70px) + 여백
        item_font = self._font(24, bold=True)
        desc_font = self._font(18, bold=False)
        number_size = 48  # 번호 박스 크기 (정사각형)
        item_gap = 20     # 항목 간 간격

        for i, bullet in enumerate(bullets[:5]):
            if item_y + number_size > self.H - 60:
                break

            # 번호 박스 (정사각형, number_bg 색상)
            box_x, box_y = 50, item_y
            draw.rectangle(
                [box_x, box_y, box_x + number_size, box_y + number_size],
                fill=t["number_bg"]
            )

            # 번호 텍스트 중앙 정렬 (01, 02, ...)
            num_font = self._font(22, bold=True)
            num_text = f"{i+1:02d}"
            num_bbox = draw.textbbox((0, 0), num_text, font=num_font)
            nw = num_bbox[2] - num_bbox[0]
            nh = num_bbox[3] - num_bbox[1]
            draw.text(
                (box_x + (number_size - nw) // 2, box_y + (number_size - nh) // 2 - 2),
                num_text, font=num_font, fill=t["number_text"]
            )

            # bullet 텍스트: " — " 또는 ": " 구분자로 굵은 본문 + 설명 분리
            text_x = box_x + number_size + 18
            parts = bullet.split(" -- ", 1) if " -- " in bullet else bullet.split(": ", 1)
            if len(parts) == 2:
                main_part, desc_part = parts
                main_lines = self._wrap_text(main_part, item_font, item_max_w)[:1]
                draw.text(
                    (text_x, box_y + 4),
                    main_lines[0] if main_lines else main_part,
                    font=item_font, fill=t["text_primary"]
                )
                desc_lines = self._wrap_text(desc_part, desc_font, item_max_w)[:1]
                draw.text(
                    (text_x, box_y + 32),
                    desc_lines[0] if desc_lines else desc_part,
                    font=desc_font, fill=t["text_secondary"]
                )
            else:
                main_lines = self._wrap_text(bullet, item_font, item_max_w)[:2]
                for li, ml in enumerate(main_lines):
                    draw.text((text_x, box_y + li * 28), ml, font=item_font, fill=t["text_primary"])

            item_y += number_size + item_gap

        self._draw_channel_bar(img, draw)
        return img

    def render_summary(self, slide: dict) -> "Image.Image":
        """summary 슬라이드: 상단 accent 블록 + 체크마크 목록."""
        from PIL import Image, ImageDraw
        img, draw = self._base_image()
        t = self.theme

        header_text = _normalize_text(slide.get("title", slide.get("header", "핵심 정리")))
        bullets = [_normalize_text(b) for b in slide.get("bullets", [])]

        # 상단 accent 블록 (120px) - accent_dark 배경 + 하단 4px accent 라인
        draw.rectangle([0, 0, self.W, 120], fill=t["accent_dark"])
        draw.rectangle([0, 118, self.W, 122], fill=t["accent"])
        # SUMMARY 레이블 (소문자 스타일)
        label_font = self._font(18, bold=False)
        draw.text((40, 16), "SUMMARY", font=label_font, fill=t["accent"])
        # 헤더 제목
        title_font = self._font(38, bold=True)
        draw.text((40, 44), header_text, font=title_font, fill=t["text_primary"])

        # 체크마크 목록 - Y=140부터
        item_y = 140
        check_font = self._font(22, bold=False)
        check_char = "v"  # 특수문자 대신 v 사용 (인코딩 안전)

        for bullet in bullets[:5]:
            if item_y + 32 > self.H - 60:
                break
            # 체크마크 기호
            draw.text((50, item_y), check_char, font=check_font, fill=t["check_color"])
            # 항목 텍스트 (최대 2줄)
            lines = self._wrap_text(bullet, check_font, self.W - 120)[:2]
            for li, line in enumerate(lines):
                draw.text((90, item_y + li * 28), line, font=check_font, fill=t["text_primary"])
            item_y += 28 * len(lines) + 16

        self._draw_channel_bar(img, draw)
        return img

    def render_quote(self, slide: dict) -> "Image.Image":
        """quote 슬라이드: 대형 인용 기호 + 중앙 인용 텍스트 + 출처."""
        from PIL import Image, ImageDraw
        img, draw = self._base_image()
        t = self.theme

        bullets = slide.get("bullets", [])
        quote_text = _normalize_text(bullets[0]) if bullets else _normalize_text(slide.get("title", ""))
        source_text = _normalize_text(bullets[1]) if len(bullets) > 1 else ""

        # 대형 인용 기호 (좌상단)
        quote_mark_font = self._font(120, bold=True)
        draw.text((60, 40), '"', font=quote_mark_font, fill=t["accent"])

        # 인용 텍스트 (중앙 정렬)
        quote_font = self._font(32, bold=False)
        lines = self._wrap_text(quote_text, quote_font, self.W - 160)[:4]
        total_h = len(lines) * 44
        start_y = (self.H - 60) // 2 - total_h // 2 + 20
        for i, line in enumerate(lines):
            draw.text((80, start_y + i * 44), line, font=quote_font, fill=t["text_primary"])

        # 구분선 + 출처 텍스트
        if source_text:
            line_y = start_y + total_h + 20
            draw.rectangle([80, line_y, self.W - 80, line_y + 2], fill=t["divider"])
            src_font = self._font(18, bold=False)
            draw.text((80, line_y + 10), source_text, font=src_font, fill=t["text_secondary"])

        self._draw_channel_bar(img, draw)
        return img

    def render_content_with_chart(self, slide: dict, chart_path: str) -> "Image.Image":
        """content 슬라이드에 우측 차트 패널을 추가한 버전.

        레이아웃: 좌측 항목 텍스트(최대 3개) / 우측 460x540 차트 이미지.
        차트 로드 실패 시 render_content()로 폴백한다.
        """
        from PIL import Image, ImageDraw

        img, draw = self._base_image()
        t = self.theme

        header_text = _normalize_text(slide.get("title", slide.get("header", "")))
        bullets = [_normalize_text(b) for b in slide.get("bullets", [])]

        # 헤더 블록 (80px) - accent_dark 배경 + 좌측 6px accent 바
        draw.rectangle([0, 0, self.W, 80], fill=t["accent_dark"])
        draw.rectangle([0, 0, 6, 80], fill=t["accent"])
        header_font = self._font(28, bold=True)
        draw.text((30, 22), header_text, font=header_font, fill=t["text_primary"])

        # 차트 패널 좌표 (우측 460x540)
        CHART_X = 780
        CHART_Y = 90
        CHART_W = 460
        CHART_H = 540

        # 차트 이미지 붙이기
        try:
            chart_img = Image.open(chart_path).convert("RGB")
            chart_img = chart_img.resize((CHART_W, CHART_H), Image.LANCZOS)
            img.paste(chart_img, (CHART_X, CHART_Y))
            # 차트 테두리 (1px accent 색)
            draw.rectangle(
                [CHART_X - 1, CHART_Y - 1, CHART_X + CHART_W, CHART_Y + CHART_H],
                outline=t["accent"], width=1
            )
        except Exception as e:
            logger.warning(f"[CardNewsRenderer] 차트 삽입 실패 - render_content 폴백: {e}")
            return self.render_content(slide)

        # 좌측 항목 목록 (최대 3개, 번호 박스 포함)
        item_y = 100
        item_font = self._font(22, bold=True)
        desc_font = self._font(17, bold=False)
        number_size = 44
        LEFT_MAX_W = CHART_X - 100  # 좌측 항목 텍스트 최대 너비

        for i, bullet in enumerate(bullets[:3]):
            if item_y + number_size > self.H - 60:
                break

            box_x = 40
            # 번호 박스
            draw.rectangle(
                [box_x, item_y, box_x + number_size, item_y + number_size],
                fill=t["number_bg"]
            )
            num_font = self._font(20, bold=True)
            num_text = f"{i + 1:02d}"
            num_bbox = draw.textbbox((0, 0), num_text, font=num_font)
            nw = num_bbox[2] - num_bbox[0]
            nh = num_bbox[3] - num_bbox[1]
            draw.text(
                (box_x + (number_size - nw) // 2, item_y + (number_size - nh) // 2 - 2),
                num_text, font=num_font, fill=t["number_text"]
            )

            # bullet 텍스트: " - " 구분자로 본문/설명 분리
            text_x = box_x + number_size + 14
            parts = bullet.split(" - ", 1) if " - " in bullet else [bullet]
            main_lines = self._wrap_text(parts[0], item_font, LEFT_MAX_W - text_x)[:1]
            draw.text(
                (text_x, item_y + 4),
                main_lines[0] if main_lines else parts[0][:30],
                font=item_font, fill=t["text_primary"]
            )
            if len(parts) > 1:
                desc_lines = self._wrap_text(parts[1], desc_font, LEFT_MAX_W - text_x)[:1]
                draw.text(
                    (text_x, item_y + 30),
                    desc_lines[0] if desc_lines else parts[1][:40],
                    font=desc_font, fill=t["text_secondary"]
                )

            item_y += number_size + 18

        self._draw_channel_bar(img, draw)
        return img

    def render(self, slide: dict) -> "Image.Image":
        """슬라이드 타입별 render 메서드를 디스패치한다.

        type 키 기준: title -> render_title, summary -> render_summary,
        quote -> render_quote, 그 외 -> render_content.
        """
        slide_type = slide.get("type", "content")
        if slide_type == "title":
            return self.render_title(slide)
        elif slide_type == "summary":
            return self.render_summary(slide)
        elif slide_type == "quote":
            return self.render_quote(slide)
        else:
            return self.render_content(slide)

    @staticmethod
    def _wrap_text(text: str, font, max_width: int) -> list[str]:
        """텍스트를 max_width 픽셀에 맞게 단어 단위로 줄바꿈한다.

        임시 이미지의 Draw 객체로 텍스트 폭을 측정한다.
        단어 단위로 추가하며 max_width 초과 시 개행한다.
        """
        from PIL import ImageDraw, Image
        tmp = Image.new("RGB", (1, 1))
        tmp_draw = ImageDraw.Draw(tmp)

        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = tmp_draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [text]


class Stage04VideoGen(BaseStage, BasePipeline):
    """F006 STAGE_04 - Pillow 기반 PPT 슬라이드 이미지 생성.

    ComfyUI 의존성 없이 로컬 Pillow만으로 1280x720 PNG 슬라이드를 생성한다.
    슬라이드 타입(title/content/summary/quote)에 따라 전용 렌더러를 호출한다.
    STAGE_05에서 narration 비례 배분을 위해 clips에 narration 필드를 포함한다.
    출력 경로는 storage/results/f006/{job_id}/slides/로 설정된다.
    """

    STAGE_ID: str = "STAGE_04_VIDEO_GEN"
    STAGE_ORDER: int = 4

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE04", "name": "STAGE_04_VIDEO_GEN"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 유효성 검증 - slides 또는 scenes 키 중 하나 이상 존재해야 통과."""
        slides = data.get("slides") or data.get("scenes", [])
        if not slides:
            return ValidationResult(
                is_valid=False,
                rejection_reason="slides 데이터 없음. STAGE_02에서 슬라이드 구조를 생성하세요.",
                rejection_target="STAGE_02_SCRIPT",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_04 실행 - 슬라이드별 PNG 이미지 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                slides (list): 슬라이드 목록 (STAGE_02 출력)
                scenes (list): slides 없을 때 폴백 키 (동일 구조)
                selected_topic (str): 주제명 (로그용)
                slide_theme (str): 테마명 (dark_blue/dark_green/corporate)
            }

        Returns:
            {
                stage_id, status, generation_backend,
                clips: [{slide_no, file_path, duration_sec, narration, type}],
                thumbnail_path, thumbnail_candidates, total_clips, generated_at
            }
        """
        logger.info(f"[F006][STAGE_04][job_id={job_id}] 슬라이드 생성 시작")

        slides = input_data.get("slides") or input_data.get("scenes", [])
        selected_topic = input_data.get("selected_topic", "주제")
        theme_name = input_data.get("slide_theme", DEFAULT_THEME)
        channel_name: str = input_data.get("channel_name", "") or input_data.get("channel_category", "")
        render_mode: str = input_data.get("render_mode", "ffmpeg")

        custom_font = input_data.get("slide_font_path", "")
        if custom_font:
            logger.info(f"[F006][STAGE_04][job_id={job_id}] 사용자 지정 폰트 경로: {custom_font}")

        # 출력 디렉토리 - f006 경로 사용 (절대 경로, ERR-007 방지)
        project_root = Path(__file__).parent.parent.parent.parent
        output_dir = (
            project_root / "storage" / "results" / "f006" / str(job_id) / "slides"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        # -- cardnews 모드: CardNewsRenderer로 슬라이드 PNG 생성 후 즉시 반환 --
        if render_mode == "cardnews":
            logger.info(
                f"[F006][STAGE_04][job_id={job_id}] render_mode=cardnews "
                f"-> CardNewsRenderer (theme={theme_name})"
            )
            slides = [_clean_slide(s) for s in slides]
            cn_renderer = CardNewsRenderer(theme_name=theme_name, channel_name=channel_name)
            if custom_font:
                cn_renderer.set_custom_font(custom_font)

            # cardnews 차트 인프라 초기화
            from pipelines.f006_youtube_v4.stages.chart_generator import (
                extract_ticker, detect_indicators, ChartGenerator
            )
            _cn_user_context = input_data.get("user_context", "")
            _cn_ticker = extract_ticker(selected_topic, _cn_user_context)
            _cn_effective_ticker: str = _cn_ticker or "^KS11"
            cn_chart_dir = output_dir.parent / "charts"
            cn_chart_dir.mkdir(parents=True, exist_ok=True)
            _cn_theme = CARDNEWS_THEMES.get(theme_name, CARDNEWS_THEMES["dark_blue"])
            cn_chart_gen = ChartGenerator(theme_colors=_cn_theme)

            cn_clips: list[dict] = []
            for slide in slides:
                slide_no: int = slide.get("slide_no", len(cn_clips) + 1)
                slide_type: str = slide.get("type", "content")
                is_last_cn: bool = (slide_no == len(slides))
                out_path = str(output_dir / f"slide_{slide_no:02d}.png")
                try:
                    # content 슬라이드 + 마지막 슬라이드 아님 -> 차트 감지 시도
                    cn_chart_path = None
                    if slide_type == "content" and not is_last_cn:
                        slide_text = (
                            slide.get("title", "")
                            + " "
                            + " ".join(slide.get("bullets", []))
                        )
                        cn_indicators = detect_indicators(slide_text)
                        if cn_indicators:
                            cn_chart_out = str(cn_chart_dir / f"chart_cn_{slide_no:02d}.png")
                            cn_ok = cn_chart_gen.generate(
                                ticker=_cn_effective_ticker,
                                indicators=cn_indicators,
                                output_path=cn_chart_out,
                                period="3mo",
                                chart_size=(460, 540),
                            )
                            if cn_ok:
                                cn_chart_path = cn_chart_out
                                logger.info(
                                    f"[F006][STAGE_04][job_id={job_id}] "
                                    f"[cardnews] 슬라이드 {slide_no} 차트 생성: {cn_indicators}"
                                )

                    if cn_chart_path:
                        img = cn_renderer.render_content_with_chart(slide, cn_chart_path)
                    else:
                        img = cn_renderer.render(slide)

                    img.save(out_path, "PNG")
                    narration: str = slide.get("narration", slide.get("description", ""))
                    cn_clips.append({
                        "slide_no": slide_no,
                        "file_path": out_path,
                        "duration_sec": 0,      # STAGE_05에서 narration 비례로 재계산
                        "narration": narration,
                        "type": slide_type,
                    })
                    logger.info(
                        f"[F006][STAGE_04][job_id={job_id}] "
                        f"[cardnews] 슬라이드 {slide_no} 완료"
                    )
                except Exception as e:
                    logger.warning(
                        f"[F006][STAGE_04][job_id={job_id}] "
                        f"[cardnews] 슬라이드 {slide_no} 실패: {e}"
                    )

            # 폴백: 전체 실패 시 검정 슬라이드 1장
            if not cn_clips:
                fallback_path = str(output_dir / "slide_01.png")
                try:
                    from PIL import Image as _PILImage
                    _PILImage.new("RGB", (W, H), (10, 22, 40)).save(fallback_path, "PNG")
                    cn_clips.append({
                        "slide_no": 1,
                        "file_path": fallback_path,
                        "duration_sec": 5,
                        "narration": "",
                        "type": "content",
                    })
                    logger.warning(
                        f"[F006][STAGE_04][job_id={job_id}] [cardnews] 폴백 슬라이드 생성 완료"
                    )
                except Exception as fe:
                    logger.error(f"[F006][STAGE_04] [cardnews] 폴백 슬라이드 생성 실패: {fe}")

            # 썸네일 - 첫 번째 슬라이드 복사
            cn_thumbnail: Optional[str] = None
            if cn_clips:
                import shutil as _shutil
                thumb_dir = (
                    project_root / "storage" / "results" / "f006" / str(job_id) / "thumbnails"
                )
                thumb_dir.mkdir(parents=True, exist_ok=True)
                cn_thumbnail = str(thumb_dir / "thumbnail.png")
                try:
                    _shutil.copy2(cn_clips[0]["file_path"], cn_thumbnail)
                except Exception as te:
                    logger.warning(f"[F006][STAGE_04] [cardnews] 썸네일 복사 실패: {te}")
                    cn_thumbnail = None

            logger.info(
                f"[F006][STAGE_04][job_id={job_id}] [cardnews] 완료 - 슬라이드 {len(cn_clips)}장"
            )
            return {
                "stage_id": "STAGE_04_VIDEO_GEN",
                "status": "COMPLETED",
                "generation_backend": "cardnews",
                "clips": cn_clips,
                "thumbnail_path": cn_thumbnail,
                "thumbnail_candidates": [cn_thumbnail] if cn_thumbnail else [],
                "total_clips": len(cn_clips),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        # -- 이하 기존 PPT 슬라이드(SlideRenderer) 처리 --
        theme = SLIDE_THEMES.get(theme_name, SLIDE_THEMES[DEFAULT_THEME])
        renderer = SlideRenderer(theme=theme, custom_font_path=custom_font, channel_name=channel_name)
        total = len(slides)
        clips: list[dict] = []

        # -- 우측 패널 이미지 인프라 초기화 --
        # 전략 결정은 슬라이드 단위로 수행 (채널 카테고리가 아닌 슬라이드 텍스트 기반).
        # 슬라이드 텍스트에 금융 지표 키워드 존재 -> 차트 우선
        # 지표 키워드 없고 채널 카테고리 존재 -> image_fetcher
        # 둘 다 없으면 -> 텍스트 전용 레이아웃
        channel_category: str = input_data.get("channel_category", "")

        from pipelines.f006_youtube_v4.stages.chart_generator import (
            extract_ticker, detect_indicators, ChartGenerator
        )

        user_context = input_data.get("user_context", "")
        ticker = extract_ticker(selected_topic, user_context)

        # 티커 없어도 지표 키워드가 있으면 KOSPI 기본 티커로 차트 생성
        # ^KS11 = KOSPI 지수 - 종목 불명 시 시장 전반 차트로 대체
        _DEFAULT_TICKER = "^KS11"
        effective_ticker: Optional[str] = ticker or _DEFAULT_TICKER

        # 차트 인프라 - 항상 준비 (슬라이드별 지표 감지 후 필요 시 사용)
        chart_dir = output_dir.parent / "charts"
        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_gen = ChartGenerator(theme_colors=theme)

        # 이미지 fetcher 제거 - 지표 차트만 허용 (카테고리 랜덤 이미지 사용 안 함)

        logger.info(
            f"[F006][STAGE_04][job_id={job_id}] "
            f"ticker={ticker or '없음'} effective={effective_ticker} "
            f"channel_name={channel_name or '없음'}"
        )

        # 슬라이드 텍스트 정규화 - □ 제거, ₩->원, 금액 만원 단위 통일
        slides = [_clean_slide(s) for s in slides]

        for slide in slides:
            slide_no: int = slide.get("slide_no", len(clips) + 1)
            slide_type: str = slide.get("type", "content")
            is_last_slide: bool = (slide_no == len(slides))
            out_path = str(output_dir / f"slide_{slide_no:02d}.png")

            try:
                # 우측 패널 차트 - content 타입 + 금융 지표 감지 시에만 생성
                # summary(핵심요약) 또는 마지막 슬라이드는 차트 없음
                chart_path = None
                if slide_type == "content" and not is_last_slide:
                    slide_text = (
                        slide.get("title", "")
                        + " "
                        + " ".join(slide.get("bullets", []))
                    )
                    indicators = detect_indicators(slide_text)

                    if indicators:
                        # 금융 지표 키워드 감지 -> 차트 생성 (티커 없으면 ^KS11 기본값)
                        chart_out = str(chart_dir / f"chart_{slide_no:02d}.png")
                        ok = chart_gen.generate(
                            ticker=effective_ticker,
                            indicators=indicators,
                            output_path=chart_out,
                            period="3mo",
                            chart_size=(CHART_PANEL_W, CHART_PANEL_H),
                        )
                        if ok:
                            chart_path = chart_out
                            logger.info(
                                f"[F006][STAGE_04][job_id={job_id}] "
                                f"슬라이드 {slide_no}: 지표={indicators} 차트 생성"
                            )
                    # 지표 없으면 -> 차트/이미지 없이 텍스트 전용 레이아웃

                if slide_type == "title":
                    img = renderer.render_title(slide, page=slide_no, total=total)
                elif chart_path:
                    img = renderer.render_content_with_chart(
                        slide, chart_path, page=slide_no, total=total
                    )
                elif slide_type == "summary":
                    img = renderer.render_summary(slide, page=slide_no, total=total)
                elif slide_type == "quote":
                    img = renderer.render_quote(slide, page=slide_no, total=total)
                else:
                    img = renderer.render_content(slide, page=slide_no, total=total)

                img.save(out_path, "PNG")

                narration: str = slide.get("narration", slide.get("description", ""))
                clips.append({
                    "slide_no": slide_no,
                    "file_path": out_path,
                    "duration_sec": 0,      # STAGE_05에서 narration 비례로 재계산
                    "narration": narration,
                    "type": slide_type,
                })
                logger.info(
                    f"[F006][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 완료"
                )

            except Exception as e:
                logger.warning(
                    f"[F006][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 실패: {e}"
                )

        # 슬라이드 전체 실패 시 - 검정 슬라이드 1장 생성 (폴백)
        if not clips:
            fallback_path = str(output_dir / "slide_01.png")
            try:
                from PIL import Image

                Image.new("RGB", (W, H), (15, 25, 50)).save(fallback_path, "PNG")
                clips.append({
                    "slide_no": 1,
                    "file_path": fallback_path,
                    "duration_sec": 5,
                    "narration": "",
                    "type": "content",
                })
                logger.warning(
                    f"[F006][STAGE_04][job_id={job_id}] 폴백 슬라이드 생성 완료"
                )
            except Exception as fe:
                logger.error(
                    f"[F006][STAGE_04] 폴백 슬라이드 생성 실패: {fe}"
                )

        # 썸네일 - 첫 번째 슬라이드 복사
        thumbnail_path: Optional[str] = None
        if clips:
            import shutil

            thumb_dir = (
                project_root
                / "storage"
                / "results"
                / "f006"
                / str(job_id)
                / "thumbnails"
            )
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_path = str(thumb_dir / "thumbnail.png")
            try:
                shutil.copy2(clips[0]["file_path"], thumbnail_path)
            except Exception as te:
                logger.warning(
                    f"[F006][STAGE_04] 썸네일 복사 실패: {te}"
                )
                thumbnail_path = None

        logger.info(
            f"[F006][STAGE_04][job_id={job_id}] 완료 - 슬라이드 {len(clips)}장"
        )

        return {
            "stage_id": "STAGE_04_VIDEO_GEN",
            "status": "COMPLETED",
            "generation_backend": "ppt_slide",
            "clips": clips,
            "thumbnail_path": thumbnail_path,
            "thumbnail_candidates": [thumbnail_path] if thumbnail_path else [],
            "total_clips": len(clips),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 유효성 검증 - clips가 비어 있으면 자기 재시도."""
        if not output.get("clips"):
            return ValidationResult(
                is_valid=False,
                rejection_reason="슬라이드 이미지 생성 실패. 재시도합니다.",
                rejection_target="STAGE_04_VIDEO_GEN",
            )
        return ValidationResult(is_valid=True)
