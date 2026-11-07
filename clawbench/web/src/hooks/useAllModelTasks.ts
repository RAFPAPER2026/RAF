import { api } from "../api/client";
import type { TaskScore } from "../types";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 多个模型各自的任务（Record<modelId, TaskScore[]>），并行拉取 */
export function useAllModelTasks(
  modelIds: string[],
  runId = "average",
): ApiState<Record<string, TaskScore[]>> {
  return useApi(
    async (sig) => {
      const out: Record<string, TaskScore[]> = {};
      await Promise.all(
        modelIds.map(async (id) => {
          out[id] = await api.modelTasks(id, runId, sig);
        }),
      );
      return out;
    },
    [modelIds.join("|"), runId],
  );
}
