/** 分数 0..1 → 百分比字符串（1 位小数） */
export function fmtScore(v: number | null | undefined, suffix = "%"): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(1)}${suffix}`;
}

/** 已是百分数（0-100）的比率 → 百分比字符串（pass_rate 等，不再乘 100） */
export function fmtRate(v: number | null | undefined, suffix = "%"): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)}${suffix}`;
}

/** 分数 0..1 → 整数百分比（图表轴/徽标用） */
export function fmtPctInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${Math.round(v * 100)}%`;
}

/** 千分位整数 */
export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("zh-CN");
}

/** 时长（秒）→ 可读字符串 */
export function fmtDuration(sec: number | null | undefined): string {
  if (sec === null || sec === undefined || Number.isNaN(sec)) return "—";
  const s = Math.abs(sec);
  if (s < 60) return `${sec.toFixed(1)}s`;
  if (s < 3600) return `${(sec / 60).toFixed(1)}m`;
  return `${(sec / 3600).toFixed(2)}h`;
}

/** Token 数 → 紧凑单位 */
export function fmtTokens(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toLocaleString("zh-CN");
}

/** 成本（美元）→ 紧凑字符串 */
export function fmtCost(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (v === 0) return "$0";
  if (v < 0.01) return `$${v.toExponential(2)}`;
  return `$${v.toFixed(4)}`;
}

/** 百分比（0..1）→ 0..100 数字（1 位小数） */
export function toPercent(v: number | null | undefined): number {
  if (v === null || v === undefined || Number.isNaN(v)) return 0;
  return v * 100;
}
