// 목적: F006 fluid_bg 모드 - SVG feTurbulence/feDisplacementMap 유체 배경(Level 3) + 글라스모피즘 카드 텍스트 렌더링
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
import { SlideDataB } from "./F006VideoB";

// ── Props 타입 ───────────────────────────────────────────────────

export interface F006VideoCProps {
  slides: SlideDataB[];
  audio_path: string;
  srt_entries: SRTEntry[];
  channel_name: string;
  /** 종목 표시 라벨 — "삼성전자(005930)" 형식, 없으면 빈 문자열 */
  ticker_label?: string;
  theme: string;
  transition_mode: string;
}

// ── 테마 색상 (fluid_bg 전용 - orb/particle/glass 색상 포함) ────

interface ThemeColorSet {
  bg: string;
  orb1: string;
  orb2: string;
  orb3: string;
  particle: string;
  text: string;
  accent: string;
  header: string;
  sub: string;
  card: string;
  cardBorder: string;
  bar: string;
}

const THEME_COLORS: Record<string, ThemeColorSet> = {
  dark_blue: {
    bg: "#060e20",
    orb1: "rgba(15, 70, 190, 0.42)",
    orb2: "rgba(0, 145, 175, 0.32)",
    orb3: "rgba(70, 15, 185, 0.26)",
    particle: "#4a9fd4",
    text: "#ffffff",
    accent: "#4a9fd4",
    header: "#e8f4ff",
    sub: "#a0c4e8",
    card: "rgba(6, 18, 55, 0.60)",
    cardBorder: "rgba(74, 159, 212, 0.24)",
    bar: "rgba(4, 10, 28, 0.84)",
  },
  warm_gray: {
    bg: "#0c0905",
    orb1: "rgba(185, 95, 12, 0.38)",
    orb2: "rgba(145, 55, 22, 0.30)",
    orb3: "rgba(105, 75, 8, 0.24)",
    particle: "#e8a54b",
    text: "#f5ede0",
    accent: "#e8a54b",
    header: "#fff5e8",
    sub: "#c4a882",
    card: "rgba(28, 20, 8, 0.64)",
    cardBorder: "rgba(232, 165, 75, 0.24)",
    bar: "rgba(12, 9, 5, 0.86)",
  },
  clean_white: {
    bg: "#e4eaf4",
    orb1: "rgba(37, 99, 235, 0.20)",
    orb2: "rgba(6, 182, 212, 0.16)",
    orb3: "rgba(99, 102, 241, 0.14)",
    particle: "#2563eb",
    text: "#1a2332",
    accent: "#2563eb",
    header: "#0f172a",
    sub: "#475569",
    card: "rgba(255, 255, 255, 0.60)",
    cardBorder: "rgba(37, 99, 235, 0.20)",
    bar: "rgba(228, 234, 244, 0.90)",
  },
};

// ── 전환 프레임 수 ────────────────────────────────────────────────

const TRANSITION_FRAMES = 12;

function getTransitionPresentation(fromType: string, toType: string, mode: string) {
  if (mode === "fade_only") return fade();
  if (mode === "slide_only") return slide({ direction: "from-right" });
  if (fromType === "title") return slide({ direction: "from-bottom" });
  if (toType === "summary") return fade();
  if (toType === "quote") return fade();
  return slide({ direction: "from-right" });
}

function getTransitionTiming(fromType: string, toType: string, mode: string) {
  if (mode === "fade_only") return linearTiming({ durationInFrames: TRANSITION_FRAMES });
  if (fromType === "title" || toType === "summary")
    return linearTiming({ durationInFrames: TRANSITION_FRAMES });
  return springTiming({ durationInFrames: TRANSITION_FRAMES });
}

// ── 결정적 의사난수 (seed 기반) ───────────────────────────────────
// Remotion은 프레임별 독립 렌더링 - Math.random() 금지, seeded 함수 필수

function seededFloat(seed: number): number {
  const x = Math.sin(seed + 1) * 10000;
  return x - Math.floor(x);
}

// ── 파티클 정적 데이터 (모듈 레벨 - 재생성 방지) ─────────────────

const PARTICLE_COUNT = 40;

interface Particle {
  x0: number;
  y0: number;
  vx: number;
  vy: number;
  size: number;
  opacity: number;
}

// 파티클 초기 상태 - seed 기반으로 결정적 생성
const PARTICLES: Particle[] = Array.from({ length: PARTICLE_COUNT }, (_, i) => {
  const speed = seededFloat(i * 3.1 + 3) * 0.28 + 0.08;
  const angle = seededFloat(i * 5.9 + 4) * Math.PI * 2;
  return {
    x0: seededFloat(i * 7.3 + 1) * 1920,
    y0: seededFloat(i * 13.7 + 2) * 1080,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    size: seededFloat(i * 11.1 + 5) * 8 + 3,
    opacity: seededFloat(i * 17.3 + 6) * 0.32 + 0.08,
  };
});

// ── 유체 배경 컴포넌트 (Level 3) ─────────────────────────────────
// SVG feTurbulence + feDisplacementMap으로 진짜 유체 왜곡 효과
// orb = SVG ellipse → filter 파이프라인: noise → displacement → gaussian blur
// 파티클 = HTML div 레이어 (반짝임 보완)

const FluidBackground: React.FC<{ colors: ThemeColorSet }> = ({ colors }) => {
  const frame = useCurrentFrame();
  const t = frame * 0.006;

  // orb 중심 이동 - 사인파 기반 결정적 경로
  const orb1X = 555 + Math.sin(t) * 443;
  const orb1Y = 353 + Math.cos(t * 0.73) * 258;
  const orb2X = 1335 + Math.cos(t * 1.21) * 363;
  const orb2Y = 683 + Math.sin(t * 0.87) * 288;
  const orb3X = 960 + Math.sin(t * 0.63 + 1.5) * 312;
  const orb3Y = 518 + Math.cos(t * 1.04 + 0.8) * 207;

  // feTurbulence 파라미터 - 천천히 변화해 유기적 흐름 연출
  const bfx = (0.009 + Math.sin(t * 0.28) * 0.003).toFixed(5);
  const bfy = (0.013 + Math.cos(t * 0.21) * 0.004).toFixed(5);
  // displacement 강도 - 숨쉬는 느낌으로 진폭 변화
  const dispScale = Math.round(95 + Math.sin(t * 0.44) * 38);
  // seed - 180프레임(6초)마다 교체해 패턴 다양화, 급격한 점프 없이 조용히 변경
  const seed = Math.floor(frame / 180) % 100;

  return (
    <AbsoluteFill style={{ background: colors.bg, overflow: "hidden" }}>
      {/* SVG 유체 레이어 - feTurbulence displacement로 orb 왜곡 */}
      <svg
        width="1920"
        height="1080"
        style={{ position: "absolute", top: 0, left: 0 }}
      >
        <defs>
          <filter
            id="fluid-distort"
            x="-30%"
            y="-30%"
            width="160%"
            height="160%"
            colorInterpolationFilters="sRGB"
          >
            {/* 1단계: fractalNoise로 부드러운 유체 노이즈 생성 */}
            <feTurbulence
              type="fractalNoise"
              baseFrequency={`${bfx} ${bfy}`}
              numOctaves={4}
              seed={seed}
              result="noise"
            />
            {/* 2단계: 노이즈로 소스(ellipse)를 공간 왜곡 */}
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale={dispScale}
              xChannelSelector="R"
              yChannelSelector="G"
              result="displaced"
            />
            {/* 3단계: 왜곡된 형태를 소프트 블러로 마무리 - 유체 경계 */}
            <feGaussianBlur in="displaced" stdDeviation="52" />
          </filter>
        </defs>

        {/* orb 1 - 가장 크고 강한 메인 */}
        <ellipse
          cx={orb1X}
          cy={orb1Y}
          rx={570}
          ry={525}
          fill={colors.orb1}
          filter="url(#fluid-distort)"
        />
        {/* orb 2 */}
        <ellipse
          cx={orb2X}
          cy={orb2Y}
          rx={465}
          ry={420}
          fill={colors.orb2}
          filter="url(#fluid-distort)"
        />
        {/* orb 3 - 작은 강조 */}
        <ellipse
          cx={orb3X}
          cy={orb3Y}
          rx={353}
          ry={323}
          fill={colors.orb3}
          filter="url(#fluid-distort)"
        />
      </svg>

      {/* 파티클 레이어 - 글리터 효과로 배경에 반짝임 추가 */}
      {PARTICLES.map((p, i) => {
        const px = ((p.x0 + p.vx * frame) % 1920 + 1920) % 1920;
        const py = ((p.y0 + p.vy * frame) % 1080 + 1080) % 1080;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: px,
              top: py,
              width: p.size,
              height: p.size,
              borderRadius: "50%",
              background: colors.particle,
              opacity: p.opacity,
              boxShadow: `0 0 ${p.size * 2}px ${p.size * 0.8}px ${colors.particle}44`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// ── 글라스모피즘 카드 ────────────────────────────────────────────

interface GlassCardProps {
  children: React.ReactNode;
  colors: ThemeColorSet;
  style?: React.CSSProperties;
}

const GlassCard: React.FC<GlassCardProps> = ({ children, colors, style }) => (
  <div
    style={{
      background: colors.card,
      backdropFilter: "blur(22px)",
      border: `1px solid ${colors.cardBorder}`,
      borderRadius: 27,
      padding: "42px 57px",
      ...style,
    }}
  >
    {children}
  </div>
);

// ── 키워드 강조 텍스트 ────────────────────────────────────────────

interface HighlightedTextProps {
  text: string;
  keywords: string[];
  accentColor: string;
  baseStyle: React.CSSProperties;
}

const HighlightedText: React.FC<HighlightedTextProps> = ({
  text,
  keywords,
  accentColor,
  baseStyle,
}) => {
  if (keywords.length === 0) return <span style={baseStyle}>{text}</span>;
  const escaped = keywords.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <span style={baseStyle}>
      {parts.map((part, idx) => {
        const isKeyword = keywords.some((k) => k.toLowerCase() === part.toLowerCase());
        return isKeyword ? (
          <span key={idx} style={{ color: accentColor, fontWeight: 700 }}>
            {part}
          </span>
        ) : (
          <span key={idx}>{part}</span>
        );
      })}
    </span>
  );
};

// ── 슬라이드 렌더러 (fluid_bg 전용 레이아웃) ─────────────────────

interface SlideRendererCProps {
  slide: SlideDataB;
  colors: ThemeColorSet;
  channelName: string;
  tickerLabel: string;
}

const SlideRendererC: React.FC<SlideRendererCProps> = ({
  slide,
  colors,
  channelName,
  tickerLabel,
}) => {
  const frame = useCurrentFrame();
  const fontFamily = "Noto Sans KR, Malgun Gothic, sans-serif";

  // 카드 페이드인 (0~12프레임)
  const cardOpacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  // 헤더 슬라이드인 (0~18프레임)
  const headerOpacity = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const headerY = interpolate(frame, [0, 18], [-33, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  // 본문 슬라이드인 (10~28프레임)
  const bodyOpacity = interpolate(frame, [10, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyY = interpolate(frame, [10, 28], [24, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill>
      {/* 유체 배경 */}
      <FluidBackground colors={colors} />

      {/* 상단 바 — title/summary는 채널명 숨김, 나머지는 채널명|종목|제목 표시 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 66,
          background: colors.bar,
          borderBottom: `1px solid ${colors.cardBorder}`,
          display: "flex",
          alignItems: "center",
          paddingLeft: 42,
          paddingRight: 42,
          zIndex: 20,
        }}
      >
        {slide.type !== "title" && slide.type !== "summary" && (
          <span
            style={{
              color: colors.sub,
              fontSize: 22,
              fontFamily,
              fontWeight: 600,
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {[channelName, tickerLabel, slide.header].filter(Boolean).join(" | ")}
          </span>
        )}
      </div>

      {/* title 슬라이드 - 중앙 글라스 카드 */}
      {slide.type === "title" && (
        <div
          style={{
            position: "absolute",
            top: 66,
            left: 0,
            right: 0,
            bottom: 75,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "0 120px",
          }}
        >
          <GlassCard
            colors={colors}
            style={{
              width: "100%",
              maxWidth: 1260,
              textAlign: "center",
              opacity: cardOpacity,
            }}
          >
            {channelName && (
              <div
                style={{
                  color: colors.accent,
                  fontSize: 21,
                  fontFamily,
                  fontWeight: 700,
                  letterSpacing: 2.5,
                  textTransform: "uppercase",
                  marginBottom: 27,
                  opacity: headerOpacity,
                }}
              >
                {channelName}
              </div>
            )}
            <div
              style={{
                color: colors.header,
                fontSize: 78,
                fontFamily,
                fontWeight: 800,
                lineHeight: 1.25,
                marginBottom: 27,
                opacity: headerOpacity,
                transform: `translateY(${headerY}px)`,
              }}
            >
              {slide.header}
            </div>
            {/* accent 구분선 */}
            <div
              style={{
                width: 96,
                height: 5,
                background: colors.accent,
                margin: "0 auto 27px",
                borderRadius: 3,
                opacity: headerOpacity,
              }}
            />
            {slide.body_text && (
              <div
                style={{
                  color: colors.sub,
                  fontSize: 39,
                  fontFamily,
                  fontWeight: 600,
                  lineHeight: 1.65,
                  opacity: bodyOpacity,
                  transform: `translateY(${bodyY}px)`,
                  WebkitFontSmoothing: "antialiased",
                  MozOsxFontSmoothing: "grayscale",
                  textRendering: "geometricPrecision",
                }}
              >
                {slide.body_text}
              </div>
            )}
          </GlassCard>
        </div>
      )}

      {/* content 슬라이드 - 글라스 카드 + (차트 있으면) 우측 차트 이미지 */}
      {slide.type === "content" && (
        <div
          style={{
            position: "absolute",
            top: 66,
            left: 0,
            right: 0,
            bottom: 75,
            display: "flex",
            flexDirection: "row",
            alignItems: "center",
            padding: "36px 84px",
            gap: 30,
          }}
        >
          <GlassCard
            colors={colors}
            style={{
              flex: slide.chart_path ? "0 0 44%" : "0 0 66%",
              opacity: cardOpacity,
              borderLeft: `3px solid ${colors.accent}`,
              borderRadius: "4px 18px 18px 4px",
            }}
          >
            {slide.header && (
              <div
                style={{
                  color: colors.header,
                  fontSize: 48,
                  fontFamily,
                  fontWeight: 800,
                  lineHeight: 1.3,
                  marginBottom: 21,
                  opacity: headerOpacity,
                  transform: `translateY(${headerY}px)`,
                }}
              >
                {slide.header}
              </div>
            )}
            {slide.header && (
              <div
                style={{
                  width: 72,
                  height: 3,
                  background: colors.accent,
                  marginBottom: 27,
                  borderRadius: 3,
                  opacity: headerOpacity,
                }}
              />
            )}
            {slide.body_text && (
              <div
                style={{
                  opacity: bodyOpacity,
                  transform: `translateY(${bodyY}px)`,
                }}
              >
                <HighlightedText
                  text={slide.body_text}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: 39,
                    fontFamily,
                    fontWeight: 600,
                    lineHeight: 1.88,
                    display: "block",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                />
              </div>
            )}
          </GlassCard>
          {/* 차트 이미지 — chart_path 있을 때만 표시 */}
          {slide.chart_path && (
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
                  maxHeight: 735,
                  borderRadius: 18,
                  objectFit: "contain",
                }}
              />
            </div>
          )}
        </div>
      )}

      {/* summary 슬라이드 - 중앙 와이드 글라스 카드 */}
      {slide.type === "summary" && (
        <div
          style={{
            position: "absolute",
            top: 66,
            left: 0,
            right: 0,
            bottom: 75,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "36px 108px",
          }}
        >
          <GlassCard
            colors={colors}
            style={{ width: "100%", maxWidth: 1380, opacity: cardOpacity }}
          >
            {slide.header && (
              <div
                style={{
                  color: colors.accent,
                  fontSize: 20,
                  fontFamily,
                  fontWeight: 700,
                  letterSpacing: 2.5,
                  textTransform: "uppercase",
                  marginBottom: 15,
                  opacity: headerOpacity,
                }}
              >
                {slide.header}
              </div>
            )}
            <div
              style={{
                width: 84,
                height: 3,
                background: colors.accent,
                marginBottom: 30,
                borderRadius: 3,
                opacity: headerOpacity,
              }}
            />
            {slide.body_text && (
              <div style={{ opacity: bodyOpacity, transform: `translateY(${bodyY}px)` }}>
                <HighlightedText
                  text={slide.body_text}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: 39,
                    fontFamily,
                    fontWeight: 600,
                    lineHeight: 1.88,
                    display: "block",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                />
              </div>
            )}
          </GlassCard>
        </div>
      )}

      {/* quote 슬라이드 - 중앙 인용 카드 */}
      {slide.type === "quote" && (
        <div
          style={{
            position: "absolute",
            top: 66,
            left: 0,
            right: 0,
            bottom: 75,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "36px 150px",
          }}
        >
          <GlassCard
            colors={colors}
            style={{ maxWidth: 1290, textAlign: "center", opacity: cardOpacity }}
          >
            <div
              style={{
                color: colors.accent,
                fontSize: 114,
                fontFamily: "Georgia, serif",
                lineHeight: 0.8,
                marginBottom: 21,
                opacity: 0.42,
              }}
            >
              {'"'}
            </div>
            {slide.body_text && (
              <div style={{ opacity: bodyOpacity, transform: `translateY(${bodyY}px)` }}>
                <HighlightedText
                  text={slide.body_text}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: 42,
                    fontFamily,
                    fontStyle: "italic",
                    fontWeight: 500,
                    lineHeight: 1.72,
                    display: "block",
                    WebkitFontSmoothing: "antialiased",
                    MozOsxFontSmoothing: "grayscale",
                    textRendering: "geometricPrecision",
                  }}
                />
              </div>
            )}
          </GlassCard>
        </div>
      )}

      {/* 하단 바 */}
      <div
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: 75,
          background: colors.bar,
          borderTop: `1px solid ${colors.cardBorder}`,
          zIndex: 20,
        }}
      />
    </AbsoluteFill>
  );
};

// ── 자막 오버레이 ────────────────────────────────────────────────
// 상위에서 globalFrame / fps로 계산한 currentSec를 받아 오디오와 동기화

interface SubtitleOverlayProps {
  srtEntries: SRTEntry[];
  currentSec: number;
}

const SubtitleOverlay: React.FC<SubtitleOverlayProps> = ({ srtEntries, currentSec }) => {
  const activeEntry = srtEntries.find(
    (e) => e.start_sec <= currentSec && currentSec < e.end_sec
  );
  if (!activeEntry) return null;

  const fadeStart = activeEntry.end_sec - 0.3;
  const opacity =
    currentSec >= fadeStart
      ? interpolate(currentSec, [fadeStart, activeEntry.end_sec], [1, 0], {
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
          background: "rgba(0,0,0,0.68)",
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
          opacity,
        }}
      >
        {activeEntry.text}
      </div>
    </AbsoluteFill>
  );
};

// ── 메인 컴포넌트 ────────────────────────────────────────────────

export const F006VideoC: React.FC<F006VideoCProps> = ({
  slides,
  audio_path,
  srt_entries,
  channel_name,
  ticker_label,
  theme,
  transition_mode,
}) => {
  const { fps } = useVideoConfig();
  // 전역 프레임 - 자막 오버레이가 오디오 타임라인과 동기화되도록 TransitionSeries 밖에서 참조
  const globalFrame = useCurrentFrame();
  const globalCurrentSec = globalFrame / fps;

  const colors: ThemeColorSet = THEME_COLORS[theme] ?? THEME_COLORS["dark_blue"];

  if (slides.length === 0) {
    return <AbsoluteFill style={{ background: colors.bg }} />;
  }

  // 각 슬라이드의 durationInFrames 계산
  const slideDurationFrames = slides.map((s) => Math.ceil(s.duration_sec * fps));

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
              <TransitionSeries.Sequence durationInFrames={slideDurationFrames[i]}>
                <AbsoluteFill>
                  <SlideRendererC
                    slide={slideItem}
                    colors={colors}
                    channelName={channel_name}
                    tickerLabel={ticker_label ?? ""}
                  />
                </AbsoluteFill>
              </TransitionSeries.Sequence>
              {nextSlide && (
                <TransitionSeries.Transition
                  presentation={getTransitionPresentation(fromType, toType, transition_mode)}
                  timing={getTransitionTiming(fromType, toType, transition_mode)}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* 자막 오버레이 - TransitionSeries 바깥, 전역 currentSec으로 오디오 동기화 */}
      {srt_entries.length > 0 && (
        <SubtitleOverlay srtEntries={srt_entries} currentSec={globalCurrentSec} />
      )}
    </AbsoluteFill>
  );
};
