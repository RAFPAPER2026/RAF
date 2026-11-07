import type { QueryRubric, RubricNode, TaskScore } from "../types";

/**
 * Rubric 标签聚合（tags.ts）。
 * 规则：
 * - 仅 tree 格式任务参与；
 * - 叶子通过判定 = 顶层 task.rubric_results?.[leaf_id] === true；
 * - 一片叶子带多个标签则计入每个标签；无标签叶子跳过；
 * - 按 (task_name, leaf_id) 去重；
 * - 平均视图任务无顶层 rubric_results，从 task.runs[].rubric_results 逐 run 聚合，
 *   k 次 run 的 case 每个标签计 k 次。
 */

/** 是否为 tree 格式任务（rubric_format==='tree' 且 rubric 为对象而非数组） */
export function isTreeRubricTask(task: TaskScore): boolean {
  return (
    task.rubric_format === "tree" &&
    task.rubric !== null &&
    task.rubric !== undefined &&
    typeof task.rubric === "object" &&
    !Array.isArray(task.rubric)
  );
}

/** 遍历 completion + quality 两棵树，返回 [leaf_id, tags][] */
export function collectLeafTags(rubric: QueryRubric): Array<[string, string[]]> {
  const out: Array<[string, string[]]> = [];
  const walk = (nodes: RubricNode[] | undefined): void => {
    if (!nodes) return;
    for (const n of nodes) {
      if (n.type === "leaf") out.push([n.id, n.tags ?? []]);
      if (n.children) walk(n.children);
    }
  };
  walk(rubric.completion_rubric);
  walk((rubric.quality_rubric ?? []).map((i) => i.node));
  return out;
}

/** 任务的逐 run 叶子结果源；平均视图从 runs 聚合，单 run 视图取顶层 */
export function leafResultsSources(task: TaskScore): Array<Record<string, boolean>> {
  const runs = task.runs;
  if (runs && runs.length > 0) {
    return runs
      .map((r) => r.rubric_results)
      .filter((r): r is Record<string, boolean> => r !== null && r !== undefined);
  }
  if (task.rubric_results) return [task.rubric_results];
  return [];
}

/** 每标签的叶子覆盖数（按 (task_name, leaf_id) 去重；平均视图逐 run 计 k 次） */
export function countLeafCoverage(tasks: TaskScore[]): Record<string, number> {
  const counts: Record<string, number> = {};
  const seen = new Set<string>();
  for (const t of tasks) {
    if (!isTreeRubricTask(t)) continue;
    const leafTags = collectLeafTags(t.rubric as QueryRubric);
    const sources = leafResultsSources(t);
    sources.forEach((results, srcIdx) => {
      for (const [leafId, tags] of leafTags) {
        if (results[leafId] !== true) continue; // 叶子通过判定
        const key = `${srcIdx}|${t.task_name}|${leafId}`;
        if (seen.has(key)) continue;
        seen.add(key);
        for (const tag of tags) {
          if (!tag) continue; // 无标签叶子跳过
          counts[tag] = (counts[tag] ?? 0) + 1;
        }
      }
    });
  }
  return counts;
}

/** 按叶子覆盖度降序取 top-n 标签 */
export function computeTopTags(tasks: TaskScore[], n = 12): string[] {
  const coverage = countLeafCoverage(tasks);
  return Object.entries(coverage)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, n)
    .map(([tag]) => tag);
}

/** 每标签 {passed, total, rate}；平均视图逐 run 聚合（k 次 run 计 k 次） */
export function computeTagPassRates(
  tasks: TaskScore[],
  axisTags: string[],
): Record<string, { passed: number; total: number; rate: number }> {
  const stats: Record<string, { passed: number; total: number }> = {};
  for (const tag of axisTags) stats[tag] = { passed: 0, total: 0 };

  const seen = new Set<string>();
  for (const t of tasks) {
    if (!isTreeRubricTask(t)) continue;
    const leafTags = collectLeafTags(t.rubric as QueryRubric);
    const sources = leafResultsSources(t);
    sources.forEach((results, srcIdx) => {
      for (const [leafId, tags] of leafTags) {
        const pairKey = `${srcIdx}|${t.task_name}|${leafId}`;
        if (seen.has(pairKey)) continue;
        seen.add(pairKey);
        const ok = results[leafId] === true;
        for (const tag of tags) {
          const s = stats[tag];
          if (!s) continue;
          s.total += 1;
          if (ok) s.passed += 1;
        }
      }
    });
  }

  const out: Record<string, { passed: number; total: number; rate: number }> = {};
  for (const tag of axisTags) {
    const { passed, total } = stats[tag];
    out[tag] = { passed, total, rate: total > 0 ? passed / total : 0 };
  }
  return out;
}

/** 各模型筛选任务并集 → computeTopTags，保证雷达图多边形共享轴 */
export function buildAxisFromModels(
  perModelTasks: Record<string, TaskScore[]>,
  n = 12,
): string[] {
  const all = Object.values(perModelTasks).flat();
  return computeTopTags(all, n);
}
