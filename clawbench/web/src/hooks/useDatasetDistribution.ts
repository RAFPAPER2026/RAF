import { api } from "../api/client";
import type { DatasetDistribution } from "../api/client";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 数据集难度/复杂度分布 */
export function useDatasetDistribution(): ApiState<DatasetDistribution> {
  return useApi((sig) => api.datasetDistribution(sig), []);
}
