// 목적: Remotion Composition 등록 - F006Video / F006VideoB / F006VideoA / F006VideoC 컴포지션을 등록하고 메타데이터를 동적 계산한다.
import React from "react";
import type { ComponentType } from "react";
import { Composition, registerRoot } from "remotion";
import { F006Video, F006VideoProps } from "./F006Video";
import { F006VideoB, F006VideoBProps } from "./F006VideoB";
import { F006VideoA, F006VideoAProps } from "./F006VideoA";
import { F006VideoC, F006VideoCProps } from "./F006VideoC";

// Remotion Composition의 component prop은 ComponentType<Record<string, unknown>> 타입을 요구.
// 각 컴포넌트의 Props 인터페이스는 구체적으로 정의되어 있어 직접 할당이 불가능하므로
// ComponentType 캐스팅을 통해 타입 호환성을 확보한다.
type AnyComponentType = ComponentType<Record<string, unknown>>;

// ── 전환 프레임 수 상수 — 3개 컴포지션 공통 ──────────────────────
const TRANSITION_FRAMES = 12;

/**
 * 슬라이드 duration_sec 합계 기반 전체 프레임 계산.
 * TransitionSeries는 전환 구간만큼 슬라이드 구간을 겹치므로
 *   durationInFrames = totalSlideFrames - (slideCount - 1) * TRANSITION_FRAMES
 * slides는 런타임에 정확한 타입이 보장되므로 unknown[] 로 수신 후 내부에서 안전하게 접근한다.
 */
function calcDurationInFrames(slides: unknown[], fps: number): number {
  const totalSlideFrames = slides.reduce<number>((sum, s) => {
    const slide = s as Record<string, unknown>;
    const sec = typeof slide["duration_sec"] === "number" ? slide["duration_sec"] : 0;
    return sum + Math.ceil(sec * fps);
  }, 0);
  const overlapFrames = Math.max(0, slides.length - 1) * TRANSITION_FRAMES;
  return Math.max(totalSlideFrames - overlapFrames, fps);
}

// ── 기본 props — remotion studio 미리보기용 ───────────────────────

const defaultProps: F006VideoProps = {
  slides: [],
  audio_path: "",
  srt_entries: [],
  theme: "dark_blue",
  transition_mode: "auto",
};

const defaultPropsB: F006VideoBProps = {
  slides: [],
  audio_path: "",
  srt_entries: [],
  channel_name: "채널명",
  theme: "dark_blue",
  transition_mode: "auto",
};

const defaultPropsA: F006VideoAProps = {
  slides: [],
  audio_path: "",
  srt_entries: [],
  channel_name: "채널명",
  theme: "dark_blue",
  transition_mode: "auto",
};

const defaultPropsC: F006VideoCProps = {
  slides: [],
  audio_path: "",
  srt_entries: [],
  channel_name: "채널명",
  theme: "dark_blue",
  transition_mode: "auto",
};

// ── Remotion Root ─────────────────────────────────────────────────

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* F006Video — kenburns / png_slide 모드 (PNG 슬라이드 + Ken Burns 애니메이션) */}
      <Composition
        id="F006Video"
        component={F006Video as unknown as AnyComponentType}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultProps as unknown as Record<string, unknown>}
        calculateMetadata={({ props }) => {
          const slides = (props as unknown as F006VideoProps).slides;
          return { durationInFrames: calcDurationInFrames(slides, 30) };
        }}
      />

      {/* F006VideoB — video_bg 모드 (애니메이션 그라디언트 배경 + JSON 텍스트 렌더링) */}
      <Composition
        id="F006VideoB"
        component={F006VideoB as unknown as AnyComponentType}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultPropsB as unknown as Record<string, unknown>}
        calculateMetadata={({ props }) => {
          const slides = (props as unknown as F006VideoBProps).slides;
          return { durationInFrames: calcDurationInFrames(slides, 30) };
        }}
      />

      {/* F006VideoA — remotion_native 모드 (전체 네이티브 렌더링, 숫자 카운터 + 분할 레이아웃) */}
      <Composition
        id="F006VideoA"
        component={F006VideoA as unknown as AnyComponentType}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultPropsA as unknown as Record<string, unknown>}
        calculateMetadata={({ props }) => {
          const slides = (props as unknown as F006VideoAProps).slides;
          return { durationInFrames: calcDurationInFrames(slides, 30) };
        }}
      />

      {/* F006VideoC — fluid_bg 모드 (파티클 애니메이션 배경 + 글라스모피즘 카드) */}
      <Composition
        id="F006VideoC"
        component={F006VideoC as unknown as AnyComponentType}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={defaultPropsC as unknown as Record<string, unknown>}
        calculateMetadata={({ props }) => {
          const slides = (props as unknown as F006VideoCProps).slides;
          return { durationInFrames: calcDurationInFrames(slides, 30) };
        }}
      />
    </>
  );
};

// Remotion CLI 진입점 — registerRoot() 필수
registerRoot(RemotionRoot);
