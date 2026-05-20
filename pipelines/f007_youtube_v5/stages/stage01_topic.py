# pipelines/f007_youtube_v5/stages/stage01_topic.py
# 목적: F007 STAGE_01 - SearXNG + Ollama 자동 주제 발굴 (channel_type 분기)
# finance: 금융/경제 뉴스 검색 -> 투자 관련 주제 발굴
# language: 영어 학습 트렌드 검색 -> 실용 영어 표현 주제 발굴

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import re
import logging
from datetime import datetime, timezone

from pipelines.f007_youtube_v5.stages import BaseStage, ValidationResult
from pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

# channel_type별 SearXNG 검색 쿼리 템플릿 - {today} 자리 표시자 포함
_SEARCH_QUERY_MAP = {
    "finance":  "주식 ETF 경제 투자 뉴스 {today}",
    "language": "영어 학습 표현 회화 유튜브 {today}",
}

# channel_type별 Ollama 주제 발굴 프롬프트 템플릿
_TOPIC_PROMPT_MAP = {
    "finance": (
        "다음은 오늘({today}) 수집한 금융/경제 뉴스 데이터입니다.\n"
        "{search_context}\n\n"
        "위 데이터를 분석하여 유튜브 쇼츠/롱폼에 적합한 금융 주제 3개를 선정하세요.\n"
        "기준: 시청자 관심도 높음, 최신 데이터 있음, 법적 문제 없음.\n"
        "투자 권유 문구 절대 금지. JSON 배열로만 출력:\n"
        '[{{"rank":1,"title":"주제1","reason":"이유"}}, ...]'
    ),
    "language": (
        "다음은 오늘({today}) 수집한 영어 학습 트렌드 데이터입니다.\n"
        "{search_context}\n\n"
        "위 데이터를 분석하여 한국인 영어 학습자에게 유용한 유튜브 주제 3개를 선정하세요.\n"
        "기준: 실용적, 즉시 사용 가능한 표현, 학습 효과 높음.\n"
        "JSON 배열로만 출력:\n"
        '[{{"rank":1,"title":"주제1","reason":"이유"}}, ...]'
    ),
}

# channel_type별 폴백 주제 (SearXNG + Ollama 모두 실패 시 사용)
_FALLBACK_TOPICS = {
    "finance": "오늘의 증시 핵심 이슈 정리",
    "language": "원어민이 매일 쓰는 영어 표현 5가지",
}


class Stage01Topic(BaseStage, BasePipeline):
    """STAGE_01 - SearXNG + Ollama 자동 주제 발굴.

    처리 흐름:
      1. channel_type 유효성 확인 (finance/language)
      2. SearXNG로 최신 기사/트렌드 검색 (max_age_days 기준 필터)
      3. Ollama로 주제 후보 3개 생성 (JSON 배열)
      4. 가장 높은 rank 주제를 selected_topic으로 확정
      5. 폴백: SearXNG/Ollama 실패 시 기본 주제 사용
    """
    STAGE_ID: str = "STAGE_01_TOPIC"
    STAGE_ORDER: int = 1

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE01", "name": "STAGE_01_TOPIC"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - channel_type이 finance 또는 language인지 확인."""
        ct = data.get("channel_type", "")
        if ct not in ("finance", "language"):
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    f"channel_type='{ct}'은 유효하지 않습니다. "
                    f"'finance' 또는 'language'를 선택하세요."
                ),
                rejection_target="STAGE_01_TOPIC",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_01 실행 - 주제 자동 발굴.

        Args:
            job_id: content_jobs.id
            input_data: {
                channel_type (str, 필수): "finance" 또는 "language"
                days (int, 기본 3): 검색 기간 (최근 N일)
            }

        Returns:
            {
                stage_id, status, channel_type,
                selected_topic (str): 1순위 주제 제목,
                topics (list): 후보 주제 3개 목록,
                search_context (str): SearXNG 검색 결과 요약,
                enriched_context (str): 다음 스테이지용 컨텍스트,
                searxng_results_count (int): 수집된 검색 결과 수,
                generated_at (str): ISO 8601 UTC 타임스탬프
            }
        """
        channel_type: str = input_data.get("channel_type", "finance")
        days: int = int(input_data.get("days", 3))
        today_str: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        logger.info(
            f"[F007][STAGE_01][job_id={job_id}] 시작 - "
            f"channel_type={channel_type}, days={days}"
        )

        # 1. SearXNG 검색 - 최근 N일 이내 기사 수집
        query_tmpl = _SEARCH_QUERY_MAP.get(channel_type, _SEARCH_QUERY_MAP["finance"])
        query = query_tmpl.format(today=today_str)
        searxng_results = []
        try:
            searxng_results = self.call_searxng(
                query=query, max_results=20, max_age_days=days
            )
            logger.info(
                f"[F007][STAGE_01][job_id={job_id}] "
                f"SearXNG 검색 완료 - {len(searxng_results)}건"
            )
        except Exception as e:
            logger.warning(
                f"[F007][STAGE_01][job_id={job_id}] "
                f"SearXNG 실패 (폴백으로 계속 진행): {e}"
            )

        # 검색 결과 컨텍스트 구성
        search_context = self._build_context(searxng_results)

        # 2. Ollama 주제 발굴 (JSON 배열 반환)
        prompt_tmpl = _TOPIC_PROMPT_MAP.get(channel_type, _TOPIC_PROMPT_MAP["finance"])
        prompt = prompt_tmpl.format(today=today_str, search_context=search_context)
        topics = []
        try:
            raw = self.call_ollama(prompt=prompt, timeout=120, num_predict=1024)
            topics = self._parse_topics(raw)
            logger.info(
                f"[F007][STAGE_01][job_id={job_id}] "
                f"Ollama 주제 발굴 완료 - {len(topics)}개"
            )
        except Exception as e:
            logger.warning(
                f"[F007][STAGE_01][job_id={job_id}] "
                f"Ollama 주제 발굴 실패 (폴백 사용): {e}"
            )

        # 3. 폴백: 주제 발굴 실패 시 기본 주제 사용
        if not topics:
            fallback_title = _FALLBACK_TOPICS.get(channel_type, "오늘의 유튜브 주제")
            topics = [{"rank": 1, "title": fallback_title, "reason": "fallback"}]
            logger.warning(
                f"[F007][STAGE_01][job_id={job_id}] "
                f"폴백 주제 사용: {fallback_title}"
            )

        # 1순위 주제 확정 (rank 오름차순 정렬 후 첫 번째)
        topics_sorted = sorted(topics, key=lambda x: x.get("rank", 99))
        selected_topic: str = topics_sorted[0].get("title", "").strip()

        logger.info(
            f"[F007][STAGE_01][job_id={job_id}] 완료 - "
            f"selected_topic={selected_topic!r}"
        )

        return {
            "stage_id": "STAGE_01_TOPIC",
            "status": "COMPLETED",
            "channel_type": channel_type,
            "selected_topic": selected_topic,
            "topics": topics_sorted,
            "search_context": search_context,
            "enriched_context": search_context,  # STAGE_02에서 enriched_context로 참조
            "searxng_results_count": len(searxng_results),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - selected_topic이 비어 있으면 자기 재시도."""
        if not output.get("selected_topic", "").strip():
            return ValidationResult(
                is_valid=False,
                rejection_reason="selected_topic이 없습니다. 주제 발굴에 실패했습니다.",
                rejection_target="STAGE_01_TOPIC",
            )
        return ValidationResult(is_valid=True)

    def _build_context(self, results: list) -> str:
        """검색 결과 리스트를 LLM 입력용 컨텍스트 문자열로 변환한다.

        항목당 최대 150자, 전체 3000자 이내로 제한한다.
        """
        if not results:
            return "(검색 결과 없음)"

        parts = []
        for i, item in enumerate(results[:15], 1):
            title = item.get("title", "")
            content = item.get("content", "")
            pub = item.get("published_date", "")
            date_label = f"[{pub[:10]}]" if pub else ""
            if title or content:
                parts.append(f"{i}.{date_label} {title}: {content[:150]}")

        return "\n".join(parts)[:3000]

    def _parse_topics(self, raw: str) -> list:
        """Ollama 응답에서 JSON 배열(주제 목록)을 추출한다.

        JSON 파싱 실패 시 빈 리스트를 반환한다.
        """
        # 코드펜스 제거
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # JSON 배열 추출 시도
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1:
            try:
                data = json.loads(cleaned[start:end + 1])
                if isinstance(data, list) and data:
                    # 각 항목에 title 키가 있는지 확인
                    valid = [
                        item for item in data
                        if isinstance(item, dict) and item.get("title", "").strip()
                    ]
                    return valid
            except (json.JSONDecodeError, ValueError):
                pass

        logger.debug(
            f"[STAGE_01] JSON 배열 파싱 실패 - raw 길이: {len(raw)}자"
        )
        return []
