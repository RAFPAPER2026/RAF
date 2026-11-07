import type { ReactNode } from "react";

interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: string;
}

/** 统计卡片：label（句首大写，无尾冒号）· value（Sans semibold 大号数字）· sub（可选） */
export function StatCard({ label, value, sub, accent }: StatCardProps) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-sm">
      <div className="text-xs text-ink-2">{label}</div>
      <div
        className="mt-1 text-3xl font-semibold leading-tight"
        style={accent ? { color: accent } : undefined}
      >
        {value}
      </div>
      {sub ? <div className="mt-1 text-xs text-ink-3">{sub}</div> : null}
    </div>
  );
}
