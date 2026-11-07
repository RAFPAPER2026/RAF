import { isTaskPassed } from "../types";
import type { TaskScore } from "../types";

/** 人工评分状态筛选的取值（显示名在组件层映射） */
export const MANUAL_SCORED = "scored";
export const MANUAL_UNSCORED = "unscored";

export type DimensionKey =
  | "primary_scenario"
  | "secondary_scenario"
  | "ability_category"
  | "difficulty"
  | "complexity";

/** 单维度匹配：ability_category 按逗号拆分精确包含；其他维度直接相等 */
export function taskMatchesDimension(
  task: TaskScore,
  dimension: string,
  value: string,
): boolean {
  if (dimension === "ability_category") {
    const cats = (task.ability_category ?? [])
      .flatMap((c) => c.split(",").map((s) => s.trim()))
      .filter((s) => s.length > 0);
    return cats.includes(value);
  }
  return (task as unknown as Record<string, unknown>)[dimension] === value;
}

/** 多维度筛选：维度间 AND、维度内 OR；manual_score_status 特殊处理 */
export function taskMatchesAllFilters(
  task: TaskScore,
  filters: Record<string, string[] | undefined>,
): boolean {
  for (const dim of Object.keys(filters)) {
    const values = filters[dim];
    if (!values || values.length === 0) continue;

    if (dim === "manual_score_status") {
      const scored = task.manual_score !== null && task.manual_score !== undefined;
      const ok = values.some((v) =>
        v === MANUAL_SCORED ? scored : v === MANUAL_UNSCORED ? !scored : false,
      );
      if (!ok) return false;
      continue;
    }
    if (!values.some((v) => taskMatchesDimension(task, dim, v))) return false;
  }
  return true;
}

/** 提取某维度全部选项（去重、保序） */
export function extractDimensionOptions(tasks: TaskScore[], dimension: string): string[] {
  const set = new Set<string>();
  for (const t of tasks) {
    if (dimension === "ability_category") {
      for (const c of t.ability_category ?? []) {
        for (const s of c.split(",")) {
          const v = s.trim();
          if (v) set.add(v);
        }
      }
    } else {
      const v = (t as unknown as Record<string, unknown>)[dimension];
      if (v !== undefined && v !== null && v !== "") set.add(String(v));
    }
  }
  return [...set];
}

/** 任务是否通过（complete_flag=1 或 score ≥ 阈值） */
export function isModelCompleted(task: TaskScore): boolean {
  return isTaskPassed(task);
}

/** 人工评价为好评（manual_feedback === 1） */
export function isModelFeedbackGood(task: TaskScore): boolean {
  return task.manual_feedback === 1;
}

/** 人工评价为差评（manual_feedback === -1） */
export function isModelFeedbackBad(task: TaskScore): boolean {
  return task.manual_feedback === -1;
}

function collectRubricQueryStrings(rubric: unknown): string[] {
  const out: string[] = [];
  const walk = (node: unknown): void => {
    if (node === null || node === undefined) return;
    if (Array.isArray(node)) {
      for (const n of node) walk(n);
      return;
    }
    if (typeof node === "object") {
      const obj = node as Record<string, unknown>;
      for (const key of ["query", "name", "id"]) {
        const v = obj[key];
        if (typeof v === "string" && v) out.push(v);
      }
      for (const key of ["completion_rubric", "children"]) {
        walk(obj[key]);
      }
      const qr = obj["quality_rubric"];
      if (Array.isArray(qr)) {
        for (const item of qr) {
          if (item && typeof item === "object") walk((item as Record<string, unknown>)["node"]);
        }
      }
    }
  };
  walk(rubric);
  return out;
}

/** 搜索：任务名 / prompt / tree-rubric 的 query 子串匹配（不区分大小写） */
export function taskMatchesSearch(task: TaskScore, keyword: string): boolean {
  const k = keyword.trim();
  if (!k) return true;
  const low = k.toLowerCase();
  const hay = [
    task.task_name ?? "",
    task.prompt ?? "",
    ...collectRubricQueryStrings(task.rubric),
  ];
  return hay.some((s) => s.toLowerCase().includes(low));
}
