# F001 유튜브 컨텐츠 제작 파이프라인 — 주제와 스타일을 입력받아 Ollama로 영상 스크립트를 생성한다.
# BasePipeline을 상속받으며, runner.py에서 독립 프로세스로 실행된다.

import sys
import logging
from typing import Optional

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from pipelines.base import BasePipeline

logger = logging.getLogger(__name__)


class F001Pipeline(BasePipeline):
    """
    F001 유튜브 컨텐츠 제작 파이프라인.

    입력 파라미터:
    - topic (str, 필수): 영상 주제 (예: "파이썬 비동기 프로그래밍")
    - style (str, 선택, 기본값 "educational"): 영상 스타일
      - "educational": 교육적, 정보 전달 중심
      - "entertaining": 재미있고 가벼운 톤
      - "tutorial": 단계별 튜토리얼 형식
    - duration_min (int, 선택, 기본값 10): 목표 영상 길이 (분)

    출력 형식:
    {
        "title": str,       # 영상 제목
        "description": str, # 유튜브 영상 설명문
        "script": str       # 전체 영상 스크립트
    }
    """

    def get_metadata(self) -> dict:
        """F001 파이프라인 메타데이터 반환."""
        return {
            "feature_id": "F001",
            "name": "유튜브 컨텐츠 제작",
            "description": "주제와 스타일을 입력하면 Ollama LLM이 유튜브 영상 스크립트를 자동 생성합니다.",
            "input_schema": {
                "topic": {
                    "type": "str",
                    "required": True,
                    "description": "영상 주제 (예: '파이썬 비동기 프로그래밍')",
                },
                "style": {
                    "type": "str",
                    "required": False,
                    "default": "educational",
                    "description": "영상 스타일: educational / entertaining / tutorial",
                },
                "duration_min": {
                    "type": "int",
                    "required": False,
                    "default": 10,
                    "description": "목표 영상 길이 (분 단위, 1~60)",
                },
            },
            "supports_schedule": False,
        }

    def run(self, task_id: int, params: dict) -> dict:
        """
        유튜브 컨텐츠 제작 파이프라인 실행.

        Args:
            task_id: DB tasks 테이블 PK
            params: 실행 파라미터 딕셔너리

        Returns:
            {"title": ..., "description": ..., "script": ...}

        Raises:
            ValueError: 필수 파라미터 누락 시
            RuntimeError: Ollama 호출 실패 시
        """
        logger.info(f"[F001][task_id={task_id}] 파이프라인 실행 시작")

        # ------------------------------------------------------------------
        # [1] 파라미터 추출 및 기본값 적용
        # ------------------------------------------------------------------
        topic: str = params.get("topic", "").strip()
        if not topic:
            raise ValueError("필수 파라미터 'topic'이 없거나 비어 있습니다.")

        style: str = params.get("style", "educational").strip()
        # 허용된 스타일 값 검증
        allowed_styles: list[str] = ["educational", "entertaining", "tutorial"]
        if style not in allowed_styles:
            logger.warning(f"[F001] 알 수 없는 style '{style}' — 'educational'로 대체")
            style = "educational"

        # duration_min 파싱 — 문자열로 들어올 수 있으므로 변환 처리
        try:
            duration_min: int = int(params.get("duration_min", 10))
        except (ValueError, TypeError):
            logger.warning("[F001] duration_min 파싱 실패 — 기본값 10분 사용")
            duration_min = 10

        # 범위 보정 (1~60분)
        duration_min = max(1, min(60, duration_min))

        logger.info(
            f"[F001][task_id={task_id}] 파라미터 — "
            f"topic: {topic!r}, style: {style}, duration_min: {duration_min}"
        )

        # ------------------------------------------------------------------
        # [2] RUNNING 상태 업데이트
        # ------------------------------------------------------------------
        self.update_status(task_id=task_id, status="RUNNING")

        # ------------------------------------------------------------------
        # [3] 취소 여부 확인 (실행 전)
        # ------------------------------------------------------------------
        if self.is_cancelled(task_id):
            logger.info(f"[F001][task_id={task_id}] 실행 전 취소 감지 — 중단")
            return {}

        # ------------------------------------------------------------------
        # [4] 스타일별 프롬프트 설명 구성
        # ------------------------------------------------------------------
        style_descriptions: dict[str, str] = {
            "educational": "교육적이고 정보 전달에 충실한 스타일. 명확하고 구조적인 설명.",
            "entertaining": "재미있고 가볍고 유머 감각이 있는 스타일. 시청자를 즐겁게.",
            "tutorial": "단계별로 따라할 수 있는 튜토리얼 스타일. 순서가 명확해야 함.",
        }
        style_desc: str = style_descriptions[style]

        # 분당 한국어 기준 약 150~200단어 기준으로 예상 분량 안내
        estimated_words: int = duration_min * 170

        # ------------------------------------------------------------------
        # [5-A] 제목 생성 — Ollama 1차 호출
        # ------------------------------------------------------------------
        logger.info(f"[F001][task_id={task_id}] 1단계: 제목 생성 중...")
        self.update_status(
            task_id=task_id,
            status="RUNNING",
            result={"progress": "1/3 제목 생성 중..."},
        )

        title_prompt: str = (
            f"유튜브 영상 제목을 한국어로 1개만 생성해줘.\n"
            f"주제: {topic}\n"
            f"스타일: {style_desc}\n"
            f"조건: 클릭을 유도하는 매력적인 제목, 50자 이내, 제목만 출력 (설명 없이)"
        )

        if self.is_cancelled(task_id):
            logger.info(f"[F001][task_id={task_id}] 제목 생성 전 취소 감지")
            return {}

        title_raw: str = self.call_ollama(
            prompt=title_prompt,
            timeout=60,
        )
        # 앞뒤 공백/따옴표 제거
        title: str = title_raw.strip().strip('"').strip("'").strip()
        logger.info(f"[F001][task_id={task_id}] 제목 생성 완료: {title!r}")

        # ------------------------------------------------------------------
        # [5-B] 영상 설명문 생성 — Ollama 2차 호출
        # ------------------------------------------------------------------
        logger.info(f"[F001][task_id={task_id}] 2단계: 영상 설명문 생성 중...")
        self.update_status(
            task_id=task_id,
            status="RUNNING",
            result={"progress": "2/3 설명문 생성 중...", "title": title},
        )

        description_prompt: str = (
            f"유튜브 영상 설명문을 한국어로 작성해줘.\n"
            f"영상 제목: {title}\n"
            f"주제: {topic}\n"
            f"스타일: {style_desc}\n"
            f"조건:\n"
            f"- 150~300자 분량\n"
            f"- 영상 핵심 내용 요약\n"
            f"- 구독 및 좋아요 유도 문구 포함\n"
            f"- 관련 해시태그 3~5개 포함\n"
            f"- 설명문만 출력 (추가 안내 없이)"
        )

        if self.is_cancelled(task_id):
            logger.info(f"[F001][task_id={task_id}] 설명문 생성 전 취소 감지")
            return {"title": title}

        description: str = self.call_ollama(
            prompt=description_prompt,
            timeout=60,
        ).strip()
        logger.info(f"[F001][task_id={task_id}] 설명문 생성 완료 ({len(description)}자)")

        # ------------------------------------------------------------------
        # [5-C] 스크립트 생성 — Ollama 3차 호출 (가장 오래 걸림)
        # ------------------------------------------------------------------
        logger.info(f"[F001][task_id={task_id}] 3단계: 영상 스크립트 생성 중...")
        self.update_status(
            task_id=task_id,
            status="RUNNING",
            result={
                "progress": "3/3 스크립트 생성 중...",
                "title": title,
                "description": description,
            },
        )

        script_prompt: str = (
            f"유튜브 영상 스크립트를 한국어로 작성해줘.\n"
            f"영상 제목: {title}\n"
            f"주제: {topic}\n"
            f"스타일: {style_desc}\n"
            f"목표 영상 길이: {duration_min}분 (약 {estimated_words}자 분량)\n"
            f"조건:\n"
            f"- 인트로(오프닝 인사, 주제 소개) 포함\n"
            f"- 본론: 주요 내용을 섹션으로 나눠 서술\n"
            f"- 아웃트로(요약, 구독 요청) 포함\n"
            f"- [섹션 제목] 형식으로 구분\n"
            f"- 스크립트만 출력 (메타 설명 없이)"
        )

        if self.is_cancelled(task_id):
            logger.info(f"[F001][task_id={task_id}] 스크립트 생성 전 취소 감지")
            return {"title": title, "description": description}

        script: str = self.call_ollama(
            prompt=script_prompt,
            timeout=120,
        ).strip()
        logger.info(f"[F001][task_id={task_id}] 스크립트 생성 완료 ({len(script)}자)")

        # ------------------------------------------------------------------
        # [6] 최종 결과 구성
        # ------------------------------------------------------------------
        result: dict = {
            "title": title,
            "description": description,
            "script": script,
        }

        logger.info(f"[F001][task_id={task_id}] 파이프라인 완료")
        return result
