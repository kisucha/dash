# 목적: STAGE_06 — SEO 최적화 메타데이터 생성 및 YouTube 업로드 스테이지.
# Ollama로 제목/설명/태그를 생성하고, upload_mode=auto이면 YouTube API로 업로드한다.
# YouTube API 실제 업로드는 Phase 5에서 완성 예정 (현재는 NotImplementedError).

import sys
import json
import re
import logging
import sqlite3

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f001_youtube.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 — 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# DB 경로 상수 — base.py와 동일한 경로 사용
DB_PATH: str = r"C:\Develop\Dash\storage\dash.db"


class Stage06Upload(BaseStage, BasePipeline):
    """STAGE_06 — SEO 최적화 + YouTube 업로드 스테이지.

    처리 흐름:
      1. Ollama로 SEO 제목/설명/태그/제목 변형 생성
      2. upload_mode == "auto": YouTube API로 업로드 (Phase 5 완성 예정)
      3. upload_mode == "manual_approval": PENDING_APPROVAL 상태로 대기
    """

    STAGE_ID: str = "STAGE_06_UPLOAD"
    STAGE_ORDER: int = 6

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F001_STAGE06", "name": "STAGE_06_UPLOAD"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_06 실행 — SEO 생성 + 업로드 처리.

        Args:
            job_id: content_jobs.id
            input_data: {
                script (dict): STAGE_02 스크립트 {hook, body, cta}
                selected_topic (str): 선택된 주제 제목
                upload_mode (str): "manual_approval" 또는 "auto"
                video_file_path (str, optional): STAGE_05 출력 MP4 경로
                privacy (str, 기본 "private"): YouTube 공개 설정
            }

        Returns:
            {
                stage_id, status="COMPLETED",
                seo_metadata (dict), upload_mode,
                upload_status ("PENDING_APPROVAL" 또는 "UPLOADED"),
                youtube_video_id (str or None),
                youtube_url (str or None), generated_at
            }
        """
        # 파라미터 추출
        script_data: dict = input_data.get("script", {})
        selected_topic: str = input_data.get("selected_topic", "")
        upload_mode: str = input_data.get("upload_mode", "manual_approval")
        video_file_path: Optional[str] = input_data.get("video_file_path")
        privacy: str = input_data.get("privacy", "private")

        logger.info(
            f"[STAGE_06][job_id={job_id}] 실행 시작 — "
            f"주제: {selected_topic!r}, 업로드 모드: {upload_mode}"
        )

        # ----------------------------------------------------------------
        # SEO 메타데이터 생성 (Ollama)
        # ----------------------------------------------------------------
        hook_preview: str = script_data.get("hook", "")[:200]
        seo_prompt: str = (
            f"당신은 유튜브 SEO 전문가입니다.\n"
            f"다음 스크립트를 기반으로 최적화된 메타데이터를 JSON으로 생성하세요.\n"
            f"주제: {selected_topic}\n"
            f"훅: {hook_preview}\n\n"
            f"다음 JSON 형식으로만 출력하세요:\n"
            f"{{\n"
            f"  \"title\": \"클릭을 유도하는 제목 (60자 이내)\",\n"
            f"  \"description\": \"영상 설명 (500자 이내, 핵심 키워드 포함, 해시태그 3~5개)\",\n"
            f"  \"tags\": [\"태그1\", \"태그2\", \"태그3\"],\n"
            f"  \"category\": \"28\",\n"
            f"  \"title_variants\": [\"A/B 변형 제목 1\", \"A/B 변형 제목 2\"]\n"
            f"}}\n"
            f"JSON만 출력하세요."
        )

        logger.info(f"[STAGE_06][job_id={job_id}] SEO 메타데이터 생성 Ollama 호출 시작")
        try:
            raw_seo: str = self.call_ollama(
                prompt=seo_prompt,
                timeout=120,
                num_predict=1024,
            )
        except Exception as e:
            logger.error(f"[STAGE_06][job_id={job_id}] SEO Ollama 실패: {e}")
            raise RuntimeError(f"STAGE_06 SEO 생성 실패: {e}") from e

        seo_metadata: dict = self._parse_seo_json(raw_seo, selected_topic)
        logger.info(
            f"[STAGE_06][job_id={job_id}] SEO 메타데이터 생성 완료 — "
            f"제목: {seo_metadata.get('title', '')!r}"
        )

        # ----------------------------------------------------------------
        # 업로드 처리 분기
        # ----------------------------------------------------------------
        upload_status: str = "PENDING_APPROVAL"
        youtube_video_id: Optional[str] = None

        if upload_mode == "auto" and video_file_path and Path(video_file_path).exists():
            logger.info(f"[STAGE_06][job_id={job_id}] auto 모드 — YouTube 업로드 시도")

            # YouTube 잔여 유닛 확인
            remaining_units = self._get_youtube_quota_remaining()
            if remaining_units < 1650:
                raise RuntimeError(
                    f"YouTube API 일일 유닛 부족 (잔여: {remaining_units}유닛). "
                    f"업로드에는 최소 1,650유닛이 필요합니다. 내일 재시도하세요."
                )

            try:
                youtube_video_id = self._upload_to_youtube(
                    video_file_path, input_data, seo_metadata, privacy
                )
                upload_status = "UPLOADED"
                logger.info(
                    f"[STAGE_06][job_id={job_id}] YouTube 업로드 완료 — "
                    f"video_id: {youtube_video_id}"
                )
            except NotImplementedError:
                # Phase 5 이전에는 NotImplementedError를 경고로 처리
                logger.warning(
                    f"[STAGE_06][job_id={job_id}] YouTube 업로드 미구현 — "
                    f"PENDING_APPROVAL로 전환"
                )
                upload_status = "PENDING_APPROVAL"
            except Exception as e:
                logger.error(f"[STAGE_06][job_id={job_id}] YouTube 업로드 실패: {e}")
                raise RuntimeError(f"YouTube 업로드 실패: {e}") from e
        else:
            logger.info(
                f"[STAGE_06][job_id={job_id}] manual_approval 모드 — "
                f"업로드 승인 대기 상태로 전환"
            )

        youtube_url: Optional[str] = (
            f"https://youtu.be/{youtube_video_id}" if youtube_video_id else None
        )

        return {
            "stage_id": "STAGE_06_UPLOAD",
            "status": "COMPLETED",
            "seo_metadata": seo_metadata,
            "upload_mode": upload_mode,
            "upload_status": upload_status,
            "youtube_video_id": youtube_video_id,
            "youtube_url": youtube_url,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # YouTube 관련 헬퍼
    # ------------------------------------------------------------------

    def _get_youtube_quota_remaining(self) -> int:
        """settings 테이블에서 오늘 소모한 YouTube API 유닛을 읽어 잔여 유닛을 반환.

        기본 일일 한도는 10,000유닛이다.
        settings 키 'youtube_quota_used_today'가 없으면 0 소모로 간주한다.

        Returns:
            잔여 유닛 수 (int)
        """
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                cursor = conn.execute(
                    "SELECT value FROM settings WHERE key = 'youtube_quota_used_today'"
                )
                row = cursor.fetchone()
                used = int(row[0]) if row and row[0] else 0
                remaining = max(0, 10000 - used)
                logger.info(f"YouTube API 유닛 — 소모: {used}, 잔여: {remaining}")
                return remaining
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"YouTube 유닛 조회 실패 ({e}), 잔여 10000으로 간주")
            return 10000

    def _upload_to_youtube(
        self,
        video_file_path: str,
        input_data: dict,
        seo_metadata: dict,
        privacy: str,
    ) -> str:
        """YouTube Data API v3로 영상 업로드.

        이 메서드는 Phase 5에서 OAuth 인증 흐름과 함께 구현 예정이다.
        현재는 NotImplementedError를 발생시켜 호출자가 처리하도록 한다.

        Args:
            video_file_path: 업로드할 MP4 파일 경로
            input_data: 전체 입력 데이터 (채널 카테고리 등 메타 포함)
            seo_metadata: STAGE_06에서 생성한 SEO 딕셔너리
            privacy: "public" / "unlisted" / "private"

        Returns:
            업로드된 YouTube 영상 ID (str)

        Raises:
            NotImplementedError: Phase 5 이전에는 항상 발생
        """
        # YouTube API 업로드 구현 (google-api-python-client 필요)
        # 구현 완료 후이 예외를 제거하고 실제 업로드 코드로 교체한다.
        raise NotImplementedError(
            "YouTube 업로드는 OAuth 2.0 설정 완료 후 Phase 5에서 구현됩니다. "
            "upload_mode='manual_approval'로 사용하세요."
        )

    # ------------------------------------------------------------------
    # SEO JSON 파싱 헬퍼
    # ------------------------------------------------------------------

    def _parse_seo_json(self, raw: str, selected_topic: str) -> dict:
        """Ollama SEO 응답에서 JSON을 파싱.

        파싱 실패 시 기본 SEO 딕셔너리를 반환한다.

        Args:
            raw: Ollama 응답 원본 텍스트
            selected_topic: 폴백 제목에 사용할 주제 텍스트

        Returns:
            {title, description, tags, category, title_variants} 딕셔너리
        """
        cleaned: str = re.sub(r"```(?:json)?\s*", "", raw).strip()
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        brace_start: int = cleaned.find("{")
        brace_end: int = cleaned.rfind("}")
        if brace_start != -1 and brace_end != -1:
            cleaned = cleaned[brace_start : brace_end + 1]

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                # 필수 키 기본값 보완
                parsed.setdefault("title", selected_topic[:60])
                parsed.setdefault("description", f"{selected_topic} 영상입니다.")
                parsed.setdefault("tags", [selected_topic])
                parsed.setdefault("category", "28")  # 카테고리 28: Science & Technology
                parsed.setdefault("title_variants", [])
                return parsed
            raise ValueError("dict가 아닌 타입 반환")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"SEO JSON 파싱 실패 ({e}), 폴백 메타데이터 사용")
            return {
                "title": selected_topic[:60],
                "description": f"{selected_topic}에 대한 영상입니다. 구독과 좋아요 부탁드립니다!",
                "tags": [selected_topic, "유튜브", "AI"],
                "category": "28",
                "title_variants": [
                    f"{selected_topic} 완벽 정리",
                    f"꼭 알아야 할 {selected_topic}",
                ],
            }
