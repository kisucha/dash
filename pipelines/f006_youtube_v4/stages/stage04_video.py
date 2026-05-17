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

    def _make_base_image(self, gradient: bool = False):
        """배경 이미지와 Draw 객체를 생성해 반환한다."""
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (W, H), self.theme["bg"])

        if gradient:
            try:
                import numpy as np

                bg = np.array(self.theme["bg"], dtype=float)
                ac = np.array(self.theme["accent"], dtype=float)
                arr = np.zeros((H, W, 3), dtype=np.uint8)
                for y in range(H):
                    for x in range(W):
                        t = (x / W + y / H) / 2 * 0.18
                        arr[y, x] = (bg * (1 - t) + ac * t).clip(0, 255).astype(np.uint8)
                img = Image.fromarray(arr, "RGB")
            except ImportError:
                pass  # numpy 없으면 단색 유지

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
        """타이틀 슬라이드 렌더링."""
        img, draw = self._make_base_image(gradient=True)
        title = slide.get("title", "")
        subtitle = slide.get("subtitle", "")

        self._draw_header(draw, "", is_title_page=True)

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
        return img


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

        custom_font = input_data.get("slide_font_path", "")
        if custom_font:
            logger.info(f"[F006][STAGE_04][job_id={job_id}] 사용자 지정 폰트 경로: {custom_font}")

        # 출력 디렉토리 - f006 경로 사용 (절대 경로, ERR-007 방지)
        project_root = Path(__file__).parent.parent.parent.parent
        output_dir = (
            project_root / "storage" / "results" / "f006" / str(job_id) / "slides"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

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
