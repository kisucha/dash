# 목적: F006 STAGE_06 - SEO 최적화 메타데이터 생성 및 YouTube 업로드 스테이지.
# Ollama로 제목/설명/태그를 생성하고, upload_mode=auto이면 YouTube API로 업로드한다.
# YouTube API 실제 업로드는 Phase 5에서 완성 예정 (현재는 NotImplementedError).

import sys
import json
import re
import logging
import sqlite3

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# 스테이지 베이스 클래스 및 검증 결과 임포트
from pipelines.f006_youtube_v4.stages import BaseStage, ValidationResult

# BasePipeline 유틸(call_ollama) 사용을 위한 임포트
from pipelines.base import BasePipeline

# 로거 - 모듈명으로 계층적 로깅
logger = logging.getLogger(__name__)

# 동적 경로 계산 - 하드코딩 금지 (ERR 방지)
DB_PATH: str = str(Path(__file__).parent.parent.parent.parent / "storage" / "dash.db")


class Stage06Upload(BaseStage, BasePipeline):
    """STAGE_06 - SEO 최적화 + YouTube 업로드 스테이지.

    처리 흐름:
      1. Ollama로 SEO 제목/설명/태그/제목 변형 생성
      2. upload_mode == "auto": YouTube API로 업로드 (Phase 5 완성 예정)
      3. upload_mode == "manual_approval": PENDING_APPROVAL 상태로 대기
    """

    STAGE_ID: str = "STAGE_06_UPLOAD"
    STAGE_ORDER: int = 6

    def get_metadata(self) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return {"feature_id": "F006_STAGE06", "name": "STAGE_06_UPLOAD"}

    def run(self, task_id: int, params: dict) -> dict:
        """BasePipeline 추상 메서드 충족용."""
        return self.execute(task_id, params)

    def execute(self, job_id: int, input_data: dict) -> dict:
        """STAGE_06 실행 - SEO 생성 + 업로드 처리.

        Args:
            job_id: content_jobs.id
            input_data: {
                script_text (str): STAGE_02 전체 나레이션 텍스트 (SEO 훅 생성용)
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
        script_text: str = input_data.get("script_text", "")
        selected_topic: str = input_data.get("selected_topic", "")
        upload_mode: str = input_data.get("upload_mode", "manual_approval")
        video_file_path: Optional[str] = input_data.get("video_file_path")
        privacy: str = input_data.get("privacy", "private")

        logger.info(
            f"[F006][STAGE_06][job_id={job_id}] 실행 시작 - "
            f"주제: {selected_topic!r}, 업로드 모드: {upload_mode}"
        )

        # ----------------------------------------------------------------
        # SEO 메타데이터 생성 (Ollama)
        # ----------------------------------------------------------------
        # script_text 앞 200자를 훅으로 활용
        hook_preview: str = script_text[:200]
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

        logger.info(f"[F006][STAGE_06][job_id={job_id}] SEO 메타데이터 생성 Ollama 호출 시작")
        try:
            raw_seo: str = self.call_ollama(
                prompt=seo_prompt,
                timeout=120,
                num_predict=1024,
            )
        except Exception as e:
            logger.error(f"[F006][STAGE_06][job_id={job_id}] SEO Ollama 실패: {e}")
            raise RuntimeError(f"STAGE_06 SEO 생성 실패: {e}") from e

        seo_metadata: dict = self._parse_seo_json(raw_seo, selected_topic)
        logger.info(
            f"[F006][STAGE_06][job_id={job_id}] SEO 메타데이터 생성 완료 - "
            f"제목: {seo_metadata.get('title', '')!r}"
        )

        # ----------------------------------------------------------------
        # 업로드 처리 분기
        # ----------------------------------------------------------------
        upload_status: str = "PENDING_APPROVAL"
        youtube_video_id: Optional[str] = None

        if upload_mode == "auto" and video_file_path and Path(video_file_path).exists():
            logger.info(f"[F006][STAGE_06][job_id={job_id}] auto 모드 - YouTube 업로드 시도")

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
                    f"[F006][STAGE_06][job_id={job_id}] YouTube 업로드 완료 - "
                    f"video_id: {youtube_video_id}"
                )
            except Exception as e:
                logger.error(f"[F006][STAGE_06][job_id={job_id}] YouTube 업로드 실패: {e}")
                raise RuntimeError(f"YouTube 업로드 실패: {e}") from e
        else:
            logger.info(
                f"[F006][STAGE_06][job_id={job_id}] manual_approval 모드 - "
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
                logger.info(f"YouTube API 유닛 - 소모: {used}, 잔여: {remaining}")
                return remaining
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"YouTube 유닛 조회 실패 ({e}), 잔여 10000으로 간주")
            return 10000

    def _load_youtube_credentials(self) -> dict:
        """YouTube API 인증 정보 로드 - 환경변수 우선, 없으면 config.json.

        Returns:
            {"client_id": str, "client_secret": str, "refresh_token": str}

        Raises:
            RuntimeError: 인증 정보 미설정
        """
        import os

        config_path = Path(__file__).parent.parent / "config.json"
        cfg: dict = {}
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            logger.warning(f"config.json 읽기 실패: {e}")

        client_id = os.getenv("YOUTUBE_CLIENT_ID") or cfg.get("youtube_client_id", "")
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET") or cfg.get("youtube_client_secret", "")
        refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN") or cfg.get("youtube_refresh_token", "")

        missing = [k for k, v in [
            ("youtube_client_id", client_id),
            ("youtube_client_secret", client_secret),
            ("youtube_refresh_token", refresh_token),
        ] if not v]

        if missing:
            raise RuntimeError(
                f"YouTube API 인증 정보 미설정: {', '.join(missing)}. "
                f"config.json 또는 환경변수에 설정 후 재시도하세요."
            )
        return {"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token}

    def _get_access_token_sync(self, client_id: str, client_secret: str, refresh_token: str) -> str:
        """OAuth2 refresh_token으로 access_token 동기 갱신 (subprocess 환경용).

        Returns:
            access_token 문자열

        Raises:
            RuntimeError: 갱신 실패
        """
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        import httpx as _httpx
        resp = _httpx.post("https://oauth2.googleapis.com/token", data=payload, timeout=30.0)
        if resp.status_code != 200:
            raise RuntimeError(f"access_token 갱신 실패 (HTTP {resp.status_code}): {resp.text[:200]}")
        token = resp.json().get("access_token", "")
        if not token:
            raise RuntimeError(f"access_token 응답에 토큰 없음: {resp.text[:200]}")
        logger.info("YouTube access_token 갱신 완료")
        return token

    def _upload_to_youtube(
        self,
        video_file_path: str,
        input_data: dict,
        seo_metadata: dict,
        privacy: str,
    ) -> str:
        """YouTube Data API v3 resumable upload - httpx 동기 구현.

        Args:
            video_file_path: 업로드할 MP4 파일 경로
            input_data: 전체 입력 데이터
            seo_metadata: SEO 딕셔너리 {title, description, tags, category}
            privacy: "public" / "unlisted" / "private"

        Returns:
            업로드된 YouTube 영상 ID (str)

        Raises:
            RuntimeError: 인증 정보 미설정 / 업로드 실패
        """
        import httpx as _httpx

        # 인증 정보 로드
        creds = self._load_youtube_credentials()
        access_token = self._get_access_token_sync(
            creds["client_id"], creds["client_secret"], creds["refresh_token"]
        )

        video_file = Path(video_file_path)
        if not video_file.exists():
            raise RuntimeError(f"업로드할 영상 파일이 없습니다: {video_file_path}")

        file_size = video_file.stat().st_size
        title: str = seo_metadata.get("title", "유튜브 영상")[:100]
        description: str = seo_metadata.get("description", "")[:5000]
        tags: list = seo_metadata.get("tags", [])
        category: str = seo_metadata.get("category", "28")

        metadata = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": category,
            },
            "status": {"privacyStatus": privacy or "private"},
        }

        # -- 1단계: resumable upload 세션 초기화 --
        init_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        }
        params = {"uploadType": "resumable", "part": "snippet,status"}

        init_resp = _httpx.post(
            "https://www.googleapis.com/upload/youtube/v3/videos",
            params=params,
            headers=init_headers,
            json=metadata,
            timeout=60.0,
        )
        if init_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"YouTube 업로드 세션 초기화 실패 (HTTP {init_resp.status_code}): {init_resp.text[:300]}"
            )

        session_uri = init_resp.headers.get("Location", "")
        if not session_uri:
            raise RuntimeError("YouTube 업로드 세션 URI를 받지 못했습니다.")

        logger.info(f"YouTube resumable 세션 생성 - {file_size}바이트 업로드 시작")

        # -- 2단계: 파일 업로드 --
        upload_timeout = max(300.0, 300.0 + (file_size / (100 * 1024 * 1024)) * 120.0)
        upload_headers = {
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size),
        }
        with open(video_file_path, "rb") as f:
            video_bytes = f.read()

        upload_resp = _httpx.put(
            session_uri,
            headers=upload_headers,
            content=video_bytes,
            timeout=upload_timeout,
        )
        if upload_resp.status_code not in (200, 201):
            raise RuntimeError(
                f"YouTube 영상 업로드 실패 (HTTP {upload_resp.status_code}): {upload_resp.text[:300]}"
            )

        result = upload_resp.json()
        video_id = result.get("id", "")
        if not video_id:
            raise RuntimeError(f"YouTube 응답에 video ID 없음: {result}")

        logger.info(f"YouTube 업로드 완료 - video_id: {video_id}")
        return video_id

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
