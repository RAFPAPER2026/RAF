import type { ReactNode } from "react";

type BadgeTone = "good" | "bad" | "warn" | "neutral" | "info";

const TONE_STYLES: Record<BadgeTone, { text: string; dot: string; bg: string }> = {
  good: { text: "text-good", dot: "bg-good", bg: "bg-good/10 border-good/25" },
  bad: { text: "text-critical", dot: "bg-critical", bg: "bg-critical/10 border-critical/25" },
  warn: { text: "text-warn", dot: "bg-warn", bg: "bg-warn/10 border-warn/25" },
  neutral: { text: "text-ink-2", dot: "bg-ink-3", bg: "bg-surface-2 border-line" },
  info: { text: "text-series-1", dot: "bg-series-1", bg: "bg-series-1/10 border-series-1/25" },
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  title?: string;
}

/** 状态徽标：状态色 + 图标点 + 文字（状态色从不单独传达含义） */
export function Badge({ tone = "neutral", children, title }: BadgeProps) {
  const s = TONE_STYLES[tone];
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${s.text} ${s.bg}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
      {children}
    </span>
  );
}
