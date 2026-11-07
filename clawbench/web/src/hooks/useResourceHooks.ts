import { useState } from "react";
import { api, downloadBlob } from "../api/client";
import type { SessionsData } from "../api/client";
import { useApi } from "./useApi";
import type { ApiState } from "./useApi";

/** 会话轨迹（sessions.json；仅具体 run，average 需在调用方映射为 run_1） */
export function useSessions(
  modelId: string | undefined,
  taskName: string,
  runId: string,
): ApiState<SessionsData> {
  return useApi(
    (sig) =>
      modelId
        ? api.sessions(modelId, taskName, runId, sig)
        : Promise.resolve({ container: "", sessions: [] }),
    [modelId, taskName, runId],
  );
}

/** 运行日志 parsed_entries */
export function useWorkspaceDownload(
  modelId: string | undefined,
  taskName: string,
  runs: string[],
) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const downloadWorkspace = async () => {
    if (!modelId || runs.length === 0) return;
    setDownloading(true);
    setError(null);
    try {
      for (const runId of runs) {
        const blob = await api.workspace(modelId, taskName, runId);
        downloadBlob(blob, `${modelId}_${taskName}_${runId}.zip`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloading(false);
    }
  };

  return { downloading, error, downloadWorkspace };
}
