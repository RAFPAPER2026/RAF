import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useChartPalette } from "../../utils/chartTheme";
import { ChartTooltip, rechartsTooltipRows } from "./ChartTooltip";

export interface BarDatum {
  name: string;
  key: string;
  value: number; // 0..100
  colorIndex: number; // 模型在原列表中的序号（颜色跟随实体，不随排序）
}

interface ScoreBarChartProps {
  data: BarDatum[];
  height?: number;
  unit?: string;
}

/** 柱状图「模型效果分对比」：逐格着色（颜色跟随模型身份），条形 ≤24px */
export function ScoreBarChart({ data, height = 280, unit = "%" }: ScoreBarChartProps) {
  const p = useChartPalette();

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="30%">
          <CartesianGrid stroke={p.grid} vertical={false} strokeWidth={1} />
          <XAxis
            dataKey="name"
            tick={{ fill: p.ink2, fontSize: 12 }}
            axisLine={{ stroke: p.baseline }}
            tickLine={false}
            interval={0}
            tickFormatter={(v: string) => (v.length > 14 ? `${v.slice(0, 12)}…` : v)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: p.ink3, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${v}%`}
            width={44}
          />
          <Tooltip
            cursor={{ fill: p.grid, opacity: 0.35 }}
            content={({ active, payload, label }) =>
              active && payload ? (
                <ChartTooltip
                  title={String(label ?? "")}
                  rows={rechartsTooltipRows(payload, (v) => `${v.toFixed(1)}${unit}`)}
                />
              ) : null
            }
          />
          <Bar dataKey="value" name="效果分" maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.key} fill={p.series(d.colorIndex)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
