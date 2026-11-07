// Prompt 版本模块级 diff 对比
import { useEffect, useState } from "react";
import * as api from "../lib/api";
import { PromptVersionDiff } from "../lib/types";

const MODULE_NAMES: Record<string, string> = {
  role: "角色定义",
  structure: "量规结构",
  principles: "设计原则",
  examples: "示例",
  constraints: "输出前自检清单",
  capabilities: "能力项与标签",
  output: "输出要求",
};

interface VersionCompareProps {
  versionA: string;
  versionB: string;
}

export default function VersionCompare({ versionA, versionB }: VersionCompareProps) {
  const [diff, setDiff] = useState<PromptVersionDiff | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setDiff(null);
    setError("");
    api
      .diffPromptVersions(versionA, versionB)
      .then(setDiff)
      .catch((e) => setError(String(e)));
  }, [versionA, versionB]);

  if (error) return <div className="text-sm text-red-600">对比失败：{error}</div>;
  if (!diff) return <div className="text-sm text-gray-400">加载中…</div>;

  return (
    <div className="space-y-4">
      <div className="text-xs text-gray-400">
        对比：<span className="text-red-500 font-medium">{diff.version_old}</span>（旧）→{" "}
        <span className="text-green-600 font-medium">{diff.version_new}</span>（新），共{" "}
        {diff.changed_modules.length} 个模块有变更
      </div>
      {Object.entries(diff.modules).map(([key, m]) => (
        <div key={key} className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b border-gray-200">
            <span className="text-sm font-semibold text-gray-700">{MODULE_NAMES[key] ?? key}</span>
            <code className="text-xs text-gray-400">{key}</code>
            {m.changed ? (
              <span className="tag bg-amber-50 text-amber-700 border border-amber-200">有变更</span>
            ) : (
              <span className="tag bg-gray-50 text-gray-400 border border-gray-200">无变更</span>
            )}
          </div>
          {m.changed && (
            <div className="grid grid-cols-2 divide-x divide-gray-200">
              <div>
                <div className="px-3 py-1 text-xs text-gray-400 bg-red-50/60">旧（{diff.version_old}）</div>
                <pre className="px-3 py-2 text-xs whitespace-pre-wrap max-h-64 overflow-auto">{m.old}</pre>
              </div>
              <div>
                <div className="px-3 py-1 text-xs text-gray-400 bg-green-50/60">新（{diff.version_new}）</div>
                <pre className="px-3 py-2 text-xs whitespace-pre-wrap max-h-64 overflow-auto">{m.new}</pre>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
