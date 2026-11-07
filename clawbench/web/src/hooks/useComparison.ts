import { api } from "../api/client";
import type { ComparisonData } from "../types";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 模型对比数据（按维度） */
export function useComparison(
  dimension: string,
  runId?: string,
): ApiState<ComparisonData> {
  return useApi((sig) => api.comparison(dimension, runId, sig), [dimension, runId]);
}
