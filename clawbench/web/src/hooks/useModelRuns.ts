import { api } from "../api/client";
import type { ModelRunsData } from "../api/client";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 模型的 run 信息（runs / max_run / per_case_runs） */
export function useModelRuns(modelId: string | undefined): ApiState<ModelRunsData> {
  return useApi(
    (sig) => (modelId ? api.modelRuns(modelId, sig) : Promise.resolve({ runs: [], max_run: 0, per_case_runs: {} })),
    [modelId],
  );
}
