import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Badge } from "../common/Badge";
import { TreeRubricReportView } from "./TreeRubricReportView";
import { SessionTimeline } from "./SessionTimeline";
import { useModelTasks } from "../../hooks/useModelTasks";
import { useSessions, useWorkspaceDownload } from "../../hooks/useResourceHooks";
import type { TaskRunInfo, TaskScore } from "../../types";
import { fmtScore, fmtDuration, fmtInt, fmtCost, fmtTokens } from "../../utils/format";

interface ExpandedTaskDetailProps {
  modelId: string;
  task: TaskScore;
  pageRun: string; // 页面级选中 run（average 或具体 run）
  perCaseRuns: string[]; // 该任务的有效 run 列表
  onClose: () => void;
}

const RUNS_EMPTY: TaskRunInfo[] = [];

export function ExpandedTaskDetail({
  modelId,
  task,
  pageRun,
  perCaseRuns,
}: ExpandedTaskDetailProps) {
  const [caseRun, setCaseRun] = useState<string>(() =>
    pageRun === "average" || !perCaseRuns.includes(pageRun) ? "average" : pageRun,
  );
  const isAverage = caseRun === "average";
  const effectiveRun = isAverage ? "run_1" : caseRun; // sessions/logs/judge 需有效 run

  // 具体 per-case run 时重取该 run 的真实 TaskScore
  const { data: runTasks, loading: runTasksLoading } = useModelTasks(modelId, caseRun);
  const liveTask = useMemo<TaskScore | null>(() => {
    if (isAverage) return task;
    return (
      runTasks?.find((t) => t.task_id === task.task_id || t.task_name === task.task_name) ?? null
    );
  }, [isAverage, runTasks, task]);

  const { data: sessions, loading: sessionsLoading } = useSessions(modelId, task.task_name, effectiveRun);
  const wsRuns = useMemo(() => (isAverage ? perCaseRuns : [effectiveRun]), [isAverage, perCaseRuns, effectiveRun]);
  const { downloading: wsDownloading, error: wsError, downloadWorkspace } = useWorkspaceDownload(modelId, task.task_name, wsRuns);

  const runs = task.runs ?? RUNS_EMPTY;

  const scrollToTimeline = () => {
    document.getElementById("task-session-timeline")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      {/* 主内容 */}
      <div className="min-w-0 flex-1 space-y-4">
        {/* per-case run 选择器 */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-ink-3">本轮选择：</span>
          <select
            value={caseRun}
            onChange={(e) => setCaseRun(e.target.value)}
            className="rounded-md border border-line bg-surface-2 px-2 py-1 text-xs text-ink outline-none"
          >
            <option value="average">平均（跨 run 合成）</option>
            {perCaseRuns.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <span className="text-xs text-ink-3">
            日志/轨迹/裁判按 {effectiveRun} 读取
          </span>
        </div>

        {/* 任务描述 */}
        <Section title="任务描述">
          <pre className="code-block max-h-48 overflow-y-auto rounded-md bg-surface-2 p-3 text-ink-2">{task.prompt || "（无）"}</pre>
        </Section>

        {/* 分类信息 */}
        <Section title="分类信息">
          <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-xs">
            <Info label="主场景" value={task.primary_scenario} />
            <Info label="次场景" value={task.secondary_scenario} />
            <Info label="能力" value={(task.ability_category ?? []).join(" / ")} />
            <Info label="难度" value={task.difficulty} />
            <Info label="复杂度" value={task.complexity} />
          </div>
        </Section>

        {/* 评估结果 */}
        <Section title="评估结果">
          {isAverage ? (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tnum text-lg font-semibold text-ink">{fmtScore(task.score)}</span>
                <Badge tone={task.pass_rate_over_runs != null && task.pass_rate_over_runs >= 0.75 ? "good" : "bad"}>
                  通过率(runs) {fmtScore(task.pass_rate_over_runs)}
                </Badge>
                <Badge tone={task.pass_at_1 ? "good" : "bad"}>pass@1 {task.pass_at_1 ? "✓" : "✗"}</Badge>
                <Badge tone={task.pass_k ? "good" : "bad"}>pass^k {task.pass_k ? "✓" : "✗"}</Badge>
                <span className="text-xs text-ink-3">共 {task.run_count ?? runs.length} 次 run</span>
              </div>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-line text-left text-ink-3">
                    <th className="py-1.5 pr-3 font-medium">run</th>
                    <th className="py-1.5 pr-3 font-medium">分数</th>
                    <th className="py-1.5 pr-3 font-medium">状态</th>
                    <th className="py-1.5 pr-3 font-medium">完成</th>
                    <th className="py-1.5 pr-3 font-medium">质量分</th>
                    <th className="py-1.5 font-medium">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.run_id} className="border-b border-line/60 last:border-0">
                      <td className="tnum py-1.5 pr-3 text-ink">{r.run_id}</td>
                      <td className="tnum py-1.5 pr-3 text-ink-2">{fmtScore(r.score)}</td>
                      <td className="py-1.5 pr-3 text-ink-2">{r.status ?? "—"}</td>
                      <td className="py-1.5 pr-3">
                        <Badge tone={r.passed ? "good" : "bad"}>{r.passed ? "通过" : "未通过"}</Badge>
                      </td>
                      <td className="tnum py-1.5 pr-3 text-ink-2">{fmtScore(r.quality_score)}</td>
                      <td className="tnum py-1.5 text-ink-2">{fmtDuration(r.duration)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : runTasksLoading || !liveTask ? (
            <div className="py-4 text-xs text-ink-3">加载该 run 的任务数据…</div>
          ) : (
            <div className="space-y-1.5 text-xs">
              <Row label="分数" value={fmtScore(liveTask.score)} strong />
              <Row label="状态" value={liveTask.status ?? "—"} />
              <Row label="完成标记" value={liveTask.complete_flag === 1 ? "已完成" : liveTask.complete_flag === 0 ? "未完成" : "—"} />
              <Row label="质量分" value={fmtScore(liveTask.quality_score)} />
              <Row label="完成率" value={fmtScore(liveTask.completion_rate)} />
              <Row label="耗时" value={fmtDuration(liveTask.duration)} />
            </div>
          )}
        </Section>

        {/* 人工评分详情（仅具体 run） */}
        {!isAverage && liveTask ? (
          <Section title="人工评分详情">
            <div className="space-y-3">
              {liveTask.rubric_format === "tree" ? (
                <TreeRubricReportView task={liveTask} />
              ) : liveTask.rubric_format === "flat" && liveTask.rubric_scores?.length ? (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-line text-left text-ink-3">
                      <th className="py-1.5 pr-3 font-medium">#</th>
                      <th className="py-1.5 pr-3 font-medium">完成度</th>
                      <th className="py-1.5 pr-3 font-medium">质量分</th>
                      <th className="py-1.5 font-medium">条目分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveTask.rubric_scores.map((s, i) => (
                      <tr key={i} className="border-b border-line/60 last:border-0">
                        <td className="tnum py-1.5 pr-3 text-ink">{i + 1}</td>
                        <td className="tnum py-1.5 pr-3 text-ink-2">{fmtScore(s.completion)}</td>
                        <td className="tnum py-1.5 pr-3 text-ink-2">{fmtScore(s.quality_score)}</td>
                        <td className="tnum py-1.5 text-ink-2">{fmtScore(s.item_score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
              {liveTask.trace_quality ? (
                <div className="text-xs">
                  <span className="text-ink-3">过程评价维度：</span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {Object.entries(liveTask.trace_quality.dimensions ?? {}).map(([k, v]) => (
                      <span key={k} className="rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">
                        {k} {fmtScore(v)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
              {liveTask.manual_score != null ? (
                <div className="text-xs">
                  <span className="text-ink-3">人工分数：</span>
                  <span className="font-medium text-ink">{liveTask.manual_score}</span>
                  <span className="ml-3 text-ink-3">评价：</span>
                  <Badge tone={liveTask.manual_feedback === 1 ? "good" : liveTask.manual_feedback === -1 ? "bad" : "neutral"}>
                    {liveTask.manual_feedback === 1 ? "好评 👍" : liveTask.manual_feedback === -1 ? "差评 👎" : "未标记"}
                  </Badge>
                </div>
              ) : (
                <div className="text-xs text-ink-3">该任务未进行人工评分</div>
              )}
            </div>
          </Section>
        ) : null}

        {/* 工具统计 / token 成本 / 错误恢复 */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Section title="工具统计">
            <div className="space-y-1.5 text-xs">
              <Row label="工具调用" value={fmtInt(toolStats(task).calls)} />
              <Row label="成功" value={fmtInt(toolStats(task).success)} />
              <Row label="失败" value={fmtInt(toolStats(task).failed)} />
              <Row label="成功率" value={fmtScore(toolStats(task).rate)} />
            </div>
          </Section>
          <Section title="Token 与成本">
            <div className="space-y-1.5 text-xs">
              <Row label="输入 Token" value={fmtTokens(task.input_tokens)} />
              <Row label="输出 Token" value={fmtTokens(task.output_tokens)} />
              <Row label="输入成本" value={fmtCost(task.input_cost)} />
              <Row label="输出成本" value={fmtCost(task.output_cost)} />
            </div>
          </Section>
          <Section title="错误恢复">
            <div className="space-y-1.5 text-xs">
              <Row label="API 调用" value={fmtInt(task.api_calls)} />
              <Row label="错误恢复" value={fmtInt(task.error_recoveries)} />
              <Row label="恢复率" value={fmtScore(task.error_recovery_rate)} />
            </div>
          </Section>
        </div>

        {/* 底部动作 */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface-2 px-4 py-3">
          <button
            type="button"
            onClick={downloadWorkspace}
            disabled={wsDownloading || wsRuns.length === 0}
            className="rounded-md bg-series-1 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {wsDownloading ? "下载中…" : isAverage ? `下载全部 Workspace（${wsRuns.length} 个 run）` : "下载 Workspace"}
          </button>
          <button
            type="button"
            onClick={scrollToTimeline}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-ink-2 transition-colors hover:text-ink"
          >
            查看轨迹
          </button>
          {wsError ? <span className="text-xs text-critical">{wsError}</span> : null}
        </div>
      </div>

      {/* 会话轨迹侧栏 */}
      <div id="task-session-timeline" className="w-full shrink-0 lg:w-80">
        <SessionTimeline data={sessions} loading={sessionsLoading} taskName={task.task_name} />
      </div>
    </div>
  );
}

function toolStats(task: TaskScore) {
  return {
    calls: task.tool_calls,
    success: task.tool_success,
    failed: task.tool_failed,
    rate: task.tool_success_rate,
  };
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-surface p-3.5">
      <div className="mb-2 text-xs font-semibold text-ink">
        {title}
        {subtitle ? <span className="ml-2 font-normal text-ink-3">{subtitle}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Info({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <span className="text-ink-3">{label}：</span>
      <span className="text-ink">{value ?? "—"}</span>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value?: string | number | null; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-ink-3">{label}</span>
      <span className={`tnum ${strong ? "font-semibold text-ink" : "text-ink-2"}`}>{value ?? "—"}</span>
    </div>
  );
}
