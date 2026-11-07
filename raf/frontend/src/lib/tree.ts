// 树操作工具：构建器的不可变树编辑
import { RubricNode } from "./types";

let counter = 0;

export function genId(prefix = "node"): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}${counter.toString(36)}${Math.random()
    .toString(36)
    .slice(2, 8)}`;
}

export function newLeaf(name = ""): RubricNode {
  return { id: genId(), type: "leaf", name, combinator: "and", children: [], tags: [] };
}

export function newGroup(name = "", combinator: "and" | "or" = "and"): RubricNode {
  return {
    id: genId(),
    type: "group",
    name,
    combinator,
    children: [newLeaf(), newLeaf()],
    tags: [],
  };
}

export function mapNode(node: RubricNode, fn: (n: RubricNode) => RubricNode): RubricNode {
  return fn({ ...node, children: node.children.map((c) => mapNode(c, fn)) });
}

export function mapNodes(nodes: RubricNode[], fn: (n: RubricNode) => RubricNode): RubricNode[] {
  return nodes.map((n) => mapNode(n, fn));
}

export function updateNodeById(nodes: RubricNode[], id: string, patch: Partial<RubricNode>): RubricNode[] {
  return mapNodes(nodes, (n) => (n.id === id ? { ...n, ...patch } : n));
}

export function findNode(nodes: RubricNode[], id: string): RubricNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    const found = findNode(n.children, id);
    if (found) return found;
  }
  return null;
}

export function removeNodeById(nodes: RubricNode[], id: string): RubricNode[] {
  return nodes
    .filter((n) => n.id !== id)
    .map((n) => ({ ...n, children: removeNodeById(n.children, id) }));
}

export function addChildToGroup(nodes: RubricNode[], groupId: string, child: RubricNode): RubricNode[] {
  return mapNodes(nodes, (n) => (n.id === groupId ? { ...n, children: [...n.children, child] } : n));
}

export function collectLeafNames(nodes: RubricNode[]): string[] {
  const names: string[] = [];
  for (const n of nodes) {
    if (n.type === "leaf") names.push(n.name);
    else names.push(...collectLeafNames(n.children));
  }
  return names;
}
