import { Badge } from "../common/Badge";
import { isTaskPassed } from "../../types";
import type { TaskScore } from "../../types";
import { fmtScore, fmtDuration, fmtInt } from "../../utils/format";

interface TaskCardProps {
  task: TaskScore;
  perCaseRuns?: string[]; // 该任务的有效 run 列表
  onOpen: (task: TaskScore) => void;
}

/** 任务卡片：名称、截断 prompt、PASS/FAIL、分数、时长、工具调用；多轮平均额外显示 run 摘要 */
export function TaskCard({ task, perCaseRuns, onOpen }: TaskCardProps) {
  const passed = isTaskPassed(task);
  const isMultiRunAverage = (task.runs?.length ?? 0) > 0;

  const prompt = task.prompt ?? "";
  const promptPreview = prompt.length > 80 ? `${prompt.slice(0, 80)}…` : prompt;

  return (
    <button
      type="button"
      onClick={() => onOpen(task)}
      className="group flex w-full flex-col gap-2 rounded-xl border border-line bg-surface p-4 text-left shadow-sm transition-colors hover:border-ink-3"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink" title={task.task_name}>
            {task.task_name}
          </div>
          <div className="mt-0.5 flex flex-wrap gap-1.5">
            {passed ? <Badge tone="good">PASS</Badge> : <Badge tone="bad">FAIL</Badge>}
            {isMultiRunAverage ? (
              <>
                <Badge tone="info">通过率 {fmtScore(task.pass_rate_over_runs)}</Badge>
                <Badge tone={task.pass_at_1 ? "good" : "bad"}>pass@1 {task.pass_at_1 ? "✓" : "✗"}</Badge>
                <Badge tone={task.pass_k ? "good" : "bad"}>pass^k {task.pass_k ? "✓" : "✗"}</Badge>
              </>
            ) : null}
          </div>
        </div>
      </div>

      <p className="text-xs leading-relaxed text-ink-2">{promptPreview || "（无描述）"}</p>

      <div className="mt-auto flex items-center justify-between border-t border-line pt-2 text-xs">
        <span className="tnum font-semibold text-ink">{fmtScore(task.score)}</span>
        <span className="flex items-center gap-3 text-ink-3">
          <span className="tnum">{fmtDuration(task.duration)}</span>
          <span className="tnum">{fmtInt(task.tool_calls)} 次工具</span>
          {perCaseRuns && perCaseRuns.length > 1 ? (
            <span className="tnum text-ink-2">{perCaseRuns.length} runs</span>
          ) : null}
        </span>
      </div>
    </button>
  );
}
