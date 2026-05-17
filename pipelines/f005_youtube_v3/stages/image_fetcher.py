# 목적: F005 STAGE_04 보조 모듈 — 채널 카테고리별 배경 이미지 다운로드 및 Pillow 폴백 생성.
# 네트워크 가능 시 loremflickr.com에서 카테고리 관련 실사 이미지 다운로드.
# 네트워크 불가 시 Pillow로 카테고리별 추상 그래디언트 배경 생성.

import sys

# 인코딩 안전 설정 — Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# -- loremflickr 기본 URL --
# loremflickr.com/{w}x{h}/{category} — 무료, API 키 불필요, 카테고리별 실사 이미지
_FLICKER_BASE = "https://loremflickr.com"

# -- 채널 카테고리 → 카테고리 그룹 매핑 --
# 부분 문자열 일치로 그룹을 결정한다 (우선순위: 앞에서부터)
_CATEGORY_GROUP_MAP: list[tuple[str, str]] = [
    # 금융/경제 (차트 생성기가 별도 처리 — 여기선 ticker 없는 경우만 도달)
    ("경제", "finance"),
    ("재테크", "finance"),
    ("투자", "finance"),
    ("금융", "finance"),
    # IT/기술
    ("IT", "technology"),
    ("기술", "technology"),
    ("과학", "technology"),
    ("프로그래밍", "technology"),
    ("AI", "technology"),
    ("인공지능", "technology"),
    ("소프트웨어", "technology"),
    # 건강/의학
    ("건강", "health"),
    ("운동", "fitness"),
    ("의학", "medical"),
    ("헬스", "fitness"),
    ("다이어트", "fitness"),
    ("병원", "medical"),
    # 음식/요리
    ("요리", "food"),
    ("음식", "food"),
    ("맛집", "restaurant"),
    ("식품", "food"),
    ("베이킹", "baking"),
    # 라이프스타일
    ("뷰티", "beauty"),
    ("패션", "fashion"),
    ("여행", "travel"),
    ("라이프", "lifestyle"),
    # 교육
    ("교육", "education"),
    ("학습", "study"),
    ("어학", "language"),
    ("책", "books"),
    # 부동산
    ("부동산", "architecture"),
    ("인테리어", "interior"),
    # 게임/엔터
    ("게임", "gaming"),
    ("엔터", "entertainment"),
    # 스포츠
    ("스포츠", "sports"),
    ("축구", "soccer"),
    ("야구", "baseball"),
    ("농구", "basketball"),
    # 뉴스/사회
    ("뉴스", "news"),
    ("정치", "politics"),
    ("사회", "society"),
]

# -- 그룹별 Pillow 폴백 색상 팔레트 --
# (배경색, 강조색1, 강조색2) — 카테고리 분위기에 맞춤
_GROUP_PALETTE: dict[str, tuple] = {
    "finance":    ((10, 20, 40),    (0,  120, 255),  (0,   80, 200)),
    "technology": ((5,  15, 30),    (0,  200, 180),  (0,  150, 255)),
    "health":     ((10, 30, 15),    (0,  200, 100),  (50, 230, 100)),
    "fitness":    ((20, 10, 30),    (200, 50, 255),  (150, 50, 200)),
    "medical":    ((10, 20, 40),    (100,180, 255),  (50, 120, 200)),
    "food":       ((40, 15,  5),    (230,120,  20),  (200, 80,   0)),
    "restaurant": ((30, 10,  5),    (200, 80,  20),  (180, 60,  10)),
    "baking":     ((40, 25, 10),    (220,160,  50),  (180,120,  30)),
    "beauty":     ((30, 10, 25),    (220, 80, 180),  (180, 60, 140)),
    "fashion":    ((25, 10, 30),    (200,100, 220),  (160, 60, 180)),
    "travel":     ((5,  20, 35),    (0,  160, 200),  (0,  100, 160)),
    "lifestyle":  ((20, 15, 30),    (180,100, 220),  (140, 70, 180)),
    "education":  ((25, 20, 10),    (200,160,  50),  (160,120,  30)),
    "study":      ((20, 18, 10),    (180,150,  60),  (140,110,  40)),
    "language":   ((10, 20, 30),    (100,160, 220),  (60, 120, 180)),
    "books":      ((30, 22, 12),    (180,140,  60),  (140,100,  40)),
    "architecture":((10, 15, 20),   (150,180, 200),  (100,130, 160)),
    "interior":   ((25, 20, 15),    (200,180, 140),  (160,140, 100)),
    "gaming":     ((10,  5, 25),    (100, 50, 255),  (60,  20, 200)),
    "entertainment":((15,5, 20),    (220, 60, 180),  (160, 40, 140)),
    "sports":     ((5,  20, 10),    (50, 220,  80),  (20, 160,  60)),
    "soccer":     ((5,  20, 10),    (30, 200, 100),  (20, 160,  80)),
    "baseball":   ((5,  10, 25),    (50, 100, 220),  (30,  60, 180)),
    "basketball": ((30, 15,  5),    (220, 90,  20),  (180, 60,  10)),
    "news":       ((15, 15, 20),    (150,160, 200),  (100,110, 160)),
    "politics":   ((20, 10, 10),    (200, 80,  80),  (160, 50,  50)),
    "society":    ((15, 15, 15),    (160,160, 200),  (100,100, 160)),
    "default":    ((15, 20, 30),    (80, 120, 200),  (50,  80, 160)),
}


def detect_category_group(channel_category: str) -> str:
    """channel_category 문자열로 loremflickr 검색 그룹을 결정한다.

    _CATEGORY_GROUP_MAP 순서대로 부분 문자열 일치 검사.
    일치 없으면 'default' 반환.
    """
    cat = channel_category.strip()
    for keyword, group in _CATEGORY_GROUP_MAP:
        if keyword in cat:
            return group
    return "default"


def _download_image(url: str, output_path: str, timeout: int = 8) -> bool:
    """URL에서 이미지를 다운로드해 output_path에 저장한다.

    Returns:
        True: 성공 (파일 저장됨), False: 실패
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Dash-F005/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()

        if len(data) < 2000:
            logger.warning(f"[ImageFetcher] 응답 크기 이상 ({len(data)} bytes) — 이미지 아님")
            return False

        Path(output_path).write_bytes(data)
        return True

    except urllib.error.URLError as e:
        logger.warning(f"[ImageFetcher] 네트워크 오류: {e}")
        return False
    except Exception as e:
        logger.warning(f"[ImageFetcher] 다운로드 실패: {e}")
        return False


def _generate_pillow_background(
    group: str,
    output_path: str,
    size: tuple[int, int] = (492, 540),
) -> bool:
    """Pillow로 카테고리별 추상 그래디언트 배경 이미지를 생성한다.

    네트워크 불가 시 폴백으로 사용. 카테고리별 고유 색상 팔레트 적용.
    """
    try:
        from PIL import Image, ImageDraw
        import math
        import random

        rng = random.Random(hash(group) & 0xFFFF)

        palette = _GROUP_PALETTE.get(group, _GROUP_PALETTE["default"])
        bg_col, acc1, acc2 = palette

        w, h = size
        img = Image.new("RGB", (w, h), bg_col)
        draw = ImageDraw.Draw(img)

        # 그래디언트 배경 — 좌상단에서 우하단으로 accent 색상 페이드
        for y in range(h):
            t = y / h
            r = int(bg_col[0] * (1 - t * 0.4) + acc2[0] * t * 0.4)
            g = int(bg_col[1] * (1 - t * 0.4) + acc2[1] * t * 0.4)
            b = int(bg_col[2] * (1 - t * 0.4) + acc2[2] * t * 0.4)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # 장식 원 — 카테고리별 시드로 재현 가능한 패턴
        for _ in range(6):
            cx = rng.randint(0, w)
            cy = rng.randint(0, h)
            r = rng.randint(40, 120)
            alpha_color = tuple(
                min(255, c + 30) for c in acc1
            )
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline=alpha_color,
                width=2,
            )

        # 대각선 장식 라인
        for i in range(3):
            x_off = rng.randint(-50, w // 2)
            draw.line(
                [(x_off, 0), (x_off + w // 3, h)],
                fill=acc1,
                width=1,
            )

        img.save(output_path, "PNG")
        logger.info(f"[ImageFetcher] Pillow 배경 생성 완료: {Path(output_path).name} ({group})")
        return True

    except ImportError:
        logger.warning("[ImageFetcher] Pillow 미설치 — 배경 생성 불가")
        return False
    except Exception as e:
        logger.warning(f"[ImageFetcher] Pillow 배경 생성 실패: {e}")
        return False


def fetch_slide_image(
    channel_category: str,
    slide_index: int,
    output_path: str,
    size: tuple[int, int] = (492, 540),
    timeout: int = 8,
) -> bool:
    """채널 카테고리 기반 배경 이미지를 가져와 output_path에 저장한다.

    1차: loremflickr.com 실사 이미지 다운로드 시도
    2차: 네트워크 실패 시 Pillow 추상 배경 생성 (항상 동작)

    Args:
        channel_category: 채널 카테고리 (예: "IT/기술")
        slide_index: 슬라이드 번호 — 슬라이드마다 다른 이미지 확보용
        output_path: 저장할 PNG 파일 경로
        size: 이미지 크기 (width, height)
        timeout: HTTP 요청 타임아웃(초)

    Returns:
        True: 이미지 저장 성공, False: 완전 실패 (텍스트 레이아웃 폴백 필요)
    """
    group = detect_category_group(channel_category)
    w, h = size

    # 1차 시도: loremflickr 실사 이미지
    # ?lock={slide_index}로 슬라이드마다 다른 이미지 요청
    url = f"{_FLICKER_BASE}/{w}/{h}/{group}?lock={slide_index}"
    logger.info(f"[ImageFetcher] 이미지 요청: group={group} idx={slide_index}")

    if _download_image(url, output_path, timeout=timeout):
        return True

    logger.info(f"[ImageFetcher] loremflickr 실패 — Pillow 폴백 실행")

    # 2차 시도: Pillow 추상 배경
    return _generate_pillow_background(group, output_path, size=size)
