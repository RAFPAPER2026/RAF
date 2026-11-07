import { columnLabel } from "../../utils/model";
import type { TaskScore } from "../../types";

export type SortField =
  | "case_name"
  | "duration"
  | "score"
  | "api_calls"
  | "input_tokens"
  | "output_tokens"
  | "tool_calls"
  | "tool_success_rate";

export const SORT_FIELDS: SortField[] = [
  "case_name",
  "duration",
  "score",
  "api_calls",
  "input_tokens",
  "output_tokens",
  "tool_calls",
  "tool_success_rate",
];

export function sortTasks(tasks: TaskScore[], field: SortField, desc: boolean): TaskScore[] {
  const copy = [...tasks];
  const num = (v: number | null | undefined): number =>
    v === null || v === undefined || Number.isNaN(v) ? -1 : v;
  copy.sort((a, b) => {
    let r: number;
    if (field === "case_name") {
      r = (a.task_name ?? "").localeCompare(b.task_name ?? "", "zh-CN");
    } else {
      r = num(a[field] as number | null | undefined) - num(b[field] as number | null | undefined);
    }
    return desc ? -r : r;
  });
  return copy;
}

interface SortToolbarProps {
  field: SortField;
  onFieldChange: (f: SortField) => void;
  desc: boolean;
  onDescChange: (d: boolean) => void;
  keyword: string;
  onKeywordChange: (k: string) => void;
}

export function SortToolbar({
  field,
  onFieldChange,
  desc,
  onDescChange,
  keyword,
  onKeywordChange,
}: SortToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-xs text-ink-3">排序字段</label>
      <select
        value={field}
        onChange={(e) => onFieldChange(e.target.value as SortField)}
        className="rounded-md border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink outline-none"
      >
        {SORT_FIELDS.map((f) => (
          <option key={f} value={f}>
            {columnLabel(f)}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => onDescChange(!desc)}
        className="flex items-center gap-1 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink-2 transition-colors hover:text-ink"
        title={desc ? "降序" : "升序"}
      >
        {desc ? "降序" : "升序"}
        <svg width="10" height="10" viewBox="0 0 10 10" style={{ transform: desc ? "scaleY(-1)" : "none" }}>
          <path d="M5 1v8M5 9L2 6M5 9l3-3" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      <div className="ml-auto flex items-center gap-2">
        <label className="text-xs text-ink-3">搜索</label>
        <input
          type="search"
          value={keyword}
          onChange={(e) => onKeywordChange(e.target.value)}
          placeholder="任务名 / prompt / rubric query"
          className="w-56 rounded-md border border-line bg-surface-2 px-2.5 py-1.5 text-xs text-ink outline-none placeholder:text-ink-3 focus:border-series-1"
        />
      </div>
    </div>
  );
}
