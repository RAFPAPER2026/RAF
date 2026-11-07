import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TaskScore } from "../../types";
import { computeTagPassRates, computeTopTags } from "../../rubric/tags";
import { useChartPalette } from "../../utils/chartTheme";
import { ChartTooltip, rechartsTooltipRows } from "../charts/ChartTooltip";

interface TagBarChartProps {
  tasks: TaskScore[];
  height?: number;
}

/** 「Rubric标签通过率」横向条形图：按叶子覆盖度 top-12 标签，条形按通过率排序 */
export function TagBarChart({ tasks, height = 320 }: TagBarChartProps) {
  const p = useChartPalette();

  const rows = useMemo(() => {
    const tags = computeTopTags(tasks, 12);
    const rates = computeTagPassRates(tasks, tags);
    return tags
      .map((tag) => ({
        tag,
        rate: rates[tag]?.rate ?? 0,
        passed: rates[tag]?.passed ?? 0,
        total: rates[tag]?.total ?? 0,
      }))
      .sort((a, b) => a.rate - b.rate || a.tag.localeCompare(b.tag)); // 升序 → 最优在顶部
  }, [tasks]);

  if (rows.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-ink-3">
        暂无标签数据
      </div>
    );
  }

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 24, left: 8, bottom: 0 }} barCategoryGap="28%">
          <CartesianGrid stroke={p.grid} horizontal={false} strokeWidth={1} />
          <XAxis
            type="number"
            domain={[0, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fill: p.ink3, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            type="category"
            dataKey="tag"
            width={110}
            tick={{ fill: p.ink2, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: p.grid, opacity: 0.35 }}
            content={({ active, payload }) =>
              active && payload ? (
                <ChartTooltip
                  rows={rechartsTooltipRows(payload, (v) => `${(v * 100).toFixed(1)}%`)}
                />
              ) : null
            }
          />
          <Bar dataKey="rate" name="通过率" maxBarSize={18} radius={[0, 4, 4, 0]} fill={p.series(0)} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
