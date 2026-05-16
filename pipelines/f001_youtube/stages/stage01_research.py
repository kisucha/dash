# 목적: STAGE_01 — 트렌드 분석 및 유튜브 주제 후보 발굴 스테이지.
# SearXNG로 트렌드 데이터를 수집하고 Ollama로 주제 후보를 스코어링한다.
# YouTube API는 구조만 준비하고, 실제 호출은 Phase 5에서 완성한다.

import sys
import json
import re
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f001_youtube.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama, call_searxng) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage01Research(BaseStage, BasePipeline):
    """STAGE_01 — 채널 카테고리 기반 트렌드 분석 및 주제 후보 발굴.

    처리 흐름:
      1. SearXNG로 채널 카테고리 관련 트렌드 검색 (YouTube API는 Phase 5)
      2. 검색 결과를 컨텍스트로 Ollama에 전달
      3. Ollama가 주제 후보 N개를 JSON 형식으로 생성
      4. 파싱 실패 시 기본 주제 1개로 폴백

    출력 딕셔너리의 selected_topic은 초기 None이며,
    사용자가 UI에서 주제를 선택한 뒤 API를 통해 채워진다.
    """

    STAGE_ID: str = "STAGE_01_RESEARCH"
    STAGE_ORDER: int = 1

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용 — 스테이지는 직접 실행되지 않는다."""
        return {"feature_id": "F001_STAGE01", "name": "STAGE_01_RESEARCH"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용 — 실제 실행은 execute()를 사용한다."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 — channel_category 필수.

        channel_category가 없거나 비어 있으면 자기 스테이지로 반송 요청을 반환한다.
        """
        channel_category: str = data.get("channel_category", "").strip()
        if not channel_category:
            return ValidationResult(
                is_valid=False,
                rejection_reason="채널 카테고리(channel_category)가 필수입니다. 입력 후 재시도하세요.",
                rejection_target="STAGE_01_RESEARCH",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_01 실행 — 트렌드 수집 + 주제 후보 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                channel_category (str, 필수): 채널 카테고리 (예: "IT/기술")
                target_count (int, 기본 5): 생성할 주제 후보 수
                search_provider (str, 기본 "youtube+searxng"): 검색 소스
                days (int, 기본 7): 트렌드 검색 기간(일)
            }

        Returns:
            {
                stage_id, status, channel_category,
                searxng_results_count, topics (list), selected_topic (None),
                generated_at
            }
        """
        # 파라미터 추출 및 기본값 적용
        channel_category: str = input_data.get("channel_category", "").strip()
        target_count: int = int(input_data.get("target_count", 5))
        search_provider: str = input_data.get("search_provider", "youtube+searxng")
        days: int = int(input_data.get("days", 7))

        logger.info(
            f"[STAGE_01][job_id={job_id}] 실행 시작 — "
            f"카테고리: {channel_category!r}, 후보 수: {target_count}"
        )

        # SearXNG 검색 결과 수집
        searxng_results: list[dict] = []
        if "searxng" in search_provider:
            query = f"{channel_category} 트렌드 인기 유튜브 영상"
            try:
                searxng_results = self.call_searxng(query, max_results=20)
                logger.info(
                    f"[STAGE_01][job_id={job_id}] SearXNG 검색 완료 — "
                    f"{len(searxng_results)}건 수신"
                )
            except Exception as e:
                # SearXNG 실패는 경고만 기록하고 Ollama 단독으로 계속 진행
                logger.warning(
                    f"[STAGE_01][job_id={job_id}] SearXNG 검색 실패 (Ollama 단독 진행): {e}"
                )

        # 검색 결과를 프롬프트 컨텍스트로 변환 (최대 3000자)
        search_context: str = self._build_search_context(searxng_results)

        # Ollama 프롬프트 구성 — 주제 후보 스코어링 요청
        prompt: str = (
            f"당신은 유튜브 컨텐츠 전략 전문가입니다.\n"
            f"채널 카테고리: {channel_category}\n"
            f"트렌드 데이터:\n{search_context}\n\n"
            f"위 데이터를 분석하여 유튜브 영상 주제 후보 {target_count}개를 생성하세요.\n"
            f"각 주제는 다음 JSON 배열 형식으로만 출력하세요:\n"
            f"[\n"
            f"  {{\"rank\": 1, \"title\": \"...\", \"estimated_views\": \"...\","
            f" \"competition_level\": \"낮음/중간/높음\","
            f" \"recommended_reason\": \"...\","
            f" \"keywords\": [\"...\", \"...\"], \"score\": 85, \"source\": \"searxng\"}}\n"
            f"]\n"
            f"JSON만 출력하고 다른 텍스트는 포함하지 마세요."
        )

        logger.info(f"[STAGE_01][job_id={job_id}] Ollama 주제 생성 요청 시작")

        # Ollama 호출 — call_ollama()는 BasePipeline에서 상속
        try:
            raw_response: str = self.call_ollama(
                prompt=prompt,
                timeout=120,
                num_predict=2048,
            )
        except Exception as e:
            logger.error(f"[STAGE_01][job_id={job_id}] Ollama 호출 실패: {e}")
            raise RuntimeError(f"STAGE_01 Ollama 호출 실패: {e}") from e

        # JSON 파싱 — ```json ... ``` 블록 제거 후 파싱 시도
        topics: list[dict] = self._parse_topics(
            raw_response, channel_category, target_count
        )

        logger.info(
            f"[STAGE_01][job_id={job_id}] 주제 후보 생성 완료 — "
            f"{len(topics)}개"
        )

        return {
            "stage_id": "STAGE_01_RESEARCH",
            "status": "COMPLETED",
            "channel_category": channel_category,
            "searxng_results_count": len(searxng_results),
            "topics": topics,
            "selected_topic": None,  # 사용자가 UI에서 선택 후 API로 채워짐
            # STAGE_02 스크립트 생성 시 실제 리서치 컨텍스트로 주입됨
            "search_context": search_context,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 — topics 배열이 비어 있으면 반송."""
        topics: list = output.get("topics", [])
        if not topics:
            return ValidationResult(
                is_valid=False,
                rejection_reason="주제 후보 생성 실패. Ollama 응답 파싱에 실패했습니다. 재시도하세요.",
                rejection_target="STAGE_01_RESEARCH",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    def _build_search_context(self, searxng_results: list[dict]) -> str:
        """SearXNG 검색 결과를 프롬프트 컨텍스트 텍스트로 변환.

        각 결과의 title + content를 연결하고 최대 3000자로 자른다.

        Args:
            searxng_results: call_searxng()의 반환 리스트

        Returns:
            컨텍스트 텍스트 문자열 (최대 3000자)
        """
        if not searxng_results:
            return "(검색 결과 없음 — Ollama의 사전 지식 기반으로 생성)"

        parts: list[str] = []
        for i, item in enumerate(searxng_results[:15], start=1):
            # title과 content(스니펫) 조합
            title: str = item.get("title", "")
            content: str = item.get("content", "")
            if title or content:
                parts.append(f"{i}. {title}: {content[:150]}")

        context: str = "\n".join(parts)
        # 최대 3000자로 제한 (Ollama 컨텍스트 절약)
        return context[:3000]

    def _parse_topics(
        self,
        raw_response: str,
        channel_category: str,
        target_count: int,
    ) -> list[dict]:
        """Ollama 응답에서 JSON 주제 배열을 파싱.

        ```json ... ``` 마크다운 블록을 제거한 뒤 JSON 파싱을 시도한다.
        파싱 실패 시 기본 주제 1개(폴백)를 반환한다.

        Args:
            raw_response: Ollama 응답 원본 텍스트
            channel_category: 폴백 주제 생성에 사용
            target_count: 요청한 후보 수 (로그용)

        Returns:
            파싱된 주제 딕셔너리 리스트
        """
        # ```json ... ``` 또는 ``` ... ``` 블록 제거
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw_response).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # 배열 시작([) 이전의 불필요한 텍스트 제거
        bracket_start: int = cleaned.find("[")
        bracket_end: int = cleaned.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            cleaned = cleaned[bracket_start : bracket_end + 1]

        try:
            topics = json.loads(cleaned)
            if isinstance(topics, list) and topics:
                logger.info(f"JSON 파싱 성공 — {len(topics)}개 주제 파싱됨")
                return topics
            else:
                raise ValueError("빈 배열 또는 리스트가 아님")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"주제 JSON 파싱 실패 ({e}), 폴백 주제 1개로 대체 — "
                f"원본 응답 앞 200자: {raw_response[:200]}"
            )
            # 파싱 실패 시 기본 주제 1개 반환
            return [
                {
                    "rank": 1,
                    "title": f"{channel_category} 최신 트렌드 총정리",
                    "estimated_views": "1만~10만",
                    "competition_level": "중간",
                    "recommended_reason": "Ollama 응답 파싱 실패로 생성된 기본 주제입니다. 재시도를 권장합니다.",
                    "keywords": [channel_category, "트렌드", "최신"],
                    "score": 50,
                    "source": "fallback",
                }
            ]
