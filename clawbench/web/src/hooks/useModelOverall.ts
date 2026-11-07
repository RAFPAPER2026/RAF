import { api } from "../api/client";
import type { OverallStats } from "../types";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 模型总体统计（按指定 run） */
export function useModelOverall(
  modelId: string | undefined,
  runId: string,
): ApiState<OverallStats> {
  return useApi(
    (sig) => (modelId ? api.modelOverall(modelId, runId, sig) : Promise.resolve(null as unknown as OverallStats)),
    [modelId, runId],
  );
}
