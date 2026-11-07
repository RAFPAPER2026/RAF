import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Modal } from "../common/Modal";
import { Badge } from "../common/Badge";
import { SectionCard } from "../common/SectionCard";
import { StatCard } from "../common/StatCard";
import { CrossFilterPanel } from "../CrossFilterPanel";
import type { FilterState } from "../CrossFilterPanel";
import { TaskCard } from "./TaskCard";
import { TagBarChart } from "./TagBarChart";
import { SortToolbar } from "./SortToolbar";
import { ExpandedTaskDetail } from "./ExpandedTaskDetail";
import { useModelRuns } from "../../hooks/useModelRuns";
import { useModelTasks } from "../../hooks/useModelTasks";
import { useModelOverall } from "../../hooks/useModelOverall";
import { useExportExcel } from "../../hooks/useExportExcel";
import { isTaskPassed } from "../../types";
import type { TaskScore } from "../../types";
import { parseModelName } from "../../utils/model";
import {
  isModelFeedbackBad,
  isModelFeedbackGood,
  taskMatchesAllFilters,
  taskMatchesSearch,
} from "../../utils/filterUtils";
import { fmtScore, fmtRate, fmtDuration, fmtInt, fmtTokens, fmtCost } from "../../utils/format";
import { sortTasks } from "./SortToolbar";
import type { SortField } from "./SortToolbar";

type CaseFilter = "all" | "good" | "bad";

export default function ModelDetail() {
  const { modelId } = useParams<{ modelId: string }>();

  const { data: runsData, loading: runsLoading } = useModelRuns(modelId);
  const availableRuns = useMemo(() => runsData?.runs ?? [], [runsData]);
  const perCaseRuns = runsData?.per_case_runs ?? {};

  const [selectedRun, setSelectedRun] = useState<string>("average");
  const [filters, setFilters] = useState<FilterState>({});
  const [caseFilter, setCaseFilter] = useState<CaseFilter>("all");
  const [sortField, setSortField] = useState<SortField>("score");
  const [desc, setDesc] = useState(true);
  const [keyword, setKeyword] = useState("");
  const [openTask, setOpenTask] = useState<TaskScore | null>(null);

  const { data: tasks, loading: tasksLoading, error: tasksError, refresh: refreshTasks } = useModelTasks(modelId, selectedRun);
  const { data: overall } = useModelOverall(modelId, selectedRun);

  /* ---------------- 筛选管线：交叉筛选 → Case标记 → 搜索 → 排序 ---------------- */
  const allTasks = tasks ?? [];
  const crossFiltered = useMemo(
    () => allTasks.filter((t) => taskMatchesAllFilters(t, filters)),
    [allTasks, filters],
  );
  const caseFiltered = useMemo(() => {
    if (caseFilter === "good") return crossFiltered.filter(isModelFeedbackGood);
    if (caseFilter === "bad") return crossFiltered.filter(isModelFeedbackBad);
    return crossFiltered;
  }, [crossFiltered, caseFilter]);
  const searched = useMemo(
    () => (keyword ? caseFiltered.filter((t) => taskMatchesSearch(t, keyword)) : caseFiltered),
    [caseFiltered, keyword],
  );
  const filteredTasks = useMemo(
    () => sortTasks(searched, sortField, desc),
    [searched, sortField, desc],
  );

  const hasAnyFilter = useMemo(
    () =>
      Object.values(filters).some((v) => (v?.length ?? 0) > 0) ||
      caseFilter !== "all" ||
      keyword.trim().length > 0,
    [filters, caseFilter, keyword],
  );

  /* ---------------- 头部 summary（均取筛选后） ---------------- */
  const summary = useMemo(() => {
    const scores = searched
      .map((t) => t.score)
      .filter((s): s is number => s !== null && s !== undefined);
    const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : null;
    const passedCount = searched.filter(isTaskPassed).length;
    return {
      avgScore: avg,
      count: searched.length,
      duration: searched.reduce((a, t) => a + (t.duration ?? 0), 0),
      passRate: searched.length > 0 ? passedCount / searched.length : null,
    };
  }, [searched]);

  /* ---------------- 统计概览（均取筛选后） ---------------- */
  const overview = useMemo(() => {
    const sum = (fn: (t: TaskScore) => number | undefined) =>
      searched.reduce((a, t) => a + (fn(t) ?? 0), 0);
    const toolCalls = sum((t) => t.tool_calls);
    const toolSuccess = sum((t) => t.tool_success);
    return {
      inputTokens: sum((t) => t.input_tokens),
      outputTokens: sum((t) => t.output_tokens),
      toolCalls,
      toolSuccess,
      toolSuccessRate: toolCalls > 0 ? toolSuccess / toolCalls : null,
      inputCost: sum((t) => t.input_cost),
      outputCost: sum((t) => t.output_cost),
      totalCost: sum((t) => t.input_cost) + sum((t) => t.output_cost),
      apiCalls: sum((t) => t.api_calls),
    };
  }, [searched]);

  /* ---------------- 导出 ---------------- */
  const { exporting: exportingXlsx, error: exportError, exportExcel } = useExportExcel(
    modelId,
    selectedRun,
    filteredTasks,
  );

  const modelName = modelId ? parseModelName(modelId) : "—";
  const showRunSelector = availableRuns.length > 1;

  return (
    <div className="space-y-4">
      {/* 1. 头部卡 */}
      <div className="rounded-xl border border-line bg-surface p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-lg font-semibold text-ink">
              {modelName}
              <span className="ml-2 text-sm font-normal text-ink-3">详细评测结果</span>
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-3">
              <span className="code-block">{modelId}</span>
              {availableRuns.length > 1 ? (
                <Badge tone="info">{availableRuns.length} runs</Badge>
              ) : null}
              {runsLoading ? <span>加载 run 信息…</span> : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {showRunSelector ? (
              <select
                value={selectedRun}
                onChange={(e) => setSelectedRun(e.target.value)}
                className="rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-none"
                title="选择评测 run"
              >
                <option value="average">平均（跨 run 合成）</option>
                {availableRuns.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            ) : null}
            <button
              type="button"
              onClick={exportExcel}
              disabled={exportingXlsx}
              className="rounded-md bg-series-1 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              {exportingXlsx ? "导出中…" : "导出Excel"}
            </button>
            {exportError ? <span className="text-xs text-critical">{exportError}</span> : null}
          </div>
        </div>

        {/* 4 个 summary 项 */}
        <div className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
          <div>
            <div className="text-xs text-ink-3">
              效果分{hasAnyFilter ? "（筛选后）" : ""}
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  summary.avgScore === null
                    ? "bg-ink-3"
                    : summary.avgScore >= 0.75
                      ? "bg-good"
                      : summary.avgScore >= 0.5
                        ? "bg-warn"
                        : "bg-critical"
                }`}
                aria-hidden
              />
              <span className="text-2xl font-semibold text-ink">{fmtScore(summary.avgScore)}</span>
            </div>
          </div>
          <StatCard label="任务数" value={fmtInt(summary.count)} />
          <StatCard label="总耗时" value={fmtDuration(summary.duration)} />
          <StatCard label="通过率" value={fmtRate(summary.passRate)} />
        </div>

        {/* 筛选控件 */}
        <div className="mt-4 space-y-3">
          <CrossFilterPanel tasks={allTasks} filters={filters} onChange={setFilters} />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-ink-3">Case标记筛选：</span>
            {(
              [
                { v: "all", label: "全部" },
                { v: "good", label: "👍 好评" },
                { v: "bad", label: "👎 差评" },
              ] as Array<{ v: CaseFilter; label: string }>
            ).map((opt) => (
              <button
                key={opt.v}
                type="button"
                onClick={() => setCaseFilter(opt.v)}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  caseFilter === opt.v
                    ? "border-series-1 bg-series-1/15 font-medium text-series-1"
                    : "border-line bg-surface-2 text-ink-2 hover:border-ink-3"
                }`}
                aria-pressed={caseFilter === opt.v}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {tasksError ? (
        <div className="rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm text-critical">
          任务数据加载失败：{tasksError}
          <button type="button" onClick={refreshTasks} className="ml-3 underline decoration-dotted underline-offset-2">
            重试
          </button>
        </div>
      ) : null}

      {/* 2. 统计概览卡 */}
      <SectionCard title="统计概览" subtitle={`基于当前筛选后的 ${filteredTasks.length} 个任务`}>
        <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <StatMini label="总输入Token" value={fmtTokens(overview.inputTokens)} />
          <StatMini label="总输出Token" value={fmtTokens(overview.outputTokens)} />
          <StatMini label="总工具调用" value={fmtInt(overview.toolCalls)} />
          <StatMini label="工具成功率" value={fmtScore(overview.toolSuccessRate)} />
          <StatMini label="输入成本" value={fmtCost(overview.inputCost)} />
          <StatMini label="输出成本" value={fmtCost(overview.outputCost)} />
          <StatMini label="总成本" value={fmtCost(overview.totalCost)} />
          <StatMini label="API调用次数" value={fmtInt(overview.apiCalls)} />
        </div>
        {overall ? (
          <div className="mt-3 border-t border-line pt-2 text-[11px] text-ink-3">
            总体统计（未筛选）：{fmtScore(overall.average_score)} 平均分 · {fmtRate(overall.pass_rate)} 通过率 ·{" "}
            {fmtDuration(overall.total_duration)} 总耗时 · 全部 {overall.total_tasks} 任务
          </div>
        ) : null}
      </SectionCard>

      {/* 3. TagBarChart */}
      <SectionCard title="Rubric标签通过率" subtitle="按叶子覆盖度 top-12 标签，条形按通过率排序">
        <TagBarChart tasks={filteredTasks} />
      </SectionCard>

      {/* 4. 任务列表 */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-ink">
            任务列表
            <span className="tnum ml-2 text-sm font-normal text-ink-3">
              {filteredTasks.length} 个任务
              {hasAnyFilter ? "（已筛选）" : ""}
            </span>
          </h2>
        </div>
        <SortToolbar
          field={sortField}
          onFieldChange={setSortField}
          desc={desc}
          onDescChange={setDesc}
          keyword={keyword}
          onKeywordChange={setKeyword}
        />
        {tasksLoading ? (
          <div className="py-10 text-center text-sm text-ink-3">加载任务数据…</div>
        ) : filteredTasks.length === 0 ? (
          <div className="rounded-xl border border-line bg-surface py-10 text-center text-sm text-ink-3">
            无匹配任务
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredTasks.map((t) => (
              <TaskCard
                key={t.task_id || t.task_name}
                task={t}
                perCaseRuns={perCaseRuns[t.task_name] ?? []}
                onOpen={setOpenTask}
              />
            ))}
          </div>
        )}
      </div>

      {/* 弹窗：任务详情 + 会话轨迹 */}
      <Modal
        open={openTask !== null}
        onClose={() => setOpenTask(null)}
        title={
          openTask ? (
            <span className="flex items-center gap-2">
              {openTask.task_name}
              <Badge tone={isTaskPassed(openTask) ? "good" : "bad"}>
                {isTaskPassed(openTask) ? "PASS" : "FAIL"}
              </Badge>
            </span>
          ) : null
        }
        maxWidth="max-w-6xl"
      >
        {openTask ? (
          <ExpandedTaskDetail
            modelId={modelId ?? ""}
            task={openTask}
            pageRun={selectedRun}
            perCaseRuns={perCaseRuns[openTask.task_name] ?? []}
            onClose={() => setOpenTask(null)}
          />
        ) : null}
      </Modal>
    </div>
  );
}

function StatMini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface-2 px-3 py-2">
      <div className="text-[11px] text-ink-3">{label}</div>
      <div className="tnum mt-0.5 text-sm font-semibold text-ink">{value}</div>
    </div>
  );
}
