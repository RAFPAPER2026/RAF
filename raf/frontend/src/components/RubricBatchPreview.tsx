// RubricBatchPreview：批量 rubric 折叠预览（人工质量初筛时粗看整批树）
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { QueryRubric, RubricNode } from "../lib/types";
import RubricTree from "./RubricTree";

function countLeaves(node: RubricNode): number {
  if (node.type === "leaf") return 1;
  return (node.children ?? []).reduce((sum, c) => sum + countLeaves(c), 0);
}

function rubricStats(r: QueryRubric): number {
  const inTrees = (arr: RubricNode[]) => arr.reduce((sum, n) => sum + countLeaves(n), 0);
  return inTrees(r.completion_rubric) + inTrees(r.quality_rubric.map((i) => i.node));
}

interface Props {
  rubrics: QueryRubric[];
}

export default function RubricBatchPreview({ rubrics }: Props) {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());

  // rubrics 内容（切换轮次 / 重新生成）变化时重置展开状态：以 rubric id 集合为
  // 内容签名，避免旧一批 id 残留在 openIds 中导致按钮文案与实际展开状态不一致。
  const idsKey = rubrics
    .map((r) => r.id)
    .sort()
    .join("|");
  useEffect(() => {
    setOpenIds(new Set());
  }, [idsKey]);

  // allOpen 需逐一核对当前批次的 id 都已展开，不能只比数量（旧批残留会误判）
  const allOpen = rubrics.length > 0 && rubrics.every((r) => openIds.has(r.id));

  const toggle = (id: string) =>
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const setAll = (open: boolean) =>
    setOpenIds(open ? new Set(rubrics.map((r) => r.id)) : new Set());

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs text-gray-400">{rubrics.length} 份 rubric（点击展开粗看）</span>
        <button
          type="button"
          className="text-xs text-blue-600 hover:underline"
          onClick={() => setAll(!allOpen)}
        >
          {allOpen ? "全部收起" : "全部展开"}
        </button>
      </div>
      <div className="space-y-1.5">
        {rubrics.map((r, i) => {
          const open = openIds.has(r.id);
          return (
            <div key={r.id} className="border border-gray-200 rounded-md overflow-hidden">
              <button
                type="button"
                onClick={() => toggle(r.id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 transition-colors"
              >
                {open ? (
                  <ChevronDown size={14} className="text-gray-400 shrink-0" />
                ) : (
                  <ChevronRight size={14} className="text-gray-400 shrink-0" />
                )}
                <span className="text-xs font-medium text-gray-700 min-w-0 flex-1 truncate" title={r.query}>
                  {i + 1}. {r.query}
                </span>
                <span className="text-[11px] text-gray-400 shrink-0">
                  {r.prompt_version} · {rubricStats(r)} 检查项
                </span>
              </button>
              {open && (
                <div className="border-t border-gray-100 p-3 max-h-96 overflow-auto bg-white">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-gray-400 mb-1.5">完成量规</div>
                      <RubricTree nodes={r.completion_rubric} mode="view" />
                    </div>
                    <div>
                      <div className="text-xs text-gray-400 mb-1.5">质量量规</div>
                      {r.quality_rubric.map((item) => (
                        <div key={item.node.id} className="mb-2.5">
                          <span className="tag bg-amber-50 text-amber-700 mb-1 inline-block">
                            权重 {item.weight}
                          </span>
                          <RubricTree nodes={[item.node]} mode="view" />
                        </div>
                      ))}
                      {r.quality_rubric.length === 0 && (
                        <div className="text-xs text-gray-400">（暂无质量量规项）</div>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
