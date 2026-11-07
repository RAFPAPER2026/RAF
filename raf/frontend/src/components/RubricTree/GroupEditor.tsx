// 组编辑器：名称 + combinator 切换 + 子节点增删
import { ChevronRight, Trash2 } from "lucide-react";
import { newGroup, newLeaf } from "../../lib/tree";
import TreeNode from "./TreeNode";
import type { TreeNodeProps } from "./TreeNode";

export default function GroupEditor(props: TreeNodeProps) {
  const { node, depth, index, onPatch, onDelete, onAddChild, capabilities } = props;

  return (
    <div style={{ paddingLeft: depth * 20 }}>
      <div className="flex items-center gap-1.5 py-1 px-1.5 rounded border-l-2 border-blue-200 bg-blue-50/40 group">
        <span className="text-xs text-gray-300 w-4 text-center shrink-0">{index + 1}</span>
        <ChevronRight size={13} className="text-blue-400 shrink-0" />
        <select
          className="input py-0.5 text-xs shrink-0"
          value={node.combinator}
          onChange={(e) => onPatch?.(node.id, { combinator: e.target.value as "and" | "or" })}
          title="AND=全部满足（取平均分）/ OR=任一满足（取最大值）"
        >
          <option value="and">AND</option>
          <option value="or">OR</option>
        </select>
        <input
          className="input flex-1"
          value={node.name}
          placeholder="组名称"
          onChange={(e) => onPatch?.(node.id, { name: e.target.value })}
        />
        <button className="btn text-xs py-0.5 shrink-0" onClick={() => onAddChild?.(node.id, newLeaf("新检查项"))}>
          + 叶
        </button>
        <button
          className="btn text-xs py-0.5 shrink-0"
          onClick={() => onAddChild?.(node.id, newGroup("新 AND 组", "and"))}
        >
          + AND
        </button>
        <button
          className="btn text-xs py-0.5 shrink-0"
          onClick={() => onAddChild?.(node.id, newGroup("新 OR 组", "or"))}
        >
          + OR
        </button>
        <button
          className="btn-danger text-xs py-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={() => onDelete?.(node.id)}
          title="删除"
        >
          <Trash2 size={13} />
        </button>
      </div>
      <div className="ml-3 pl-2 border-l border-gray-200">
        {node.children.map((c, i) => (
          <TreeNode key={c.id} {...props} node={c} depth={depth + 1} index={i} />
        ))}
      </div>
    </div>
  );
}
