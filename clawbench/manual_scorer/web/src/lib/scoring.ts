// 树形 rubric 评分逻辑（与后端 src/rubric/scoring.py 保持一致的镜像实现）
// 质量分口径：paper=论文 Eq.1（AND 组全过才得 1，否则 0）；legacy_mean=AND 组取均值
import type { QueryRubric, RubricNode, WeightedItem } from '../types';

export type ScoringMode = 'paper' | 'legacy_mean';
export const SCORING_MODES: ScoringMode[] = ['paper', 'legacy_mean'];

/** 节点布尔判定：leaf → 结果映射；or → any；and（默认）→ all；空组 → all([]) == true */
export function nodePassed(node: RubricNode, results: Record<string, boolean>): boolean {
  if (node.type === 'leaf' || !node.children || node.children.length === 0) {
    return results[node.id] === true;
  }
  if (node.combinator === 'or') {
    return node.children.some((c) => nodePassed(c, results));
  }
  return node.children.every((c) => nodePassed(c, results));
}

/** 节点质量分（0-1）：leaf → 1.0/0.0；空组 → 0.0；or → max；and → paper 二值 / legacy 均值 */
export function nodeScore(
  node: RubricNode,
  results: Record<string, boolean>,
  mode: ScoringMode = 'paper',
): number {
  if (node.type === 'leaf') {
    return results[node.id] === true ? 1.0 : 0.0;
  }
  if (!node.children || node.children.length === 0) {
    return 0.0;
  }
  const scores = node.children.map((c) => nodeScore(c, results, mode));
  if (node.combinator === 'or') {
    return Math.max(...scores);
  }
  if (mode === 'paper') {
    return scores.every((s) => s === 1.0) ? 1.0 : 0.0;
  }
  return scores.reduce((a, b) => a + b, 0) / scores.length;
}

/** DFS 收集全部叶子节点 */
export function collectLeaves(nodes: RubricNode[]): RubricNode[] {
  const leaves: RubricNode[] = [];
  for (const node of nodes) {
    if (node.type === 'leaf' || !node.children || node.children.length === 0) {
      leaves.push(node);
    } else {
      leaves.push(...collectLeaves(node.children));
    }
  }
  return leaves;
}

/** 完成度：{completed(顶层全过), total(叶子数), passed(通过叶子数)} */
export function evaluateCompletion(
  nodes: RubricNode[],
  results: Record<string, boolean>,
): { completed: boolean; total: number; passed: number } {
  const leaves = collectLeaves(nodes);
  const passed = leaves.filter((l) => results[l.id] === true).length;
  const completed = nodes.every((n) => nodePassed(n, results));
  return { completed, total: leaves.length, passed };
}

/** 质量分：顶层加权平均（Σ(weight·score) / Σweight），空 → 0.0 */
export function scoreQuality(
  items: WeightedItem[],
  results: Record<string, boolean>,
  mode: ScoringMode = 'paper',
): { score: number; totalWeight: number; itemScores: Array<{ id: string; name: string; weight: number; score: number }> } {
  const itemScores = items.map((item) => ({
    id: item.node.id,
    name: item.node.name,
    weight: item.weight,
    score: nodeScore(item.node, results, mode),
  }));
  const totalWeight = itemScores.reduce((a, b) => a + b.weight, 0);
  const score = totalWeight > 0 ? itemScores.reduce((a, b) => a + b.weight * b.score, 0) / totalWeight : 0.0;
  return { score, totalWeight, itemScores };
}

/** 汇总：返回与后端 compute_rubric_score 一致的派生结果 */
export function computeTreeScore(
  rubric: QueryRubric,
  results: Record<string, boolean>,
  mode: ScoringMode = 'paper',
): {
  completion: { completed: boolean; total: number; passed: number };
  quality: { score: number; totalWeight: number };
  completion_rate: number;
  complete_flag: 0 | 1;
  score: number;
  scoring_mode: ScoringMode;
} {
  const completion = evaluateCompletion(rubric.completion_rubric ?? [], results);
  const quality = scoreQuality(rubric.quality_rubric ?? [], results, mode);
  const completion_rate = completion.total > 0 ? completion.passed / completion.total : 0.0;
  const complete_flag: 0 | 1 = completion.completed ? 1 : 0;
  return {
    completion,
    quality,
    completion_rate,
    complete_flag,
    score: quality.score,
    scoring_mode: mode,
  };
}

/** 嗅探 rubric 格式（镜像 src/rubric/compat.py::detect_rubric_format） */
export function detectRubricFormat(rubric: unknown): 'tree' | 'flat' {
  if (rubric && typeof rubric === 'object' && !Array.isArray(rubric)) {
    const r = rubric as Record<string, unknown>;
    const fmt = r.rubric_format;
    if (fmt === 'tree' || fmt === 'flat') return fmt;
    const completion = r.completion_rubric;
    if (Array.isArray(completion) && completion.length > 0) {
      const first = completion[0];
      if (first && typeof first === 'object' && (first as Record<string, unknown>).type === 'leaf') return 'tree';
      if (first && typeof first === 'object' && (first as Record<string, unknown>).type === 'group') return 'tree';
    }
    const quality = r.quality_rubric;
    if (Array.isArray(quality) && quality.length > 0) {
      const first = quality[0];
      if (first && typeof first === 'object' && typeof (first as Record<string, unknown>).node === 'object') return 'tree';
    }
  }
  return 'flat';
}

/** 从 score.json 提取树形 rubric_results（兼容任意存储形态） */
export function extractRubricResults(score: Record<string, any> | null | undefined): Record<string, boolean> {
  if (!score || typeof score !== 'object') return {};
  const raw = score.rubric_results;
  if (raw && typeof raw === 'object') {
    const out: Record<string, boolean> = {};
    for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
      out[k] = v === true;
    }
    return out;
  }
  return {};
}
