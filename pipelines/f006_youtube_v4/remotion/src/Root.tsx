// 목적: Remotion Composition 등록 - F006Video 컴포지션을 등록하고 메타데이터를 동적 계산한다.
import { Composition, registerRoot } from "remotion";
import { F006Video, F006VideoProps } from "./F006Video";

// 기본 props - remotion studio에서 미리보기용
const defaultProps: F006VideoProps = {
  slides: [],
  audio_path: "",
  srt_entries: [],
  theme: "dark_blue",
  transition_mode: "auto",
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="F006Video"
      component={F006Video}
      fps={30}
      width={1280}
      height={720}
      defaultProps={defaultProps}
      calculateMetadata={({ props }) => {
        const fps = 30;
        // 전환 프레임 수 - 슬라이드당 약 0.4초(12프레임)
        const TRANSITION_FRAMES = 12;
        const totalSlideFrames = props.slides.reduce(
          (sum, s) => sum + Math.ceil(s.duration_sec * fps),
          0
        );
        const transitionCount = Math.max(0, props.slides.length - 1);
        const durationInFrames = totalSlideFrames + transitionCount * TRANSITION_FRAMES;
        return { durationInFrames: Math.max(durationInFrames, fps) };
      }}
    />
  );
};

// Remotion CLI 진입점 — registerRoot() 필수
registerRoot(RemotionRoot);
