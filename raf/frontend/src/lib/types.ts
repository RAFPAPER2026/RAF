// 与后端 rubric/models.py、models_optim.py 对齐的类型定义

export type Combinator = "and" | "or";
export type NodeType = "leaf" | "group";

export interface RubricNode {
  id: string;
  type: NodeType;
  name: string;
  combinator: Combinator;
  children: RubricNode[];
  tags: string[];
}

export interface WeightedItem {
  weight: number;
  node: RubricNode;
}

export interface QueryRubric {
  id: string;
  query: string;
  query_id: string;
  prompt_version: string;
  completion_rubric: RubricNode[];
  quality_rubric: WeightedItem[];
}

export interface QueryRubricListItem extends QueryRubric {
  review_count: number;
  review_avg_completion: number | null;
  review_avg_quality: number | null;
  query_tags: string[];
}

export interface RubricReview {
  id: string;
  rubric_id: string;
  prompt_version: string;
  completion_score: number;
  quality_score: number;
  notes: string[];
  created_at: string;
}

export interface ReviewStats {
  prompt_version: string;
  count: number;
  avg_completion: number;
  avg_quality: number;
  completion_distribution: Record<string, number>;
  quality_distribution: Record<string, number>;
}

export interface PromptVersionSummary {
  version: string;
  parent_version: string;
  created_at: string;
  change_description: string;
  metrics_summary: Record<string, unknown>;
  module_sizes: Record<string, number>;
  active: boolean;
}

export interface PromptVersionDetail {
  version: string;
  parent_version: string;
  created_at: string;
  change_description: string;
  metrics_summary: Record<string, unknown>;
  modules: Record<string, string>;
  assembled_prompt: string;
  module_order: string[];
}

export interface ModuleDiff {
  changed: boolean;
  old: string;
  new: string;
}

export interface PromptVersionDiff {
  version_new: string;
  version_old: string;
  changed_modules: string[];
  modules: Record<string, ModuleDiff>;
}

export interface QueryItem {
  id: string;
  text: string;
  tags: string[];
  created_at: string;
  updated_at: string;
  rubric_count?: number;
}

export interface CompletionResult {
  completed: boolean;
  total: number;
  passed: number;
  itemResults: Record<string, boolean>;
}

export interface QualityResult {
  weightedCompleted: number;
  totalWeight: number;
  score: number;
  itemScores: { weight: number; nodeId: string; score: number }[];
  scoringMode?: string;
}

export interface ScoreResponse {
  completion: CompletionResult;
  quality: QualityResult;
}

export interface BatchGenerateStatus {
  task_id: string;
  status: "running" | "generating" | "done" | "error";
  prompt_version: string;
  total: number;
  progress: Record<string, "pending" | "generating" | "done" | "error">;
  errors: Record<string, string>;
}

// ---------- 优化运行（PROMPT-R） ----------

export interface ScoreEntry {
  rubric_id: string;
  gold_score: number;
  rater_scores: Record<string, number>;
}

export type QualityDecision = "approved" | "rejected";

export interface RoundQualityReview {
  decision: QualityDecision;
  comment: string;
  created_at: string;
  updated_at: string;
}

export interface RoundMetrics {
  pearson_r: number | null;
  spearman_rho: number | null;
  qwk: number | null;
  composite: number | null;
  per_query_deviation: Record<string, number>;
  n_entries: number;
  error?: string | null;
  computed_at?: string;
}

export interface FailureFinding {
  pattern: string;
  node_name: string;
  category: string;
  evidence: string;
  severity: string;
  suggestion: string;
}

export interface RoundDiagnosis {
  findings: FailureFinding[];
  aggregated: string;
  errors: { rubric_id?: string; error: string }[];
}

export interface OptimizationSuggestion {
  id: string;
  module: string;
  problem: string;
  suggestion: string;
  status: string;
  accepted: boolean;
}

export interface RoundResult {
  round_number: number;
  prompt_version: string;
  status: string;
  generation_task_id?: string | null;
  score_sheet: { entries: ScoreEntry[] };
  metrics: RoundMetrics | null;
  quality_review?: RoundQualityReview | null;
  diagnosis: RoundDiagnosis | null;
  suggestions: OptimizationSuggestion[];
  refined_prompt_version?: string | null;
  created_at: string;
  updated_at: string;
  rubrics?: QueryRubric[];
}

export interface OptimizationRun {
  run_id: string;
  name: string;
  query_ids: string[];
  rater_ids: string[];
  current_prompt_version: string;
  status: string;
  rounds: RoundResult[];
  created_at: string;
  updated_at: string;
}

export interface StoppingCheck {
  should_stop: boolean;
  reason: string;
  metrics: RoundMetrics | null;
  thresholds: Record<string, number>;
}
