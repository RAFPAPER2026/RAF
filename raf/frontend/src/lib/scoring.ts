// 前端评分实现：与后端 rubric/scoring.py 逻辑一致（双份实现，修改需同步）
import { CompletionResult, QualityResult, RubricNode, WeightedItem } from "./types";

export type ScoringMode = "paper" | "legacy_mean";
export const SCORING_MODES: ScoringMode[] = ["paper", "legacy_mean"];

export function evaluateNode(node: RubricNode, results: Record<string, boolean>): boolean {
  if (node.type === "leaf") return !!results[node.id];
  const values = node.children.map((c) => evaluateNode(c, results));
  return node.combinator === "or" ? values.some(Boolean) : values.every(Boolean);
}

export function evaluateCompletion(
  nodes: RubricNode[],
  results: Record<string, boolean>
): CompletionResult {
  const itemResults: Record<string, boolean> = {};
  for (const node of nodes) itemResults[node.id] = evaluateNode(node, results);
  const passed = Object.values(itemResults).filter(Boolean).length;
  const total = nodes.length;
  return { completed: passed === total, total, passed, itemResults };
}

export function evaluateNodeScore(
  node: RubricNode,
  results: Record<string, boolean>,
  mode: ScoringMode = "paper",
): number {
  if (node.type === "leaf") return results[node.id] ? 1 : 0;
  const values = node.children.map((c) => evaluateNodeScore(c, results, mode));
  if (values.length === 0) return 0;
  if (node.combinator === "or") return Math.max(...values);
  if (mode === "paper") return values.every((v) => v === 1) ? 1 : 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

export function scoreQuality(
  items: WeightedItem[],
  results: Record<string, boolean>,
  mode: ScoringMode = "paper",
): QualityResult {
  const itemScores = items.map((item) => ({
    weight: item.weight,
    nodeId: item.node.id,
    score: evaluateNodeScore(item.node, results, mode),
  }));
  const totalWeight = itemScores.reduce((a, b) => a + b.weight, 0);
  const weightedCompleted = itemScores.reduce((a, b) => a + b.weight * b.score, 0);
  return {
    weightedCompleted,
    totalWeight,
    score: totalWeight ? weightedCompleted / totalWeight : 0,
    itemScores,
    scoringMode: mode,
  };
}

export function collectLeafIds(nodes: RubricNode[]): string[] {
  const ids: string[] = [];
  for (const node of nodes) {
    if (node.type === "leaf") ids.push(node.id);
    else ids.push(...collectLeafIds(node.children));
  }
  return ids;
}
