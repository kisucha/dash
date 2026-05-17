// 목적: F006 Remotion 영상 테마 정의 - dark_blue/warm_gray/clean_white 3종

export interface Theme {
  background: string;
  headerBg: string;
  titleColor: string;
  bodyColor: string;
  accentColor: string;
  subtitleBg: string;
  subtitleColor: string;
}

const darkBlue: Theme = {
  background: "#0D1B2A",
  headerBg: "#1a2d42",
  titleColor: "#E8F4FD",
  bodyColor: "#CBD5E1",
  accentColor: "#4FC3F7",
  subtitleBg: "rgba(0,0,0,0.65)",
  subtitleColor: "#FFFFFF",
};

const warmGray: Theme = {
  background: "#1C1C1E",
  headerBg: "#2C2C2E",
  titleColor: "#F5F5F0",
  bodyColor: "#D4D4D0",
  accentColor: "#FFB74D",
  subtitleBg: "rgba(0,0,0,0.65)",
  subtitleColor: "#FFFFFF",
};

const cleanWhite: Theme = {
  background: "#FAFAFA",
  headerBg: "#EFEFEF",
  titleColor: "#1A1A2E",
  bodyColor: "#333344",
  accentColor: "#3F51B5",
  subtitleBg: "rgba(0,0,0,0.72)",
  subtitleColor: "#FFFFFF",
};

const THEMES: Record<string, Theme> = {
  dark_blue: darkBlue,
  warm_gray: warmGray,
  clean_white: cleanWhite,
};

export function getTheme(name: string): Theme {
  return THEMES[name] ?? darkBlue;
}
