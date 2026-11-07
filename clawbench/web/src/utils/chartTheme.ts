import { useTheme } from "../context/ThemeContext";

/** 分类色 8 槽（dataviz skill 默认调色板，浅色） */
export const SERIES_LIGHT = [
  "#2a78d6", // blue
  "#eb6834", // orange
  "#1baf7a", // aqua
  "#eda100", // yellow
  "#e87ba4", // magenta
  "#008300", // green
  "#4a3aa7", // violet
  "#e34948", // red
];

/** 分类色 8 槽（深色表面步进） */
export const SERIES_DARK = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
];

/** 蓝色序数渐变（浅端 → 深端；浅色下从 step250 起，保证 ≥2:1） */
export const ORDINAL_BLUE = [
  "#86b6ef",
  "#6da7ec",
  "#5598e7",
  "#3987e5",
  "#2a78d6",
  "#256abf",
  "#1c5cab",
  "#184f95",
];

/** 状态色（固定） */
export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

export function seriesColor(i: number, dark: boolean): string {
  const arr = dark ? SERIES_DARK : SERIES_LIGHT;
  return arr[((i % arr.length) + arr.length) % arr.length];
}

export interface ChartPalette {
  dark: boolean;
  series: (i: number) => string;
  ordinal: string[];
  status: typeof STATUS;
  grid: string;
  baseline: string;
  ink: string;
  ink2: string;
  ink3: string;
  surface: string;
  successText: string;
}

/** 供 recharts 使用的调色板（随主题切换解析为具体 hex） */
export function useChartPalette(): ChartPalette {
  const { dark } = useTheme();
  return {
    dark,
    series: (i: number) => seriesColor(i, dark),
    ordinal: ORDINAL_BLUE,
    status: STATUS,
    grid: dark ? "#2c2c2a" : "#e1e0d9",
    baseline: dark ? "#383835" : "#c3c2b7",
    ink: dark ? "#ffffff" : "#0b0b0b",
    ink2: dark ? "#c3c2b7" : "#52514e",
    ink3: "#898781",
    surface: dark ? "#1a1a19" : "#fcfcfb",
    successText: dark ? "#0ca30c" : "#006300",
  };
}
