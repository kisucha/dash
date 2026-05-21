# pipelines/f007_youtube_v5/stages/stage04_visual.py
# 목적: F007 STAGE_04 - shared/slide_renderer.py를 사용해 슬라이드 PNG 생성
# SlideRenderer: render_title(slide, page, total) / render_content(slide, page, total) 등 (page, total 인수 필요)
# CardNewsRenderer: render(slide) / render_title(slide) 등 (page, total 인수 없음)

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipelines.f007_youtube_v5.stages import BaseStage, ValidationResult
from pipelines.base import BasePipeline

# shared 슬라이드 렌더러 임포트
from pipelines.shared.slide_renderer import (
    SlideRenderer, CardNewsRenderer,
    SLIDE_THEMES, CARDNEWS_THEMES, DEFAULT_THEME,
    _clean_slide,
)

logger = logging.getLogger(__name__)

# 캔버스 크기 (shared/slide_renderer.py 상수와 동일)
_W, _H = 1280, 720


class Stage04Visual(BaseStage, BasePipeline):
    """STAGE_04 - Pillow 기반 슬라이드 이미지 생성.

    shared/slide_renderer.py의 SlideRenderer/CardNewsRenderer를 사용한다.
    render_mode에 따라 렌더러를 선택한다:
      - "slide" (기본): SlideRenderer - PPT 스타일
      - "cardnews": CardNewsRenderer - 카드뉴스 스타일

    SlideRenderer 호출 시 주의:
      - render_title(slide, page=slide_no, total=total)
      - render_content(slide, page=slide_no, total=total)
      - render_summary(slide, page=slide_no, total=total)
      - render_quote(slide, page=slide_no, total=total)

    CardNewsRenderer 호출 시 주의:
      - render(slide)  # page, total 인수 없음
      - render_title(slide)  # page, total 인수 없음

    출력 경로: storage/results/f007/{job_id}/slides/
    """
    STAGE_ID: str = "STAGE_04_VISUAL"
    STAGE_ORDER: int = 4

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE04", "name": "STAGE_04_VISUAL"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - slides 키 필수."""
        if not data.get("slides"):
            return ValidationResult(
                is_valid=False,
                rejection_reason="slides 데이터 없음. STAGE_02에서 슬라이드 구조를 생성하세요.",
                rejection_target="STAGE_02_SCRIPT",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_04 실행 - 슬라이드 PNG 이미지 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                slides (list): 슬라이드 목록 (STAGE_02 출력)
                selected_topic (str): 주제명 (로그/썸네일용)
                channel_type (str, 기본 "finance"): 채널 유형
                channel_name (str, 기본 ""): 채널명 (브랜딩 바)
                slide_theme (str, 기본 "dark_blue"): 테마명
                render_mode (str, 기본 "slide"): "slide" 또는 "cardnews"
            }

        Returns:
            {
                stage_id, status, generation_backend,
                clips: [{slide_no, file_path, duration_sec, narration, type}],
                thumbnail_path, thumbnail_candidates, total_clips, generated_at
            }
        """
        slides = input_data.get("slides", [])
        selected_topic: str = input_data.get("selected_topic", "주제")
        channel_type: str = input_data.get("channel_type", "finance")
        channel_name: str = input_data.get("channel_name", "")
        theme_name: str = input_data.get("slide_theme", DEFAULT_THEME)
        render_mode: str = input_data.get("render_mode", "slide")
        custom_font: str = input_data.get("slide_font_path", "")

        logger.info(
            f"[F007][STAGE_04][job_id={job_id}] 시작 - "
            f"render_mode={render_mode}, theme={theme_name}, "
            f"슬라이드 {len(slides)}장, channel_type={channel_type}"
        )

        # 출력 디렉토리 생성
        project_root = Path(__file__).parent.parent.parent.parent
        output_dir = project_root / "storage" / "results" / "f007" / str(job_id) / "slides"
        output_dir.mkdir(parents=True, exist_ok=True)

        # 텍스트 정규화 (□ 방지, 금액 통일)
        slides = [_clean_slide(s) for s in slides]

        if render_mode == "cardnews":
            clips, thumbnail_path = self._render_cardnews(
                slides=slides,
                theme_name=theme_name,
                channel_name=channel_name,
                custom_font=custom_font,
                output_dir=output_dir,
                job_id=job_id,
                project_root=project_root,
            )
            backend = "cardnews"
        else:
            # 기본: slide (SlideRenderer PPT 스타일)
            clips, thumbnail_path = self._render_slide(
                slides=slides,
                theme_name=theme_name,
                channel_name=channel_name,
                custom_font=custom_font,
                output_dir=output_dir,
                job_id=job_id,
                project_root=project_root,
                selected_topic=selected_topic,
                channel_type=channel_type,
                input_data=input_data,
            )
            backend = "ppt_slide"

        logger.info(
            f"[F007][STAGE_04][job_id={job_id}] 완료 - "
            f"슬라이드 {len(clips)}장, backend={backend}"
        )

        return {
            "stage_id": "STAGE_04_VISUAL",
            "status": "COMPLETED",
            "generation_backend": backend,
            "clips": clips,
            "thumbnail_path": thumbnail_path,
            "thumbnail_candidates": [thumbnail_path] if thumbnail_path else [],
            "total_clips": len(clips),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - clips가 비어 있으면 자기 재시도."""
        if not output.get("clips"):
            return ValidationResult(
                is_valid=False,
                rejection_reason="슬라이드 이미지 생성 실패. 재시도합니다.",
                rejection_target="STAGE_04_VISUAL",
            )
        return ValidationResult(is_valid=True)

    def _render_slide(
        self,
        slides: list,
        theme_name: str,
        channel_name: str,
        custom_font: str,
        output_dir: Path,
        job_id: int,
        project_root: Path,
        selected_topic: str,
        channel_type: str,
        input_data: dict,
    ) -> tuple[list, Optional[str]]:
        """SlideRenderer로 PPT 스타일 슬라이드 PNG 생성.

        SlideRenderer의 render_* 메서드는 모두 page, total 인수가 필요하다.
        """
        theme = SLIDE_THEMES.get(theme_name, SLIDE_THEMES[DEFAULT_THEME])
        renderer = SlideRenderer(
            theme=theme,
            custom_font_path=custom_font,
            channel_name=channel_name,
        )
        total = len(slides)
        clips: list[dict] = []

        # 차트 지원 여부 판단 (finance 채널에서만 시도)
        chart_gen = None
        effective_ticker: Optional[str] = None
        chart_dir: Optional[Path] = None

        if channel_type == "finance":
            try:
                from pipelines.f006_youtube_v4.stages.chart_generator import (
                    extract_ticker, detect_indicators, ChartGenerator
                )
                user_context = input_data.get("user_context", "")
                ticker = extract_ticker(selected_topic, user_context)
                effective_ticker = ticker or "^KS11"  # KOSPI 기본 티커
                chart_dir = output_dir.parent / "charts"
                chart_dir.mkdir(parents=True, exist_ok=True)
                chart_gen = ChartGenerator(theme_colors=theme)
                logger.info(
                    f"[F007][STAGE_04][job_id={job_id}] "
                    f"차트 인프라 초기화 - ticker={effective_ticker}"
                )
            except Exception as e:
                logger.warning(
                    f"[F007][STAGE_04][job_id={job_id}] "
                    f"chart_generator 임포트 실패 (차트 없이 진행): {e}"
                )

        # finance/language 모두 VisualFetcher 초기화 (chart 없는 content 슬라이드용)
        visual_fetcher = None
        visual_dir = None
        try:
            from pipelines.f007_youtube_v5.stages.visual_fetcher import VisualFetcher
            visual_dir = output_dir.parent / "visuals"
            visual_dir.mkdir(parents=True, exist_ok=True)
            visual_fetcher = VisualFetcher(str(visual_dir))
            logger.info(
                f"[F007][STAGE_04][job_id={job_id}] "
                f"VisualFetcher 초기화 완료 (channel={channel_type})"
            )
        except Exception as e:
            logger.warning(
                f"[F007][STAGE_04][job_id={job_id}] VisualFetcher 초기화 실패: {e}"
            )

        for slide in slides:
            slide_no: int = slide.get("slide_no", len(clips) + 1)
            slide_type: str = slide.get("type", "content")
            is_last_slide: bool = (slide_no == total)
            out_path = str(output_dir / f"slide_{slide_no:02d}.png")

            try:
                chart_path: Optional[str] = None

                # finance 채널 + content 타입 + 마지막 아님 -> 차트 시도
                if (
                    chart_gen is not None
                    and slide_type == "content"
                    and not is_last_slide
                    and chart_dir is not None
                ):
                    try:
                        from pipelines.f006_youtube_v4.stages.chart_generator import detect_indicators
                        slide_text = (
                            slide.get("title", "")
                            + " "
                            + " ".join(slide.get("bullets", []))
                        )
                        indicators = detect_indicators(slide_text)
                        if indicators and effective_ticker:
                            chart_out = str(chart_dir / f"chart_{slide_no:02d}.png")
                            ok = chart_gen.generate(
                                ticker=effective_ticker,
                                indicators=indicators,
                                output_path=chart_out,
                                period="3mo",
                            )
                            if ok:
                                chart_path = chart_out
                                logger.info(
                                    f"[F007][STAGE_04][job_id={job_id}] "
                                    f"슬라이드 {slide_no}: 차트 생성 - {indicators}"
                                )
                    except Exception as ce:
                        logger.debug(
                            f"[F007][STAGE_04][job_id={job_id}] "
                            f"슬라이드 {slide_no} 차트 생성 실패: {ce}"
                        )

                # language 채널 content 슬라이드: 보조 이미지 fetch (chart 없을 때만)
                visual_img_path: Optional[str] = None
                if (
                    visual_fetcher is not None
                    and slide_type == "content"
                    and chart_path is None
                ):
                    keyword = slide.get("title", selected_topic)
                    visual_img_path = visual_fetcher.fetch_for_slide(
                        slide_no=slide_no,
                        keyword=keyword,
                    )

                # SlideRenderer: render_* 메서드는 page, total 인수 필요
                # 분기 순서: title -> chart -> visual -> summary -> quote -> 나머지
                if slide_type == "title":
                    img = renderer.render_title(slide, page=slide_no, total=total)
                elif chart_path:
                    img = renderer.render_content_with_chart(
                        slide, chart_path, page=slide_no, total=total
                    )
                elif visual_img_path:
                    img = renderer.render_content_with_chart(
                        slide, visual_img_path, page=slide_no, total=total
                    )
                elif slide_type == "summary":
                    img = renderer.render_summary(slide, page=slide_no, total=total)
                elif slide_type == "quote":
                    img = renderer.render_quote(slide, page=slide_no, total=total)
                elif slide_type == "disclaimer":
                    # 면책 슬라이드: content 레이아웃으로 렌더링 (accent 색상 변경 없이)
                    img = renderer.render_content(slide, page=slide_no, total=total)
                else:
                    img = renderer.render_content(slide, page=slide_no, total=total)

                img.save(out_path, "PNG")
                narration: str = slide.get("narration", "")
                clips.append({
                    "slide_no": slide_no,
                    "file_path": out_path,
                    "duration_sec": 0,  # STAGE_05에서 narration 비례로 재계산
                    "narration": narration,
                    "type": slide_type,
                })
                logger.info(f"[F007][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 완료")

            except Exception as e:
                logger.warning(
                    f"[F007][STAGE_04][job_id={job_id}] 슬라이드 {slide_no} 실패: {e}"
                )

        # 전체 실패 폴백 - 검정 슬라이드 1장
        if not clips:
            clips = self._make_fallback_clip(output_dir, job_id)

        thumbnail_path = self._copy_thumbnail(clips, project_root, job_id)
        return clips, thumbnail_path

    def _render_cardnews(
        self,
        slides: list,
        theme_name: str,
        channel_name: str,
        custom_font: str,
        output_dir: Path,
        job_id: int,
        project_root: Path,
    ) -> tuple[list, Optional[str]]:
        """CardNewsRenderer로 카드뉴스 스타일 슬라이드 PNG 생성.

        CardNewsRenderer의 render_* 메서드는 page, total 인수가 없다.
        render(slide)로 타입별 디스패치한다.
        """
        renderer = CardNewsRenderer(theme_name=theme_name, channel_name=channel_name)
        if custom_font:
            renderer.set_custom_font(custom_font)

        clips: list[dict] = []

        for slide in slides:
            slide_no: int = slide.get("slide_no", len(clips) + 1)
            slide_type: str = slide.get("type", "content")
            out_path = str(output_dir / f"slide_{slide_no:02d}.png")

            try:
                # CardNewsRenderer: render(slide)로 타입 자동 디스패치
                # page, total 인수 전달하지 않음 (CardNewsRenderer는 페이지 번호 없음)
                img = renderer.render(slide)
                img.save(out_path, "PNG")
                narration: str = slide.get("narration", "")
                clips.append({
                    "slide_no": slide_no,
                    "file_path": out_path,
                    "duration_sec": 0,  # STAGE_05에서 narration 비례로 재계산
                    "narration": narration,
                    "type": slide_type,
                })
                logger.info(f"[F007][STAGE_04][job_id={job_id}] [cardnews] 슬라이드 {slide_no} 완료")

            except Exception as e:
                logger.warning(
                    f"[F007][STAGE_04][job_id={job_id}] [cardnews] 슬라이드 {slide_no} 실패: {e}"
                )

        if not clips:
            clips = self._make_fallback_clip(output_dir, job_id)

        thumbnail_path = self._copy_thumbnail(clips, project_root, job_id)
        return clips, thumbnail_path

    def _make_fallback_clip(self, output_dir: Path, job_id: int) -> list[dict]:
        """전체 슬라이드 생성 실패 시 검정 배경 폴백 슬라이드 1장 생성."""
        fallback_path = str(output_dir / "slide_01.png")
        try:
            from PIL import Image as _PILImage
            _PILImage.new("RGB", (_W, _H), (10, 22, 40)).save(fallback_path, "PNG")
            logger.warning(
                f"[F007][STAGE_04][job_id={job_id}] 폴백 슬라이드 생성 완료"
            )
        except Exception as fe:
            logger.error(f"[F007][STAGE_04] 폴백 슬라이드 생성 실패: {fe}")
            return []
        return [{
            "slide_no": 1,
            "file_path": fallback_path,
            "duration_sec": 5,
            "narration": "",
            "type": "content",
        }]

    def _copy_thumbnail(
        self,
        clips: list,
        project_root: Path,
        job_id: int,
    ) -> Optional[str]:
        """첫 번째 슬라이드를 썸네일로 복사한다."""
        if not clips:
            return None

        import shutil
        thumb_dir = project_root / "storage" / "results" / "f007" / str(job_id) / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumbnail_path = str(thumb_dir / "thumbnail.png")
        try:
            shutil.copy2(clips[0]["file_path"], thumbnail_path)
            return thumbnail_path
        except Exception as te:
            logger.warning(f"[F007][STAGE_04] 썸네일 복사 실패: {te}")
            return None
