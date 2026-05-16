# 목적: F004 STAGE_02 — 슬라이드 친화적 유튜브 스크립트 생성
# Ollama로 PPT 슬라이드 구조(title/content/summary)의 스크립트를 직접 생성한다.

import sys

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import re
import logging

from datetime import datetime, timezone

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f004_youtube_v2.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage02Script(BaseStage, BasePipeline):
    """STAGE_02 — 선택된 주제 기반 슬라이드 친화적 스크립트 생성 스테이지.

    처리 흐름:
      1. STAGE_01에서 사용자가 선택한 selected_topic 확인
      2. 슬라이드 수 / 목표 글자 수 계산
      3. Ollama로 PPT 슬라이드 구조 JSON 스크립트 생성 (단일 호출)
      4. slides 배열 파싱 + script_text 조합 + 분량 검증

    validate_input에서 selected_topic이 없으면
    STAGE_01_RESEARCH로 반송 요청을 반환한다.

    출력 키 변경 사항:
      - scenes 키 제거 (ComfyUI 불필요)
      - slides 배열 추가 (PPT 슬라이드 구조)
      - script_text 유지 (STAGE_03 TTS가 이 키를 읽음)
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
        return {"feature_id": "F004_STAGE02", "name": "STAGE_02_SCRIPT"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 — selected_topic 필수.

        selected_topic이 없으면 STAGE_01로 반송 — 주제 미선택 상태.
        """
        if not data.get("selected_topic", "").strip():
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    "selected_topic 없음. STAGE_01에서 주제를 선택하세요."
                ),
                rejection_target="STAGE_01_RESEARCH",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_02 실행 — 슬라이드 구조 스크립트 생성.

        Args:
            job_id: content_jobs.id
            input_data: {
                selected_topic (str, 필수): 사용자가 선택한 주제 제목
                duration_min (int, 기본 10): 목표 영상 길이(분)
                channel_tone (str, 기본 "educational"): 채널 톤
                hook_style (str, 기본 "question"): 훅 스타일
                cta_type (str, 기본 "subscribe"): CTA 유형
                channel_category (str, 기본 ""): 채널 카테고리 (STAGE_01 인계)
                search_context (str, 기본 ""): SearXNG 리서치 컨텍스트 (STAGE_01 인계)
                topics (list, 기본 []): 주제 후보 목록 (선택 주제 세부 정보 추출용)
            }

        Returns:
            {
                stage_id, status, selected_topic,
                slides (list): PPT 슬라이드 배열 (title/content/summary),
                script_text (str): 전체 나레이션 텍스트 (STAGE_03 TTS용),
                total_chars (int), estimated_duration_min (int),
                total_slides (int), generated_at (str)
            }
        """
        # 파라미터 추출 및 기본값 적용
        selected_topic: str = str(input_data.get("selected_topic", "")).strip()
        duration_min: int = int(input_data.get("duration_min", 10))
        hook_style: str = input_data.get("hook_style", "question")
        cta_type: str = input_data.get("cta_type", "subscribe")
        channel_category: str = input_data.get("channel_category", "")
        search_context: str = input_data.get("search_context", "")
        topics: list = input_data.get("topics", [])
        days: int = int(input_data.get("days", 7))
        today_str: str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 슬라이드 수 및 목표 글자 수 계산
        # content 슬라이드: 분당 80초 기준, 최소 4장 최대 12장
        n_content_slides: int = max(4, min(12, (duration_min * 60) // 80))
        # title 1장 + summary 1장 고정
        n_total_slides: int = n_content_slides + 2
        # 분당 170자 기준 목표 글자 수
        target_chars: int = duration_min * 170

        # 선택된 주제의 세부 정보 추출 (STAGE_01 topics 목록에서)
        topic_detail: dict = self._find_topic_detail(selected_topic, topics)
        keywords: str = ", ".join(topic_detail.get("keywords", [])) or selected_topic
        recommended_reason: str = topic_detail.get("recommended_reason", "")

        # 훅/CTA 설명 문자열 결정
        hook_description: str = self._HOOK_DESCRIPTIONS.get(hook_style, "강한 훅으로 시작")
        cta_description: str = self._CTA_DESCRIPTIONS.get(cta_type, "구독 유도")

        logger.info(
            f"[F004][STAGE_02][job_id={job_id}] 실행 시작 — "
            f"주제: {selected_topic!r}, 목표: {duration_min}분({target_chars}자), "
            f"슬라이드: {n_total_slides}장(content {n_content_slides}장), "
            f"리서치 컨텍스트: {len(search_context)}자"
        )

        # ----------------------------------------------------------------
        # 1단계: 검색 컨텍스트 / 주제 배경 섹션 구성
        # ----------------------------------------------------------------
        # 검색 컨텍스트 섹션 (있을 때만 포함)
        search_context_section: str = ""
        if search_context and search_context.strip() and "(검색 결과 없음" not in search_context:
            search_context_section = (
                f"\n[트렌드 리서치 데이터 — {today_str} 기준 최근 {days}일 이내 수집]\n"
                f"아래는 이 주제와 관련해 수집된 실제 트렌드 데이터입니다.\n"
                f"슬라이드 작성 시 이 데이터를 적극 활용하여 구체적 사실과 맥락을 제공하세요.\n"
                f"주의: {today_str} 기준 {days}일 이상 된 오래된 사건이나 수치는 인용하지 마세요.\n"
                f"{search_context[:2500]}\n"
            )

        # 주제 배경 섹션 (있을 때만 포함)
        topic_context_section: str = ""
        if recommended_reason or keywords:
            topic_context_section = (
                f"\n[주제 선정 배경]\n"
                f"선정 이유: {recommended_reason}\n"
                f"핵심 키워드: {keywords}\n"
            )

        # topics 후보 제목 목록 (LLM 참고용)
        topics_text: str = ""
        if topics:
            topic_titles = [
                t.get("title", "") for t in topics if isinstance(t, dict) and t.get("title")
            ]
            topics_text = "\n".join(f"- {t}" for t in topic_titles[:10])

        # ----------------------------------------------------------------
        # 2단계: 슬라이드 스크립트 생성 (단일 Ollama 호출)
        # ----------------------------------------------------------------
        slide_prompt: str = self._build_slide_prompt(
            selected_topic=selected_topic,
            channel_category=channel_category,
            duration_min=duration_min,
            n_total_slides=n_total_slides,
            n_content_slides=n_content_slides,
            target_chars=target_chars,
            search_context_section=search_context_section,
            topic_context_section=topic_context_section,
            topics_text=topics_text,
            hook_description=hook_description,
            cta_description=cta_description,
            today_str=today_str,
            days=days,
        )

        logger.info(
            f"[F004][STAGE_02][job_id={job_id}] 슬라이드 스크립트 Ollama 호출 시작 — "
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
                f"[F004][STAGE_02][job_id={job_id}] 슬라이드 생성 Ollama 실패: {e}"
            )
            raise RuntimeError(f"STAGE_02 슬라이드 생성 실패: {e}") from e

        # ----------------------------------------------------------------
        # 3단계: slides 배열 파싱
        # ----------------------------------------------------------------
        slides: list[dict] = self._parse_slides_json(
            raw=raw_slides,
            n_slides=n_total_slides,
            selected_topic=selected_topic,
        )
        logger.info(
            f"[F004][STAGE_02][job_id={job_id}] 슬라이드 파싱 완료 — {len(slides)}장"
        )

        # ----------------------------------------------------------------
        # 4단계: script_text 조합 및 분량 계산
        # ----------------------------------------------------------------
        script_text: str = self._build_script_text(slides)
        total_chars: int = len(script_text)
        estimated_duration_min: int = max(1, total_chars // 170)

        logger.info(
            f"[F004][STAGE_02][job_id={job_id}] 완료 — "
            f"슬라이드 {len(slides)}장, 총 {total_chars}자, "
            f"추정 {estimated_duration_min}분"
        )

        return {
            "stage_id": "STAGE_02_SCRIPT",
            "status": "COMPLETED",
            "selected_topic": selected_topic,
            "slides": slides,
            "script_text": script_text,
            "total_chars": total_chars,
            "estimated_duration_min": estimated_duration_min,
            "total_slides": len(slides),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 — 슬라이드 최소 3장 이상 + 나레이션 최소 200자 이상.

        슬라이드 부족 또는 나레이션 분량 미달 시 STAGE_02 자기 재시도 요청.
        """
        slides = output.get("slides", [])
        if len(slides) < 3:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    f"슬라이드 수 부족: {len(slides)}장. 최소 3장 필요."
                ),
                rejection_target="STAGE_02_SCRIPT",
            )

        total_chars: int = output.get("total_chars", 0)
        if total_chars < 200:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    f"나레이션 분량 부족: {total_chars}자. 최소 200자 이상 필요."
                ),
                rejection_target="STAGE_02_SCRIPT",
            )

        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    def _build_slide_prompt(
        self,
        selected_topic: str,
        channel_category: str,
        duration_min: int,
        n_total_slides: int,
        n_content_slides: int,
        target_chars: int,
        search_context_section: str,
        topic_context_section: str,
        topics_text: str,
        hook_description: str,
        cta_description: str,
        today_str: str = "",
        days: int = 7,
    ) -> str:
        """Ollama에 전달할 슬라이드 생성 프롬프트 구성.

        단일 호출로 PPT 슬라이드 구조 전체를 생성하도록 지시한다.
        title 1장 + content N장 + summary 1장 구조를 명시한다.
        """
        # 참고 주제 후보 섹션 (있을 때만 포함)
        topics_section: str = ""
        if topics_text:
            topics_section = f"\n[참고 주제 후보들]\n{topics_text}\n"

        # 마지막 summary 슬라이드 번호
        last_slide_no: int = n_total_slides

        # content 슬라이드 예시 범위 (2 ~ n_total_slides-1)
        content_range_note: str = (
            f"slide_no 3 ~ {n_total_slides - 1}: type=\"content\""
            if n_content_slides > 1
            else ""
        )

        date_constraint: str = ""
        if today_str:
            date_constraint = (
                f"오늘 날짜: {today_str}\n"
                f"[중요] 반드시 {today_str} 기준 최근 {days}일 이내의 정보만 사용하세요. "
                f"{days}일보다 오래된 사건, 수치, 뉴스는 언급하지 마세요.\n\n"
            )

        prompt: str = (
            f"당신은 뉴스/정보 채널 전문 유튜브 스크립트 작가입니다.\n"
            f"{date_constraint}"
            f"아래 주제로 PPT 발표 형식의 유튜브 영상 스크립트를 작성하세요.\n\n"
            f"[주제]: {selected_topic}\n"
            f"[채널 카테고리]: {channel_category or '정보/뉴스'}\n"
            f"[영상 목표 길이]: {duration_min}분\n"
            f"[슬라이드 수]: 정확히 {n_total_slides}장 "
            f"(title 1장 + content {n_content_slides}장 + summary 1장)\n"
            f"[전체 나레이션 목표]: {target_chars}자 이상\n"
            f"{search_context_section}"
            f"{topic_context_section}"
            f"{topics_section}\n"
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
            f"        \"구체적 수치나 사실 포함한 핵심 포인트 1\",\n"
            f"        \"핵심 포인트 2\",\n"
            f"        \"핵심 포인트 3\"\n"
            f"      ],\n"
            f"      \"source\": \"뉴스 출처 또는 데이터 출처\",\n"
            f"      \"narration\": \"이 슬라이드 상세 설명 (250~350자, 구체적 사실 중심)\"\n"
            f"    }},\n"
            f"    // ... {content_range_note} ...\n"
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
            f"반드시 JSON만 출력하세요."
        )
        return prompt

    def _parse_slides_json(
        self, raw: str, n_slides: int, selected_topic: str
    ) -> list[dict]:
        """Ollama 응답에서 slides 배열 추출.

        폴백 체계:
          1. 완전 JSON 파싱 시도 (dict.slides 또는 list)
          2. "slides" 배열 부분만 추출
          3. 최후 폴백: 기본 슬라이드 3장 생성

        Args:
            raw: Ollama 원본 응답 문자열
            n_slides: 목표 슬라이드 수 (폴백 로그용)
            selected_topic: 선택된 주제 (폴백 슬라이드 제목용)

        Returns:
            slides 딕셔너리 리스트
        """
        # 코드펜스 제거
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # 주석 라인 제거 (// ... 패턴)
        cleaned = re.sub(r"//[^\n]*", "", cleaned)

        # 1단계: 완전 JSON 파싱 시도 — dict { "slides": [...] } 형태
        brace_start: int = cleaned.find("{")
        brace_end: int = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            candidate: str = cleaned[brace_start : brace_end + 1]
            try:
                data = json.loads(candidate)
                if isinstance(data, dict) and "slides" in data:
                    slides = data["slides"]
                    if isinstance(slides, list) and len(slides) > 0:
                        logger.info(
                            f"[F004][STAGE_02] JSON 파싱 성공 (dict.slides) — {len(slides)}장"
                        )
                        return slides
            except (json.JSONDecodeError, ValueError):
                pass

        # 1단계 보조: JSON 배열 직접 파싱 시도
        bracket_start: int = cleaned.find("[")
        bracket_end: int = cleaned.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            candidate_list: str = cleaned[bracket_start : bracket_end + 1]
            try:
                data_list = json.loads(candidate_list)
                if isinstance(data_list, list) and len(data_list) > 0:
                    logger.info(
                        f"[F004][STAGE_02] JSON 파싱 성공 (list) — {len(data_list)}장"
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
                        f"[F004][STAGE_02] JSON 파싱 성공 (slides 부분 추출) — "
                        f"{len(slides_candidate)}장"
                    )
                    return slides_candidate
            except (json.JSONDecodeError, ValueError):
                pass

        # 3단계: 최후 폴백 — 기본 슬라이드 3장 생성
        logger.warning(
            f"[F004][STAGE_02] JSON 파싱 실패 — 기본 슬라이드 3장 생성 "
            f"(목표 {n_slides}장, raw 길이 {len(raw)}자)"
        )
        # raw 텍스트를 분할하여 나레이션에 활용
        raw_part1: str = raw[:300].strip()
        raw_part2: str = raw[300:800].strip()
        raw_part3: str = raw[800:1100].strip()

        return [
            {
                "slide_no": 1,
                "type": "title",
                "title": selected_topic[:20],
                "subtitle": "",
                "narration": raw_part1 if raw_part1 else f"{selected_topic} 주제로 시작합니다.",
            },
            {
                "slide_no": 2,
                "type": "content",
                "title": "주요 내용",
                "bullets": ["내용을 확인하세요"],
                "source": "",
                "narration": raw_part2 if raw_part2 else "주요 내용을 설명합니다.",
            },
            {
                "slide_no": 3,
                "type": "summary",
                "title": "핵심 요약",
                "bullets": [f"주제: {selected_topic[:20]}"],
                "narration": raw_part3 if raw_part3 else "오늘 영상을 마칩니다. 구독 부탁드립니다.",
            },
        ]

    def _build_script_text(self, slides: list[dict]) -> str:
        """모든 슬라이드의 narration을 이어붙여 TTS용 script_text 생성.

        STAGE_03 TTS가 이 키를 읽어 음성 생성에 사용한다.
        빈 narration 슬라이드는 건너뛴다.

        Args:
            slides: PPT 슬라이드 딕셔너리 리스트

        Returns:
            전체 나레이션 텍스트 (공백으로 연결)
        """
        parts: list[str] = []
        for slide in slides:
            narration: str = slide.get("narration", "").strip()
            if narration:
                parts.append(narration)
        return " ".join(parts)

    def _find_topic_detail(self, selected_topic: str, topics: list) -> dict:
        """topics 목록에서 selected_topic 제목과 일치하는 항목의 세부 정보 반환.

        일치 항목 없으면 빈 dict 반환 — 호출부에서 get()으로 안전하게 접근 가능.

        Args:
            selected_topic: 사용자가 선택한 주제 제목 문자열
            topics: STAGE_01이 생성한 주제 후보 딕셔너리 리스트

        Returns:
            일치하는 주제 딕셔너리 또는 {}
        """
        for topic in topics:
            if isinstance(topic, dict) and topic.get("title", "") == selected_topic:
                return topic
        return {}
