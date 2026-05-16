# 목적: YouTube Data API v3 업로드 유틸리티 — httpx 기반 비동기 구현.
# OAuth2 refresh_token으로 access_token을 갱신하고 resumable upload로 영상을 업로드한다.
# backend/routers/f004.py, f005.py approve 엔드포인트에서 호출한다.

import sys
import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

# 인코딩 안전 설정
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logger = logging.getLogger(__name__)

# YouTube OAuth2 토큰 엔드포인트
OAUTH2_TOKEN_URL = "https://oauth2.googleapis.com/token"
# YouTube 영상 업로드 엔드포인트 (resumable)
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# 각 파이프라인 config.json 경로 — 우선순위 순서
_CONFIG_PATHS = [
    Path(__file__).parent.parent.parent / "pipelines" / "f005_youtube_v3" / "config.json",
    Path(__file__).parent.parent.parent / "pipelines" / "f004_youtube_v2" / "config.json",
]


def load_youtube_credentials() -> dict:
    """YouTube API 인증 정보 로드.

    우선순위:
      1. 환경변수 YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN
      2. pipelines/f005_youtube_v3/config.json
      3. pipelines/f004_youtube_v2/config.json

    Returns:
        {"client_id": str, "client_secret": str, "refresh_token": str}

    Raises:
        RuntimeError: 인증 정보가 설정되지 않은 경우
    """
    client_id = os.getenv("YOUTUBE_CLIENT_ID", "")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "")

    if not (client_id and client_secret and refresh_token):
        # 환경변수 없으면 파이프라인 config.json 순서대로 탐색
        for config_path in _CONFIG_PATHS:
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                client_id = client_id or cfg.get("youtube_client_id", "")
                client_secret = client_secret or cfg.get("youtube_client_secret", "")
                refresh_token = refresh_token or cfg.get("youtube_refresh_token", "")
                if client_id and client_secret and refresh_token:
                    break
            except Exception as e:
                logger.warning(f"config.json 읽기 실패 ({config_path.name}): {e}")

    missing = []
    if not client_id:
        missing.append("youtube_client_id")
    if not client_secret:
        missing.append("youtube_client_secret")
    if not refresh_token:
        missing.append("youtube_refresh_token")

    if missing:
        raise RuntimeError(
            f"YouTube API 인증 정보 미설정: {', '.join(missing)}. "
            f"pipelines/f005_youtube_v3/config.json 또는 환경변수에 설정하세요."
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }


async def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """OAuth2 refresh_token으로 access_token을 갱신.

    Args:
        client_id: Google OAuth2 클라이언트 ID
        client_secret: Google OAuth2 클라이언트 시크릿
        refresh_token: 장기 유효 refresh token

    Returns:
        access_token 문자열

    Raises:
        RuntimeError: 토큰 갱신 실패
    """
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(OAUTH2_TOKEN_URL, data=payload)

    if resp.status_code != 200:
        raise RuntimeError(
            f"access_token 갱신 실패 (HTTP {resp.status_code}): {resp.text[:200]}"
        )

    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        raise RuntimeError(f"access_token 응답에 토큰 없음: {data}")

    logger.info("YouTube access_token 갱신 완료")
    return token


async def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    category: str,
    privacy: str,
    access_token: str,
    job_id: Optional[int] = None,
) -> str:
    """YouTube resumable upload API로 영상 업로드.

    Args:
        video_path: 업로드할 MP4 파일 절대 경로
        title: YouTube 영상 제목 (60자 이하 권장)
        description: 영상 설명
        tags: 태그 문자열 목록
        category: YouTube 카테고리 ID (기본 "28" = Science & Technology)
        privacy: "public" / "unlisted" / "private"
        access_token: OAuth2 access token
        job_id: 로그 식별용 (선택)

    Returns:
        업로드된 YouTube 영상 ID (str)

    Raises:
        RuntimeError: 파일 없음 / 업로드 실패
    """
    log_prefix = f"[YouTube][job_id={job_id}]" if job_id else "[YouTube]"

    video_file = Path(video_path)
    if not video_file.exists():
        raise RuntimeError(f"업로드할 영상 파일이 없습니다: {video_path}")

    file_size = video_file.stat().st_size
    logger.info(f"{log_prefix} 업로드 시작 — 파일: {video_file.name} ({file_size // 1024 // 1024}MB)")

    # YouTube API 요청 메타데이터
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500],
            "categoryId": category or "28",
        },
        "status": {
            "privacyStatus": privacy or "private",
        },
    }

    # ── 1단계: resumable upload 세션 초기화 ──
    init_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(file_size),
    }
    params = {"uploadType": "resumable", "part": "snippet,status"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        init_resp = await client.post(
            YOUTUBE_UPLOAD_URL,
            params=params,
            headers=init_headers,
            json=metadata,
        )

    if init_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"YouTube resumable upload 세션 초기화 실패 "
            f"(HTTP {init_resp.status_code}): {init_resp.text[:300]}"
        )

    session_uri = init_resp.headers.get("Location", "")
    if not session_uri:
        raise RuntimeError("YouTube 업로드 세션 URI를 받지 못했습니다.")

    logger.info(f"{log_prefix} 업로드 세션 생성 완료 — {file_size}바이트 전송 시작")

    # ── 2단계: 파일 스트리밍 업로드 ──
    # 타임아웃: 파일 크기에 비례 (최소 300초, 100MB당 +120초)
    upload_timeout = max(300.0, 300.0 + (file_size / (100 * 1024 * 1024)) * 120.0)

    upload_headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(file_size),
    }

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    async with httpx.AsyncClient(timeout=upload_timeout) as client:
        upload_resp = await client.put(
            session_uri,
            headers=upload_headers,
            content=video_bytes,
        )

    if upload_resp.status_code not in (200, 201):
        raise RuntimeError(
            f"YouTube 영상 업로드 실패 "
            f"(HTTP {upload_resp.status_code}): {upload_resp.text[:300]}"
        )

    result = upload_resp.json()
    video_id = result.get("id", "")
    if not video_id:
        raise RuntimeError(f"YouTube 응답에 video ID 없음: {result}")

    logger.info(f"{log_prefix} 업로드 완료 — video_id: {video_id}")
    return video_id
