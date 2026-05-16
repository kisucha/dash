# 목적: STAGE_02 — 선택된 주제 기반 유튜브 스크립트 생성 스테이지.
# Ollama로 훅/본문/CTA 구조의 스크립트를 생성하고 씬 단위로 분해한다.

import sys
import json
import re
import logging

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f001_youtube.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)


class Stage02Script(BaseStage, BasePipeline):
    """STAGE_02 — 선택된 주제 기반 스크립트 생성 스테이지.

    처리 흐름:
      1. STAGE_01에서 사용자가 선택한 selected_topic 확인
      2. Ollama로 훅/본문/CTA JSON 스크립트 생성
      3. Ollama로 스크립트를 씬(scene) 단위로 분해
      4. 전체 스크립트 텍스트 조합 + 분량 검증

    validate_input에서 selected_topic이 없으면
    STAGE_01_RESEARCH로 반송 요청을 반환한다.
    """

    STAGE_ID: str = "STAGE_02_SCRIPT"
    STAGE_ORDER: int = 2

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F001_STAGE02", "name": "STAGE_02_SCRIPT"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 — selected_topic 필수.

        selected_topic이 없으면 STAGE_01로 반송 — 주제 미선택 상태.
        """
        selected_topic = data.get("selected_topic")
        if not selected_topic or not str(selected_topic).strip():
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    "선택된 주제가 없습니다. "
                    "STAGE_01에서 주제를 선택한 뒤 STAGE_02를 재시작하세요."
                ),
                rejection_target="STAGE_01_RESEARCH",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_02 실행 — 스크립트 생성 + 씬 분해.

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
                script (dict: hook/body/cta), scenes (list),
                script_text (str), total_chars (int),
                estimated_duration_min (int), generated_at
            }
        """
        # 파라미터 추출 및 기본값 적용
        selected_topic: str = str(input_data.get("selected_topic", "")).strip()
        duration_min: int = int(input_data.get("duration_min", 10))
        channel_tone: str = input_data.get("channel_tone", "educational")
        hook_style: str = input_data.get("hook_style", "question")
        cta_type: str = input_data.get("cta_type", "subscribe")
        channel_category: str = input_data.get("channel_category", "")
        search_context: str = input_data.get("search_context", "")
        topics: list = input_data.get("topics", [])

        # 분당 170자 기준 목표 글자 수 산정
        target_chars: int = duration_min * 170

        # 씬당 25초 기준 목표 씬 수 — duration_min 설정에 비례해 자동 산정
        # 예: 10분 → 24씬, 5분 → 12씬, 최소 8씬 보장
        n_scenes_target: int = max(8, int(round(duration_min * 60 / 25)))

        # 선택된 주제의 세부 정보 추출 (keywords, recommended_reason, score)
        topic_detail: dict = self._find_topic_detail(selected_topic, topics)
        keywords: str = ", ".join(topic_detail.get("keywords", [])) or selected_topic
        recommended_reason: str = topic_detail.get("recommended_reason", "")
        topic_score: int = topic_detail.get("score", 0)

        # 훅 스타일 한국어 설명 매핑
        hook_style_map: dict = {
            "question": "질문형 — '이거 알고 있었나요?' 같은 직접 질문으로 시작",
            "statistic": "수치/통계형 — 충격적인 숫자나 퍼센트로 시작 (예: '실제로 90%가...')",
            "story": "스토리텔링형 — 개인 경험이나 실제 사례 에피소드로 시작",
            "problem": "문제 제기형 — 시청자가 겪는 고통·불편을 정확히 짚어 시작",
            "shock": "충격/반전형 — '지금까지 알던 것이 틀렸습니다' 같은 반전으로 시작",
        }
        hook_description: str = hook_style_map.get(hook_style, hook_style)

        # 채널 톤 한국어 설명 매핑
        tone_map: dict = {
            "educational": "교육형 — 명확한 개념 설명, 단계별 학습 구조, 이해하기 쉬운 비유",
            "entertaining": "엔터테인먼트형 — 유머, 과장, 빠른 전개, 감정 자극",
            "informative": "정보 전달형 — 팩트 중심, 밀도 높은 정보, 객관적 근거 제시",
            "conversational": "대화형 — 친근한 말투, 시청자와 대화하듯, 공감 유도",
            "professional": "전문가형 — 업계 전문 용어 사용, 권위 있는 분석, 심층 인사이트",
        }
        tone_description: str = tone_map.get(channel_tone, channel_tone)

        # CTA 유형 설명 매핑
        cta_map: dict = {
            "subscribe": "구독 유도 — '다음 영상도 놓치지 않으려면 구독 버튼을'",
            "like": "좋아요 유도 — '도움이 됐다면 좋아요 한 번이 큰 힘이 됩니다'",
            "comment": "댓글 유도 — '여러분의 경험을 댓글로 알려주세요'",
            "next_video": "다음 영상 연결 — '이 내용을 더 깊이 이해하려면 이 영상을 보세요'",
        }
        cta_description: str = cta_map.get(cta_type, cta_type)

        logger.info(
            f"[STAGE_02][job_id={job_id}] 실행 시작 — "
            f"주제: {selected_topic!r}, 목표: {duration_min}분({target_chars}자), "
            f"리서치 컨텍스트: {len(search_context)}자"
        )

        # ----------------------------------------------------------------
        # 1단계: 스크립트 생성 (Ollama) — 리서치 컨텍스트 + 전문성 지시 포함
        # ----------------------------------------------------------------
        # 검색 컨텍스트 섹션 (있을 때만 포함)
        research_section: str = ""
        if search_context and search_context.strip() and "(검색 결과 없음" not in search_context:
            research_section = (
                f"\n[트렌드 리서치 데이터]\n"
                f"아래는 이 주제와 관련해 수집된 실제 트렌드 데이터입니다.\n"
                f"스크립트 작성 시 이 데이터를 적극 활용하여 구체적 사실과 맥락을 제공하세요.\n"
                f"{search_context[:2500]}\n"
            )

        topic_context_section: str = ""
        if recommended_reason or keywords:
            topic_context_section = (
                f"\n[주제 선정 배경]\n"
                f"선정 이유: {recommended_reason}\n"
                f"핵심 키워드: {keywords}\n"
            )

        script_prompt: str = (
            f"당신은 구독자 100만 채널을 운영한 경험이 있는 전문 유튜브 스크립트 작가입니다.\n"
            f"아래 조건에 맞는 완성도 높은 스크립트를 작성하세요.\n\n"
            f"[채널 정보]\n"
            f"카테고리: {channel_category or '일반'}\n"
            f"주제: {selected_topic}\n"
            f"채널 스타일: {tone_description}\n"
            f"목표 영상 길이: {duration_min}분 (약 {target_chars}자 이상)\n"
            f"{research_section}"
            f"{topic_context_section}\n"
            f"[스크립트 작성 필수 지침]\n"
            f"1. 훅 (처음 15초): {hook_description}\n"
            f"   - 추상적 표현 금지. 구체적 수치·사례·질문 반드시 포함\n"
            f"   - 시청자가 이 영상을 끝까지 봐야 하는 이유를 명확히 제시\n"
            f"2. 본문 각 섹션:\n"
            f"   - 최소 3개 이상의 독립 섹션으로 구성\n"
            f"   - 각 섹션마다 구체적 수치, 통계, 실제 사례, 전문가 의견 포함\n"
            f"   - '~합니다' 같은 단순 설명 대신 WHY(왜)와 HOW(어떻게)를 깊이 설명\n"
            f"   - 시청자가 즉시 활용 가능한 실용적 인사이트 제공\n"
            f"3. 아웃트로: {cta_description}\n\n"
            f"[출력 형식] 아래 JSON만 출력하세요. 다른 텍스트 금지:\n"
            f"{{\n"
            f"  \"hook\": \"시청자를 강하게 끌어당기는 오프닝 멘트 (구체적 수치/사례 포함)\",\n"
            f"  \"body\": [\n"
            f"    {{\"section_title\": \"섹션 제목\", \"content\": \"충분한 깊이의 본문 내용 (최소 200자)\", \"duration_sec\": 120}}\n"
            f"  ],\n"
            f"  \"cta\": \"자연스럽고 설득력 있는 아웃트로\"\n"
            f"}}\n"
            f"JSON만 출력하세요."
        )

        logger.info(f"[STAGE_02][job_id={job_id}] 스크립트 생성 Ollama 호출 시작")
        try:
            raw_script: str = self.call_ollama(
                prompt=script_prompt,
                timeout=180,
                num_predict=4096,
            )
        except Exception as e:
            logger.error(f"[STAGE_02][job_id={job_id}] 스크립트 생성 Ollama 실패: {e}")
            raise RuntimeError(f"STAGE_02 스크립트 생성 실패: {e}") from e

        # 스크립트 JSON 파싱
        parsed_script: dict = self._parse_script_json(raw_script)
        logger.info(
            f"[STAGE_02][job_id={job_id}] 스크립트 파싱 완료 — "
            f"body 섹션: {len(parsed_script.get('body', []))}개"
        )

        # ----------------------------------------------------------------
        # 2단계: 씬 분해 (Ollama) — 목표 씬 수 명시로 충분한 클립 생성 보장
        # ----------------------------------------------------------------
        # 씬 분해 프롬프트에 스크립트 앞 5000자 제공 (2000자에서 확장)
        script_text_preview: str = self._build_script_text(parsed_script)[:5000]
        total_target_sec: int = duration_min * 60

        scene_prompt: str = (
            f"다음 스크립트를 유튜브 영상 씬으로 분해하세요.\n\n"
            f"[필수 조건]\n"
            f"- 총 영상 길이: {duration_min}분 ({total_target_sec}초)\n"
            f"- 씬 수: 정확히 {n_scenes_target}개\n"
            f"- 씬당 시간: 약 {total_target_sec // n_scenes_target}초 (내용에 따라 15~35초 범위)\n"
            f"- 모든 씬의 duration_sec 합계는 {total_target_sec}초가 되어야 함\n"
            f"- 각 씬의 description은 해당 구간 스크립트 내용을 기반으로 배경 영상 구성을 묘사\n\n"
            f"[출력 형식] JSON 배열만 출력하세요. 다른 텍스트 금지:\n"
            f"[{{\"scene_no\": 1, \"description\": \"씬 배경 영상 설명\", \"duration_sec\": 25}}, ...]\n\n"
            f"스크립트:\n{script_text_preview}\n\n"
            f"JSON만 출력하세요."
        )

        logger.info(
            f"[STAGE_02][job_id={job_id}] 씬 분해 Ollama 호출 — "
            f"목표 {n_scenes_target}씬 / {total_target_sec}초"
        )
        try:
            raw_scenes: str = self.call_ollama(
                prompt=scene_prompt,
                timeout=180,
                num_predict=4096,
            )
        except Exception as e:
            logger.warning(
                f"[STAGE_02][job_id={job_id}] 씬 분해 Ollama 실패 (빈 씬으로 계속): {e}"
            )
            raw_scenes = "[]"

        # 씬 JSON 파싱
        scenes: list[dict] = self._parse_scenes_json(raw_scenes)
        logger.info(
            f"[STAGE_02][job_id={job_id}] 씬 분해 완료 — {len(scenes)}개"
        )

        # ── duration_sec 정규화 — 합계를 duration_min * 60으로 스케일 ──
        # Ollama가 반환한 duration_sec 합계와 실제 목표 길이를 일치시킨다.
        if scenes:
            raw_total_sec: int = sum(int(s.get("duration_sec", 25)) for s in scenes)
            if raw_total_sec > 0 and abs(raw_total_sec - total_target_sec) > 10:
                scale: float = total_target_sec / raw_total_sec
                for s in scenes:
                    s["duration_sec"] = max(5, int(int(s.get("duration_sec", 25)) * scale))
                logger.info(
                    f"[STAGE_02][job_id={job_id}] duration_sec 정규화 — "
                    f"{raw_total_sec}초 → {total_target_sec}초 (scale={scale:.2f})"
                )

        # ----------------------------------------------------------------
        # 3단계: 전체 스크립트 텍스트 조합 및 분량 계산
        # ----------------------------------------------------------------
        script_text: str = self._build_script_text(parsed_script)
        total_chars: int = len(script_text)
        estimated_duration_min: int = max(1, total_chars // 170)

        logger.info(
            f"[STAGE_02][job_id={job_id}] 완료 — "
            f"총 {total_chars}자, 추정 {estimated_duration_min}분"
        )

        return {
            "stage_id": "STAGE_02_SCRIPT",
            "status": "COMPLETED",
            "selected_topic": selected_topic,
            "script": parsed_script,
            "scenes": scenes,
            "script_text": script_text,
            "total_chars": total_chars,
            "estimated_duration_min": estimated_duration_min,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 — 스크립트 분량 최소 200자 이상.

        200자 미만이면 Ollama가 충분한 스크립트를 생성하지 못한 것으로 판단해
        STAGE_02 자기 재시도를 요청한다.
        """
        total_chars: int = output.get("total_chars", 0)
        if total_chars < 200:
            return ValidationResult(
                is_valid=False,
                rejection_reason=(
                    f"스크립트 분량 부족 ({total_chars}자). "
                    f"최소 200자 이상이어야 합니다. 재생성이 필요합니다."
                ),
                rejection_target="STAGE_02_SCRIPT",
            )
        return ValidationResult(is_valid=True)

    # ------------------------------------------------------------------
    # 내부 헬퍼 메서드
    # ------------------------------------------------------------------

    def _parse_script_json(self, raw: str) -> dict:
        """Ollama 스크립트 응답에서 JSON을 파싱.

        파싱 실패 시 원본 텍스트를 hook으로 사용하는 폴백 딕셔너리를 반환한다.
        """
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # 중괄호 범위 추출
        brace_start: int = cleaned.find("{")
        brace_end: int = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            cleaned = cleaned[brace_start : brace_end + 1]

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("dict가 아닌 타입 반환")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"스크립트 JSON 파싱 실패 ({e}), 원본 텍스트를 hook으로 폴백"
            )
            return {
                "hook": raw[:500],
                "body": [{"section_title": "본문", "content": raw[500:], "duration_sec": 60}],
                "cta": "구독과 좋아요 부탁드립니다!",
            }

    def _parse_scenes_json(self, raw: str) -> list[dict]:
        """Ollama 씬 분해 응답에서 JSON 배열을 파싱.

        파싱 실패 시 빈 리스트를 반환한다 (씬 없어도 파이프라인 계속 진행 가능).
        """
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        bracket_start: int = cleaned.find("[")
        bracket_end: int = cleaned.rfind("]")
        if bracket_start != -1 and bracket_end != -1:
            cleaned = cleaned[bracket_start : bracket_end + 1]

        try:
            scenes = json.loads(cleaned)
            if isinstance(scenes, list):
                return scenes
            raise ValueError("list가 아닌 타입 반환")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"씬 JSON 파싱 실패 ({e}), 빈 씬 반환")
            return []

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

    def _build_script_text(self, parsed_script: dict) -> str:
        """파싱된 스크립트 딕셔너리에서 전체 텍스트를 조합.

        hook + body 각 섹션 content + cta를 공백으로 연결한다.

        Args:
            parsed_script: {hook: str, body: list[{content: str}], cta: str}

        Returns:
            전체 스크립트 텍스트 문자열
        """
        parts: list[str] = []

        hook: str = parsed_script.get("hook", "")
        if hook:
            parts.append(hook)

        body: list[dict] = parsed_script.get("body", [])
        for section in body:
            content: str = section.get("content", "")
            if content:
                parts.append(content)

        cta: str = parsed_script.get("cta", "")
        if cta:
            parts.append(cta)

        return " ".join(parts)
