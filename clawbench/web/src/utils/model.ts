/**
 * 模型 id 解析工具。
 * 例：TasksV4_glm-5_20260327_143052_abc123 → 名称 TasksV4_glm-5，分组 TasksV4。
 */

/** 取前两个 `_` 分隔段作为模型名 */
export function parseModelName(id: string): string {
  const parts = id.split("_");
  if (parts.length >= 2) return parts.slice(0, 2).join("_");
  return id;
}

/** 取首个 `_` 之前的前缀作为模型分组 */
export function getModelGroup(id: string): string {
  const idx = id.indexOf("_");
  if (idx <= 0) return id;
  return id.slice(0, idx);
}

/** 排序/表列的中文短名；具体 run 时追加 ` (run_n)` */
const COLUMN_LABELS: Record<string, string> = {
  case_name: "Case名称",
  duration: "耗时",
  score: "分数",
  api_calls: "API调用次数",
  input_tokens: "输入Token",
  output_tokens: "输出Token",
  tool_calls: "工具调用次数",
  tool_success_rate: "工具成功率",
};

export function columnLabel(col: string, runSuffix?: string): string {
  const base = COLUMN_LABELS[col] ?? col;
  return runSuffix ? `${base} (${runSuffix})` : base;
}
