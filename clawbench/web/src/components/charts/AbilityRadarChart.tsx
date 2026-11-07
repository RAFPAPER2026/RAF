import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useChartPalette } from "../../utils/chartTheme";
import { ChartTooltip, rechartsTooltipRows } from "./ChartTooltip";

export interface RadarSeries {
  key: string; // 模型 id
  name: string;
  colorIndex: number;
  values: Record<string, number>; // 类别 → 0..100
}

interface AbilityRadarChartProps {
  categories: string[];
  series: RadarSeries[];
  height?: number;
}

/** 雷达图「按能力项统计平均得分」：每模型一个多边形，系列色 2px 描边 + 10% 面积染色 */
export function AbilityRadarChart({ categories, series, height = 300 }: AbilityRadarChartProps) {
  const p = useChartPalette();

  const data = categories.map((cat) => {
    const row: Record<string, string | number> = { category: cat };
    for (const s of series) row[s.key] = s.values[cat] ?? 0;
    return row;
  });

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="68%">
          <PolarGrid stroke={p.grid} strokeWidth={1} />
          <PolarAngleAxis
            dataKey="category"
            tick={{ fill: p.ink2, fontSize: 11 }}
            tickLine={false}
          />
          <PolarRadiusAxis
            domain={[0, 100]}
            angle={90}
            tick={{ fill: p.ink3, fontSize: 10 }}
            axisLine={false}
            tickCount={5}
          />
          <Tooltip
            content={({ active, payload, label }) =>
              active && payload ? (
                <ChartTooltip
                  title={String(label ?? "")}
                  rows={rechartsTooltipRows(payload, (v) => `${v.toFixed(1)}%`)}
                />
              ) : null
            }
          />
          {series.map((s) => (
            <Radar
              key={s.key}
              name={s.name}
              dataKey={s.key}
              stroke={p.series(s.colorIndex)}
              strokeWidth={2}
              fill={p.series(s.colorIndex)}
              fillOpacity={0.1}
              dot={false}
              isAnimationActive={false}
            />
          ))}
          {series.length >= 2 ? (
            <Legend
              iconType="line"
              wrapperStyle={{ fontSize: 12, color: p.ink2 }}
            />
          ) : null}
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
