# 목적: F006 STAGE_04B - PNG 슬라이드 생성 없이 슬라이드 텍스트 데이터를 JSON으로 출력.
# video_bg / remotion_native render_mode에서 사용 - Remotion이 직접 텍스트를 렌더링하므로 PNG 불필요.
# orchestrator에서 render_mode in ("video_bg", "remotion_native") 시 Stage04VideoGen 대신 선택된다.
# STAGE_ID는 DB 호환성을 위해 Stage04VideoGen과 동일하게 "STAGE_04_VIDEO_GEN"을 사용한다.

import sys
import re
import logging

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage04bVideoJson(BaseStage, BasePipeline):
    """F006 STAGE_04B - 슬라이드 텍스트 JSON 출력 스테이지.

    PNG 이미지를 생성하지 않고 슬라이드 구조를 JSON으로 변환한다.
    video_bg / remotion_native 모드에서 Remotion이 이 JSON을 받아 자체 렌더링한다.

    처리 흐름:
      1. input_data에서 slides 배열 추출
      2. 각 슬라이드에서 텍스트 데이터 추출 및 **키워드** 패턴 파싱
      3. slide_json_data 구성 후 반환 (clips=[] — PNG 없음)

    DB 호환성:
      STAGE_ID = "STAGE_04_VIDEO_GEN" - orchestrator stages 테이블 레코드와 일치
    """

    # DB 호환성: Stage04VideoGen과 동일한 STAGE_ID 사용
    STAGE_ID: str = "STAGE_04_VIDEO_GEN"
    STAGE_ORDER: int = 4

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE04B", "name": "STAGE_04B_VIDEO_JSON"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 유효성 검증 - slides가 없어도 통과 (빈 목록은 유효).

        slides / scenes 모두 없으면 경고 로그만 남기고 통과 (빈 JSON 출력).
        """
        slides = data.get("slides") or data.get("scenes", [])
        if not slides:
            logger.warning(
                "[F006][STAGE_04B] slides 없음 - 빈 slide_json_data로 진행"
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_04B 실행 - 슬라이드 텍스트 JSON 구성.

        Args:
            job_id: content_jobs.id
            input_data: {
                slides (list): 슬라이드 목록 (STAGE_02 output)
                scenes (list): slides 없을 때 폴백 키
                channel_name (str): 채널 이름 (Remotion props로 전달)
                channel_category (str): 채널 카테고리 (channel_name 없을 때 폴백)
            }

        Returns:
            {
                stage_id, status="COMPLETED",
                clips=[],               -- PNG 없음
                slide_json_data=[...],  -- Remotion이 사용할 슬라이드 텍스트 데이터
                channel_name (str),
                generated_at (str)
            }
        """
        logger.info(f"[F006][STAGE_04B][job_id={job_id}] 슬라이드 JSON 변환 시작")

        slides = input_data.get("slides") or input_data.get("scenes", [])
        channel_name: str = (
            input_data.get("channel_name") or input_data.get("channel_category", "")
        )

        slide_json_data: list[dict] = []

        for i, slide in enumerate(slides):
            slide_no: int = slide.get("slide_no", i + 1)
            slide_type: str = slide.get("type", "content")

            # header: title 키 우선, 없으면 header 키
            header: str = slide.get("title", slide.get("header", ""))

            # body_text: bullets 배열을 개행으로 합치거나, body_text/body 키 직접 사용
            bullets: list[str] = slide.get("bullets", [])
            if bullets:
                body_raw: str = "\n".join(bullets)
            else:
                body_raw = slide.get("body_text", slide.get("body", ""))

            # **키워드** 패턴 추출 (볼드 마크다운)
            keywords: list[str] = re.findall(r'\*\*(.+?)\*\*', body_raw)
            # ** 마크업 제거
            body_text_clean: str = re.sub(r'\*\*', '', body_raw)

            narration: str = slide.get("narration", slide.get("description", ""))

            slide_json_data.append({
                "slide_no": slide_no,
                "type": slide_type,
                "header": header,
                "body_text": body_text_clean,
                "narration": narration,
                "keywords": keywords,
            })

            logger.info(
                f"[F006][STAGE_04B][job_id={job_id}] 슬라이드 {slide_no} 변환 완료 "
                f"(type={slide_type}, keywords={len(keywords)}개)"
            )

        logger.info(
            f"[F006][STAGE_04B][job_id={job_id}] 완료 - {len(slide_json_data)}개 슬라이드 JSON 변환"
        )

        return {
            "stage_id": "STAGE_04_VIDEO_GEN",
            "status": "COMPLETED",
            "generation_backend": "json_only",
            # clips 빈 목록 - PNG 파일 없음, stage05r_b/a가 slide_json_data를 사용
            "clips": [],
            "slide_json_data": slide_json_data,
            "channel_name": channel_name,
            "total_clips": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 유효성 검증 - slide_json_data 키 존재 여부만 확인."""
        if "slide_json_data" not in output:
            return ValidationResult(
                is_valid=False,
                rejection_reason="STAGE_04B: slide_json_data 키가 출력에 없음. 재시도하세요.",
                rejection_target="STAGE_04_VIDEO_GEN",
            )
        return ValidationResult(is_valid=True)
