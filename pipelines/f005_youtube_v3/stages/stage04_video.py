# 목적: F005 STAGE_04 — Pillow 기반 PPT 슬라이드 PNG 이미지 생성.
# ComfyUI 없이 로컬에서 1280x720 슬라이드 이미지를 생성한다.

import sys

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f005_youtube_v3.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
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

# -- 폰트 캐시 — 동일 크기/굵기 반복 로드 방지 --
_FONT_CACHE: dict = {}

# 한글 폰트 후보 — 절대 경로(Bold) 우선, 이후 Regular, 이후 영문 폴백
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

    def __init__(self, theme: dict, custom_font_path: str = ""):
        # 테마 딕셔너리 — 색상 참조에 사용
        self.theme = theme
        # 사용자 지정 폰트 경로 — 전역 FONT_CANDIDATES 변경 없이 우선 탐색
        self._extra: list[str] = [custom_font_path] if custom_font_path else []

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

    def _draw_header(self, draw, title: str, page: int, total: int) -> None:
        """헤더 영역(배경 + accent 라인 + 제목 + 페이지)을 그린다."""
        draw.rectangle([0, 0, W, HEADER_H], fill=self.theme["header_bg"])
        draw.rectangle([0, HEADER_H - 3, W, HEADER_H], fill=self.theme["accent"])
        font = self._font(34, bold=True)
        draw.text(
            (MARGIN_X, HEADER_H // 2),
            title[:40],
            font=font,
            fill=self.theme["text_primary"],
            anchor="lm",
        )
        if total > 0:
            pfont = self._font(22)
            draw.text(
                (W - MARGIN_X, HEADER_H // 2),
                f"{page} / {total}",
                font=pfont,
                fill=self.theme["text_secondary"],
                anchor="rm",
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

        self._draw_header(draw, "유튜브 컨텐츠 제작 V3", page, total)

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
        self._draw_header(draw, slide.get("title", ""), page, total)
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
        self._draw_header(draw, slide.get("title", "핵심 요약"), page, total)

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
        self._draw_header(draw, slide.get("title", ""), page, total)
        self._draw_footer(draw, slide.get("source", ""), page, total)

        # 텍스트 영역 — 좌측 60%에 bullets 렌더링
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

        # 구분선 — 텍스트/차트 경계
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
            logger.warning(f"[SlideRenderer] 차트 이미지 로드 실패 — 폴백: {e}")
            return self.render_content(slide, page, total)

        return img

    def render_quote(self, slide: dict, page: int, total: int) -> "Image.Image":
        """인용/수치 슬라이드 렌더링 (type=="quote")."""
        img, draw = self._make_base_image()
        self._draw_header(draw, slide.get("title", ""), page, total)

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
    """F005 STAGE_04 — Pillow 기반 PPT 슬라이드 이미지 생성.

    ComfyUI 의존성 없이 로컬 Pillow만으로 1280x720 PNG 슬라이드를 생성한다.
    슬라이드 타입(title/content/summary/quote)에 따라 전용 렌더러를 호출한다.
    STAGE_05에서 narration 비례 배분을 위해 clips에 narration 필드를 포함한다.
    출력 경로는 storage/results/f005/{job_id}/slides/로 설정된다.
    """

    STAGE_ID: str = "STAGE_04_VIDEO_GEN"
    STAGE_ORDER: int = 4

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F005_STAGE04", "name": "STAGE_04_VIDEO_GEN"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 유효성 검증 — slides 또는 scenes 키 중 하나 이상 존재해야 통과."""
        slides = data.get("slides") or data.get("scenes", [])
        if not slides:
            return ValidationResult(
                is_valid=False,
                rejection_reason="slides 데이터 없음. STAGE_02에서 슬라이드 구조를 생성하세요.",
                rejection_target="STAGE_02_SCRIPT",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_04 실행 — 슬라이드별 PNG 이미지 생성.

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
        logger.info(f"[F005][STAGE_04][job_id={job_id}] 슬라이드 생성 시작")

        slides = input_data.get("slides") or input_data.get("scenes", [])
        selected_topic = input_data.get("selected_topic", "주제")
        theme_name = input_data.get("slide_theme", DEFAULT_THEME)

        custom_font = input_data.get("slide_font_path", "")
        if custom_font:
            logger.info(f"[F005][STAGE_04][job_id={job_id}] 사용자 지정 폰트 경로: {custom_font}")

        # 출력 디렉토리 — f005 경로 사용 (절대 경로, ERR-007 방지)
        project_root = Path(__file__).parent.parent.parent.parent
        output_dir = (
            project_root / "storage" / "results" / "f005" / str(job_id) / "slides"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        theme = SLIDE_THEMES.get(theme_name, SLIDE_THEMES[DEFAULT_THEME])
        renderer = SlideRenderer(theme=theme, custom_font_path=custom_font)
        total = len(slides)
        clips: list[dict] = []

        # 차트 생성기 초기화 — 티커 추출 실패 시 chart_gen=None으로 건너뜀
        from pipelines.f005_youtube_v3.stages.chart_generator import (
            extract_ticker, detect_indicators, ChartGenerator
        )
        user_context = input_data.get("user_context", "")
        ticker = extract_ticker(selected_topic, user_context)
        if ticker:
            logger.info(f"[F005][STAGE_04][job_id={job_id}] 감지된 티커: {ticker}")
            chart_dir = output_dir.parent / "charts"
            chart_dir.mkdir(parents=True, exist_ok=True)
            chart_gen = ChartGenerator(theme_colors=theme)
        else:
            logger.info(f"[F005][STAGE_04][job_id={job_id}] 티커 감지 실패 — 차트 없이 진행")
            chart_gen = None
            chart_dir = None

        for slide in slides:
            slide_no: int = slide.get("slide_no", len(clips) + 1)
            slide_type: str = slide.get("type", "content")
            out_path = str(output_dir / f"slide_{slide_no:02d}.png")

            try:
                # 차트 생성 시도 — content/summary 타입이고 티커가 있을 때만
                chart_path = None
                if ticker and chart_gen and slide_type in ("content", "summary"):
                    slide_text = (
                        slide.get("title", "")
                        + " "
                        + " ".join(slide.get("bullets", []))
                    )
                    indicators = detect_indicators(slide_text)
                    chart_out = str(chart_dir / f"chart_{slide_no:02d}.png")
                    ok = chart_gen.generate(
                        ticker=ticker,
                        indicators=indicators,
                        output_path=chart_out,
                        period="3mo",
                        chart_size=(CHART_PANEL_W, CHART_PANEL_H),
                    )
                    if ok:
                        chart_path = chart_out

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
                    f"[F005][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 완료"
                )

            except Exception as e:
                logger.warning(
                    f"[F005][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 실패: {e}"
                )

        # 슬라이드 전체 실패 시 — 검정 슬라이드 1장 생성 (폴백)
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
                    f"[F005][STAGE_04][job_id={job_id}] 폴백 슬라이드 생성 완료"
                )
            except Exception as fe:
                logger.error(
                    f"[F005][STAGE_04] 폴백 슬라이드 생성 실패: {fe}"
                )

        # 썸네일 — 첫 번째 슬라이드 복사
        thumbnail_path: Optional[str] = None
        if clips:
            import shutil

            thumb_dir = (
                project_root
                / "storage"
                / "results"
                / "f005"
                / str(job_id)
                / "thumbnails"
            )
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_path = str(thumb_dir / "thumbnail.png")
            try:
                shutil.copy2(clips[0]["file_path"], thumbnail_path)
            except Exception as te:
                logger.warning(
                    f"[F005][STAGE_04] 썸네일 복사 실패: {te}"
                )
                thumbnail_path = None

        logger.info(
            f"[F005][STAGE_04][job_id={job_id}] 완료 — 슬라이드 {len(clips)}장"
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
        """출력 유효성 검증 — clips가 비어 있으면 자기 재시도."""
        if not output.get("clips"):
            return ValidationResult(
                is_valid=False,
                rejection_reason="슬라이드 이미지 생성 실패. 재시도합니다.",
                rejection_target="STAGE_04_VIDEO_GEN",
            )
        return ValidationResult(is_valid=True)
