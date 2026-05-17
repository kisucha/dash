// 목적: F006 remotion_native 모드 — 전체 네이티브 렌더링, 숫자 카운터 애니메이션 + 분할 레이아웃
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
// SlideDataB와 Props 타입을 F006VideoB에서 재사용
export type { SlideDataB } from "./F006VideoB";
import { SlideDataB } from "./F006VideoB";

// ── Props 타입 (F006VideoBProps와 동일 구조) ─────────────────────

export interface F006VideoAProps {
  slides: SlideDataB[];
  audio_path: string;
  srt_entries: SRTEntry[];
  channel_name: string;
  theme: string;
  transition_mode: string;
}

// ── 테마 색상 상수 (F006VideoB와 동일 — 공유 모듈 없이 자급) ────

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

// ── 전환 효과 선택 ─────────────────────────────────────────────

const TRANSITION_FRAMES = 12;

function getTransitionPresentation(
  fromType: string,
  toType: string,
  mode: string
) {
  if (mode === "fade_only") return fade();
  if (mode === "slide_only") return slide({ direction: "from-right" });

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

// ── 색상 헬퍼 ─────────────────────────────────────────────────

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  return [r, g, b];
}

function mixColor(hexA: string, hexB: string, ratio: number): string {
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

// ── 숫자 카운터 애니메이션 ─────────────────────────────────────
// body_text에서 숫자 패턴 감지 후 0→실제값으로 40프레임 카운터 애니메이션 적용

const NUMBER_PATTERN = /(\d+(?:[,.]?\d+)*)/g;

/**
 * 문자열을 숫자/비숫자 파트로 분리.
 * ex) "영업이익 1,234억" => ["영업이익 ", "1,234", "억"]
 */
function splitByNumbers(text: string): Array<{ isNumber: boolean; value: string }> {
  const parts: Array<{ isNumber: boolean; value: string }> = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  NUMBER_PATTERN.lastIndex = 0;

  while ((match = NUMBER_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ isNumber: false, value: text.slice(lastIndex, match.index) });
    }
    parts.push({ isNumber: true, value: match[0] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push({ isNumber: false, value: text.slice(lastIndex) });
  }
  return parts;
}

interface AnimatedNumberProps {
  rawValue: string;
  frame: number;
  color: string;
}

const AnimatedNumber: React.FC<AnimatedNumberProps> = ({
  rawValue,
  frame,
  color,
}) => {
  // 콤마/점 제거 후 실제 숫자값 파싱
  const actualNum = parseFloat(rawValue.replace(/,/g, ""));
  const animated = Math.round(
    interpolate(frame, [0, 40], [0, actualNum], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  // 원래 포맷(콤마 포함) 여부 판단
  const hasComma = rawValue.includes(",");
  const display = hasComma ? animated.toLocaleString() : String(animated);

  return (
    <span style={{ color, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>
      {display}
    </span>
  );
};

// ── 키워드 + 숫자 강조 텍스트 렌더러 ──────────────────────────────

interface EnhancedTextProps {
  text: string;
  keywords: string[];
  accentColor: string;
  baseStyle: React.CSSProperties;
}

const EnhancedText: React.FC<EnhancedTextProps> = ({
  text,
  keywords,
  accentColor,
  baseStyle,
}) => {
  const frame = useCurrentFrame();
  const parts = splitByNumbers(text);

  return (
    <span style={baseStyle}>
      {parts.map((part, idx) => {
        if (part.isNumber) {
          return (
            <AnimatedNumber
              key={idx}
              rawValue={part.value}
              frame={frame}
              color={accentColor}
            />
          );
        }
        // 비숫자 파트에서 키워드 강조
        if (keywords.length === 0) {
          return <span key={idx}>{part.value}</span>;
        }
        const escaped = keywords.map((k) =>
          k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
        );
        const kwPattern = new RegExp(`(${escaped.join("|")})`, "gi");
        const subParts = part.value.split(kwPattern);
        return (
          <span key={idx}>
            {subParts.map((sub, sIdx) => {
              const isKw = keywords.some(
                (k) => k.toLowerCase() === sub.toLowerCase()
              );
              return isKw ? (
                <span key={sIdx} style={{ color: accentColor, fontWeight: 700 }}>
                  {sub}
                </span>
              ) : (
                <span key={sIdx}>{sub}</span>
              );
            })}
          </span>
        );
      })}
    </span>
  );
};

// ── 슬라이드 렌더러 (remotion_native 전용) ────────────────────────
// 레이아웃: 좌측 40% (헤더 + 키워드), 우측 60% (본문)
// summary 타입: 좌측 전체에 주요 숫자 크게 + 우측 설명

interface SlideRendererAProps {
  slide: SlideDataB;
  colors: ThemeColorSet;
  channelName: string;
  totalDuration: number;
}

const SlideRendererA: React.FC<SlideRendererAProps> = ({
  slide,
  colors,
  channelName,
  totalDuration,
}) => {
  const frame = useCurrentFrame();

  // 헤더 등장: 0~15프레임
  const headerOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const headerTranslateY = interpolate(frame, [0, 15], [-20, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 본문 등장: 8~25프레임
  const bodyOpacity = interpolate(frame, [8, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyTranslateY = interpolate(frame, [8, 25], [15, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // title 타입: 중앙 전체 레이아웃
  if (slide.type === "title") {
    return (
      <AbsoluteFill>
        <GradientBackground colors={colors} totalDuration={totalDuration} />
        {/* 상단 채널명 바 */}
        <TopBar colors={colors} channelName={channelName} />
        {/* 중앙 정렬 제목 */}
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
            alignItems: "center",
            padding: "32px 64px",
            gap: 20,
          }}
        >
          <div
            style={{
              opacity: headerOpacity,
              transform: `translateY(${headerTranslateY}px)`,
              color: colors.header,
              fontSize: 60,
              fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
              fontWeight: 800,
              lineHeight: 1.3,
              textAlign: "center",
            }}
          >
            {slide.header}
          </div>
          {slide.body_text && (
            <div
              style={{
                opacity: bodyOpacity,
                transform: `translateY(${bodyTranslateY}px)`,
                color: colors.sub,
                fontSize: 22,
                fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                fontWeight: 400,
                textAlign: "center",
              }}
            >
              {slide.body_text}
            </div>
          )}
        </div>
        <BottomBar colors={colors} channelName={channelName} />
      </AbsoluteFill>
    );
  }

  // quote 타입: 중앙 정렬 인용문
  if (slide.type === "quote") {
    return (
      <AbsoluteFill>
        <GradientBackground colors={colors} totalDuration={totalDuration} />
        <TopBar colors={colors} channelName={channelName} />
        <div
          style={{
            position: "absolute",
            top: 40,
            left: 0,
            right: 0,
            bottom: 48,
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            padding: "32px 80px",
          }}
        >
          <div
            style={{
              opacity: bodyOpacity,
              transform: `translateY(${bodyTranslateY}px)`,
              color: colors.text,
              fontSize: 32,
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
            <EnhancedText
              text={slide.body_text}
              keywords={slide.keywords}
              accentColor={colors.accent}
              baseStyle={{}}
            />
          </div>
        </div>
        <BottomBar colors={colors} channelName={channelName} />
      </AbsoluteFill>
    );
  }

  // summary 타입: 좌측에 주요 숫자 크게, 우측에 설명
  if (slide.type === "summary") {
    // 본문에서 첫 번째 숫자 추출 — 왼쪽 패널에 크게 표시
    NUMBER_PATTERN.lastIndex = 0;
    const numberMatch = NUMBER_PATTERN.exec(slide.body_text);
    const bigNumber = numberMatch ? numberMatch[0] : null;
    const bigNumActual = bigNumber
      ? parseFloat(bigNumber.replace(/,/g, ""))
      : 0;
    const bigNumAnimated = bigNumber
      ? Math.round(
          interpolate(frame, [0, 40], [0, bigNumActual], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })
        )
      : 0;
    const bigNumDisplay = bigNumber?.includes(",")
      ? bigNumAnimated.toLocaleString()
      : bigNumber
      ? String(bigNumAnimated)
      : "";

    return (
      <AbsoluteFill>
        <GradientBackground colors={colors} totalDuration={totalDuration} />
        <TopBar colors={colors} channelName={channelName} />
        <div
          style={{
            position: "absolute",
            top: 40,
            left: 0,
            right: 0,
            bottom: 48,
            display: "flex",
            flexDirection: "row",
          }}
        >
          {/* 좌측 패널 — 주요 숫자 크게 표시 */}
          <div
            style={{
              width: "40%",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              alignItems: "center",
              borderRight: `2px solid ${colors.accent}`,
              padding: "32px 24px",
              gap: 12,
            }}
          >
            <div
              style={{
                opacity: headerOpacity,
                transform: `translateY(${headerTranslateY}px)`,
                color: colors.sub,
                fontSize: 16,
                fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                fontWeight: 600,
                letterSpacing: 1,
                textTransform: "uppercase",
                textAlign: "center",
              }}
            >
              {slide.header}
            </div>
            {bigNumber && (
              <div
                style={{
                  opacity: bodyOpacity,
                  color: colors.accent,
                  fontSize: 64,
                  fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                  fontWeight: 900,
                  lineHeight: 1.1,
                  textAlign: "center",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                {bigNumDisplay}
              </div>
            )}
            {/* 키워드 태그 */}
            {slide.keywords.length > 0 && (
              <div
                style={{
                  opacity: bodyOpacity,
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 8,
                  justifyContent: "center",
                }}
              >
                {slide.keywords.map((kw, idx) => (
                  <span
                    key={idx}
                    style={{
                      background: `${colors.accent}22`,
                      color: colors.accent,
                      fontSize: 14,
                      fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                      fontWeight: 600,
                      padding: "4px 12px",
                      borderRadius: 20,
                      border: `1px solid ${colors.accent}66`,
                    }}
                  >
                    {kw}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 우측 패널 — 본문 설명 */}
          <div
            style={{
              width: "60%",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              padding: "32px 40px",
            }}
          >
            <div
              style={{
                opacity: bodyOpacity,
                transform: `translateY(${bodyTranslateY}px)`,
              }}
            >
              <EnhancedText
                text={slide.body_text}
                keywords={slide.keywords}
                accentColor={colors.accent}
                baseStyle={{
                  color: colors.text,
                  fontSize: 22,
                  fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                  fontWeight: 400,
                  lineHeight: 1.8,
                  display: "block",
                }}
              />
            </div>
          </div>
        </div>
        <BottomBar colors={colors} channelName={channelName} />
      </AbsoluteFill>
    );
  }

  // content 타입: 좌측 40% 헤더+키워드, 우측 60% bullet 목록
  // body_text를 줄별로 분리해 bullet 목록으로 표시
  const bodyLines = slide.body_text
    .split(/\n|(?<=。|다\.|다！|다\?|다!)/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  return (
    <AbsoluteFill>
      <GradientBackground colors={colors} totalDuration={totalDuration} />
      <TopBar colors={colors} channelName={channelName} />
      <div
        style={{
          position: "absolute",
          top: 40,
          left: 0,
          right: 0,
          bottom: 48,
          display: "flex",
          flexDirection: "row",
        }}
      >
        {/* 좌측 패널 — 헤더 + 키워드 태그 */}
        <div
          style={{
            width: "40%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "flex-start",
            borderRight: `2px solid ${colors.accent}`,
            padding: "32px 32px 32px 40px",
            gap: 16,
          }}
        >
          <div
            style={{
              opacity: headerOpacity,
              transform: `translateY(${headerTranslateY}px)`,
              color: colors.header,
              fontSize: 36,
              fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
              fontWeight: 800,
              lineHeight: 1.3,
            }}
          >
            {slide.header}
          </div>
          <div
            style={{
              width: 60,
              height: 3,
              background: colors.accent,
              opacity: headerOpacity,
              borderRadius: 2,
            }}
          />
          {slide.keywords.length > 0 && (
            <div
              style={{
                opacity: bodyOpacity,
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              {slide.keywords.map((kw, idx) => (
                <span
                  key={idx}
                  style={{
                    background: `${colors.accent}22`,
                    color: colors.accent,
                    fontSize: 14,
                    fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                    fontWeight: 600,
                    padding: "4px 12px",
                    borderRadius: 20,
                    border: `1px solid ${colors.accent}66`,
                  }}
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 우측 패널 — bullet 목록 */}
        <div
          style={{
            width: "60%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            padding: "32px 40px",
            gap: 14,
          }}
        >
          {bodyLines.map((line, idx) => {
            // 각 bullet item은 순서대로 약간 딜레이를 두고 등장
            const lineDelay = 8 + idx * 6;
            const lineOpacity = interpolate(
              frame,
              [lineDelay, lineDelay + 15],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );
            const lineTranslateX = interpolate(
              frame,
              [lineDelay, lineDelay + 15],
              [20, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );

            return (
              <div
                key={idx}
                style={{
                  opacity: lineOpacity,
                  transform: `translateX(${lineTranslateX}px)`,
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 12,
                }}
              >
                {/* bullet dot */}
                <div
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: colors.accent,
                    marginTop: 10,
                    flexShrink: 0,
                  }}
                />
                <EnhancedText
                  text={line}
                  keywords={slide.keywords}
                  accentColor={colors.accent}
                  baseStyle={{
                    color: colors.text,
                    fontSize: 22,
                    fontFamily: "Noto Sans KR, Malgun Gothic, sans-serif",
                    fontWeight: 400,
                    lineHeight: 1.6,
                    display: "block",
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
      <BottomBar colors={colors} channelName={channelName} />
    </AbsoluteFill>
  );
};

// ── 공통 바 컴포넌트 ─────────────────────────────────────────────

interface BarProps {
  colors: ThemeColorSet;
  channelName: string;
}

const TopBar: React.FC<BarProps> = ({ colors, channelName }) => (
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
);

const BottomBar: React.FC<BarProps> = ({ colors, channelName }) => (
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
);

// ── 자막 오버레이 ────────────────────────────────────────────────
// currentSec는 상위(F006VideoA)에서 전역 프레임 기반으로 직접 계산해 전달
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

export const F006VideoA: React.FC<F006VideoAProps> = ({
  slides,
  audio_path,
  srt_entries,
  channel_name,
  theme,
  transition_mode,
}) => {
  const { fps } = useVideoConfig();
  // 전역 프레임 — Audio 트랙과 동일한 타임라인 기준
  const globalFrame = useCurrentFrame();
  const globalCurrentSec = globalFrame / fps;

  const colors: ThemeColorSet = THEME_COLORS[theme] ?? THEME_COLORS["dark_blue"];

  if (slides.length === 0) {
    return <AbsoluteFill style={{ background: colors.bg1 }} />;
  }

  const slideDurationFrames = slides.map((s) => Math.ceil(s.duration_sec * fps));
  const totalFrames = slideDurationFrames.reduce((a, b) => a + b, 0);

  return (
    <AbsoluteFill>
      {audio_path && <Audio src={staticFile(audio_path)} />}

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
                  <SlideRendererA
                    slide={slideItem}
                    colors={colors}
                    channelName={channel_name}
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
