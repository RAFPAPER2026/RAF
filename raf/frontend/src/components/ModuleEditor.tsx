// Prompt 模块编辑器（弹窗）
import { useState } from "react";
import * as api from "../lib/api";

interface ModuleEditorProps {
  version: string;
  moduleKey: string;
  moduleName: string;
  initialContent: string;
  onClose: () => void;
  onSaved: () => void;
}

export default function ModuleEditor({
  version,
  moduleKey,
  moduleName,
  initialContent,
  onClose,
  onSaved,
}: ModuleEditorProps) {
  const [content, setContent] = useState(initialContent);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setSaving(true);
    setError("");
    try {
      await api.updatePromptModule(version, moduleKey, content);
      onSaved();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl w-[80%] max-w-4xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <div className="text-sm font-semibold text-gray-800">
            编辑模块：{moduleName}
            <code className="ml-2 text-xs text-gray-400">
              {version}/{moduleKey}
            </code>
          </div>
          <button className="btn" onClick={onClose}>
            关闭
          </button>
        </div>
        <textarea
          className="flex-1 m-4 p-3 font-mono text-xs border border-gray-200 rounded-md resize-none min-h-[50vh] focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        {error && <div className="px-4 pb-2 text-sm text-red-600">保存失败：{error}</div>}
        <div className="px-4 py-3 border-t border-gray-200 flex justify-end gap-2">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn-primary" disabled={saving} onClick={save}>
            {saving ? "保存中…" : "保存模块"}
          </button>
        </div>
      </div>
    </div>
  );
}
