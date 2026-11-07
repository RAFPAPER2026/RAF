// 树节点分发：edit → LeafEditor/GroupEditor；score → 勾选视图；view → 只读视图
import { evaluateNode } from "../../lib/scoring";
import { RubricNode } from "../../lib/types";
import GroupEditor from "./GroupEditor";
import LeafEditor from "./LeafEditor";
import type { TreeMode } from "./index";

export interface TreeNodeProps {
  node: RubricNode;
  depth: number;
  index: number;
  mode: TreeMode;
  results?: Record<string, boolean>;
  onToggle?: (id: string) => void;
  onPatch?: (id: string, patch: Partial<RubricNode>) => void;
  onDelete?: (id: string) => void;
  onAddChild?: (groupId: string, child: RubricNode) => void;
  capabilities: string[];
}

export default function TreeNode(props: TreeNodeProps) {
  if (props.mode === "edit") {
    return props.node.type === "leaf" ? <LeafEditor {...props} /> : <GroupEditor {...props} />;
  }
  if (props.mode === "score") {
    return <ScoreNode {...props} />;
  }
  return <ViewNode {...props} />;
}

function NodeHeader({
  props,
  groupOk,
}: {
  props: TreeNodeProps;
  groupOk: boolean;
}) {
  const { node, depth } = props;
  return (
    <div className="flex items-center gap-2 py-1 px-1.5">
      <span
        className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${
          node.combinator === "and"
            ? "bg-purple-50 text-purple-600 border-purple-200"
            : "bg-teal-50 text-teal-600 border-teal-200"
        }`}
      >
        {node.combinator.toUpperCase()}
      </span>
      <span
        className={`text-sm font-medium ${
          depth === 0 ? "text-gray-800" : groupOk ? "text-green-700" : "text-gray-400"
        }`}
      >
        {node.name}
      </span>
    </div>
  );
}

function ScoreNode(props: TreeNodeProps) {
  const { node, depth, results, onToggle } = props;
  const indent = { paddingLeft: depth * 20 };

  if (node.type === "leaf") {
    const checked = !!results?.[node.id];
    return (
      <div style={indent}>
        <label className="flex items-start gap-2 py-1 px-1.5 rounded hover:bg-gray-50 cursor-pointer">
          <input
            type="checkbox"
            checked={checked}
            onChange={() => onToggle?.(node.id)}
            className="mt-0.5 accent-blue-600"
          />
          <span className={`text-sm ${checked ? "text-gray-800" : "text-gray-500"}`}>{node.name}</span>
        </label>
        {node.tags.length > 0 && (
          <div style={{ paddingLeft: 24 }} className="flex gap-1 flex-wrap pb-1">
            {node.tags.map((t) => (
              <span key={t} className="tag">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  const childResults = node.children.map((c) => evaluateNode(c, results ?? {}));
  const passed = childResults.filter(Boolean).length;
  const groupOk = node.combinator === "or" ? passed > 0 : passed === node.children.length;

  return (
    <div style={indent}>
      <NodeHeader props={props} groupOk={groupOk} />
      <div className={`flex items-center gap-1 pl-6 text-xs ${groupOk ? "text-green-600" : "text-gray-400"}`}>
        {node.combinator === "and" ? `${passed}/${node.children.length} 通过` : groupOk ? "已达成" : "未达成"}
      </div>
      {node.children.map((c, i) => (
        <TreeNode key={c.id} {...props} node={c} depth={depth + 1} index={i} />
      ))}
    </div>
  );
}

function ViewNode(props: TreeNodeProps) {
  const { node, depth } = props;
  const indent = { paddingLeft: depth * 20 };

  if (node.type === "leaf") {
    return (
      <div style={indent}>
        <div className="flex items-start gap-2 py-1 px-1.5">
          <span className="text-sm text-gray-700">• {node.name}</span>
        </div>
        {node.tags.length > 0 && (
          <div style={{ paddingLeft: 24 }} className="flex gap-1 flex-wrap pb-1">
            {node.tags.map((t) => (
              <span key={t} className="tag">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={indent}>
      <NodeHeader props={props} groupOk={false} />
      <div className="pl-6">
        {node.children.map((c, i) => (
          <TreeNode key={c.id} {...props} node={c} depth={depth + 1} index={i} />
        ))}
      </div>
    </div>
  );
}
