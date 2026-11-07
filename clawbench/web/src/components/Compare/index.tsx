import { useState } from "react";
import { useComparison } from "../../hooks/useComparison";
import { parseModelName } from "../../utils/model";
import { fmtScore, fmtRate } from "../../utils/format";
import { DIMENSION_LABELS } from "../../utils/constants";
import { useChartPalette } from "../../utils/chartTheme";

const DIMENSIONS = [
  "primary_scenario",
  "secondary_scenario",
  "ability_category",
  "difficulty",
  "complexity",
];

/** 模型对比占位页：模型 × 类别得分表 */
export default function Compare() {
  const p = useChartPalette();
  const [dimension, setDimension] = useState("primary_scenario");
  const { data: cmp, loading, error, refresh } = useComparison(dimension);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-lg font-semibold text-ink">模型对比</h1>
        <select
          value={dimension}
          onChange={(e) => setDimension(e.target.value)}
          className="rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-none"
        >
          {DIMENSIONS.map((d) => (
            <option key={d} value={d}>
              {DIMENSION_LABELS[d] ?? d}
            </option>
          ))}
        </select>
      </div>

      {error ? (
        <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical">
          对比数据加载失败：{error}
          <button type="button" onClick={refresh} className="ml-3 underline decoration-dotted underline-offset-2">
            重试
          </button>
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs text-ink-3">
              <th className="px-4 py-2.5 font-medium">模型</th>
              {(cmp?.categories ?? []).map((c) => (
                <th key={c} className="px-4 py-2.5 font-medium">
                  {c}
                </th>
              ))}
              <th className="px-4 py-2.5 font-medium">总体</th>
              <th className="px-4 py-2.5 font-medium">通过率</th>
            </tr>
          </thead>
          <tbody>
            {cmp?.models.map((m, i) => (
              <tr key={m.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3">
                  <span className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: p.series(i) }}
                      aria-hidden
                    />
                    <span className="font-medium text-ink">{m.name || parseModelName(m.id)}</span>
                  </span>
                </td>
                {(cmp?.categories ?? []).map((c) => (
                  <td key={c} className="tnum px-4 py-3 text-ink-2">
                    {m.scores[c] !== undefined ? fmtScore(m.scores[c]) : "—"}
                  </td>
                ))}
                <td className="tnum px-4 py-3 font-semibold text-ink">{fmtScore(m.overall)}</td>
                <td className="tnum px-4 py-3 text-ink-2">{fmtRate(m.pass_rate)}</td>
              </tr>
            ))}
            {!loading && !cmp ? (
              <tr>
                <td colSpan={99} className="px-4 py-8 text-center text-sm text-ink-3">
                  暂无对比数据
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        {loading ? (
          <div className="py-6 text-center text-xs text-ink-3">加载中…</div>
        ) : null}
      </div>
    </div>
  );
}
