// 全部 API 调用封装（对应 rubric/routes.py）

import {
  BatchGenerateStatus,
  ModuleDiff,
  OptimizationRun,
  PromptVersionDetail,
  PromptVersionDiff,
  PromptVersionSummary,
  QueryItem,
  QueryRubric,
  QueryRubricListItem,
  ReviewStats,
  RubricReview,
  ScoreEntry,
  ScoreResponse,
  StoppingCheck,
} from "./types";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      // 非 JSON 错误体，保留默认信息
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// ---------- Rubric CRUD ----------

export function listRubrics(params: { search?: string; limit?: number; offset?: number; dedup?: boolean } = {}) {
  const qs = new URLSearchParams();
  if (params.search) qs.set("search", params.search);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  if (params.dedup) qs.set("dedup", "true");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request<QueryRubricListItem[]>(`/api/rubrics${suffix}`);
}

export function getRubric(id: string) {
  return request<QueryRubric>(`/api/rubrics/${id}`);
}

export function createRubric(data: Partial<QueryRubric>) {
  return request<QueryRubric>("/api/rubrics", { method: "POST", body: JSON.stringify(data) });
}

export function updateRubric(id: string, data: Partial<QueryRubric>) {
  return request<QueryRubric>(`/api/rubrics/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export function deleteRubric(id: string) {
  return request<{ deleted: boolean }>(`/api/rubrics/${id}`, { method: "DELETE" });
}

export function cleanupRubrics() {
  return request<{ removed: number }>("/api/rubrics/cleanup", { method: "POST" });
}

export function scoreRubric(
  id: string,
  results: Record<string, boolean>,
  scoringMode: string = "paper",
) {
  return request<ScoreResponse>(`/api/rubrics/${id}/score`, {
    method: "POST",
    body: JSON.stringify({ results, scoring_mode: scoringMode }),
  });
}

// ---------- 审核 ----------

export function listReviews() {
  return request<RubricReview[]>("/api/reviews");
}

export function getReviewStats() {
  return request<ReviewStats[]>("/api/reviews/stats");
}

export function getReviewForRubric(rubricId: string) {
  return request<RubricReview>(`/api/reviews/${rubricId}`);
}

export function submitReview(data: { rubric_id: string; completion_score: number; quality_score: number; notes: string[] }) {
  return request<RubricReview>("/api/reviews", { method: "POST", body: JSON.stringify(data) });
}

// ---------- Prompt 版本管理 ----------

export function listPromptVersions() {
  return request<{ versions: PromptVersionSummary[]; active: string }>("/api/prompt-versions");
}

export function getPromptVersion(version: string) {
  return request<PromptVersionDetail>(`/api/prompt-versions/${version}`);
}

export function diffPromptVersions(version: string, compareTo: string) {
  return request<PromptVersionDiff>(`/api/prompt-versions/${version}/diff?compare_to=${compareTo}`);
}

export function updatePromptModule(version: string, moduleKey: string, content: string) {
  return request<{ version: string; module: string; updated: boolean }>(
    `/api/prompt-versions/${version}/modules/${moduleKey}`,
    { method: "PUT", body: JSON.stringify({ content }) }
  );
}

export function clonePromptVersion(version: string, newVersion: string, changeDescription = "") {
  return request<PromptVersionDetail>(`/api/prompt-versions/${version}/clone`, {
    method: "POST",
    body: JSON.stringify({ new_version: newVersion, change_description: changeDescription }),
  });
}

export function activatePromptVersion(version: string) {
  return request<{ active: string }>(`/api/prompt-versions/${version}/activate`, { method: "PUT" });
}

// ---------- 能力项 ----------

export function getCapabilities() {
  return request<{ capabilities: string[] }>("/api/capabilities");
}

export function updateCapabilities(capabilities: string[]) {
  return request<{ capabilities: string[] }>("/api/capabilities", {
    method: "PUT",
    body: JSON.stringify({ capabilities }),
  });
}

// ---------- Query 管理 ----------

export function listQueries() {
  return request<QueryItem[]>("/api/queries");
}

export function getQuery(id: string) {
  return request<QueryItem>(`/api/queries/${id}`);
}

export function createQuery(text: string, tags: string[] = []) {
  return request<QueryItem>("/api/queries", { method: "POST", body: JSON.stringify({ text, tags }) });
}

export function batchCreateQueries(texts: string[]) {
  return request<{ created: number; total: number; items: QueryItem[] }>("/api/queries/batch", {
    method: "POST",
    body: JSON.stringify({ texts }),
  });
}

export function updateQuery(id: string, data: { text?: string; tags?: string[] }) {
  return request<QueryItem>(`/api/queries/${id}`, { method: "PUT", body: JSON.stringify(data) });
}

export function deleteQuery(id: string) {
  return request<{ deleted: boolean }>(`/api/queries/${id}`, { method: "DELETE" });
}

export function importQueriesJson(items: { text: string; tags: string[] }[]) {
  return request<{ created: number; total: number }>("/api/queries/import", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export async function importQueriesExcel(file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/queries/import-excel", { method: "POST", body: form });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return res.json() as Promise<{ created: number; total: number }>;
}

export function migrateQueries() {
  return request<{ query_count: number; updated_rubrics: number }>("/api/queries/migrate", { method: "POST" });
}

export const exportQueriesUrl = "/api/queries/export";

// ---------- 批量生成 ----------

export function generateBatch(data: { prompt_version?: string; queries?: string[]; query_ids?: string[]; concurrency?: number }) {
  return request<{ task_id: string; total: number; prompt_version: string }>("/api/generate/batch", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export function getGenerateStatus(taskId: string) {
  return request<BatchGenerateStatus>(`/api/generate/status/${taskId}`);
}

// ---------- 优化运行（PROMPT-R） ----------

export function createOptimizationRun(data: { name: string; query_ids: string[]; rater_ids: string[]; prompt_version: string }) {
  return request<OptimizationRun>("/api/optimize/runs", { method: "POST", body: JSON.stringify(data) });
}

export function listOptimizationRuns() {
  return request<OptimizationRun[]>("/api/optimize/runs");
}

export function getOptimizationRun(id: string) {
  return request<OptimizationRun>(`/api/optimize/runs/${id}`);
}

export function deleteOptimizationRun(id: string) {
  return request<{ deleted: boolean }>(`/api/optimize/runs/${id}`, { method: "DELETE" });
}

export function startOptimizationRound(id: string) {
  return request(`/api/optimize/runs/${id}/rounds`, { method: "POST" });
}

export function submitRoundScores(id: string, roundNumber: number, entries: ScoreEntry[]) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/scores`, {
    method: "POST",
    body: JSON.stringify({ entries }),
  });
}

export function getRoundScores(id: string, roundNumber: number) {
  return request<{ entries: ScoreEntry[] }>(`/api/optimize/runs/${id}/rounds/${roundNumber}/scores`);
}

export function reviewRoundQuality(id: string, roundNumber: number, decision: "approved" | "rejected", comment: string) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/quality-review`, {
    method: "POST",
    body: JSON.stringify({ decision, comment }),
  });
}

export function computeRoundMetrics(id: string, roundNumber: number) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/metrics`, { method: "POST" });
}

export function analyzeRound(id: string, roundNumber: number) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/analyze`, { method: "POST" });
}

export function reDiagnoseRound(id: string, roundNumber: number) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/re-diagnose`, { method: "POST" });
}

export function applyRoundSuggestions(id: string, roundNumber: number, acceptedSuggestionIds: string[], newVersion: string) {
  return request(`/api/optimize/runs/${id}/rounds/${roundNumber}/apply`, {
    method: "POST",
    body: JSON.stringify({ accepted_suggestion_ids: acceptedSuggestionIds, new_version: newVersion }),
  });
}

export function checkOptimizationStop(id: string) {
  return request<StoppingCheck>(`/api/optimize/runs/${id}/check-stop`);
}
