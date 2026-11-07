import type { QueryRubric, RubricNode, WeightedItem } from "../types";

/**
 * Read-only scoring mirror used by the report page.
 * The authoritative implementation is Python `src/rubric/scoring.py`; the report
 * page re-derives per-case values from the stored `rubric_results` and the
 * `scoring_mode` recorded in `score.json` (`paper` by default, `legacy_mean` for
 * compatibility with older runs).
 */

export type ScoringMode = "paper" | "legacy_mean";

export interface CompletionEval {
  completed: boolean;
  total: number;
  passed: number;
  itemResults: Record<string, boolean>;
}

export interface QualityItemScore {
  id: string;
  score: number;
}

export interface QualityEval {
  weightedCompleted: number;
  totalWeight: number;
  score: number;
  itemScores: QualityItemScore[];
}

/** 完成度评估（二元，与口径无关） */
export function evaluateCompletion(
  nodes: RubricNode[] | undefined,
  results: Record<string, boolean>,
): CompletionEval {
  if (!nodes || nodes.length === 0) {
    return { completed: true, total: 0, passed: 0, itemResults: {} };
  }
  const itemResults: Record<string, boolean> = {};
  let total = 0;
  let passed = 0;

  const evalNode = (node: RubricNode): boolean => {
    if (node.type === "leaf") {
      const ok = results[node.id] ?? false;
      itemResults[node.id] = ok;
      total += 1;
      if (ok) passed += 1;
      return ok;
    }
    const children = node.children ?? [];
    if (children.length === 0) return true; // 空组 all([])===true
    const childResults = children.map((c) => evalNode(c));
    if (node.combinator === "or") return childResults.some(Boolean);
    return childResults.every(Boolean);
  };

  const completed = nodes.every((n) => evalNode(n));
  return { completed, total, passed, itemResults };
}

/** 质量评估（加权平均）；mode=paper 时 AND 组全过才得分，legacy_mean 取均值 */
export function scoreQuality(
  items: WeightedItem[] | undefined,
  results: Record<string, boolean>,
  mode: ScoringMode = "paper",
): QualityEval {
  if (!items || items.length === 0) {
    return { weightedCompleted: 0, totalWeight: 0, score: 0.0, itemScores: [] };
  }
  const itemScores: QualityItemScore[] = [];

  const evalNode = (node: RubricNode): number => {
    if (node.type === "leaf") {
      const s = results[node.id] ? 1.0 : 0.0;
      itemScores.push({ id: node.id, score: s });
      return s;
    }
    const children = node.children ?? [];
    if (children.length === 0) return 0.0; // 空组 → 0.0
    const childScores = children.map((c) => evalNode(c));
    if (node.combinator === "or") return Math.max(...childScores);
    if (mode === "paper") return childScores.every((s) => s === 1.0) ? 1.0 : 0.0;
    return childScores.reduce((a, b) => a + b, 0) / childScores.length;
  };

  let weightedCompleted = 0;
  let totalWeight = 0;
  for (const item of items) {
    totalWeight += item.weight;
    weightedCompleted += item.weight * evalNode(item.node);
  }
  const score = totalWeight > 0 ? weightedCompleted / totalWeight : 0.0;
  return { weightedCompleted, totalWeight, score, itemScores };
}

/** DFS 遍历 completion + quality 两树，收集全部叶子 id（去重保序） */
export function collectLeafIds(rubric: QueryRubric | null | undefined): string[] {
  const ids: string[] = [];
  const seen = new Set<string>();
  const walk = (nodes: RubricNode[] | undefined): void => {
    if (!nodes) return;
    for (const n of nodes) {
      if (n.type === "leaf") {
        if (!seen.has(n.id)) {
          seen.add(n.id);
          ids.push(n.id);
        }
      }
      if (n.children) walk(n.children);
    }
  };
  walk(rubric?.completion_rubric);
  walk((rubric?.quality_rubric ?? []).map((i) => i.node));
  return ids;
}
