export const PASS_THRESHOLD = 0.75;
export type VerifierType = "manual";

export interface TaskScore {
  task_id: string; task_name: string; prompt: string;
  verifier_type: VerifierType;
  status: string; score: number | null; duration: number | null;
  complete_flag?: 0 | 1 | null;
  manual_score?: number | null;
  manual_feedback?: -1 | 0 | 1;
  doubtful?: boolean;
  input_tokens?: number; output_tokens?: number;
  input_cost?: number; output_cost?: number;
  tool_calls?: number; tool_success?: number; tool_failed?: number; tool_success_rate?: number;
  api_calls?: number; error_recoveries?: number; error_recovery_rate?: number;
  rubric_format?: "tree" | "flat" | null;
  scoring_mode?: string;
  rubric?: any;                       // config 原始 rubric（tree 为对象）
  rubric_results?: Record<string, boolean> | null;   // 仅 tree
  completion?: { completed: boolean; total: number; passed: number } | null;
  quality_score?: number | null; completion_rate?: number | null;
  rubric_scores?: Array<{ completion: number; quality_score: number; item_score: number }> | null; // 仅 flat
  trace_quality?: { avg_score: number; dimensions: Record<string, number> } | null;
  primary_scenario?: string; secondary_scenario?: string;
  ability_category?: string[]; difficulty?: string; complexity?: string;
  pass_count?: number; total_count?: number;
  // 仅 average 视图存在的多轮字段：
  runs?: TaskRunInfo[]; run_count?: number;
  pass_rate_over_runs?: number; pass_at_1?: boolean; pass_k?: boolean; mean_score?: number | null;
}
export interface TaskRunInfo {
  run_id: string; score: number | null; status: string;
  complete_flag?: 0 | 1 | null; quality_score?: number | null;
  completion_rate?: number | null; duration?: number | null;
  passed: boolean; rubric_results?: Record<string, boolean> | null;
}
export interface ModelInfo {
  id: string; runs: string[]; max_run: number;
  stats: { average_score: number | null; pass_rate: number | null; total_tasks: number;
           total_duration: number; total_input_tokens: number; total_output_tokens: number };
}
export interface OverallStats {
  total_tasks: number; completed_tasks: number; failed_tasks: number;
  average_score: number; pass_rate: number; total_duration: number;
  total_input_tokens: number; total_output_tokens: number;
  total_input_cost: number; total_output_cost: number; total_cost: number;
  total_tool_calls: number; total_tool_success: number; total_tool_failed: number;
  overall_tool_success_rate: number; total_api_calls: number;
  total_error_recoveries: number; overall_error_recovery_rate: number;
  avg_completion_rate: number; avg_trace_dimensions: Record<string, number>;
}
export interface CategoryStats { category: string; count: number; avg_score: number; pass_rate: number; }
export interface ComparisonData {
  dimension: string; categories: string[];
  models: Array<{ id: string; name: string; scores: Record<string, number>; overall: number; pass_rate: number }>;
}
export interface RubricNode {
  id: string; type: "leaf" | "group"; name: string;
  combinator?: "and" | "or"; children?: RubricNode[]; tags?: string[];
}
export interface WeightedItem { weight: number; node: RubricNode; }
export interface QueryRubric {
  id?: string; query?: string; query_id?: string; prompt_version?: string;
  completion_rubric?: RubricNode[]; quality_rubric?: WeightedItem[];
}
export interface TraceDimension { key: string; name: string; levels: number; }
export interface TraceConfig { dimensions: TraceDimension[]; pass_threshold: number; }
export interface LogEntry { verifier: string; command: string; exit_code: number; stdout: string; stderr: string; }

export function isTaskPassed(task: { complete_flag?: 0 | 1 | null; score?: number | null }): boolean {
  // 全链路一致（§1.7）：complete_flag == 1 即通过、== 0 即未通过（完成度硬性闸门）；
  // 旧数据（无该键或显式 null）回退 score >= PASS_THRESHOLD
  if (task.complete_flag === 1) return true;
  if (task.complete_flag === 0) return false;
  return (task.score ?? -1) >= PASS_THRESHOLD;
}
