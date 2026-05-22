# pipelines/f007_youtube_v5/stages/stage02_script.py
# 목적: F007 STAGE_02 - channel_type 분기 슬라이드 스크립트 생성
# finance: 수치/데이터 중심 + 투자권유 금지 + 면책 슬라이드 포함
# language: 예문/대화 형식 + 초보자 친화적 실용 표현

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


class Stage02Script(BaseStage, BasePipeline):
    """STAGE_02 - channel_type 분기 슬라이드 친화적 스크립트 생성.

    finance 채널:
      - 수치/데이터 중심 서술
      - 투자권유 문구 절대 금지
      - 마지막 슬라이드에 면책 조항 포함

    language 채널:
      - 예문/대화 형식
      - 초보자 친화적 실용 표현 중심

    출력 키:
      - slides 배열 (PPT 슬라이드 구조)
      - script_text (STAGE_03 TTS가 이 키를 읽음)
    """
    STAGE_ID: str = "STAGE_02_SCRIPT"
    STAGE_ORDER: int = 2

    # 훅 스타일 설명 매핑
    _HOOK_DESCRIPTIONS: dict = {
        "question": "질문 형식으로 시작",
        "statistic": "충격적인 수치/통계로 시작",
        "story": "짧은 이야기로 시작",
        "problem": "문제 제기로 시작",
        "shock": "놀라운 사실로 시작",
    }

    # CTA 유형 설명 매핑
    _CTA_DESCRIPTIONS: dict = {
        "subscribe": "구독 및 알림 설정 유도",
        "like": "좋아요 유도",
        "comment": "댓글 참여 유도",
        "next_video": "다음 영상 연결",
    }

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE02", "name": "STAGE_02_SCRIPT"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - selected_topic 필수.

        selected_topic이 없으면 STAGE_01_TOPIC으로 반송.
        """
        if not data.get("selected_topic", "").strip():
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    "selected_topic 없음. STAGE_01에서 주제가 확정되지 않았습니다."
                ),
                rejection_target="STAGE_01_TOPIC",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_02 실행 - channel_type별 슬라이드 스크립트 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                selected_topic (str, 필수): STAGE_01에서 확정된 주제
                channel_type (str, 기본 "finance"): 채널 유형
                duration_min (int, 기본 10): 목표 영상 길이(분)
                hook_style (str, 기본 "question"): 훅 스타일
                cta_type (str, 기본 "subscribe"): CTA 유형
                enriched_context (str, 기본 ""): SearXNG 리서치 컨텍스트
                topics (list, 기본 []): 주제 후보 목록
            }

        Returns:
            {
                stage_id, status, channel_type, selected_topic,
                slides (list): PPT 슬라이드 배열 (title/content/summary/disclaimer),
                script_text (str): 전체 나레이션 텍스트 (STAGE_03 TTS용),
                total_chars (int), estimated_duration_min (int),
                total_slides (int), generated_at (str)
            }
        """
        selected_topic: str = str(input_data.get("selected_topic", "")).strip()
        channel_type: str = input_data.get("channel_type", "finance")
        duration_min: int = int(input_data.get("duration_min", 10))
        hook_style: str = input_data.get("hook_style", "question")
        cta_type: str = input_data.get("cta_type", "subscribe")
        channel_name: str = input_data.get("channel_name", "")
        # enriched_context 우선, 없으면 search_context 사용
        enriched_context: str = input_data.get("enriched_context", "")
        search_context: str = input_data.get("search_context", "")
        topics: list = input_data.get("topics", [])
        today_str: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 슬라이드 수 및 목표 글자 수 계산
        # content 슬라이드: 분당 80초 기준, 최소 4장 최대 12장
        n_content_slides: int = max(4, min(12, (duration_min * 60) // 80))
        # title 1장 + summary 1장 고정 (finance는 면책 1장 추가)
        n_extra_slides: int = 1 if channel_type == "finance" else 0  # 면책 슬라이드
        n_total_slides: int = n_content_slides + 2 + n_extra_slides
        # 분당 170자 기준 목표 글자 수
        target_chars: int = duration_min * 170

        hook_description: str = self._HOOK_DESCRIPTIONS.get(hook_style, "강한 훅으로 시작")
        cta_description: str = self._CTA_DESCRIPTIONS.get(cta_type, "구독 유도")

        logger.info(
            f"[F007][STAGE_02][job_id={job_id}] 시작 - "
            f"주제: {selected_topic!r}, channel_type={channel_type}, "
            f"목표: {duration_min}분({target_chars}자), 슬라이드: {n_total_slides}장"
        )

        # 컨텍스트 섹션 구성
        primary_context: str = enriched_context if enriched_context else search_context
        context_section: str = ""
        if primary_context and primary_context.strip() and "(검색 결과 없음" not in primary_context:
            context_section = (
                f"\n[리서치 컨텍스트 - {today_str} 기준 실제 검색 데이터]\n"
                f"아래는 기준 날짜에 실제 검색·수집된 데이터입니다. 이 데이터만 사용하세요.\n"
                f"자체 지식으로 수치/사실/사건을 추가하거나 만들어내는 것을 엄격히 금지합니다.\n"
                f"{primary_context[:2500]}\n"
            )

        # 주제 배경 섹션 (topics에서 추출)
        topic_detail: dict = self._find_topic_detail(selected_topic, topics)
        keywords: str = selected_topic
        recommended_reason: str = topic_detail.get("reason", "")
        topic_context_section: str = ""
        if recommended_reason:
            topic_context_section = (
                f"\n[주제 선정 배경]\n"
                f"선정 이유: {recommended_reason}\n"
                f"핵심 키워드: {keywords}\n"
            )

        # 슬라이드 생성 프롬프트 구성 (channel_type 분기)
        slide_prompt: str = self._build_slide_prompt(
            selected_topic=selected_topic,
            channel_type=channel_type,
            channel_name=channel_name,
            duration_min=duration_min,
            n_total_slides=n_total_slides,
            n_content_slides=n_content_slides,
            n_extra_slides=n_extra_slides,
            target_chars=target_chars,
            context_section=context_section,
            topic_context_section=topic_context_section,
            hook_description=hook_description,
            cta_description=cta_description,
            today_str=today_str,
        )

        logger.info(
            f"[F007][STAGE_02][job_id={job_id}] Ollama 호출 시작 - "
            f"프롬프트 {len(slide_prompt)}자"
        )
        try:
            raw_slides: str = self.call_ollama(
                prompt=slide_prompt,
                timeout=180,
                num_predict=4096,
            )
        except Exception as e:
            logger.error(
                f"[F007][STAGE_02][job_id={job_id}] 슬라이드 생성 Ollama 실패: {e}"
            )
            raise RuntimeError(f"STAGE_02 슬라이드 생성 실패: {e}") from e

        # slides 배열 파싱 - channel_type 전달 (폴백 면책 슬라이드 생성용)
        slides: list[dict] = self._parse_slides_json(
            raw=raw_slides,
            n_slides=n_total_slides,
            selected_topic=selected_topic,
            channel_type=channel_type,
        )
        logger.info(
            f"[F007][STAGE_02][job_id={job_id}] 슬라이드 파싱 완료 - {len(slides)}장"
        )

        # script_text 조합 및 분량 계산
        script_text: str = self._build_script_text(slides)
        total_chars: int = len(script_text)
        estimated_duration_min: int = max(1, total_chars // 170)

        logger.info(
            f"[F007][STAGE_02][job_id={job_id}] 완료 - "
            f"슬라이드 {len(slides)}장, 총 {total_chars}자, "
            f"추정 {estimated_duration_min}분"
        )

        return {
            "stage_id": "STAGE_02_SCRIPT",
            "status": "COMPLETED",
            "channel_type": channel_type,
            "selected_topic": selected_topic,
            "slides": slides,
            "script_text": script_text,
            "total_chars": total_chars,
            "estimated_duration_min": estimated_duration_min,
            "total_slides": len(slides),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - 슬라이드 최소 3장 이상 + 나레이션 최소 200자 이상."""
        slides = output.get("slides", [])
        if len(slides) < 3:
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"슬라이드 수 부족: {len(slides)}장. 최소 3장 필요.",
                rejection_target="STAGE_02_SCRIPT",
            )

        total_chars: int = output.get("total_chars", 0)
        if total_chars < 200:
            return ValidationResult(
                is_valid=False,
                rejection_reason=f"나레이션 분량 부족: {total_chars}자. 최소 200자 이상 필요.",
                rejection_target="STAGE_02_SCRIPT",
            )

        return ValidationResult(is_valid=True)

    def _build_slide_prompt(
        self,
        selected_topic: str,
        channel_type: str,
        channel_name: str,
        duration_min: int,
        n_total_slides: int,
        n_content_slides: int,
        n_extra_slides: int,
        target_chars: int,
        context_section: str,
        topic_context_section: str,
        hook_description: str,
        cta_description: str,
        today_str: str = "",
    ) -> str:
        """channel_type에 따라 분기된 슬라이드 생성 프롬프트를 구성한다."""
        date_constraint: str = (
            f"기준 날짜: {today_str}\n"
            "[절대 규칙] 아래 [리서치 컨텍스트]는 기준 날짜에 실제 검색·수집된 데이터입니다.\n"
            "반드시 이 데이터만 사용하세요. 컨텍스트에 없는 수치·사건·통계를 스스로 만들거나 추측하는 것을 엄격히 금지합니다.\n"
            "미래 예측 표현은 절대 사용하지 마세요.\n\n"
        )

        last_slide_no: int = n_total_slides
        content_range_note: str = (
            f"slide_no 3 ~ {n_total_slides - 1 - n_extra_slides}: type=\"content\""
            if n_content_slides > 1
            else ""
        )

        if channel_type == "finance":
            # finance 채널: 수치/데이터 중심, 투자권유 금지, 면책 슬라이드 포함
            channel_instruction = (
                "당신은 금융/경제 정보 유튜브 채널 전문 스크립트 작가입니다.\n"
                f"{date_constraint}"
                "아래 규칙을 반드시 준수하세요:\n"
                "1. 모든 수치와 데이터는 제공된 리서치 컨텍스트에서만 인용\n"
                "2. '투자 권유' 또는 '매수/매도 추천' 문구 절대 금지\n"
                "3. 불확실한 정보는 반드시 '제공된 자료 기준'이라고 명시\n"
                f"4. 마지막에서 두 번째 슬라이드(slide_no={last_slide_no - 1})는 "
                f"type=\"disclaimer\", title=\"투자 유의사항\"으로 면책 조항 슬라이드를 반드시 포함\n"
                "   면책 슬라이드 narration 예시: '이 영상은 투자 권유가 아닌 정보 제공 목적입니다. "
                "투자 결정은 반드시 전문가와 상담 후 본인 판단으로 하시기 바랍니다.'\n\n"
            )
        else:
            # language 채널: 예문/대화 형식, 실용적 영어 표현 중심
            channel_instruction = (
                "당신은 한국인 영어 학습자를 위한 유튜브 채널 전문 스크립트 작가입니다.\n"
                f"{date_constraint}"
                "아래 규칙을 반드시 준수하세요:\n"
                "1. 모든 예문은 실제 원어민이 사용하는 자연스러운 표현\n"
                "2. 예문은 반드시 영어 + 한국어 번역 형태로 제공 (예: 'I'm swamped. - 너무 바빠.') \n"
                "3. 초보자도 이해할 수 있는 쉬운 설명 사용\n"
                "4. 각 슬라이드는 1개의 핵심 표현에 집중\n\n"
            )

        # 슬라이드 수 설명
        if channel_type == "finance":
            slide_count_desc = (
                f"(title 1장 + content {n_content_slides}장 + "
                f"disclaimer 1장 + summary 1장)"
            )
        else:
            slide_count_desc = f"(title 1장 + content {n_content_slides}장 + summary 1장)"

        prompt: str = (
            f"{channel_instruction}"
            f"아래 주제로 PPT 발표 형식의 유튜브 영상 스크립트를 작성하세요.\n\n"
            f"[주제]: {selected_topic}\n"
            f"[채널명]: {channel_name or '정보 채널'}\n"
            f"[영상 목표 길이]: {duration_min}분\n"
            f"[슬라이드 수]: 정확히 {n_total_slides}장 {slide_count_desc}\n"
            f"[전체 나레이션 목표]: {target_chars}자 이상\n"
            f"{context_section}"
            f"{topic_context_section}\n"
            f"[출력 형식] 아래 JSON 구조만 출력. 다른 텍스트 금지:\n"
            f"{{\n"
            f"  \"topic\": \"{selected_topic}\",\n"
            f"  \"slides\": [\n"
            f"    {{\n"
            f"      \"slide_no\": 1,\n"
            f"      \"type\": \"title\",\n"
            f"      \"title\": \"유튜브 제목처럼 클릭 유도하는 제목 (20자 이내)\",\n"
            f"      \"subtitle\": \"주요 내용을 한 줄로 요약 (30자 이내)\",\n"
            f"      \"narration\": \"시청자 주의를 끄는 오프닝 (150~200자, {hook_description})\"\n"
            f"    }},\n"
            f"    {{\n"
            f"      \"slide_no\": 2,\n"
            f"      \"type\": \"content\",\n"
            f"      \"title\": \"첫 번째 주요 포인트\",\n"
            f"      \"bullets\": [\n"
            f"        \"구체적 사실 포함한 핵심 포인트 1\",\n"
            f"        \"핵심 포인트 2\",\n"
            f"        \"핵심 포인트 3\"\n"
            f"      ],\n"
            f"      \"source\": \"데이터 출처\",\n"
            f"      \"narration\": \"이 슬라이드 상세 설명 (250~350자)\"\n"
            f"    }},\n"
            f"    // ... {content_range_note} ...\n"
        )

        # finance 채널: 면책 슬라이드 예시 포함
        if channel_type == "finance" and n_extra_slides > 0:
            prompt += (
                f"    {{\n"
                f"      \"slide_no\": {last_slide_no - 1},\n"
                f"      \"type\": \"disclaimer\",\n"
                f"      \"title\": \"투자 유의사항\",\n"
                f"      \"bullets\": [\n"
                f"        \"이 영상은 투자 권유가 아닌 정보 제공 목적입니다\",\n"
                f"        \"투자 결정은 전문가 상담 후 본인 판단으로 하시기 바랍니다\",\n"
                f"        \"제공된 정보는 참고용이며 투자 결과에 책임지지 않습니다\"\n"
                f"      ],\n"
                f"      \"narration\": \"이 영상은 투자 권유가 아닌 정보 제공 목적입니다. "
                f"모든 투자 결정은 반드시 전문가와 상담 후 본인 책임 하에 하시기 바랍니다. "
                f"제공된 데이터는 제공된 자료 기준이며 실제 투자 결과와 다를 수 있습니다.\"\n"
                f"    }},\n"
            )

        prompt += (
            f"    {{\n"
            f"      \"slide_no\": {last_slide_no},\n"
            f"      \"type\": \"summary\",\n"
            f"      \"title\": \"핵심 요약\",\n"
            f"      \"bullets\": [\n"
            f"        \"요약 포인트 1\",\n"
            f"        \"요약 포인트 2\",\n"
            f"        \"요약 포인트 3\"\n"
            f"      ],\n"
            f"      \"narration\": \"전체 내용 정리 + 구독/좋아요 유도 ({cta_description})\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"반드시 JSON만 출력하세요.\n"
        )

        if channel_type == "finance":
            prompt += (
                "[최종 확인] 투자 권유 문구가 없는지, 면책 슬라이드가 포함됐는지 확인하세요."
            )
        return prompt

    def _parse_slides_json(
        self, raw: str, n_slides: int, selected_topic: str, channel_type: str = "finance"
    ) -> list[dict]:
        """Ollama 응답에서 slides 배열 추출.

        폴백 체계:
          1. 완전 JSON 파싱 시도 (dict.slides 또는 list)
          2. "slides" 배열 부분만 추출
          3. 최후 폴백: 기본 슬라이드 3장 생성
        """
        # 코드펜스 제거
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()
        # 줄 시작 주석만 제거 (// ... 패턴) — 문자열 내 URL(https://) 보존
        cleaned = re.sub(r"^\s*//[^\n]*", "", cleaned, flags=re.MULTILINE)

        # 1단계: dict { "slides": [...] } 형태 파싱
        brace_start: int = cleaned.find("{")
        brace_end: int = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            candidate: str = cleaned[brace_start: brace_end + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "slides" in data:
                    slides = data["slides"]
                    if isinstance(slides, list) and len(slides) > 0:
                        logger.info(
                            f"[F007][STAGE_02] JSON 파싱 성공 (dict.slides) - {len(slides)}장"
                        )
                        return slides
            except (json.JSONDecodeError, ValueError):
                pass

        # 1단계 보조: JSON 배열 직접 파싱
        bracket_start: int = cleaned.find("[")
        bracket_end: int = cleaned.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            candidate_list: str = cleaned[bracket_start: bracket_end + 1]
            try:
                data_list = json.loads(candidate_list)
                if isinstance(data_list, list) and len(data_list) > 0:
                    logger.info(
                        f"[F007][STAGE_02] JSON 파싱 성공 (list) - {len(data_list)}장"
                    )
                    return data_list
            except (json.JSONDecodeError, ValueError):
                pass

        # 2단계: "slides" 배열 부분만 정규식으로 추출
        match = re.search(r'"slides"\s*:\s*(\[.*?\])', cleaned, re.DOTALL)
        if match:
            try:
                slides_candidate = json.loads(match.group(1))
                if isinstance(slides_candidate, list) and len(slides_candidate) > 0:
                    logger.info(
                        f"[F007][STAGE_02] JSON 파싱 성공 (slides 부분 추출) - "
                        f"{len(slides_candidate)}장"
                    )
                    return slides_candidate
            except (json.JSONDecodeError, ValueError):
                pass

        # 3단계: 최후 폴백 - 기본 슬라이드 생성 (finance: 면책 포함 4장, language: 3장)
        logger.warning(
            f"[F007][STAGE_02] JSON 파싱 실패 - 폴백 슬라이드 생성 "
            f"(목표 {n_slides}장, raw 길이 {len(raw)}자, channel_type={channel_type})"
        )
        # raw JSON 조각을 narration에 넣으면 TTS가 JSON 구문을 읽으므로 안전한 기본 텍스트 사용
        fallback_slides = [
            {
                "slide_no": 1,
                "type": "title",
                "title": selected_topic[:20],
                "subtitle": "",
                "narration": f"{selected_topic} 주제로 시작합니다.",
            },
            {
                "slide_no": 2,
                "type": "content",
                "title": "주요 내용",
                "bullets": ["내용을 확인하세요"],
                "source": "",
                "narration": "주요 내용을 설명합니다.",
            },
            {
                "slide_no": 3,
                "type": "summary",
                "title": "핵심 요약",
                "bullets": [f"주제: {selected_topic[:20]}"],
                "narration": "오늘 영상을 마칩니다. 구독 부탁드립니다.",
            },
        ]
        # finance 채널: 면책 슬라이드 필수 추가 (법적 요건)
        if channel_type == "finance":
            fallback_slides.append({
                "slide_no": 4,
                "type": "disclaimer",
                "title": "투자 유의사항",
                "bullets": [
                    "이 영상은 투자 권유가 아닙니다",
                    "투자 결과에 대한 책임은 본인에게 있습니다",
                    "반드시 전문가 상담 후 투자 판단하세요",
                ],
                "narration": "이 영상은 투자 권유가 아니며, 투자 결과에 대한 책임은 본인에게 있습니다. 반드시 전문가 상담 후 투자 여부를 판단하시기 바랍니다.",
            })
        return fallback_slides

    def _build_script_text(self, slides: list[dict]) -> str:
        """모든 슬라이드의 narration을 이어붙여 TTS용 script_text 생성."""
        parts: list[str] = []
        for slide in slides:
            narration: str = slide.get("narration", "").strip()
            if narration:
                parts.append(narration)
        return " ".join(parts)

    def _find_topic_detail(self, selected_topic: str, topics: list) -> dict:
        """topics 목록에서 selected_topic 제목과 일치하는 항목의 세부 정보 반환."""
        for topic in topics:
            if isinstance(topic, dict) and topic.get("title", "") == selected_topic:
                return topic
        return {}
