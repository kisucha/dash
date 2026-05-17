// 목적: F006 video_bg 모드 — 애니메이션 그라디언트 배경 + JSON 텍스트 렌더링 컴포넌트
import React from "react";
import {
  AbsoluteFill,
  Audio,
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
  totalDuration: number;
}

const SlideRendererB: React.FC<SlideRendererBProps> = ({
  slide,
  colors,
  channelName,
  totalDuration,
}) => {
  const frame = useCurrentFrame();

  // 헤더: 0~15프레임 opacity 0→1, translateY -20→0
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const headerTranslateY = interpolate(frame, [0, 15], [-20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 본문: 8~25프레임 opacity 0→1, translateY 15→0
  const bodyOpacity = interpolate(frame, [8, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyTranslateY = interpolate(frame, [8, 25], [15, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 슬라이드 타입별 폰트 크기 설정
  const headerFontSize =
    slide.type === "title"
      ? 60
      : slide.type === "content"
      ? 38
      : slide.type === "summary"
      ? 36
      : 0; // quote는 헤더 없음

  const bodyFontSize =
    slide.type === "quote" ? 32 : 22;

  const showHeader = slide.type !== "quote" && slide.header;
  const showBody =
    slide.type !== "title" || slide.body_text;

  return (
    <AbsoluteFill>
      {/* 애니메이션 그라디언트 배경 */}
      <GradientBackground colors={colors} totalDuration={totalDuration} />

      {/* 상단 채널명 바 — 높이 40px */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 40,
          background: colors.bar,
          display: "flex",
          alignItems: "center",
          paddingLeft: 24,
          zIndex: 10,
        }}
      >
        <span
          style={{
            color: colors.sub,
            fontSize: 14,
            fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
            fontWeight: 600,
            letterSpacing: 1.5,
            textTransform: "uppercase",
          }}
        >
          {channelName}
        </span>
      </div>

      {/* 콘텐츠 영역 — 상단 바(40px)와 하단 바(48px) 사이 */}
      <div
        style={{
          position: "absolute",
          top: 40,
          left: 0,
          right: 0,
          bottom: 48,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: slide.type === "quote" ? "center" : "flex-start",
          padding: "32px 64px",
          gap: 24,
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
              width: 80,
              height: 3,
              background: colors.accent,
              opacity: headerOpacity,
              borderRadius: 2,
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
            {/* quote 타입: italic + 인용 기호 */}
            {slide.type === "quote" ? (
              <div
                style={{
                  color: colors.text,
                  fontSize: bodyFontSize,
                  fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                  fontStyle: "italic",
                  fontWeight: 400,
                  lineHeight: 1.7,
                  textAlign: "center",
                  position: "relative",
                  padding: "0 48px",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    left: 0,
                    top: -16,
                    fontSize: 80,
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
              /* title / content / summary 타입 */
              <HighlightedText
                text={slide.body_text}
                keywords={slide.keywords}
                accentColor={colors.accent}
                baseStyle={{
                  color: colors.text,
                  fontSize: bodyFontSize,
                  fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                  fontWeight: 400,
                  lineHeight: 1.8,
                  display: "block",
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* 하단 브랜딩 바 — 높이 48px */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 48,
          background: colors.bar,
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          paddingRight: 24,
          zIndex: 10,
        }}
      >
        <span
          style={{
            color: colors.accent,
            fontSize: 13,
            fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
            fontWeight: 700,
            letterSpacing: 0.5,
          }}
        >
          {channelName}
        </span>
      </div>
    </AbsoluteFill>
  );
};

// ── 자막 오버레이 ────────────────────────────────────────────────

interface SubtitleOverlayProps {
  srtEntries: SRTEntry[];
  timelineOffsetSec: number;
}

const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({
  srtEntries,
  timelineOffsetSec,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentSec = timelineOffsetSec + frame / fps;

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
        paddingBottom: 68,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          background: "rgba(0,0,0,0.65)",
          color: "#FFFFFF",
          fontSize: 28,
          fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
          fontWeight: 500,
          textShadow: "1px 1px 3px rgba(0,0,0,0.9)",
          padding: "8px 20px",
          borderRadius: 6,
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
  theme,
  transition_mode,
}) => {
  const { fps } = useVideoConfig();

  // 테마 색상 — 없으면 dark_blue 폴백
  const colors: ThemeColorSet = THEME_COLORS[theme] ?? THEME_COLORS["dark_blue"];

  if (slides.length === 0) {
    return <AbsoluteFill style={{ background: colors.bg1 }} />;
  }

  // 각 슬라이드의 durationInFrames 계산
  const slideDurationFrames = slides.map((s) => Math.ceil(s.duration_sec * fps));

  // 전체 총 프레임 수 (배경 애니메이션 사이클 기준용)
  const totalFrames = slideDurationFrames.reduce((a, b) => a + b, 0);

  // 슬라이드별 타임라인 시작 시간(초) 계산 — 자막 동기화용
  // 전환 구간 겹침 보정
  const slideStartSecs: number[] = [];
  let accFrames = 0;
  for (let i = 0; i < slides.length; i++) {
    slideStartSecs.push(accFrames / fps);
    accFrames += slideDurationFrames[i];
    if (i < slides.length - 1) accFrames -= TRANSITION_FRAMES;
  }

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
                    totalDuration={totalFrames}
                  />
                  <SubtitleOverlay
                    srtEntries={srt_entries}
                    timelineOffsetSec={slideStartSecs[i]}
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
    </AbsoluteFill>
  );
};
