// ============================================================
// 契约类型（与后端 API 严格一致，逐字采用，严禁改名）
// ============================================================

export interface ModelSummary {
  id: string;
  name: string;
  alias: string;
  total: number;
  scored: number;
  passed: number;
  unscored: number;
  avg_score: number | null;
  pass_rate: number | null;
  runs: string[];
  max_run: number;
  default_run: string;
  per_run_stats: Record<
    string,
    {
      total: number;
      scored: number;
      passed: number;
      avg_score: number | null;
      pass_rate: number | null;
    }
  >;
}

export interface TaskSummary {
  task_name: string;
  status: string;
  score: number | null;
  manual_score: number | null;
  complete_flag: 0 | 1 | null;
  manual_feedback: -1 | 0 | 1;
  doubtful: boolean;
  completion_rate: number | null;
  rubric_format: "tree" | "flat" | null;
  duration: number | null;
}

export interface TaskDetail {
  task_name: string;
  score: Record<string, any>;
  config: Record<string, any>; // 含 rubric_format 与原始 rubric
  sessions: any[];
}

export interface RubricNode {
  id: string;
  type: "leaf" | "group";
  name: string;
  combinator?: "and" | "or";
  children?: RubricNode[];
  tags?: string[];
}

export interface WeightedItem {
  weight: number;
  node: RubricNode;
}

export interface QueryRubric {
  id?: string;
  query?: string;
  query_id?: string;
  prompt_version?: string;
  completion_rubric?: RubricNode[];
  quality_rubric?: WeightedItem[];
}

export interface WorkspaceFile {
  name: string;
  path: string;
  size: number;
  type: "file" | "dir";
  children?: WorkspaceFile[];
}

export interface WorkspaceTree {
  files: WorkspaceFile[];
  total_size: number;
  total_files: number;
}

export interface UploadCheckResponse {
  session_id: string;
  run_id: string;
  results_to_import: string[];
  results_conflicts: string[];
  has_conflicts: boolean;
}

export interface AgentEvalTaskStatus {
  task_key: string;
  status: "pending" | "running" | "completed" | "failed" | "timeout";
  error?: string;
  started_at?: string;
  finished_at?: string;
  run_id?: string;
}

export interface BatchTaskStatus {
  task_key: string;
  task_name: string;
  run_id: string;
  status: "queued" | "running" | "completed" | "failed" | "timeout" | "cancelled";
  score?: number | null;
  error?: string;
  retried?: boolean;
}

export interface BatchEvalSession {
  batch_id: string;
  status: string;
  tasks: BatchTaskStatus[];
  total: number;
  skipped: number;
  started: number;
  concurrency: number;
  auto_adopt: boolean;
  evaluate_trace: boolean;
  run_id: string;
  cancelled: boolean;
  started_at?: string;
  finished_at?: string;
  summary: {
    queued: number;
    running: number;
    completed: number;
    failed: number;
    timeout: number;
    cancelled: number;
  };
}

export interface TraceDimension {
  key: string;
  name: string;
  levels: number;
}

// ============================================================
// 附加类型（非契约，仅前端使用）
// ============================================================

export interface TraceConfig {
  dimensions: TraceDimension[];
  pass_threshold: number;
}

export interface ModelStats {
  id: string;
  name: string;
  alias?: string;
  total: number;
  scored: number;
  passed: number;
  unscored: number;
  avg_score: number | null;
  pass_rate: number | null;
}

export interface Stats {
  total_models: number;
  total_tasks: number;
  total_scored: number;
  total_unscored: number;
  models: ModelStats[];
}

export interface ModelRunsInfo {
  runs: string[];
  max_run: number;
  per_case_runs: Record<string, string[]>;
  default_run: string;
  runs_detail: Array<{ run_id: string; scored_tasks: number }>;
}

export interface AgentEvalSessionInfo {
  task_key: string;
  status: string;
  error?: string;
  started_at?: string;
  finished_at?: string;
  run_id?: string;
}

export interface BatchStartResponse {
  batch_id: string;
  total: number;
  skipped: number;
  started: number;
  tasks: BatchTaskStatus[];
}

export interface FlatRubricItem {
  completion_rubric?: string;
  quality_rubric?: unknown;
  tags?: string[];
  name?: string;
}

export interface TraceQualityPayload {
  dimensions: Record<string, number>;
}
