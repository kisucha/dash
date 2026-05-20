# 목적: F006 STAGE_04 보조 모듈 - 슬라이드 텍스트 기반 기술 지표 감지 및 yfinance+matplotlib 차트 이미지 생성.

import sys

# 인코딩 안전 설정 - Windows 환경에서 한글/특수문자 출력 오류 방지
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# -- 지표 키워드 매핑 - 슬라이드 텍스트에서 기술 지표를 감지하기 위한 딕셔너리 --
INDICATOR_KEYWORDS: dict[str, list[str]] = {
    "rsi":        ["RSI", "상대강도", "과매수", "과매도"],
    "macd":       ["MACD", "macd", "시그널"],
    "bollinger":  ["볼린저", "Bollinger", "볼린저밴드", "밴드 폭", "표준편차"],
    "stochastic": ["스토캐스틱", "Stochastic", "StochRSI"],
    "ma":         ["이동평균", "MA5", "MA10", "MA20", "MA50", "MA100", "MA200",
                   "SMA", "EMA", "골든크로스", "데드크로스"],
    "volume":     ["거래량", "Volume", "거래대금"],
    "adx":        ["ADX", "DMI"],
}

# 지표 우선순위 - 차트 공간 한계로 최대 2개 반환 시 순서 기준
INDICATOR_PRIORITY: list[str] = [
    "bollinger", "macd", "rsi", "stochastic", "adx", "ma", "volume"
]

# -- 종목명-티커 매핑 - TICKER_MAP['종목명'] -> yfinance 티커 문자열 --
TICKER_MAP: dict[str, str] = {
    # 한국 주요 종목
    "삼성전자": "005930.KS",
    "삼성": "005930.KS",
    "SK하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "NAVER": "035420.KS",
    "네이버": "035420.KS",
    "카카오": "035720.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "삼성바이오로직스": "207940.KS",
    "셀트리온": "068270.KS",
    "기아": "000270.KS",
    "포스코": "005490.KS",
    "포스코홀딩스": "005490.KS",
    # 글로벌 주요 종목
    "애플": "AAPL",
    "APPLE": "AAPL",
    "엔비디아": "NVDA",
    "NVIDIA": "NVDA",
    "테슬라": "TSLA",
    "TESLA": "TSLA",
    "마이크로소프트": "MSFT",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "아마존": "AMZN",
    "메타": "META",
    # 암호화폐
    "비트코인": "BTC-USD",
    "Bitcoin": "BTC-USD",
    "이더리움": "ETH-USD",
}


def _has_korean(text: str) -> bool:
    """문자열에 한글 음절이 포함되면 True를 반환한다."""
    return any('가' <= c <= '힣' for c in text)


# 영문 대문자 2-5자 패턴이 주식 티커로 오탐되는 일반 금융/기술 용어 제외 목록
_TICKER_EXCLUSIONS: frozenset = frozenset({
    "RSI", "MACD", "EMA", "SMA", "MA", "ADX", "DMI", "ATR", "BB", "IV",
    "PE", "PER", "ROE", "ROA", "EPS", "PBR", "GDP", "CPI", "PPI", "CCI",
    "AI", "IT", "US", "USD", "KR", "JP", "EU", "ETF", "IPO", "QE",
    "FED", "SEC", "YTD", "YOY", "DCA", "DXY", "VIX", "OBV", "EV",
})

# 역방향 맵: ticker -> 대표 표시명 (동일 ticker 복수 키 중 가장 긴 이름 선택)
_REVERSE_TICKER: dict[str, str] = {}
for _n, _t in TICKER_MAP.items():
    if _t not in _REVERSE_TICKER or len(_n) > len(_REVERSE_TICKER[_t]):
        _REVERSE_TICKER[_t] = _n


def format_ticker_display(ticker: str) -> str:
    """ticker 문자열을 '종목명(코드)' 형식으로 반환한다.

    예: '005930.KS' -> '삼성전자(005930)', 'AAPL' -> 'AAPL', '' -> ''
    """
    if not ticker:
        return ""
    name = _REVERSE_TICKER.get(ticker, "")
    code = ticker.split(".")[0].split("-")[0]
    return f"{name}({code})" if name else ticker


def detect_indicators(text: str) -> list[str]:
    """슬라이드 텍스트에서 기술 지표 키워드를 감지해 우선순위 순으로 반환한다.

    Args:
        text: 슬라이드 title + bullets를 합친 문자열

    Returns:
        감지된 지표 키 리스트 (최대 2개, 우선순위 정렬)
        예: ["bollinger", "rsi"]
    """
    matched: set[str] = set()
    for indicator_key, keywords in INDICATOR_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                matched.add(indicator_key)
                break

    # 우선순위 순으로 정렬 후 최대 2개만 반환
    result = [ind for ind in INDICATOR_PRIORITY if ind in matched]
    return result[:2]


def extract_ticker(topic: str, user_context: str = "") -> Optional[str]:
    """topic 및 user_context에서 종목명 또는 티커를 추출한다.

    탐색 순서:
    1. TICKER_MAP 키에서 직접 검색 (대소문자 무시)
    2. 한국 종목코드 6자리 숫자 패턴 -> {code}.KS
    3. 영문 대문자 2-5자 티커 패턴 (AAPL, NVDA 등)
    4. 일치 없으면 None

    Args:
        topic: 콘텐츠 주제 문자열
        user_context: 추가 컨텍스트 문자열 (없으면 빈 문자열)

    Returns:
        yfinance 티커 문자열 또는 None
    """
    search_text = topic + " " + user_context

    # 1. TICKER_MAP 직접 매칭 — 한글 키를 영문 키보다 우선 체크 (오탐 방지)
    # 예: '삼성전자'(한글, len=4)가 'NAVER'(영문, len=5)보다 먼저 검색됨
    sorted_keys = sorted(
        TICKER_MAP.keys(),
        key=lambda k: (0 if _has_korean(k) else 1, -len(k))
    )
    for key in sorted_keys:
        if key.lower() in search_text.lower():
            return TICKER_MAP[key]

    # 2. 한국 종목코드 6자리 숫자 패턴
    kr_match = re.search(r'\b(\d{6})\b', search_text)
    if kr_match:
        return f"{kr_match.group(1)}.KS"

    # 3. 영문 대문자 2-5자 티커 패턴 (AAPL, MSFT 등) — 일반 금융/기술 용어 제외
    en_match = re.search(r'\b([A-Z]{2,5})\b', search_text)
    if en_match and en_match.group(1) not in _TICKER_EXCLUSIONS:
        return en_match.group(1)

    return None


def _rgb_to_hex(rgb: tuple) -> str:
    """RGB 튜플을 matplotlib 호환 hex 문자열로 변환한다."""
    r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    return f"#{r:02x}{g:02x}{b:02x}"


class ChartGenerator:
    """yfinance 데이터 수집 + matplotlib 기반 기술 지표 차트 생성기.

    SlideRenderer에서 차트 이미지 경로를 요청하면 이 클래스가 PNG를 생성한다.
    테마 색상을 주입받아 슬라이드와 색상 일관성을 유지한다.
    """

    # 기본 다크 블루 테마 색상
    _DEFAULT_THEME: dict = {
        "bg": (15, 25, 50),
        "accent": (0, 122, 255),
        "accent_light": (100, 180, 255),
        "text_primary": (255, 255, 255),
        "text_secondary": (180, 200, 220),
    }

    def __init__(self, theme_colors: dict = None):
        """
        Args:
            theme_colors: 슬라이드 테마 딕셔너리 (bg, accent, text_primary 등)
                          None이면 dark_blue 기본값 사용
        """
        self.theme = theme_colors if theme_colors else self._DEFAULT_THEME

    def generate(
        self,
        ticker: str,
        indicators: list[str],
        output_path: str,
        period: str = "6mo",
        chart_size: tuple = (520, 540),
    ) -> bool:
        """yfinance 데이터 수집 후 indicators 기반 차트를 PNG로 저장한다.

        Args:
            ticker: yfinance 티커 문자열 (예: "005930.KS", "AAPL")
            indicators: 감지된 기술 지표 리스트 (detect_indicators 출력)
            output_path: 저장할 PNG 파일 경로 (절대 경로)
            period: yfinance 데이터 조회 기간 (기본 3개월)
            chart_size: 출력 이미지 픽셀 크기 (width, height)

        Returns:
            True: 차트 생성 및 저장 성공
            False: 임포트 실패, 데이터 없음, 렌더링 예외 등 실패
        """
        # yfinance 임포트 - 미설치 시 False 반환
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("[ChartGenerator] yfinance 미설치 - 차트 생성 건너뜀")
            return False

        # matplotlib 임포트 - 미설치 시 False 반환
        try:
            import matplotlib
            matplotlib.use("Agg")  # GUI 없는 환경에서 PNG 저장
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
        except ImportError:
            logger.warning("[ChartGenerator] matplotlib 미설치 - 차트 생성 건너뜀")
            return False

        # 한글 폰트 설정 - Windows 맑은 고딕 우선
        try:
            from matplotlib import font_manager
            _KR_FONTS = ["Malgun Gothic", "NanumGothic", "AppleGothic"]
            for _f in _KR_FONTS:
                if any(_f.lower() in fm.name.lower() for fm in font_manager.fontManager.ttflist):
                    matplotlib.rcParams["font.family"] = _f
                    break
        except Exception:
            pass  # 폰트 설정 실패 시 경고 무시하고 계속

        # 데이터 수집
        try:
            df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        except Exception as e:
            logger.warning(f"[ChartGenerator] yfinance 데이터 수집 실패 ({ticker}): {e}")
            return False

        if df is None or df.empty:
            logger.warning(f"[ChartGenerator] 데이터 없음 - ticker={ticker}, period={period}")
            return False

        # 컬럼명 소문자 정규화 - yfinance 1.x는 단일 티커도 MultiIndex 반환 가능
        # MultiIndex: ('Close', 'AAPL') -> 첫 번째 요소(메트릭명)만 추출
        if hasattr(df.columns, "levels"):
            df.columns = [
                c[0].lower() if isinstance(c, tuple) else c.lower()
                for c in df.columns
            ]
        else:
            df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]

        # close 컬럼 확인
        if "close" not in df.columns:
            logger.warning(f"[ChartGenerator] close 컬럼 없음 - 컬럼: {list(df.columns)}")
            return False

        # 테마 색상 hex 변환
        bg_hex = _rgb_to_hex(self.theme.get("bg", (15, 25, 50)))
        text_hex = _rgb_to_hex(self.theme.get("text_primary", (255, 255, 255)))
        accent_hex = _rgb_to_hex(self.theme.get("accent", (0, 122, 255)))
        accent_light_hex = _rgb_to_hex(self.theme.get("accent_light", (100, 180, 255)))
        secondary_hex = _rgb_to_hex(self.theme.get("text_secondary", (180, 200, 220)))

        # matplotlib 전역 스타일 설정
        plt.rcParams.update({
            "figure.facecolor": bg_hex,
            "axes.facecolor": bg_hex,
            "axes.edgecolor": secondary_hex,
            "axes.labelcolor": text_hex,
            "xtick.color": secondary_hex,
            "ytick.color": secondary_hex,
            "text.color": text_hex,
            "grid.color": secondary_hex,
            "grid.alpha": 0.3,
        })

        # figsize - dpi=100 기준 픽셀 -> 인치 변환
        dpi = 100
        fig_w = chart_size[0] / dpi
        fig_h = chart_size[1] / dpi

        primary = indicators[0] if indicators else "default"

        try:
            fig = self._render_chart(
                df=df,
                primary=primary,
                fig_w=fig_w,
                fig_h=fig_h,
                dpi=dpi,
                ticker=ticker,
                accent_hex=accent_hex,
                accent_light_hex=accent_light_hex,
                text_hex=text_hex,
                secondary_hex=secondary_hex,
                bg_hex=bg_hex,
            )
            fig.savefig(output_path, dpi=dpi, bbox_inches="tight", facecolor=bg_hex)
            plt.close(fig)
            logger.info(f"[ChartGenerator] 차트 저장 완료 - {output_path}")
            return True

        except Exception as e:
            logger.warning(f"[ChartGenerator] 차트 렌더링 실패 ({ticker}, {primary}): {e}")
            try:
                plt.close("all")
            except Exception:
                pass
            return False

    def _render_chart(
        self,
        df,
        primary: str,
        fig_w: float,
        fig_h: float,
        dpi: int,
        ticker: str,
        accent_hex: str,
        accent_light_hex: str,
        text_hex: str,
        secondary_hex: str,
        bg_hex: str,
    ):
        """primary 지표에 맞는 matplotlib Figure를 생성해 반환한다."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        close = df["close"]

        if primary == "bollinger":
            return self._chart_bollinger(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "rsi":
            return self._chart_rsi(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "macd":
            return self._chart_macd(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "stochastic":
            return self._chart_stochastic(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "ma":
            return self._chart_ma(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "adx":
            return self._chart_adx(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        elif primary == "volume":
            return self._chart_volume(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )
        else:
            return self._chart_default(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )

    # ------------------------------------------------------------------ #
    #  지표별 차트 렌더링 메서드                                           #
    # ------------------------------------------------------------------ #

    def _chart_bollinger(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """볼린저 밴드 - 단일 axes, 종가+상단/하단 점선+중심선+fill."""
        import matplotlib.pyplot as plt

        ma20 = close.rolling(window=20).mean()
        std20 = close.rolling(window=20).std()
        upper = ma20 + 2 * std20
        lower = ma20 - 2 * std20

        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.plot(close.index, close, color=text_hex, linewidth=1.2, label="종가")
        ax.plot(close.index, upper, color=accent_hex, linewidth=1.0, linestyle="--", label="상단")
        ax.plot(close.index, lower, color=accent_hex, linewidth=1.0, linestyle="--", label="하단")
        ax.plot(close.index, ma20, color="white", linewidth=1.0, linestyle="-", label="MA20")
        ax.fill_between(close.index, upper, lower, alpha=0.1, color=accent_hex)
        ax.set_title(f"{ticker} Bollinger Band", color=text_hex, fontsize=9, pad=4)
        ax.legend(fontsize=7, loc="upper left", facecolor=bg_hex, edgecolor=secondary_hex,
                  labelcolor=text_hex)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", labelsize=7, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_rsi(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """RSI - 상단 75% 종가 / 하단 25% RSI(14일), 70/30 수평선."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        gs = gridspec.GridSpec(4, 1, hspace=0.05)
        ax1 = fig.add_subplot(gs[:3, 0])   # 상단 75%
        ax2 = fig.add_subplot(gs[3, 0], sharex=ax1)  # 하단 25%

        ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
        ax1.set_title(f"{ticker} RSI(14)", color=text_hex, fontsize=9, pad=4)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelbottom=False, labelsize=7)

        ax2.plot(rsi.index, rsi, color=accent_hex, linewidth=1.0)
        ax2.axhline(70, color="red", linestyle="--", linewidth=0.8, alpha=0.8)
        ax2.axhline(30, color="green", linestyle="--", linewidth=0.8, alpha=0.8)
        ax2.fill_between(rsi.index, rsi, 70, where=(rsi >= 70), alpha=0.2, color="red")
        ax2.fill_between(rsi.index, rsi, 30, where=(rsi <= 30), alpha=0.2, color="green")
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("RSI", color=secondary_hex, fontsize=7)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", labelsize=7, rotation=30)
        ax2.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_macd(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """MACD - 상단 60% 종가 / 하단 40% MACD+시그널+히스토그램."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        gs = gridspec.GridSpec(5, 1, hspace=0.05)
        ax1 = fig.add_subplot(gs[:3, 0])   # 상단 60%
        ax2 = fig.add_subplot(gs[3:, 0], sharex=ax1)  # 하단 40%

        ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
        ax1.set_title(f"{ticker} MACD(12,26,9)", color=text_hex, fontsize=9, pad=4)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelbottom=False, labelsize=7)

        # 히스토그램 - 양수=파랑, 음수=빨강
        colors = [accent_hex if v >= 0 else "red" for v in histogram]
        ax2.bar(histogram.index, histogram, color=colors, width=1.0, alpha=0.7)
        ax2.plot(macd_line.index, macd_line, color=accent_hex, linewidth=1.0, label="MACD")
        ax2.plot(signal_line.index, signal_line, color="orange", linewidth=0.8, label="Signal")
        ax2.axhline(0, color=secondary_hex, linewidth=0.5, linestyle="--")
        ax2.legend(fontsize=6, loc="upper left", facecolor=bg_hex, edgecolor=secondary_hex,
                   labelcolor=text_hex)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", labelsize=7, rotation=30)
        ax2.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_stochastic(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """스토캐스틱 - 상단 70% 종가 / 하단 30% %K/%D, 80/20 수평선."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        low14 = df.get("low", close).rolling(14).min()
        high14 = df.get("high", close).rolling(14).max()
        k_pct = 100 * (close - low14) / (high14 - low14 + 1e-10)
        d_pct = k_pct.rolling(3).mean()

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        gs = gridspec.GridSpec(10, 1, hspace=0.05)
        ax1 = fig.add_subplot(gs[:7, 0])
        ax2 = fig.add_subplot(gs[7:, 0], sharex=ax1)

        ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
        ax1.set_title(f"{ticker} Stochastic(14,3)", color=text_hex, fontsize=9, pad=4)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelbottom=False, labelsize=7)

        ax2.plot(k_pct.index, k_pct, color=accent_hex, linewidth=1.0, label="%K")
        ax2.plot(d_pct.index, d_pct, color="orange", linewidth=0.8, label="%D")
        ax2.axhline(80, color="red", linestyle="--", linewidth=0.8, alpha=0.8)
        ax2.axhline(20, color="green", linestyle="--", linewidth=0.8, alpha=0.8)
        ax2.set_ylim(0, 100)
        ax2.legend(fontsize=6, loc="upper left", facecolor=bg_hex, edgecolor=secondary_hex,
                   labelcolor=text_hex)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", labelsize=7, rotation=30)
        ax2.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_ma(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """이동평균 - 단일 axes, 종가+MA20(노랑)+MA60(주황)+MA120(빨강)."""
        import matplotlib.pyplot as plt

        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        ma120 = close.rolling(120).mean()

        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        ax.plot(close.index, close, color=text_hex, linewidth=1.2, label="종가")
        ax.plot(close.index, ma5, color="#00e5ff", linewidth=0.9, label="MA5")
        ax.plot(close.index, ma20, color="yellow", linewidth=0.9, label="MA20")
        ax.plot(close.index, ma60, color="orange", linewidth=0.9, label="MA60")
        ax.plot(close.index, ma120, color="red", linewidth=0.9, label="MA120")
        ax.set_title(f"{ticker} Moving Average", color=text_hex, fontsize=9, pad=4)
        ax.legend(fontsize=7, loc="upper left", facecolor=bg_hex, edgecolor=secondary_hex,
                  labelcolor=text_hex)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", labelsize=7, rotation=30)
        ax.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_adx(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """ADX/DMI - 상단 60% 종가 / 하단 40% ADX+DI+/-."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        # ADX 계산 (14일)
        high = df.get("high", close)
        low = df.get("low", close)
        prev_close = close.shift(1)

        tr = (
            (high - low).abs()
            .combine((high - prev_close).abs(), max)
            .combine((low - prev_close).abs(), max)
        )
        plus_dm = (high - high.shift(1)).clip(lower=0)
        minus_dm = (low.shift(1) - low).clip(lower=0)

        atr14 = tr.rolling(14).mean()
        plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, 1e-10)
        minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, 1e-10)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(14).mean()

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        gs = gridspec.GridSpec(5, 1, hspace=0.05)
        ax1 = fig.add_subplot(gs[:3, 0])
        ax2 = fig.add_subplot(gs[3:, 0], sharex=ax1)

        ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
        ax1.set_title(f"{ticker} ADX/DMI(14)", color=text_hex, fontsize=9, pad=4)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelbottom=False, labelsize=7)

        ax2.plot(adx.index, adx, color="white", linewidth=1.0, label="ADX")
        ax2.plot(plus_di.index, plus_di, color="green", linewidth=0.8, label="+DI")
        ax2.plot(minus_di.index, minus_di, color="red", linewidth=0.8, label="-DI")
        ax2.axhline(25, color=secondary_hex, linestyle="--", linewidth=0.8, alpha=0.7)
        ax2.legend(fontsize=6, loc="upper left", facecolor=bg_hex, edgecolor=secondary_hex,
                   labelcolor=text_hex)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", labelsize=7, rotation=30)
        ax2.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_volume(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """거래량 - 상단 70% 종가 / 하단 30% 거래량 바 (상승=파랑, 하락=빨강)."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        volume = df.get("volume", None)
        if volume is None or volume.empty:
            return self._chart_default(
                df, close, fig_w, fig_h, dpi, ticker,
                accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
            )

        fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
        gs = gridspec.GridSpec(10, 1, hspace=0.05)
        ax1 = fig.add_subplot(gs[:7, 0])
        ax2 = fig.add_subplot(gs[7:, 0], sharex=ax1)

        ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
        ax1.set_title(f"{ticker} Volume", color=text_hex, fontsize=9, pad=4)
        ax1.grid(True, alpha=0.3)
        ax1.tick_params(labelbottom=False, labelsize=7)

        # 상승일=파랑, 하락일=빨강
        vol_colors = [
            accent_hex if (i == 0 or close.iloc[i] >= close.iloc[i - 1]) else "red"
            for i in range(len(close))
        ]
        ax2.bar(volume.index, volume, color=vol_colors, width=1.0, alpha=0.8)
        ax2.set_ylabel("Volume", color=secondary_hex, fontsize=7)
        ax2.grid(True, alpha=0.3)
        ax2.tick_params(axis="x", labelsize=7, rotation=30)
        ax2.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        return fig

    def _chart_default(
        self, df, close, fig_w, fig_h, dpi, ticker,
        accent_hex, accent_light_hex, text_hex, secondary_hex, bg_hex
    ):
        """기본 차트 - 종가 라인 + 거래량 (2패널)."""
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec

        volume = df.get("volume", None)
        has_volume = volume is not None and not volume.empty

        if has_volume:
            fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
            gs = gridspec.GridSpec(10, 1, hspace=0.05)
            ax1 = fig.add_subplot(gs[:7, 0])
            ax2 = fig.add_subplot(gs[7:, 0], sharex=ax1)

            ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
            ax1.set_title(f"{ticker} Price", color=text_hex, fontsize=9, pad=4)
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(labelbottom=False, labelsize=7)

            ax2.bar(volume.index, volume, color=accent_hex, width=1.0, alpha=0.6)
            ax2.set_ylabel("Volume", color=secondary_hex, fontsize=7)
            ax2.grid(True, alpha=0.3)
            ax2.tick_params(axis="x", labelsize=7, rotation=30)
            ax2.tick_params(axis="y", labelsize=7)
        else:
            fig, ax1 = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
            ax1.plot(close.index, close, color=accent_light_hex, linewidth=1.2)
            ax1.set_title(f"{ticker} Price", color=text_hex, fontsize=9, pad=4)
            ax1.grid(True, alpha=0.3)
            ax1.tick_params(axis="x", labelsize=7, rotation=30)
            ax1.tick_params(axis="y", labelsize=7)

        fig.tight_layout()
        return fig
