import type { ReactNode } from "react";

interface TooltipRow {
  name?: ReactNode;
  value: ReactNode;
  color?: string;
}

interface ChartTooltipProps {
  title?: ReactNode;
  rows: TooltipRow[];
}

/** 统一图表 tooltip：值在前（Strong），系列名次之（Secondary），系列键为短线 */
export function ChartTooltip({ title, rows }: ChartTooltipProps) {
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      {title !== undefined && title !== null ? (
        <div className="mb-1 font-medium text-ink-2">{title}</div>
      ) : null}
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2 py-0.5">
          {r.color ? (
            <span
              className="inline-block h-[3px] w-3 rounded-full"
              style={{ background: r.color }}
              aria-hidden
            />
          ) : null}
          <span className="text-ink-2">{r.name}</span>
          <span className="tnum font-semibold text-ink">{r.value}</span>
        </div>
      ))}
    </div>
  );
}

/** recharts payload → rows 适配器（值以格式化函数输出） */
export function rechartsTooltipRows(
  payload: unknown,
  fmt?: (v: number, name: string) => string,
): TooltipRow[] {
  const list = Array.isArray(payload) ? (payload as Array<{ name?: string; value?: unknown; color?: string; fill?: string }>) : [];
  return list.map((p) => {
    const num = typeof p.value === "number" ? p.value : NaN;
    return {
      name: p.name,
      value: fmt ? fmt(num, p.name ?? "") : (p.value as ReactNode),
      color: p.color ?? p.fill,
    };
  });
}
