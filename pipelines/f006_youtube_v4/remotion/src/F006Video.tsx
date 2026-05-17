// 목적: F006 메인 동영상 컴포넌트 - PNG 슬라이드 + 오디오 + 자막 + 전환 효과 합성
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
import { getTheme } from "./themes";

// ── Props 타입 ──────────────────────────────────────────────────────

export interface SlideData {
  /** 슬라이드 번호 (1-based) */
  slide_no: number;
  /** 슬라이드 타입 */
  type: "title" | "content" | "summary" | "quote";
  /** PNG 파일 절대 경로 (Windows: E:/Dash/storage/...) */
  file_path: string;
  /** 이 슬라이드의 표시 시간(초) */
  duration_sec: number;
}

export interface SRTEntry {
  index: number;
  /** 자막 시작 시간(초) */
  start_sec: number;
  /** 자막 종료 시간(초) */
  end_sec: number;
  text: string;
}

export interface F006VideoProps {
  slides: SlideData[];
  /** 오디오 파일 절대 경로 (mp3) */
  audio_path: string;
  /** 파싱된 SRT 자막 항목 목록 */
  srt_entries: SRTEntry[];
  /** 테마 이름 (dark_blue / warm_gray / clean_white) */
  theme: string;
  /** 전환 모드 (auto / fade_only / slide_only) */
  transition_mode: string;
}

// ── 전환 효과 선택 ────────────────────────────────────────────────

const TRANSITION_FRAMES = 12;

function getTransitionPresentation(
  fromType: string,
  toType: string,
  mode: string
) {
  if (mode === "fade_only") return fade();
  if (mode === "slide_only") return slide({ direction: "from-right" });

  // auto 모드 - 슬라이드 타입별 다른 전환
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

// ── 슬라이드 렌더러 ──────────────────────────────────────────────

interface SlideRendererProps {
  filePath: string;
  slideType: string;
  durationInFrames: number;
}

const SlideRenderer: React.FC<SlideRendererProps> = ({
  filePath,
  slideType,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  // getTheme은 현재 사용되지 않지만 테마 확장을 위해 import 유지
  void getTheme;

  // 등장 애니메이션 — 처음 8프레임만 opacity 0→1
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Ken Burns 연속 애니메이션 — 슬라이드 전체 구간(durationInFrames) 동안 천천히 움직임
  // title: 천천히 줌인 (1.0 → 1.08)
  // quote: 천천히 줌아웃 (1.08 → 1.0)
  // content / summary: 고정 scale 1.03
  const scale =
    slideType === "title"
      ? interpolate(frame, [0, durationInFrames], [1.0, 1.08], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : slideType === "quote"
      ? interpolate(frame, [0, durationInFrames], [1.08, 1.0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1.03;

  // 패닝 애니메이션 — 슬라이드 전체 구간 연속 이동
  // content: 오른쪽→왼쪽 (20px → -20px)
  // summary: 왼쪽→오른쪽 (-15px → 15px)
  // title / quote: 패닝 없음
  const translateX =
    slideType === "content"
      ? interpolate(frame, [0, durationInFrames], [20, -20], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : slideType === "summary"
      ? interpolate(frame, [0, durationInFrames], [-15, 15], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 0;

  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <Img
        src={staticFile(filePath)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          opacity,
          transform: `scale(${scale}) translateX(${translateX}px)`,
        }}
      />
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

  // 자막 말미 fade out (0.3초)
  const endSec = activeEntry.end_sec;
  const fadeStartSec = endSec - 0.3;
  const subtitleOpacity =
    currentSec >= fadeStartSec
      ? interpolate(
          currentSec,
          [fadeStartSec, endSec],
          [1, 0],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
        )
      : 1;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: 60,
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

export const F006Video: React.FC<F006VideoProps> = ({
  slides,
  audio_path,
  srt_entries,
  theme,
  transition_mode,
}) => {
  const { fps } = useVideoConfig();
  // theme 변수는 현재 SlideRenderer에 전달되지 않지만 테마 확장을 위해 선언 유지
  void theme;

  if (slides.length === 0) {
    return <AbsoluteFill style={{ background: "#000" }} />;
  }

  // 각 슬라이드의 durationInFrames 계산
  const slideDurationFrames = slides.map((s) => Math.ceil(s.duration_sec * fps));

  // 슬라이드별 타임라인 시작 시간(초) 계산 - 자막 동기화용
  // TransitionSeries는 전환 구간이 겹치므로 실제 시작 오프셋 = 이전 슬라이드들의 합 - 겹친 전환 구간
  const slideStartSecs: number[] = [];
  let accFrames = 0;
  for (let i = 0; i < slides.length; i++) {
    slideStartSecs.push(accFrames / fps);
    accFrames += slideDurationFrames[i];
    if (i < slides.length - 1) accFrames -= TRANSITION_FRAMES; // 전환 오버랩
  }

  return (
    <AbsoluteFill style={{ background: "#000" }}>
      {/* 오디오 트랙 — staticFile()로 --public-dir 기준 상대 경로 접근 */}
      {audio_path && <Audio src={staticFile(audio_path)} />}

      {/* 슬라이드 전환 시리즈 */}
      <TransitionSeries>
        {slides.map((slideItem, i) => {
          const nextSlide = slides[i + 1];
          const fromType = slideItem.type;
          const toType = nextSlide?.type ?? "";

          return (
            <React.Fragment key={slideItem.slide_no}>
              {/* 슬라이드 시퀀스 */}
              <TransitionSeries.Sequence
                durationInFrames={slideDurationFrames[i]}
              >
                <AbsoluteFill>
                  <SlideRenderer
                    filePath={slideItem.file_path}
                    slideType={slideItem.type}
                    durationInFrames={slideDurationFrames[i]}
                  />
                  <SubtitleOverlay
                    srtEntries={srt_entries}
                    timelineOffsetSec={slideStartSecs[i]}
                  />
                </AbsoluteFill>
              </TransitionSeries.Sequence>

              {/* 슬라이드 사이 전환 */}
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
    </AbsoluteFill>
  );
};
