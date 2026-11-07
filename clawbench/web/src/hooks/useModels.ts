import { api } from "../api/client";
import type { ModelInfo } from "../types";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 模型列表（按时间戳倒序） */
export function useModels(): ApiState<ModelInfo[]> {
  return useApi((sig) => api.models(sig), []);
}
