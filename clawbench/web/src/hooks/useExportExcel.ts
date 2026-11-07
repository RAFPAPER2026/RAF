import { useCallback, useState } from "react";
import { api, downloadBlob } from "../api/client";
import * as XLSX from "xlsx";
import type { TaskScore } from "../types";
import { fmtScore, fmtDuration, fmtInt } from "../utils/format";

/**
 * 导出 Excel：优先走后端 /export 端点（二进制 .xlsx，文件名 {model_id}_analysis_report.xlsx）；
 * 失败时用前端 xlsx 库基于传入任务数据兜底生成。
 */
export function useExportExcel(
  modelId: string | undefined,
  runId: string,
  tasks?: TaskScore[],
) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const exportExcel = useCallback(async () => {
    if (!modelId) return;
    setExporting(true);
    setError(null);
    const filename = `${modelId}_analysis_report.xlsx`;
    try {
      try {
        const blob = await api.exportExcel(modelId, runId);
        downloadBlob(blob, filename);
        return;
      } catch {
        // 后端导出不可用 → 前端兜底
        if (!tasks || tasks.length === 0) {
          throw new Error("后端导出失败且无本地任务数据可兜底");
        }
        const rows = tasks.map((t) => ({
          任务名: t.task_name,
          分数: fmtScore(t.score),
          通过: (t.score ?? -1) >= 0.75 ? "是" : "否",
          状态: t.status ?? "",
          耗时: fmtDuration(t.duration),
          API调用次数: fmtInt(t.api_calls),
          输入Token: fmtInt(t.input_tokens),
          输出Token: fmtInt(t.output_tokens),
          工具调用: fmtInt(t.tool_calls),
          工具成功率: t.tool_success_rate != null ? `${(t.tool_success_rate * 100).toFixed(1)}%` : "",
        }));
        const ws = XLSX.utils.json_to_sheet(rows);
        ws["!cols"] = [
          { wch: 40 }, { wch: 10 }, { wch: 8 }, { wch: 12 },
          { wch: 10 }, { wch: 12 }, { wch: 12 }, { wch: 12 },
          { wch: 10 }, { wch: 12 },
        ];
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, "任务明细");
        XLSX.writeFile(wb, filename);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }, [modelId, runId, tasks]);

  return { exporting, error, exportExcel };
}
