# 목적: F005 STAGE_01 — 사용자 직접 입력 + SearXNG 보완 리서치 스테이지.
# 사용자가 채팅에서 제공한 topic/user_context를 받아 SearXNG 보완 검색 후
# Ollama로 enriched_context를 생성하고 selected_topic을 자동 확정한다.
# F004와 달리 selected_topic이 항상 자동 확정되어 WAITING 전환 없이 STAGE_02로 진행한다.

import sys
import json
import re
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f005_youtube_v3.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama, call_searxng) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage01Input(BaseStage, BasePipeline):
    """STAGE_01 — 사용자 직접 입력 기반 주제 확정 및 보완 리서치.

    F004 Stage01Research와의 차이점:
      - topic, user_context를 사용자가 직접 제공 (트렌드 자동 발굴 없음)
      - SearXNG는 보완 리서치용 (실패해도 계속 진행)
      - Ollama는 enriched_context 생성용 (실패 시 user_context로 폴백)
      - selected_topic = topic 으로 자동 확정 (사용자 선택 불필요)
      - 출력에 selected_topic이 항상 존재 -> WAITING 전환 없음

    처리 흐름:
      1. validate_input: topic 필수, user_context 최소 10자 검증
      2. SearXNG 보완 검색 (topic + keywords_hint 기반, 실패 시 경고 후 계속)
      3. _build_search_context()로 검색 결과 컨텍스트 구성
      4. Ollama로 enriched_context 생성 (실패 시 user_context로 폴백)
      5. selected_topic = topic 자동 확정
    """

    STAGE_ID: str = "STAGE_01_INPUT"
    STAGE_ORDER: int = 1

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용 — 스테이지는 직접 실행되지 않는다."""
        return {"feature_id": "F005_STAGE01", "name": "STAGE_01_INPUT"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용 — 실제 실행은 execute()를 사용한다."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 — topic 필수, user_context 최소 10자.

        Args:
            data: 이 스테이지에 전달될 입력 딕셔너리

        Returns:
            ValidationResult — 검증 실패 시 is_valid=False, STAGE_01_INPUT으로 반송
        """
        # topic 필수 검증
        topic: str = str(data.get("topic", "")).strip()
        if not topic:
            return ValidationResult(
                is_valid=False,
                rejection_reason="topic 파라미터가 필수입니다. 유튜브 컨텐츠 주제를 입력하세요.",
                rejection_target="STAGE_01_INPUT",
            )

        # user_context 최소 10자 검증
        user_context: str = str(data.get("user_context", "")).strip()
        if len(user_context) < 10:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    f"user_context가 너무 짧습니다 ({len(user_context)}자). "
                    f"최소 10자 이상의 컨텍스트 정보를 입력하세요."
                ),
                rejection_target="STAGE_01_INPUT",
            )

        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_01 실행 — 사용자 입력 기반 주제 확정 및 보완 리서치.

        Args:
            job_id: content_jobs.id
            input_data: {
                topic (str, 필수): 사용자가 입력한 주제 텍스트
                user_context (str, 필수): 채팅에서 수집한 정보/메모 (최소 10자)
                channel_category (str, 기본 ""): 채널 카테고리
                keywords_hint (str, 기본 ""): 추가 검색 키워드
                days (int, 기본 7): 보완 검색 기간(일)
            }

        Returns:
            {
                stage_id: "STAGE_01_INPUT",
                status: "COMPLETED",
                channel_category: str,
                selected_topic: str,        - 자동 확정 (None 절대 불가)
                user_context: str,
                search_context: str,
                enriched_context: str,
                searxng_results_count: int,
                topics: list,               - [{rank:1, title:topic, score:100, source:"user_input"}]
                generated_at: str
            }
        """
        # 파라미터 추출 및 기본값 적용
        topic: str = str(input_data.get("topic", "")).strip()
        user_context: str = str(input_data.get("user_context", "")).strip()
        channel_category: str = str(input_data.get("channel_category", "")).strip()
        keywords_hint: str = str(input_data.get("keywords_hint", "")).strip()
        days: int = int(input_data.get("days", 7))

        logger.info(
            f"[F005][STAGE_01][job_id={job_id}] 실행 시작 — "
            f"주제: {topic!r}, user_context: {len(user_context)}자, "
            f"keywords_hint: {keywords_hint!r}"
        )

        # ----------------------------------------------------------------
        # days -> SearXNG time_range 변환 (F004 Stage01Research와 동일 로직)
        # ----------------------------------------------------------------
        if days <= 2:
            time_range = "day"
        elif days <= 7:
            time_range = "week"
        elif days <= 30:
            time_range = "month"
        else:
            time_range = "year"

        # ----------------------------------------------------------------
        # 1단계: SearXNG 보완 검색 — 실패 시 경고 후 계속 진행 (graceful fallback)
        # ----------------------------------------------------------------
        searxng_results: list[dict] = []

        # 검색 쿼리: topic + keywords_hint 조합
        search_query: str = topic
        if keywords_hint:
            search_query = f"{topic} {keywords_hint}"

        logger.info(
            f"[F005][STAGE_01][job_id={job_id}] SearXNG 보완 검색 시작 — "
            f"쿼리: {search_query!r}, time_range={time_range}"
        )

        try:
            searxng_results = self.call_searxng(
                search_query,
                max_results=20,
                time_range=time_range,
                max_age_days=days,
            )
            logger.info(
                f"[F005][STAGE_01][job_id={job_id}] SearXNG 검색 완료 — "
                f"{len(searxng_results)}건 수신 (time_range={time_range}, max_age={days}일)"
            )
        except Exception as e:
            # SearXNG 실패는 경고만 기록하고 계속 진행 — 보완 리서치이므로 필수 아님
            logger.warning(
                f"[F005][STAGE_01][job_id={job_id}] SearXNG 검색 실패 (계속 진행): {e}"
            )

        # ----------------------------------------------------------------
        # 2단계: 검색 결과를 프롬프트 컨텍스트로 변환
        # ----------------------------------------------------------------
        search_context: str = self._build_search_context(searxng_results)

        # ----------------------------------------------------------------
        # 3단계: Ollama 호출 — user_context + search_context 기반 enriched_context 생성
        #         실패 시 fallback: enriched_context = user_context
        # ----------------------------------------------------------------
        today_str: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # search_context 섹션 (있을 때만 포함)
        search_section: str = ""
        if search_context and "(검색 결과 없음" not in search_context:
            search_section = (
                f"\n[보완 검색 데이터 — {today_str} 기준 최근 {days}일 이내 수집]\n"
                f"{search_context}\n"
            )

        enrichment_prompt: str = (
            f"다음 정보를 분석하여 유튜브 컨텐츠 제작에 필요한 보완 정보를 JSON으로 작성하세요.\n"
            f"오늘 날짜: {today_str}\n\n"
            f"[사용자 제공 주제]\n{topic}\n\n"
            f"[사용자 제공 컨텍스트]\n{user_context}\n"
            f"{search_section}\n"
            f"위 정보를 바탕으로 다음 JSON 형식으로만 출력하세요:\n"
            f"{{\n"
            f"  \"enriched_summary\": \"주제와 컨텍스트를 종합한 핵심 요약 (300자 이내)\",\n"
            f"  \"key_points\": [\"핵심 포인트 1\", \"핵심 포인트 2\", \"핵심 포인트 3\"],\n"
            f"  \"target_audience\": \"이 영상의 주요 시청자층\",\n"
            f"  \"content_angle\": \"컨텐츠 제작 각도 및 접근 방식\",\n"
            f"  \"supplementary_info\": \"검색 데이터 기반 보완 정보 (있는 경우)\"\n"
            f"}}\n"
            f"JSON만 출력하고 다른 텍스트는 포함하지 마세요."
        )

        enriched_context: str = user_context  # 기본값: fallback

        logger.info(f"[F005][STAGE_01][job_id={job_id}] Ollama enrichment 호출 시작")
        try:
            raw_enrichment: str = self.call_ollama(
                prompt=enrichment_prompt,
                timeout=120,
                num_predict=1024,
            )
            # JSON 파싱 시도 — 성공하면 구조화된 enriched_context로 사용
            enriched_context = self._parse_enrichment(raw_enrichment, user_context)
            logger.info(
                f"[F005][STAGE_01][job_id={job_id}] Ollama enrichment 완료 — "
                f"{len(enriched_context)}자"
            )
        except Exception as e:
            # Ollama 실패 시 fallback: enriched_context = user_context
            logger.warning(
                f"[F005][STAGE_01][job_id={job_id}] Ollama enrichment 실패 "
                f"(user_context로 폴백): {e}"
            )
            enriched_context = user_context

        # ----------------------------------------------------------------
        # 4단계: selected_topic 자동 확정 = topic (사용자 선택 불필요)
        # ----------------------------------------------------------------
        selected_topic: str = topic  # 항상 자동 확정 — None 절대 불가

        logger.info(
            f"[F005][STAGE_01][job_id={job_id}] 완료 — "
            f"selected_topic={selected_topic!r}, "
            f"SearXNG={len(searxng_results)}건"
        )

        return {
            "stage_id": "STAGE_01_INPUT",
            "status": "COMPLETED",
            "channel_category": channel_category,
            "selected_topic": selected_topic,           # 자동 확정 — None 절대 불가
            "user_context": user_context,
            "search_context": search_context,
            "enriched_context": enriched_context,
            "searxng_results_count": len(searxng_results),
            # topics 배열 — STAGE_02가 topic_detail 추출에 사용 (F004 호환 형식)
            "topics": [
                {
                    "rank": 1,
                    "title": topic,
                    "score": 100,
                    "source": "user_input",
                }
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 — selected_topic이 없으면 REJECTED.

        F005는 selected_topic이 항상 자동 확정되므로
        이 검증이 실패하는 경우는 execute() 내부 버그를 의미한다.

        Args:
            output: execute()가 반환한 출력 딕셔너리

        Returns:
            ValidationResult — selected_topic 없으면 is_valid=False
        """
        selected_topic: str = output.get("selected_topic", "")
        if not selected_topic:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    "selected_topic이 없습니다. "
                    "topic 파라미터를 확인하고 재시도하세요."
                ),
                rejection_target="STAGE_01_INPUT",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    def _build_search_context(self, searxng_results: list[dict]) -> str:
        """SearXNG 검색 결과를 프롬프트 컨텍스트 텍스트로 변환.

        F004 Stage01Research._build_search_context()와 동일 로직.
        각 결과의 title + content를 연결하고 최대 3000자로 자른다.

        Args:
            searxng_results: call_searxng()의 반환 리스트

        Returns:
            컨텍스트 텍스트 문자열 (최대 3000자)
        """
        if not searxng_results:
            return "(검색 결과 없음 — user_context 기반으로 진행)"

        parts: list[str] = []
        for i, item in enumerate(searxng_results[:15], start=1):
            title: str = item.get("title", "")
            content: str = item.get("content", "")
            pub_date: str = item.get("published_date", "")
            # 날짜 정보가 있으면 괄호로 표시 — LLM이 최신성 판단에 활용
            date_label: str = f" [{pub_date[:10]}]" if pub_date else ""
            if title or content:
                parts.append(f"{i}.{date_label} {title}: {content[:150]}")

        context: str = "\n".join(parts)
        # 최대 3000자로 제한 (Ollama 컨텍스트 절약)
        return context[:3000]

    def _parse_enrichment(self, raw_response: str, fallback: str) -> str:
        """Ollama enrichment 응답을 파싱하여 enriched_context 문자열 반환.

        JSON 파싱 성공 시 구조화된 요약 문자열을 조합해 반환한다.
        파싱 실패 시 fallback(user_context)을 반환한다.

        Args:
            raw_response: Ollama 응답 원본 텍스트
            fallback: 파싱 실패 시 반환할 기본값

        Returns:
            enriched_context 문자열
        """
        # 코드펜스 제거
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw_response).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # JSON 객체 추출 시도
        brace_start: int = cleaned.find("{")
        brace_end: int = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            candidate: str = cleaned[brace_start : brace_end + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict):
                    # 구조화된 enriched_context 조합
                    parts: list[str] = []

                    summary: str = data.get("enriched_summary", "")
                    if summary:
                        parts.append(f"[요약] {summary}")

                    key_points: list = data.get("key_points", [])
                    if key_points:
                        points_text = "\n".join(f"- {p}" for p in key_points[:5])
                        parts.append(f"[핵심 포인트]\n{points_text}")

                    target: str = data.get("target_audience", "")
                    if target:
                        parts.append(f"[시청자층] {target}")

                    angle: str = data.get("content_angle", "")
                    if angle:
                        parts.append(f"[컨텐츠 각도] {angle}")

                    supplementary: str = data.get("supplementary_info", "")
                    if supplementary:
                        parts.append(f"[보완 정보] {supplementary}")

                    if parts:
                        logger.info("[F005][STAGE_01] enrichment JSON 파싱 성공")
                        return "\n\n".join(parts)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[F005][STAGE_01] enrichment JSON 파싱 실패 ({e}), fallback 사용")

        # 파싱 실패 시 raw_response가 텍스트라면 그대로 사용, 아니면 fallback
        if len(raw_response.strip()) >= 10:
            logger.info("[F005][STAGE_01] enrichment raw 텍스트 사용")
            return raw_response.strip()[:2000]

        return fallback
