// 목적: F006 video_bg 모드 — 애니메이션 그라디언트 배경 + JSON 텍스트 렌더링 컴포넌트
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  TransitionSeries,
  linearTiming,
  springTiming,
} from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { SRTEntry } from "./F006Video";

// ── 테마 색상 상수 ───────────────────────────────────────────────

interface ThemeColorSet {
  bg1: string;
  bg2: string;
  text: string;
  accent: string;
  header: string;
  sub: string;
  bar: string;
}

const THEME_COLORS: Record<string, ThemeColorSet> = {
  dark_blue: {
    bg1: "#0a1628",
    bg2: "#0f2454",
    text: "#ffffff",
    accent: "#4a9fd4",
    header: "#e8f4ff",
    sub: "#a0c4e8",
    bar: "rgba(10, 22, 40, 0.85)",
  },
  warm_gray: {
    bg1: "#1a1614",
    bg2: "#2a2320",
    text: "#f5ede0",
    accent: "#e8a54b",
    header: "#fff5e8",
    sub: "#c4a882",
    bar: "rgba(26, 22, 20, 0.85)",
  },
  clean_white: {
    bg1: "#f0f4f8",
    bg2: "#e8f4fd",
    text: "#1a2332",
    accent: "#2563eb",
    header: "#0f172a",
    sub: "#475569",
    bar: "rgba(240, 244, 248, 0.92)",
  },
};

// ── Props 타입 ───────────────────────────────────────────────────

export interface SlideDataB {
  /** 슬라이드 번호 (1-based) */
  slide_no: number;
  /** 슬라이드 타입 */
  type: "title" | "content" | "summary" | "quote";
  /** 상단에 표시할 헤더 텍스트 */
  header: string;
  /** 본문 텍스트 */
  body_text: string;
  /** accent 색상으로 강조할 키워드 목록 */
  keywords: string[];
  /** 차트 PNG 상대 경로 (--public-dir 기준, 없으면 빈 문자열) */
  chart_path?: string;
  /** 이 슬라이드의 표시 시간(초) */
  duration_sec: number;
}

export interface F006VideoBProps {
  slides: SlideDataB[];
  /** 오디오 파일 절대 경로 (mp3) */
  audio_path: string;
  /** 파싱된 SRT 자막 항목 목록 */
  srt_entries: SRTEntry[];
  /** 채널명 (상단 바에 표시) */
  channel_name: string;
  /** 종목 표시 라벨 — "삼성전자(005930)" 형식, 없으면 빈 문자열 */
  ticker_label?: string;
  /** 테마 이름 (dark_blue / warm_gray / clean_white) */
  theme: string;
  /** 전환 모드 (auto / fade_only / slide_only) */
  transition_mode: string;
}

// ── 전환 효과 선택 ─────────────────────────────────────────────

const TRANSITION_FRAMES = 12;

function getTransitionPresentation(
  fromType: string,
  toType: string,
  mode: string
) {
  if (mode === "fade_only") return fade();
  if (mode === "slide_only") return slide({ direction: "from-right" });

  // auto 모드 — 슬라이드 타입별 전환
  if (fromType === "title") return slide({ direction: "from-bottom" });
  if (toType === "summary") return fade();
  if (toType === "quote") return fade();
  return slide({ direction: "from-right" });
}

function getTransitionTiming(fromType: string, toType: string, mode: string) {
  if (mode === "fade_only")
    return linearTiming({ durationInFrames: TRANSITION_FRAMES });
  if (fromType === "title" || toType === "summary")
    return linearTiming({ durationInFrames: TRANSITION_FRAMES });
  return springTiming({ durationInFrames: TRANSITION_FRAMES });
}

// ── 색상 헬퍼 — hex를 rgb로 변환 후 보간 ─────────────────────────

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return [r, g, b];
}

function mixColor(hexA: string, hexB: string, ratio: number): string {
  // ratio 0 = hexA, ratio 1 = hexB
  const [r1, g1, b1] = hexToRgb(hexA);
  const [r2, g2, b2] = hexToRgb(hexB);
  const r = Math.round(r1 + (r2 - r1) * ratio);
  const g = Math.round(g1 + (g2 - g1) * ratio);
  const b = Math.round(b1 + (b2 - b1) * ratio);
  return `rgb(${r}, ${g}, ${b})`;
}

// ── 애니메이션 그라디언트 배경 ───────────────────────────────────

interface GradientBackgroundProps {
  colors: ThemeColorSet;
  totalDuration: number;
}

const GradientBackground: React.FC<GradientBackgroundProps> = ({
  colors,
  totalDuration,
}) => {
  const frame = useCurrentFrame();
  // 0→totalDuration 구간을 사이클로 만들어 0→1→0 보간
  // 사이클 길이 = totalDuration * 2, 현재 위치 = frame % cycleDuration
  const cycleDuration = totalDuration * 2;
  const cyclePos = frame % cycleDuration;
  const ratio = interpolate(cyclePos, [0, totalDuration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const colorA = mixColor(colors.bg1, colors.bg2, ratio);
  const colorB = mixColor(colors.bg2, colors.bg1, ratio);

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(135deg, ${colorA} 0%, ${colorB} 100%)`,
      }}
    />
  );
};

// ── 키워드 강조 텍스트 렌더러 ────────────────────────────────────

interface HighlightedTextProps {
  text: string;
  keywords: string[];
  accentColor: string;
  baseStyle: React.CSSProperties;
  accentStyle?: React.CSSProperties;
}

const HighlightedText: React.FC<HighlightedTextProps> = ({
  text,
  keywords,
  accentColor,
  baseStyle,
  accentStyle,
}) => {
  if (keywords.length === 0) {
    return <span style={baseStyle}>{text}</span>;
  }

  // 키워드를 정규식으로 분리 (대소문자 구분 없음)
  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);

  return (
    <span style={baseStyle}>
      {parts.map((part, idx) => {
        const isKeyword = keywords.some(
          (k) => k.toLowerCase() === part.toLowerCase()
        );
        if (isKeyword) {
          return (
            <span
              key={idx}
              style={{
                color: accentColor,
                fontWeight: 700,
                ...accentStyle,
              }}
            >
              {part}
            </span>
          );
        }
        return <span key={idx}>{part}</span>;
      })}
    </span>
  );
};

// ── 슬라이드 렌더러 (video_bg 전용) ──────────────────────────────

interface SlideRendererBProps {
  slide: SlideDataB;
  colors: ThemeColorSet;
  channelName: string;
  tickerLabel: string;
  totalDuration: number;
}

const SlideRendererB: React.FC<SlideRendererBProps> = ({
  slide,
  colors,
  channelName,
  tickerLabel,
  totalDuration,
}) => {
  const frame = useCurrentFrame();

  // 헤더: 0~15프레임 opacity 0→1, translateY -20→0
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const headerTranslateY = interpolate(frame, [0, 15], [-30, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 본문: 8~25프레임 opacity 0→1, translateY 15→0
  const bodyOpacity = interpolate(frame, [8, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyTranslateY = interpolate(frame, [8, 25], [23, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 슬라이드 타입별 폰트 크기 설정
  const headerFontSize =
    slide.type === "title"
      ? 90
      : slide.type === "content"
      ? 57
      : slide.type === "summary"
      ? 54
      : 0; // quote는 헤더 없음

  const bodyFontSize =
    slide.type === "quote" ? 48 : 39;

  const showHeader = slide.type !== "quote" && slide.header;
  const showBody =
    slide.type !== "title" || slide.body_text;

  return (
    <AbsoluteFill>
      {/* 애니메이션 그라디언트 배경 */}
      <GradientBackground colors={colors} totalDuration={totalDuration} />

      {/* 상단 바 — title/summary는 채널명 숨김, 나머지는 채널명|종목|제목 표시 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 60,
          background: colors.bar,
          display: "flex",
          alignItems: "center",
          paddingLeft: 36,
          zIndex: 10,
        }}
      >
        {slide.type !== "title" && slide.type !== "summary" && (
          <span
            style={{
              color: colors.sub,
              fontSize: 22,
              fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
              fontWeight: 600,
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {[channelName, tickerLabel, slide.header].filter(Boolean).join(" | ")}
          </span>
        )}
      </div>

      {/* 콘텐츠 영역 — content+chart: 좌우 분할 / 그 외: 기존 단일 컬럼 */}
      {slide.type === "content" && slide.chart_path ? (
        // 차트 있는 content 슬라이드: 텍스트(50%) + 차트(48%) 가로 분할
        <div
          style={{
            position: "absolute",
            top: 60,
            left: 0,
            right: 0,
            bottom: 72,
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            padding: "42px 60px",
            gap: 30,
          }}
        >
          {/* 텍스트 섹션 */}
          <div
            style={{
              flex: "0 0 50%",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              gap: 30,
            }}
          >
            {showHeader && (
              <div
                style={{
                  opacity: headerOpacity,
                  transform: `translateY(${headerTranslateY}px)`,
                  color: colors.header,
                  fontSize: headerFontSize,
                  fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                  fontWeight: 800,
                  lineHeight: 1.3,
                }}
              >
                {slide.header}
              </div>
            )}
            {showBody && slide.body_text && (
              <div
                style={{
                  opacity: bodyOpacity,
                  transform: `translateY(${bodyTranslateY}px)`,
                }}
              >
                <HighlightedText
                  text={slide.body_text}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: bodyFontSize,
                    fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                    fontWeight: 600,
                    lineHeight: 1.8,
                    display: "block",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                />
              </div>
            )}
          </div>
          {/* 차트 이미지 섹션 */}
          <div
            style={{
              flex: "0 0 48%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              opacity: bodyOpacity,
            }}
          >
            <Img
              src={staticFile(slide.chart_path)}
              style={{
                width: "100%",
                height: "auto",
                maxHeight: 750,
                borderRadius: 12,
                objectFit: "contain",
              }}
            />
          </div>
        </div>
      ) : (
        // 기존 단일 컬럼 레이아웃 (title / summary / quote / chart 없는 content)
        <div
          style={{
            position: "absolute",
            top: 60,
            left: 0,
            right: 0,
            bottom: 72,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: slide.type === "quote" ? "center" : "flex-start",
            padding: "48px 96px",
            gap: 36,
          }}
        >
          {/* 헤더 텍스트 */}
          {showHeader && (
            <div
              style={{
                opacity: headerOpacity,
                transform: `translateY(${headerTranslateY}px)`,
                color: colors.header,
                fontSize: headerFontSize,
                fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                fontWeight: 800,
                lineHeight: 1.3,
                textAlign: slide.type === "title" ? "center" : "left",
                width: "100%",
              }}
            >
              {slide.header}
            </div>
          )}

          {/* summary 타입 구분선 */}
          {slide.type === "summary" && showHeader && (
            <div
              style={{
                width: 120,
                height: 5,
                background: colors.accent,
                opacity: headerOpacity,
                borderRadius: 3,
              }}
            />
          )}

          {/* 본문 텍스트 */}
          {showBody && slide.body_text && (
            <div
              style={{
                opacity: bodyOpacity,
                transform: `translateY(${bodyTranslateY}px)`,
                width: "100%",
              }}
            >
              {slide.type === "quote" ? (
                <div
                  style={{
                    color: colors.text,
                    fontSize: bodyFontSize,
                    fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                    fontStyle: "italic",
                    fontWeight: 500,
                    lineHeight: 1.7,
                    textAlign: "center",
                    position: "relative",
                    padding: "0 72px",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                >
                  <span
                    style={{
                      position: "absolute",
                      left: 0,
                      top: -24,
                      fontSize: 120,
                      color: colors.accent,
                      opacity: 0.4,
                      fontFamily: "Georgia, serif",
                      lineHeight: 1,
                    }}
                  >
                    "
                  </span>
                  <HighlightedText
                    text={slide.body_text}
                    keywords={slide.keywords}
                    accentColor={colors.accent}
                    baseStyle={{}}
                  />
                </div>
              ) : (
                <HighlightedText
                  text={slide.body_text}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: bodyFontSize,
                    fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                    fontWeight: 600,
                    lineHeight: 1.8,
                    display: "block",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* 하단 바 — 높이 72px */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 72,
          background: colors.bar,
          zIndex: 10,
        }}
      />
    </AbsoluteFill>
  );
};

// ── 자막 오버레이 ────────────────────────────────────────────────
// currentSec는 상위(F006VideoB)에서 전역 프레임 기반으로 직접 계산해 전달
// Sequence 내부 로컬 프레임을 사용하지 않으므로 오디오 타임라인과 정확히 동기화됨

interface SubtitleOverlayProps {
  srtEntries: SRTEntry[];
  currentSec: number;  // 상위에서 globalFrame / fps로 계산해 전달
}

const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({
  srtEntries,
  currentSec,
}) => {

  const activeEntry = srtEntries.find(
    (e) => e.start_sec <= currentSec && currentSec < e.end_sec
  );

  if (!activeEntry) return null;

  const endSec = activeEntry.end_sec;
  const fadeStartSec = endSec - 0.3;
  const subtitleOpacity =
    currentSec >= fadeStartSec
      ? interpolate(currentSec, [fadeStartSec, endSec], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 102,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          background: "rgba(0,0,0,0.65)",
          color: "#FFFFFF",
          fontSize: 42,
          fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
          fontWeight: 500,
          textShadow: "2px 2px 4px rgba(0,0,0,0.9)",
          padding: "12px 30px",
          borderRadius: 9,
          textAlign: "center",
          maxWidth: "80%",
          lineHeight: 1.5,
          opacity: subtitleOpacity,
        }}
      >
        {activeEntry.text}
      </div>
    </AbsoluteFill>
  );
};

// ── 메인 컴포넌트 ────────────────────────────────────────────────

export const F006VideoB: React.FC<F006VideoBProps> = ({
  slides,
  audio_path,
  srt_entries,
  channel_name,
  ticker_label,
  theme,
  transition_mode,
}) => {
  const { fps } = useVideoConfig();
  // 전역 프레임 — Audio 트랙과 동일한 타임라인 기준
  const globalFrame = useCurrentFrame();
  const globalCurrentSec = globalFrame / fps;

  // 테마 색상 — 없으면 dark_blue 폴백
  const colors: ThemeColorSet = THEME_COLORS[theme] ?? THEME_COLORS["dark_blue"];

  if (slides.length === 0) {
    return <AbsoluteFill style={{ background: colors.bg1 }} />;
  }

  // 각 슬라이드의 durationInFrames 계산
  const slideDurationFrames = slides.map((s) => Math.ceil(s.duration_sec * fps));

  // 전체 총 프레임 수 (배경 애니메이션 사이클 기준용)
  const totalFrames = slideDurationFrames.reduce((a, b) => a + b, 0);

  return (
    <AbsoluteFill>
      {/* 오디오 트랙 */}
      {audio_path && <Audio src={staticFile(audio_path)} />}

      {/* 슬라이드 전환 시리즈 */}
      <TransitionSeries>
        {slides.map((slideItem, i) => {
          const nextSlide = slides[i + 1];
          const fromType = slideItem.type;
          const toType = nextSlide?.type ?? "";

          return (
            <React.Fragment key={slideItem.slide_no}>
              <TransitionSeries.Sequence
                durationInFrames={slideDurationFrames[i]}
              >
                <AbsoluteFill>
                  <SlideRendererB
                    slide={slideItem}
                    colors={colors}
                    channelName={channel_name}
                    tickerLabel={ticker_label ?? ""}
                    totalDuration={totalFrames}
                  />
                </AbsoluteFill>
              </TransitionSeries.Sequence>

              {nextSlide && (
                <TransitionSeries.Transition
                  presentation={getTransitionPresentation(
                    fromType,
                    toType,
                    transition_mode
                  )}
                  timing={getTransitionTiming(fromType, toType, transition_mode)}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* 자막 오버레이 — TransitionSeries 바깥, 전역 currentSec 사용으로 오디오와 정확히 동기화 */}
      {srt_entries.length > 0 && (
        <SubtitleOverlay
          srtEntries={srt_entries}
          currentSec={globalCurrentSec}
        />
      )}
    </AbsoluteFill>
  );
};
