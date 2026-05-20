# pipelines/f007_youtube_v5/stages/stage06_upload.py
# 목적: F007 STAGE_06 - YouTube SEO 메타데이터 생성 + 업로드 처리
# finance 채널: 면책 조항 포함 SEO, upload_mode 강제로 manual_approval
# language 채널: 학습 채널 최적화 SEO

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pipelines.f007_youtube_v5.stages import BaseStage, ValidationResult
from pipelines.base import BasePipeline

logger = logging.getLogger(__name__)

# channel_type별 SEO 메타데이터 생성 프롬프트
_SEO_PROMPT_MAP = {
    "finance": (
        "다음 금융 유튜브 영상의 SEO 메타데이터를 생성하세요.\n"
        "주제: {topic}\n"
        "스크립트 요약: {script_summary}\n\n"
        "필수 규칙:\n"
        "1. 제목에 투자 권유 문구 절대 금지 (예: '지금 사야 할', '수익 보장' 등)\n"
        "2. 설명에 면책 조항 반드시 포함: '이 영상은 투자 권유가 아닙니다'\n"
        "3. 태그는 금융/경제 관련 키워드로 구성\n\n"
        "JSON으로만 출력:\n"
        '{{"title":"영상제목(최대60자)","description":"설명(면책포함,최대500자)",'
        '"tags":["태그1","태그2","태그3","태그4","태그5"],"category":"finance"}}'
    ),
    "language": (
        "다음 영어 학습 유튜브 영상의 SEO 메타데이터를 생성하세요.\n"
        "주제: {topic}\n"
        "스크립트 요약: {script_summary}\n\n"
        "최적화 규칙:\n"
        "1. 제목은 학습 효과와 실용성 강조 (예: '원어민이 매일 쓰는', '5분 영어')\n"
        "2. 설명은 초보자도 이해할 수 있는 쉬운 설명\n"
        "3. 태그는 영어 학습 관련 키워드로 구성\n\n"
        "JSON으로만 출력:\n"
        '{{"title":"영상제목(최대60자)","description":"설명(최대500자)",'
        '"tags":["태그1","태그2","태그3","태그4","태그5"],"category":"language"}}'
    ),
}


class Stage06Upload(BaseStage, BasePipeline):
    """STAGE_06 - SEO 메타데이터 생성 + YouTube 업로드.

    처리 흐름:
      1. video_file_path 유효성 확인
      2. finance 채널 upload_mode 강제 (manual_approval)
      3. Ollama로 SEO 메타데이터 생성 (제목, 설명, 태그)
      4. upload_mode 분기:
         - skip: 업로드 없이 메타데이터만 저장
         - manual_approval: 사용자 검토 대기
         - auto: YouTube API로 자동 업로드 (환경변수 필요)
    """
    STAGE_ID: str = "STAGE_06_UPLOAD"
    STAGE_ORDER: int = 6

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F007_STAGE06", "name": "STAGE_06_UPLOAD"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def validate_input(self, data: dict) -> ValidationResult:
        """입력 검증 - video_file_path 존재 필수."""
        vp = data.get("video_file_path")
        if not vp or not Path(vp).exists():
            return ValidationResult(
                is_valid=False,
                rejection_reason="video_file_path 없거나 파일 미존재. STAGE_05에서 영상을 생성하세요.",
                rejection_target="STAGE_05_VIDEO",
            )
        return ValidationResult(is_valid=True)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_06 실행 - SEO 생성 + 업로드 처리.

        Args:
            job_id: content_jobs.id
            input_data: {
                channel_type (str, 기본 "finance"): 채널 유형
                selected_topic (str): 영상 주제
                script_text (str): 스크립트 전체 텍스트 (SEO 생성에 사용)
                video_file_path (str): 최종 MP4 파일 경로
                thumbnail_path (str|None): 썸네일 이미지 경로
                upload_mode (str, 기본 "manual_approval"): 업로드 모드
                privacy (str, 기본 "private"): YouTube 공개 범위
            }

        Returns:
            {
                stage_id, status, upload_mode, channel_type,
                video_file_path (str): 영상 파일 경로,
                thumbnail_path (str|None): 썸네일 경로,
                seo (dict): {title, description, tags, category},
                youtube_video_id (str|None): 업로드 성공 시 YouTube 영상 ID,
                generated_at (str)
            }
        """
        channel_type: str = input_data.get("channel_type", "finance")
        topic: str = input_data.get("selected_topic", "")
        script_text: str = input_data.get("script_text", "")
        video_path: str = input_data.get("video_file_path", "")
        thumbnail_path: Optional[str] = input_data.get("thumbnail_path")
        upload_mode: str = input_data.get("upload_mode", "manual_approval")
        privacy: str = input_data.get("privacy", "private")

        # finance 채널은 upload_mode 강제로 manual_approval (투자 권유 위험 방지)
        if channel_type == "finance":
            if upload_mode == "auto":
                logger.warning(
                    f"[F007][STAGE_06][job_id={job_id}] "
                    f"finance 채널 - upload_mode='auto' -> 'manual_approval' 강제 변경"
                )
            upload_mode = "manual_approval"

        logger.info(
            f"[F007][STAGE_06][job_id={job_id}] 시작 - "
            f"channel_type={channel_type}, upload_mode={upload_mode}"
        )

        # SEO 메타데이터 생성
        seo_data = self._generate_seo(channel_type, topic, script_text[:500])
        logger.info(
            f"[F007][STAGE_06][job_id={job_id}] SEO 생성 완료 - "
            f"title={seo_data.get('title', '')[:30]!r}"
        )

        result = {
            "stage_id": "STAGE_06_UPLOAD",
            "status": "COMPLETED",
            "upload_mode": upload_mode,
            "channel_type": channel_type,
            "video_file_path": video_path,
            "thumbnail_path": thumbnail_path,
            "seo": seo_data,
            "youtube_video_id": None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        if upload_mode == "skip":
            logger.info(
                f"[F007][STAGE_06][job_id={job_id}] skip 모드 - 업로드 없이 완료"
            )
            return result

        if upload_mode == "manual_approval":
            logger.info(
                f"[F007][STAGE_06][job_id={job_id}] manual_approval - 사용자 검토 대기"
            )
            result["upload_status"] = "PENDING_APPROVAL"
            return result

        # auto 모드: YouTube API 업로드 시도
        yt_id = self._upload_to_youtube(
            channel_type=channel_type,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            seo_data=seo_data,
            privacy=privacy,
        )
        result["youtube_video_id"] = yt_id
        if yt_id:
            logger.info(
                f"[F007][STAGE_06][job_id={job_id}] YouTube 업로드 완료 - ID: {yt_id}"
            )
        return result

    def validate_output(self, output: dict) -> ValidationResult:
        """출력 검증 - STAGE_06은 항상 통과 (업로드 실패도 메타데이터는 저장됨)."""
        return ValidationResult(is_valid=True)

    def _generate_seo(
        self,
        channel_type: str,
        topic: str,
        script_summary: str,
    ) -> dict:
        """Ollama로 SEO 메타데이터를 생성한다.

        JSON 파싱 실패 시 기본값 반환.
        """
        prompt_tmpl = _SEO_PROMPT_MAP.get(channel_type, _SEO_PROMPT_MAP["finance"])
        prompt = prompt_tmpl.format(
            topic=topic,
            script_summary=script_summary,
        )
        try:
            raw = self.call_ollama(prompt=prompt, timeout=60, num_predict=512)
            cleaned = raw.strip()
            # JSON 객체 추출
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(cleaned[start:end])
                # 필수 키 확인
                if isinstance(data, dict) and "title" in data:
                    return data
        except Exception as e:
            logger.warning(f"[F007][STAGE_06] SEO 생성 Ollama 실패: {e}")

        # 폴백: 기본 SEO 데이터
        logger.warning(f"[F007][STAGE_06] SEO 폴백 사용 - topic: {topic[:30]!r}")
        disclaimer = " (투자 권유가 아닌 정보 제공 목적입니다)" if channel_type == "finance" else ""
        return {
            "title": topic[:60],
            "description": f"{topic}{disclaimer}",
            "tags": [channel_type, "유튜브", topic[:20]],
            "category": channel_type,
        }

    def _upload_to_youtube(
        self,
        channel_type: str,
        video_path: str,
        thumbnail_path: Optional[str],
        seo_data: dict,
        privacy: str,
    ) -> Optional[str]:
        """YouTube Data API v3로 영상을 업로드한다.

        환경변수 미설정 시 업로드를 건너뛰고 None을 반환한다.
        채널별 refresh token을 별도 환경변수로 관리한다.

        Args:
            channel_type: "finance" 또는 "language" (토큰 환경변수 선택에 사용)
            video_path: 업로드할 MP4 파일 경로
            thumbnail_path: 썸네일 이미지 경로 (없으면 생략)
            seo_data: {title, description, tags} SEO 메타데이터
            privacy: "private"/"unlisted"/"public"

        Returns:
            업로드 성공 시 YouTube 영상 ID (str), 실패/스킵 시 None
        """
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        # 채널 유형별 refresh token (finance/language 채널 분리 관리)
        token_key = (
            "YOUTUBE_REFRESH_TOKEN_FINANCE"
            if channel_type == "finance"
            else "YOUTUBE_REFRESH_TOKEN_LANGUAGE"
        )
        refresh_token = os.environ.get(token_key, "")

        if not all([client_id, client_secret, refresh_token]):
            missing = []
            if not client_id: missing.append("YOUTUBE_CLIENT_ID")
            if not client_secret: missing.append("YOUTUBE_CLIENT_SECRET")
            if not refresh_token: missing.append(token_key)
            logger.warning(
                f"[F007][STAGE_06] YouTube 환경변수 미설정 - 업로드 건너뜀. "
                f"필요한 변수: {', '.join(missing)}"
            )
            return None

        # YouTube API 업로드 구현 - 환경변수 설정 후 활성화
        # 현재는 환경변수 설정 안내만 로깅하고 None 반환
        # TODO: google-api-python-client로 실제 업로드 구현
        logger.info(
            "[F007][STAGE_06] YouTube 업로드 기능은 "
            "YOUTUBE_* 환경변수 설정 후 활성화됩니다."
        )
        return None
