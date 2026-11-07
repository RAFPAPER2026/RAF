import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useModels } from "../../hooks/useModels";
import { useDatasetDistribution } from "../../hooks/useDatasetDistribution";
import { useComparison } from "../../hooks/useComparison";
import { useAllModelTasks } from "../../hooks/useAllModelTasks";
import { StatCard } from "../common/StatCard";
import { SectionCard } from "../common/SectionCard";
import { Badge } from "../common/Badge";
import { ScoreBarChart } from "../charts/ScoreBarChart";
import type { BarDatum } from "../charts/ScoreBarChart";
import { AbilityRadarChart } from "../charts/AbilityRadarChart";
import type { RadarSeries } from "../charts/AbilityRadarChart";
import { SimplePieChart } from "../charts/SimplePieChart";
import type { PieDatum } from "../charts/SimplePieChart";
import { CrossFilterPanel } from "../CrossFilterPanel";
import type { FilterState } from "../CrossFilterPanel";
import { parseModelName, getModelGroup } from "../../utils/model";
import { taskMatchesAllFilters } from "../../utils/filterUtils";
import { fmtScore, fmtDuration, fmtTokens, toPercent } from "../../utils/format";
import { DIFFICULTY_LABELS, DIFFICULTY_ORDER, RANK_COLORS } from "../../utils/constants";
import { ORDINAL_BLUE, useChartPalette } from "../../utils/chartTheme";
import type { ModelInfo } from "../../types";

/** 难度序数色（浅端→深端，单一蓝色渐变） */
function difficultyColor(key: string): string {
  const idx = DIFFICULTY_ORDER.indexOf(key);
  if (idx < 0) return "#898781"; // 未知值原样显示、灰色
  return ORDINAL_BLUE[Math.min(idx, ORDINAL_BLUE.length - 1)];
}

interface LeaderRow {
  id: string;
  name: string;
  group: string;
  score: number | null;
  duration: number;
  inputTokens: number;
  outputTokens: number;
  runCount: number;
  index: number;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const p = useChartPalette();

  const { data: models, loading: modelsLoading, error: modelsError, refresh: refreshModels } = useModels();
  const { data: dist } = useDatasetDistribution();
  const { data: abilityCmp } = useComparison("ability_category");
  const modelIds = useMemo(() => (models ?? []).map((m) => m.id), [models]);
  const { data: allTasks } = useAllModelTasks(modelIds, "average");

  const [filters, setFilters] = useState<FilterState>({});
  const [radarModelFilter, setRadarModelFilter] = useState<string>("all");

  const hasFilters = useMemo(
    () => Object.values(filters).some((v) => (v?.length ?? 0) > 0),
    [filters],
  );

  /* ---------------- StatCards ---------------- */
  const modelCount = models?.length ?? 0;
  const totalTasks = useMemo(
    () => Math.max(0, ...(models ?? []).map((m) => m.stats.total_tasks ?? 0)),
    [models],
  );
  const topScore = useMemo(() => {
    const scores = (models ?? []).map((m) => m.stats.average_score).filter((s): s is number => s !== null && s !== undefined);
    return scores.length > 0 ? Math.max(...scores) : null;
  }, [models]);
  const avgScore = useMemo(() => {
    const scores = (models ?? []).map((m) => m.stats.average_score).filter((s): s is number => s !== null && s !== undefined);
    return scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
  }, [models]);

  /* ---------------- 柱状图：模型效果分对比 ---------------- */
  const barData = useMemo<BarDatum[]>(() => {
    const list = [...(models ?? [])];
    const sorted = list
      .map((m, i) => ({ m, i }))
      .sort((a, b) => (b.m.stats.average_score ?? -1) - (a.m.stats.average_score ?? -1));
    return sorted.map(({ m, i }) => ({
      name: parseModelName(m.id),
      key: m.id,
      value: toPercent(m.stats.average_score),
      colorIndex: i, // 颜色跟随模型在原列表的序号
    }));
  }, [models]);

  /* ---------------- 雷达图：按能力项统计平均得分 ---------------- */
  const radarData = useMemo<RadarSeries[]>(() => {
    if (!abilityCmp) return [];
    const showAll = radarModelFilter === "all";
    return abilityCmp.models
      .map((m, i) => ({
        key: m.id,
        name: m.name || parseModelName(m.id),
        colorIndex: i,
        values: m.scores,
      }))
      .filter((s) => showAll || s.key === radarModelFilter);
  }, [abilityCmp, radarModelFilter]);

  /* ---------------- 饼图 ---------------- */
  const difficultyData = useMemo<PieDatum[]>(() => {
    const d = dist?.difficulty ?? {};
    const ordered = DIFFICULTY_ORDER.filter((k) => (d[k] ?? 0) > 0);
    const rest = Object.keys(d).filter((k) => !DIFFICULTY_ORDER.includes(k));
    const out: PieDatum[] = [
      ...ordered.map((k) => ({
        name: DIFFICULTY_LABELS[k] ?? k,
        value: d[k] ?? 0,
        color: difficultyColor(k),
      })),
      ...rest.map((k) => ({ name: k, value: d[k] ?? 0, color: difficultyColor(k) })),
    ];
    return out.filter((x) => x.value > 0);
  }, [dist]);

  const complexityData = useMemo<PieDatum[]>(() => {
    const c = dist?.complexity ?? {};
    const entries = Object.entries(c)
      .map(([k, v]) => ({ k, v: v ?? 0 }))
      .filter((x) => x.v > 0);
    const isNum = (s: string) => /^\d+$/.test(s);
    entries.sort((a, b) => {
      const an = isNum(a.k) ? Number(a.k) : Infinity;
      const bn = isNum(b.k) ? Number(b.k) : Infinity;
      return an - bn || a.k.localeCompare(b.k);
    });
    let ci = 0;
    return entries.map(({ k, v }) => ({
      name: `${k}级`,
      value: v,
      color: isNum(k)
        ? (() => {
            const idx = Number(k) - 1;
            if (idx >= 0 && idx < ORDINAL_BLUE.length) return ORDINAL_BLUE[idx];
            const i = Math.max(0, Math.min(ORDINAL_BLUE.length - 1, ci++));
            return ORDINAL_BLUE[i];
          })()
        : "#898781",
    }));
  }, [dist]);

  /* ---------------- 排行榜 ---------------- */
  const leaderRows = useMemo<LeaderRow[]>(() => {
    if (!models) return [];
    const build = (m: ModelInfo, i: number): LeaderRow => {
      const name = parseModelName(m.id);
      if (!hasFilters) {
        return {
          id: m.id,
          name,
          group: getModelGroup(m.id),
          score: m.stats.average_score,
          duration: m.stats.total_duration ?? 0,
          inputTokens: m.stats.total_input_tokens ?? 0,
          outputTokens: m.stats.total_output_tokens ?? 0,
          runCount: m.runs?.length ?? 0,
          index: i,
        };
      }
      const tasks = (allTasks ?? {})[m.id] ?? [];
      const matched = tasks.filter((t) => taskMatchesAllFilters(t, filters));
      const scores = matched
        .map((t) => t.score)
        .filter((s): s is number => s !== null && s !== undefined);
      return {
        id: m.id,
        name,
        group: getModelGroup(m.id),
        score: scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
        duration: matched.reduce((a, t) => a + (t.duration ?? 0), 0),
        inputTokens: matched.reduce((a, t) => a + (t.input_tokens ?? 0), 0),
        outputTokens: matched.reduce((a, t) => a + (t.output_tokens ?? 0), 0),
        runCount: m.runs?.length ?? 0,
        index: i,
      };
    };
    return models
      .map(build)
      .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.id.localeCompare(b.id));
  }, [models, hasFilters, filters, allTasks]);

  const empty = !modelsLoading && !modelsError && modelCount === 0;

  return (
    <div className="space-y-4">
      {/* 错误提示 */}
      {modelsError ? (
        <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical">
          后端数据加载失败：{modelsError}
          <button
            type="button"
            onClick={refreshModels}
            className="ml-3 underline decoration-dotted underline-offset-2 hover:no-underline"
          >
            重试
          </button>
        </div>
      ) : null}
      {empty ? (
        <div className="rounded-xl border border-line bg-surface px-4 py-8 text-center text-sm text-ink-2">
          暂无评测数据。请确认后端（端口 4999）已启动并完成至少一轮评测。
        </div>
      ) : null}

      {/* 1. 统计卡片 */}
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard label="评测模型数" value={modelsLoading ? "…" : modelCount} />
        <StatCard label="总任务数" value={modelsLoading ? "…" : totalTasks.toLocaleString("zh-CN")} />
        <StatCard
          label="最高得分"
          value={fmtScore(topScore)}
          accent={topScore !== null && topScore >= 0.75 ? p.status.good : topScore !== null ? p.status.serious : undefined}
        />
        <StatCard
          label="平均得分"
          value={fmtScore(avgScore)}
          accent={avgScore !== null && avgScore >= 0.75 ? p.status.good : avgScore !== null ? p.status.serious : undefined}
        />
      </div>

      {/* 2. 2×2 图表 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SectionCard title="模型效果分对比" subtitle="各模型平均效果分（%）">
          {barData.length > 0 ? <ScoreBarChart data={barData} /> : <ChartEmpty />}
        </SectionCard>

        <SectionCard
          title="按能力项统计平均得分"
          subtitle="能力维度雷达图"
          right={
            <select
              value={radarModelFilter}
              onChange={(e) => setRadarModelFilter(e.target.value)}
              className="rounded-md border border-line bg-surface-2 px-2 py-1 text-xs text-ink-2 outline-none"
            >
              <option value="all">全部模型</option>
              {(models ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {parseModelName(m.id)}
                </option>
              ))}
            </select>
          }
        >
          {radarData.length > 0 && (abilityCmp?.categories.length ?? 0) > 0 ? (
            <AbilityRadarChart categories={abilityCmp!.categories} series={radarData} />
          ) : (
            <ChartEmpty />
          )}
        </SectionCard>

        <SectionCard title="难度等级分布" subtitle="数据集难度分布（简单 / 中等 / 困难）">
          {difficultyData.length > 0 ? (
            <SimplePieChart data={difficultyData} />
          ) : (
            <ChartEmpty />
          )}
        </SectionCard>

        <SectionCard title="复杂度等级分布" subtitle="数据集复杂度分布（N级）">
          {complexityData.length > 0 ? (
            <SimplePieChart data={complexityData} />
          ) : (
            <ChartEmpty />
          )}
        </SectionCard>
      </div>

      {/* 3. 排行榜 */}
      <div className="space-y-3">
        <CrossFilterPanel tasks={allTasks ? Object.values(allTasks).flat() : []} filters={filters} onChange={setFilters} />

        <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-ink-3">
                <th className="px-4 py-2.5 font-medium">排名</th>
                <th className="px-4 py-2.5 font-medium">模型</th>
                <th className="px-4 py-2.5 font-medium">效果分</th>
                <th className="px-4 py-2.5 font-medium">总耗时</th>
                <th className="px-4 py-2.5 font-medium">总输入Token</th>
                <th className="px-4 py-2.5 font-medium">总输出Token</th>
                <th className="px-4 py-2.5 font-medium">详情</th>
              </tr>
            </thead>
            <tbody>
              {leaderRows.map((row, i) => (
                <tr
                  key={row.id}
                  onClick={() => navigate(`/model/${row.id}`)}
                  className="cursor-pointer border-b border-line/60 transition-colors last:border-0 hover:bg-surface-2"
                >
                  <td className="px-4 py-3">
                    {i < 3 && row.score !== null ? (
                      <span
                        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white"
                        style={{ background: RANK_COLORS[i] }}
                      >
                        {i + 1}
                      </span>
                    ) : (
                      <span className="tnum text-xs text-ink-3">{i + 1}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium text-ink">{row.name}</span>
                      <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-3">
                        {row.group}
                      </span>
                      {row.runCount > 1 ? (
                        <Badge tone="info">{row.runCount} runs</Badge>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {row.score !== null ? (
                      <span className="flex items-center gap-1.5">
                        <span
                          className={`h-2 w-2 rounded-full ${
                            row.score >= 0.75
                              ? "bg-good"
                              : row.score >= 0.5
                                ? "bg-warn"
                                : "bg-critical"
                          }`}
                          aria-hidden
                        />
                        <span className="tnum font-semibold text-ink">{fmtScore(row.score)}</span>
                      </span>
                    ) : (
                      <span className="text-ink-3">—</span>
                    )}
                  </td>
                  <td className="tnum px-4 py-3 text-ink-2">{fmtDuration(row.duration)}</td>
                  <td className="tnum px-4 py-3 text-ink-2">{fmtTokens(row.inputTokens)}</td>
                  <td className="tnum px-4 py-3 text-ink-2">{fmtTokens(row.outputTokens)}</td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-series-1">查看 →</span>
                  </td>
                </tr>
              ))}
              {leaderRows.length === 0 && !modelsLoading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-ink-3">
                    无匹配数据
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ChartEmpty() {
  return (
    <div className="flex h-64 items-center justify-center text-sm text-ink-3">暂无数据</div>
  );
}
