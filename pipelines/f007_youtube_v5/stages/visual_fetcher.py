# pipelines/f007_youtube_v5/stages/visual_fetcher.py
# 목적: F007 비주얼 보조 이미지 다운로더 - SearXNG 이미지 검색 + 로컬 저장
# SlideRenderer의 우측 패널에 삽입할 관련 이미지를 수집한다.

import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import httpx
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 지원되는 이미지 MIME 타입 목록 - 이 외의 응답은 거부
_ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/gif",
}

# 이미지 다운로드 타임아웃(초)
_DOWNLOAD_TIMEOUT = 15.0


class VisualFetcher:
    """SearXNG 이미지 검색 결과에서 관련 이미지를 다운로드한다.

    BasePipeline.call_searxng_images()와 연동하여 슬라이드별 보조 이미지를 수집한다.
    다운로드 실패한 항목은 조용히 건너뛰고 성공한 것만 반환한다.
    """

    def __init__(self, output_dir: str):
        # 이미지 저장 디렉토리 (없으면 자동 생성)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_for_slide(
        self,
        slide_no: int,
        query: str,
        searxng_base_url: str = "http://192.168.20.80:8888",
        max_results: int = 5,
    ) -> Optional[str]:
        """슬라이드 번호별 보조 이미지를 SearXNG에서 검색 후 다운로드한다.

        Args:
            slide_no: 슬라이드 번호 (파일명에 사용)
            query: 이미지 검색 쿼리 (슬라이드 제목 또는 핵심 키워드)
            searxng_base_url: SearXNG 인스턴스 주소
            max_results: 검색 결과 최대 수 (다운로드는 최대 1개)

        Returns:
            성공 시 다운로드된 이미지 절대 경로, 실패 시 None
        """
        # SearXNG 이미지 검색
        image_results = self._search_images(query, searxng_base_url, max_results)
        if not image_results:
            logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: 이미지 검색 결과 없음")
            return None

        # 검색 결과 순서대로 다운로드 시도 (첫 번째 성공한 이미지 반환)
        for i, img_data in enumerate(image_results):
            img_url = img_data.get("img_src", "")
            if not img_url:
                continue
            out_path = str(self.output_dir / f"visual_{slide_no:02d}_{i}.jpg")
            result = self._download_image(img_url, out_path)
            if result:
                logger.info(
                    f"[VisualFetcher] 슬라이드 {slide_no} 이미지 다운로드 성공: {img_url[:80]}"
                )
                return result

        logger.debug(f"[VisualFetcher] 슬라이드 {slide_no}: 모든 이미지 다운로드 실패")
        return None

    def fetch_batch(
        self,
        slide_queries: list[dict],
        searxng_base_url: str = "http://192.168.20.80:8888",
    ) -> dict[int, Optional[str]]:
        """여러 슬라이드의 이미지를 일괄 다운로드한다.

        Args:
            slide_queries: [{"slide_no": int, "query": str}, ...] 목록
            searxng_base_url: SearXNG 인스턴스 주소

        Returns:
            {slide_no: image_path_or_None} 딕셔너리
        """
        results: dict[int, Optional[str]] = {}
        for item in slide_queries:
            slide_no: int = item.get("slide_no", 0)
            query: str = item.get("query", "")
            if not query:
                results[slide_no] = None
                continue
            results[slide_no] = self.fetch_for_slide(
                slide_no=slide_no,
                query=query,
                searxng_base_url=searxng_base_url,
            )
        return results

    def _search_images(
        self,
        query: str,
        searxng_base_url: str,
        max_results: int,
    ) -> list[dict]:
        """SearXNG 이미지 검색 - categories=images 파라미터 사용."""
        params = {
            "q": query,
            "format": "json",
            "categories": "images",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"{searxng_base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()

            results = []
            for r in data.get("results", []):
                img_src = r.get("img_src", "") or r.get("thumbnail", "")
                if img_src:
                    results.append({
                        "title": r.get("title", ""),
                        "img_src": img_src,
                        "url": r.get("url", ""),
                    })
                if len(results) >= max_results:
                    break
            return results

        except Exception as e:
            logger.warning(f"[VisualFetcher] SearXNG 이미지 검색 실패: {e}")
            return []

    def _download_image(self, url: str, output_path: str) -> Optional[str]:
        """URL에서 이미지를 다운로드해 output_path에 저장한다.

        허용된 MIME 타입이 아니거나 파일 크기가 너무 작으면 실패 처리.

        Args:
            url: 이미지 URL
            output_path: 저장할 파일 경로

        Returns:
            성공 시 output_path, 실패 시 None
        """
        try:
            with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()

            # MIME 타입 확인
            content_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if content_type not in _ALLOWED_CONTENT_TYPES:
                logger.debug(
                    f"[VisualFetcher] 지원하지 않는 MIME 타입: {content_type} - {url[:60]}"
                )
                return None

            # 최소 크기 확인 (1KB 미만은 의미 없는 이미지)
            content = resp.content
            if len(content) < 1024:
                logger.debug(
                    f"[VisualFetcher] 이미지 크기 너무 작음: {len(content)}bytes - {url[:60]}"
                )
                return None

            # 파일 저장
            with open(output_path, "wb") as f:
                f.write(content)

            return output_path

        except httpx.TimeoutException:
            logger.debug(f"[VisualFetcher] 이미지 다운로드 타임아웃: {url[:60]}")
        except httpx.HTTPStatusError as e:
            logger.debug(f"[VisualFetcher] HTTP 오류 {e.response.status_code}: {url[:60]}")
        except Exception as e:
            logger.debug(f"[VisualFetcher] 이미지 다운로드 실패: {e} - {url[:60]}")
        return None
