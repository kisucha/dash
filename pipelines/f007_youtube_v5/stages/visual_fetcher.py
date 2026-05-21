import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# pipelines/f007_youtube_v5/stages/visual_fetcher.py
# 목적: 슬라이드 보조 이미지 fetch - Pixabay > Pexels > Unsplash > loremflickr > Pillow 그래디언트

import os
import hashlib
import logging
from pathlib import Path
from typing import Optional

import httpx

# .env 로드 - 오케스트레이터/스테이지는 독립 프로세스로 실행되므로 자체 dotenv 로드 필요
_env_path = Path(__file__).parent.parent.parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(_env_path, override=False)

# 이미지 API 키 전역 변수 (환경변수에서 로드)
_PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
_PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
_UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

logger = logging.getLogger(__name__)

# 허용된 이미지 MIME 타입 목록
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/gif",
}

# 이미지 다운로드 타임아웃(초)
_DOWNLOAD_TIMEOUT = 15.0


class VisualFetcher:
    """슬라이드 보조 이미지 fetch 클래스.

    폴백 체인: Pixabay -> Pexels -> Unsplash -> loremflickr -> Pillow 그래디언트
    각 단계에서 실패하면 다음 단계로 넘어가며, Pillow 그래디언트는 항상 성공한다.
    """

    def __init__(self, output_dir: str):
        # 이미지 저장 디렉토리 (없으면 자동 생성)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_for_slide(
        self,
        slide_no: int,
        keyword: str,
        size: tuple = (640, 360),
    ) -> Optional[str]:
        """슬라이드 번호별 보조 이미지를 폴백 체인 순서대로 시도해 반환한다.

        Args:
            slide_no: 슬라이드 번호 (파일명에 사용)
            keyword: 이미지 검색 키워드 (슬라이드 제목 또는 주제)
            size: 이미지 크기 (width, height) - 다운로드 URL 힌트용

        Returns:
            성공 시 저장된 이미지 절대 경로, 모든 폴백 실패 시 None (실제로는 항상 반환)
        """
        out_path = str(self.output_dir / f"visual_{slide_no:02d}.jpg")

        # 1단계: Pixabay
        if _PIXABAY_API_KEY:
            result = self._pixabay(keyword, out_path, size)
            if result:
                logger.info(f"[VisualFetcher] 슬라이드 {slide_no}: Pixabay 성공")
                return result
            logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: Pixabay 실패 -> Pexels 시도")
        else:
            logger.debug(f"[VisualFetcher] PIXABAY_API_KEY 없음 -> Pexels 시도")

        # 2단계: Pexels
        if _PEXELS_API_KEY:
            result = self._pexels(keyword, out_path, size)
            if result:
                logger.info(f"[VisualFetcher] 슬라이드 {slide_no}: Pexels 성공")
                return result
            logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: Pexels 실패 -> Unsplash 시도")
        else:
            logger.debug(f"[VisualFetcher] PEXELS_API_KEY 없음 -> Unsplash 시도")

        # 3단계: Unsplash
        if _UNSPLASH_ACCESS_KEY:
            result = self._unsplash(keyword, out_path, size)
            if result:
                logger.info(f"[VisualFetcher] 슬라이드 {slide_no}: Unsplash 성공")
                return result
            logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: Unsplash 실패 -> loremflickr 시도")
        else:
            logger.debug(f"[VisualFetcher] UNSPLASH_ACCESS_KEY 없음 -> loremflickr 시도")

        # 4단계: loremflickr (키 불필요, 폴백용 일반 이미지)
        result = self._loremflickr(keyword, out_path, size)
        if result:
            logger.info(f"[VisualFetcher] 슬라이드 {slide_no}: loremflickr 성공")
            return result
        logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: loremflickr 실패 -> Pillow 그래디언트 생성")

        # 5단계: Pillow 그래디언트 (항상 성공)
        grad_path = str(self.output_dir / f"visual_{slide_no:02d}.png")
        result = self._pillow_gradient(keyword, grad_path, size)
        if result:
            logger.info(f"[VisualFetcher] 슬라이드 {slide_no}: Pillow 그래디언트 생성 완료")
        return result

    def _pixabay(self, keyword: str, out_path: str, size: tuple) -> Optional[str]:
        """Pixabay API로 이미지 검색 후 다운로드.

        GET https://pixabay.com/api/?key={KEY}&q={keyword}&image_type=photo
            &orientation=horizontal&per_page=5&safesearch=true
        hits[0]["webformatURL"] 다운로드
        """
        params = {
            "key": _PIXABAY_API_KEY,
            "q": keyword,
            "image_type": "photo",
            "orientation": "horizontal",
            "per_page": 5,
            "safesearch": "true",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get("https://pixabay.com/api/", params=params)
                resp.raise_for_status()
                data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                logger.debug("[VisualFetcher][Pixabay] 검색 결과 없음")
                return None
            img_url = hits[0].get("webformatURL", "")
            if not img_url:
                return None
            return self._download(img_url, out_path)
        except Exception as e:
            logger.debug(f"[VisualFetcher][Pixabay] 오류: {e}")
            return None

    def _pexels(self, keyword: str, out_path: str, size: tuple) -> Optional[str]:
        """Pexels API로 이미지 검색 후 다운로드.

        GET https://api.pexels.com/v1/search?query={keyword}&per_page=5&orientation=landscape
        Authorization 헤더에 PEXELS_API_KEY
        photos[0]["src"]["medium"] 다운로드
        """
        params = {
            "query": keyword,
            "per_page": 5,
            "orientation": "landscape",
        }
        headers = {"Authorization": _PEXELS_API_KEY}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://api.pexels.com/v1/search",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            photos = data.get("photos", [])
            if not photos:
                logger.debug("[VisualFetcher][Pexels] 검색 결과 없음")
                return None
            img_url = photos[0].get("src", {}).get("medium", "")
            if not img_url:
                return None
            return self._download(img_url, out_path)
        except Exception as e:
            logger.debug(f"[VisualFetcher][Pexels] 오류: {e}")
            return None

    def _unsplash(self, keyword: str, out_path: str, size: tuple) -> Optional[str]:
        """Unsplash API로 이미지 검색 후 다운로드.

        GET https://api.unsplash.com/photos/random?query={keyword}&orientation=landscape
        Authorization: Client-ID {UNSPLASH_ACCESS_KEY}
        data["urls"]["regular"] 다운로드
        """
        params = {
            "query": keyword,
            "orientation": "landscape",
        }
        headers = {"Authorization": f"Client-ID {_UNSPLASH_ACCESS_KEY}"}
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://api.unsplash.com/photos/random",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
            img_url = data.get("urls", {}).get("regular", "")
            if not img_url:
                logger.debug("[VisualFetcher][Unsplash] URL 없음")
                return None
            return self._download(img_url, out_path)
        except Exception as e:
            logger.debug(f"[VisualFetcher][Unsplash] 오류: {e}")
            return None

    def _loremflickr(self, keyword: str, out_path: str, size: tuple) -> Optional[str]:
        """loremflickr에서 일반 자연 이미지 다운로드 (키워드 무관, 폴백용).

        GET https://loremflickr.com/{w}/{h}/nature
        """
        w, h = size
        url = f"https://loremflickr.com/{w}/{h}/nature"
        try:
            return self._download(url, out_path)
        except Exception as e:
            logger.debug(f"[VisualFetcher][loremflickr] 오류: {e}")
            return None

    def _pillow_gradient(self, keyword: str, out_path: str, size: tuple) -> Optional[str]:
        """keyword MD5 기반 색상으로 Pillow 수직 그래디언트 생성.

        API 키 없이도 항상 성공하는 최종 폴백.
        keyword의 MD5 해시를 이용해 결정론적으로 색상을 결정한다.
        """
        try:
            from PIL import Image, ImageDraw

            w, h = size

            # keyword MD5 해시로 색상 결정 (결정론적)
            md5_hex = hashlib.md5(keyword.encode("utf-8")).hexdigest()
            r1 = int(md5_hex[0:2], 16)
            g1 = int(md5_hex[2:4], 16)
            b1 = int(md5_hex[4:6], 16)
            r2 = int(md5_hex[6:8], 16)
            g2 = int(md5_hex[8:10], 16)
            b2 = int(md5_hex[10:12], 16)

            # 너무 어두운 색상 방지 (최소 밝기 보정)
            r1 = max(r1, 40)
            g1 = max(g1, 40)
            b1 = max(b1, 60)
            r2 = max(r2, 20)
            g2 = max(g2, 20)
            b2 = max(b2, 40)

            # 수직 그래디언트 생성
            img = Image.new("RGB", (w, h))
            draw = ImageDraw.Draw(img)
            for y in range(h):
                t = y / h  # 0.0 ~ 1.0
                r = int(r1 + (r2 - r1) * t)
                g = int(g1 + (g2 - g1) * t)
                b = int(b1 + (b2 - b1) * t)
                draw.line([(0, y), (w, y)], fill=(r, g, b))

            img.save(out_path, "PNG")
            return out_path

        except Exception as e:
            logger.error(f"[VisualFetcher][Pillow] 그래디언트 생성 실패: {e}")
            return None

    def _download(self, url: str, out_path: str) -> Optional[str]:
        """URL에서 이미지를 다운로드해 out_path에 저장한다.

        MIME 타입 확인 및 1KB 미만 크기 거부.

        Args:
            url: 다운로드할 이미지 URL
            out_path: 저장할 파일 경로

        Returns:
            성공 시 out_path, 실패 시 None
        """
        try:
            with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()

            # MIME 타입 확인
            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type not in _ALLOWED_CONTENT_TYPES:
                logger.debug(f"[VisualFetcher] 지원하지 않는 MIME 타입: {content_type} - {url[:60]}")
                return None

            # 최소 크기 확인 (1KB 미만 거부)
            content = resp.content
            if len(content) < 1024:
                logger.debug(
                    f"[VisualFetcher] 이미지 크기 너무 작음: {len(content)}bytes - {url[:60]}"
                )
                return None

            # 파일 저장
            with open(out_path, "wb") as f:
                f.write(content)

            return out_path

        except httpx.TimeoutException:
            logger.debug(f"[VisualFetcher] 다운로드 타임아웃: {url[:60]}")
        except httpx.HTTPStatusError as e:
            logger.debug(f"[VisualFetcher] HTTP 오류 {e.response.status_code}: {url[:60]}")
        except Exception as e:
            logger.debug(f"[VisualFetcher] 다운로드 실패: {e} - {url[:60]}")
        return None
