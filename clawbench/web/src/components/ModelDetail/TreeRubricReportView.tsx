import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { QueryRubric, RubricNode, TaskScore, WeightedItem } from "../../types";
import { evaluateCompletion, scoreQuality } from "../../rubric/scoring";
import type { ScoringMode } from "../../rubric/scoring";

/** 只读渲染完成树与质量树：叶子按 rubric_results 通过/失败着色、显示 tags，AND/OR 组结果由 scoring 派生，组可折叠 */

interface TreeRubricReportViewProps {
  task: TaskScore;
}

export function TreeRubricReportView({ task }: TreeRubricReportViewProps) {
  const rubric = task.rubric as QueryRubric | null | undefined;
  const results = task.rubric_results ?? {};
  const mode: ScoringMode = task.scoring_mode === "legacy_mean" ? "legacy_mean" : "paper";
  const completion = evaluateCompletion(rubric?.completion_rubric, results);
  const quality = scoreQuality(rubric?.quality_rubric, results, mode);

  const hasCompletion = (rubric?.completion_rubric?.length ?? 0) > 0;
  const hasQuality = (rubric?.quality_rubric?.length ?? 0) > 0;

  if (!rubric || (!hasCompletion && !hasQuality)) {
    return <div className="text-sm text-ink-3">该任务无 tree rubric 数据</div>;
  }

  return (
    <div className="space-y-4">
      {hasCompletion ? (
        <div className="rounded-lg border border-line p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-ink-2">完成度评估树</span>
            <span className={completion.completed ? "text-good" : "text-critical"}>
              {completion.completed ? "整体通过" : "整体未通过"}
            </span>
            <span className="text-ink-3">
              通过叶子 {completion.passed}/{completion.total}
            </span>
          </div>
          <div className="space-y-1">
            {rubric.completion_rubric!.map((node) => (
              <TreeNode key={node.id} node={node} results={results} depth={0} />
            ))}
          </div>
        </div>
      ) : null}

      {hasQuality ? (
        <div className="rounded-lg border border-line p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-ink-2">质量评估树</span>
            <span className="text-ink-3">
              加权得分 {(quality.score * 100).toFixed(1)}%
            </span>
          </div>
          <div className="space-y-2">
            {rubric.quality_rubric!.map((item, i) => (
              <div key={i} className="rounded-md bg-surface-2 p-2">
                <div className="mb-1 text-xs text-ink-3">权重 {item.weight}</div>
                <WeightedNodeView item={item} results={results} />
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function WeightedNodeView({ item, results }: { item: WeightedItem; results: Record<string, boolean> }) {
  return <TreeNode node={item.node} results={results} depth={0} />;
}

function evalNode(node: RubricNode, results: Record<string, boolean>): boolean {
  if (node.type === "leaf") return results[node.id] === true;
  const cs = node.children ?? [];
  if (cs.length === 0) return true;
  const vals = cs.map((c) => evalNode(c, results));
  return node.combinator === "or" ? vals.some(Boolean) : vals.every(Boolean);
}

function TreeNode({
  node,
  results,
  depth,
}: {
  node: RubricNode;
  results: Record<string, boolean>;
  depth: number;
}) {
  const [open, setOpen] = useState(true);

  if (node.type === "leaf") {
    const ok = results[node.id] === true;
    return (
      <div
        className="flex items-start gap-2 rounded px-2 py-1"
        style={{ marginLeft: depth * 16 }}
      >
        <span
          className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${ok ? "bg-good" : "bg-critical"}`}
          aria-hidden
        />
        <div className="min-w-0">
          <div className="text-xs text-ink">
            {node.name || node.id}
            <span className="ml-1.5 text-[10px] text-ink-3">{node.id}</span>
          </div>
          {node.tags && node.tags.length > 0 ? (
            <div className="mt-0.5 flex flex-wrap gap-1">
              {node.tags.map((t) => (
                <span key={t} className="rounded bg-surface-2 px-1.5 py-px text-[10px] text-ink-2">
                  {t}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  }

  const groupOk = evalNode(node, results);
  const children = node.children ?? [];
  return (
    <div style={{ marginLeft: depth * 16 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-surface-2"
      >
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${groupOk ? "bg-good" : "bg-critical"}`}
          aria-hidden
        />
        <span className={`rounded px-1 text-[10px] ${node.combinator === "or" ? "bg-series-3/15 text-series-3" : "bg-series-2/15 text-series-2"}`}>
          {node.combinator === "or" ? "OR" : "AND"}
        </span>
        <span className="text-xs font-medium text-ink">{node.name || "(未命名组)"}</span>
        <span
          className={`inline-block h-2 w-2 shrink-0 border-y-4 border-x-4 border-y-transparent border-l-ink-3 transition-transform ${
            open ? "rotate-90" : ""
          }`}
          style={{ borderLeftColor: "var(--ink-3)" }}
          aria-hidden
        />
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="children"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            {children.map((c) => (
              <TreeNode key={c.id} node={c} results={results} depth={depth + 1} />
            ))}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
