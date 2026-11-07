import { api } from "../api/client";
import type { TaskScore } from "../types";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 模型任务列表（按指定 run） */
export function useModelTasks(
  modelId: string | undefined,
  runId: string,
): ApiState<TaskScore[]> {
  return useApi(
    (sig) => (modelId ? api.modelTasks(modelId, runId, sig) : Promise.resolve([] as TaskScore[])),
    [modelId, runId],
  );
}
