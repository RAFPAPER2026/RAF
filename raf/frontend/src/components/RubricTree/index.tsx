// RubricTree：树编辑（edit）/ 评分勾选（score）/ 只读展示（view）三种模式
import { RubricNode } from "../../lib/types";
import { addChildToGroup, newGroup, newLeaf, removeNodeById, updateNodeById } from "../../lib/tree";
import TreeNode from "./TreeNode";

export type TreeMode = "edit" | "score" | "view";

interface RubricTreeProps {
  nodes: RubricNode[];
  onChange?: (nodes: RubricNode[]) => void;
  mode?: TreeMode;
  results?: Record<string, boolean>;
  onToggle?: (id: string) => void;
  capabilities?: string[];
}

export default function RubricTree({
  nodes,
  onChange,
  mode = "view",
  results,
  onToggle,
  capabilities = [],
}: RubricTreeProps) {
  const editable = mode === "edit" && !!onChange;
  const handlePatch = (id: string, patch: Partial<RubricNode>) =>
    onChange?.(updateNodeById(nodes, id, patch));
  const handleDelete = (id: string) => onChange?.(removeNodeById(nodes, id));
  const handleAddChild = (groupId: string, child: RubricNode) =>
    onChange?.(addChildToGroup(nodes, groupId, child));

  return (
    <div className="space-y-1">
      {nodes.map((node, i) => (
        <TreeNode
          key={node.id}
          node={node}
          depth={0}
          index={i}
          mode={mode}
          results={results}
          onToggle={onToggle}
          onPatch={editable ? handlePatch : undefined}
          onDelete={editable ? handleDelete : undefined}
          onAddChild={editable ? handleAddChild : undefined}
          capabilities={capabilities}
        />
      ))}
      {nodes.length === 0 && (
        <div className="text-xs text-gray-400 pl-1">（暂无顶层项）</div>
      )}
      {editable && (
        <div className="flex gap-2 pt-1.5 pl-5">
          <button className="btn text-xs py-1" onClick={() => onChange?.([...nodes, newLeaf("新检查项")])}>
            + 顶层叶子
          </button>
          <button
            className="btn text-xs py-1"
            onClick={() => onChange?.([...nodes, newGroup("新 AND 组", "and")])}
          >
            + 顶层 AND 组
          </button>
          <button
            className="btn text-xs py-1"
            onClick={() => onChange?.([...nodes, newGroup("新 OR 组", "or")])}
          >
            + 顶层 OR 组
          </button>
        </div>
      )}
    </div>
  );
}
