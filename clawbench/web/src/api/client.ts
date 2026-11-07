import type {
  ComparisonData,
  ModelInfo,
  OverallStats,
  TaskScore,
  TraceConfig,
  CategoryStats,
} from "../types";

const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildUrl(path: string, params?: Record<string, string | undefined>): string {
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, v);
      }
    }
  }
  return url.toString();
}

async function requestJson<T>(
  path: string,
  params?: Record<string, string | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const res = await fetch(buildUrl(path, params), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!res.ok) {
    throw new ApiError(res.status, `API ${res.status}: ${res.statusText} ${path}`);
  }
  return (await res.json()) as T;
}

async function requestBlob(
  path: string,
  params?: Record<string, string | undefined>,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await fetch(buildUrl(path, params), { signal });
  if (!res.ok) {
    throw new ApiError(res.status, `API ${res.status}: ${res.statusText} ${path}`);
  }
  return res.blob();
}

function enc(seg: string): string {
  return encodeURIComponent(seg);
}

export interface ModelRunsData {
  runs: string[];
  max_run: number;
  per_case_runs: Record<string, string[]>;
}

export interface ModelDetailData {
  model_id: string;
  model_name: string;
  stats: OverallStats;
  task_scores: Record<string, unknown>;
  task_configs: Record<string, unknown>;
  run_id: string;
}

export interface CaseDetailData {
  task_name: string;
  score: unknown;
  config: unknown;
  sessions: unknown[] | null;
}

export interface SessionsData {
  container: string;
  sessions: unknown[];
}

export interface DatasetDistribution {
  difficulty: Record<string, number>;
  complexity: Record<string, number>;
}

export const api = {
  health: (signal?: AbortSignal) =>
    requestJson<{ status: string }>("/health", undefined, signal),

  models: (signal?: AbortSignal) =>
    requestJson<ModelInfo[]>("/models", undefined, signal),

  comparison: (dimension: string, runId?: string, signal?: AbortSignal) =>
    requestJson<ComparisonData>("/comparison", { dimension, run_id: runId }, signal),

  modelRuns: (modelId: string, signal?: AbortSignal) =>
    requestJson<ModelRunsData>(`/model/${enc(modelId)}/runs`, undefined, signal),

  modelDetail: (modelId: string, runId?: string, signal?: AbortSignal) =>
    requestJson<ModelDetailData>(`/model/${enc(modelId)}`, { run_id: runId }, signal),

  modelTasks: (modelId: string, runId: string, signal?: AbortSignal) =>
    requestJson<TaskScore[]>(`/model/${enc(modelId)}/tasks`, { run_id: runId }, signal),

  modelCategories: (modelId: string, runId: string, signal?: AbortSignal) =>
    requestJson<CategoryStats[]>(`/model/${enc(modelId)}/categories`, { run_id: runId }, signal),

  modelOverall: (modelId: string, runId: string, signal?: AbortSignal) =>
    requestJson<OverallStats>(`/model/${enc(modelId)}/overall`, { run_id: runId }, signal),

  caseDetail: (modelId: string, taskName: string, runId?: string, signal?: AbortSignal) =>
    requestJson<CaseDetailData>(`/case/${enc(modelId)}/${enc(taskName)}`, { run_id: runId }, signal),

  datasetDistribution: (signal?: AbortSignal) =>
    requestJson<DatasetDistribution>("/dataset/distribution", undefined, signal),

  exportExcel: (modelId: string, runId: string, signal?: AbortSignal) =>
    requestBlob(`/model/${enc(modelId)}/export`, { run_id: runId }, signal),

  sessions: (modelId: string, taskName: string, runId: string, signal?: AbortSignal) =>
    requestJson<SessionsData>(`/model/${enc(modelId)}/task/${enc(taskName)}/sessions`, { run_id: runId }, signal),

  workspace: (modelId: string, taskName: string, runId: string, signal?: AbortSignal) =>
    requestBlob(`/model/${enc(modelId)}/task/${enc(taskName)}/workspace`, { run_id: runId }, signal),

  traceConfig: (signal?: AbortSignal) =>
    requestJson<TraceConfig>("/trace-config", undefined, signal),
};

/** 触发浏览器下载 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}
