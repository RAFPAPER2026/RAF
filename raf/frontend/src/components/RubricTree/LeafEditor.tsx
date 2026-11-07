// 叶子编辑器：名称输入 + 能力项标签多选 + 删除
import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import type { TreeNodeProps } from "./TreeNode";

export default function LeafEditor(props: TreeNodeProps) {
  const { node, depth, index, onPatch, onDelete, capabilities } = props;
  const [showTags, setShowTags] = useState(false);

  const toggleTag = (tag: string) => {
    const tags = node.tags.includes(tag)
      ? node.tags.filter((t) => t !== tag)
      : [...node.tags, tag];
    onPatch?.(node.id, { tags });
  };

  return (
    <div style={{ paddingLeft: depth * 20 }}>
      <div className="flex items-center gap-1.5 py-1 px-1.5 rounded hover:bg-gray-50 group">
        <span className="text-xs text-gray-300 w-4 text-center shrink-0">{index + 1}</span>
        <span className="text-[10px] px-1 py-0.5 rounded bg-gray-100 text-gray-500 shrink-0">叶</span>
        <input
          className="input flex-1"
          value={node.name}
          placeholder="叶子名称（正面断言，如「正确读取了本周日程安排」）"
          onChange={(e) => onPatch?.(node.id, { name: e.target.value })}
        />
        <button
          className="btn text-xs py-0.5 shrink-0"
          onClick={() => setShowTags(!showTags)}
          title="能力项标签"
        >
          {showTags ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          标签{node.tags.length > 0 && `(${node.tags.length})`}
        </button>
        <button
          className="btn-danger text-xs py-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => onDelete?.(node.id)}
          title="删除"
        >
          <Trash2 size={13} />
        </button>
      </div>
      {showTags && (
        <div
          style={{ paddingLeft: depth * 20 + 28 }}
          className="mb-1 p-2 bg-gray-50 rounded border border-gray-100"
        >
          <div className="text-xs text-gray-400 mb-1.5">选择能力项标签（可多选，值来自能力项列表）</div>
          <div className="flex flex-wrap gap-1">
            {capabilities.map((cap) => {
              const name = cap.split(/[：:]/)[0].trim();
              const active = node.tags.includes(name);
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() => toggleTag(name)}
                  title={cap}
                  className={`text-xs px-1.5 py-0.5 rounded border transition-colors ${
                    active
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-blue-300"
                  }`}
                >
                  {active && <Check size={11} className="inline mr-0.5" />}
                  {name}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
