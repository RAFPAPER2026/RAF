import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useChartPalette } from "../../utils/chartTheme";
import { ChartTooltip, rechartsTooltipRows } from "./ChartTooltip";

export interface PieDatum {
  name: string;
  value: number;
  color: string; // 直接给定（序数渐变等）
}

interface SimplePieChartProps {
  data: PieDatum[];
  height?: number;
  showLegend?: boolean;
}

/** 饼图：分类/序数着色、逐块 tooltip、直接标签（值不入图例框） */
export function SimplePieChart({ data, height = 260, showLegend = true }: SimplePieChartProps) {
  const p = useChartPalette();
  const total = data.reduce((a, b) => a + b.value, 0);

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius="55%"
            outerRadius="82%"
            paddingAngle={2}
            strokeWidth={2}
            stroke={p.surface}
            isAnimationActive={false}
            label={(props: { name?: string; value?: number }) => {
              const v = props.value ?? 0;
              const pct = total > 0 ? ((v / total) * 100).toFixed(0) : "0";
              return `${props.name ?? ""} ${pct}%`;
            }}
            labelLine={{ stroke: p.baseline, strokeWidth: 1 }}
          >
            {data.map((d) => (
              <Cell key={d.name} fill={d.color} />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) =>
              active && payload ? (
                <ChartTooltip
                  rows={rechartsTooltipRows(payload, (v) => `${v.toLocaleString("zh-CN")} 例`)}
                />
              ) : null
            }
          />
          {showLegend && data.length > 0 ? (
            <Legend wrapperStyle={{ fontSize: 12, color: p.ink2 }} />
          ) : null}
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
