// Prompt 版本管理：版本列表、激活/克隆、模块编辑、版本对比、能力项管理
import { useEffect, useState } from "react";
import { Copy, Edit3, FileText, Power, Save } from "lucide-react";
import * as api from "../lib/api";
import { PromptVersionDetail, PromptVersionSummary } from "../lib/types";
import VersionCompare from "../components/VersionCompare";
import ModuleEditor from "../components/ModuleEditor";

// 模块中文名（顺序即展示顺序）
const MODULE_NAMES: Record<string, string> = {
  role: "角色定义",
  structure: "量规结构",
  principles: "设计原则",
  examples: "示例",
  constraints: "输出前自检清单",
  capabilities: "能力项与标签",
  output: "输出要求",
};

const MODULE_ORDER = Object.keys(MODULE_NAMES);

interface PickerState {
  version: string;
}

interface EditorState {
  version: string;
  moduleKey: string;
  moduleName: string;
  initialContent: string;
}

export default function PromptsPage() {
  const [versions, setVersions] = useState<PromptVersionSummary[]>([]);
  const [active, setActive] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [capsText, setCapsText] = useState("");
  const [capsSaving, setCapsSaving] = useState(false);
  const [compareA, setCompareA] = useState("");
  const [compareB, setCompareB] = useState("");
  const [showCompare, setShowCompare] = useState(false);
  const [picker, setPicker] = useState<PickerState | null>(null);
  const [pickerDetail, setPickerDetail] = useState<PromptVersionDetail | null>(null);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [pickerError, setPickerError] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 4000);
  };

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.listPromptVersions();
      setVersions(res.versions);
      setActive(res.active);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    api
      .getCapabilities()
      .then((res) => setCapsText(res.capabilities.join("\n")))
      .catch((e) => setError(String(e)));
  }, []);

  // 版本加载后设置对比默认值（新版本 vs 上一个版本），不覆盖用户已选的值
  useEffect(() => {
    if (versions.length === 0) return;
    const newest = versions[0];
    const previous = versions[1];
    if (newest) setCompareB((prev) => prev || newest.version);
    if (previous) setCompareA((prev) => prev || previous.version);
  }, [versions]);

  // 模块选择弹窗：打开时异步拉取完整 detail
  useEffect(() => {
    if (!picker) return;
    let cancelled = false;
    setPickerDetail(null);
    setPickerError("");
    setPickerLoading(true);
    api
      .getPromptVersion(picker.version)
      .then((d) => {
        if (!cancelled) setPickerDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setPickerError(String(e));
      })
      .finally(() => {
        if (!cancelled) setPickerLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [picker]);

  const handleActivate = async (v: PromptVersionSummary) => {
    if (!window.confirm(`确定激活版本 ${v.version}？激活后将立即生效`)) return;
    try {
      await api.activatePromptVersion(v.version);
      flash(`已激活版本 ${v.version}`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleClone = async (v: PromptVersionSummary) => {
    const newVersion = window.prompt("新版本号（如 v5.10）");
    if (!newVersion || !newVersion.trim()) return;
    try {
      await api.clonePromptVersion(v.version, newVersion.trim());
      flash(`已克隆为 ${newVersion.trim()}`);
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleSaveCaps = async () => {
    setCapsSaving(true);
    setError("");
    try {
      const caps = capsText.split("\n").map((s) => s.trim()).filter(Boolean);
      await api.updateCapabilities(caps);
      flash("能力项已更新");
    } catch (e) {
      setError(String(e));
    } finally {
      setCapsSaving(false);
    }
  };

  const handlePickModule = (key: string) => {
    if (!picker || !pickerDetail) return;
    setEditor({
      version: picker.version,
      moduleKey: key,
      moduleName: MODULE_NAMES[key] ?? key,
      initialContent: pickerDetail.modules[key] ?? "",
    });
    setPicker(null);
  };

  // 指标：pearson_r / qwk / composite 均为数字时显示三个 chip，否则「—」
  const renderMetrics = (v: PromptVersionSummary) => {
    const m = v.metrics_summary;
    const pearson = m?.pearson_r;
    const qwk = m?.qwk;
    const composite = m?.composite;
    if (typeof pearson === "number" && typeof qwk === "number" && typeof composite === "number") {
      return (
        <div className="flex gap-1 flex-wrap">
          <span className="tag">r {pearson}</span>
          <span className="tag">qwk {qwk}</span>
          <span className="tag">comp {composite}</span>
        </div>
      );
    }
    return <span className="text-gray-400">—</span>;
  };

  return (
    <div>
      <div className="page-title flex items-center gap-2">
        <FileText size={20} /> Prompt 版本管理
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}
      {message && (
        <div className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
          {message}
        </div>
      )}

      {/* Prompt 版本列表 */}
      <div className="card mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="section-title mb-0">Prompt 版本（{versions.length}）</div>
          <div className="text-xs text-gray-400">当前激活：{active}</div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b border-gray-200">
              <th className="py-2 pr-2 font-medium w-36">版本</th>
              <th className="py-2 pr-2 font-medium w-20">来源</th>
              <th className="py-2 pr-2 font-medium w-24">创建时间</th>
              <th className="py-2 pr-2 font-medium">变更说明</th>
              <th className="py-2 pr-2 font-medium w-36">指标</th>
              <th className="py-2 font-medium w-44">操作</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 pr-2">
                  <span className="tag font-medium">{v.version}</span>
                  {v.active && (
                    <span className="ml-1 tag bg-green-50 text-green-700 border border-green-200">活跃</span>
                  )}
                </td>
                <td className="py-2 pr-2 text-gray-500">{v.parent_version}</td>
                <td className="py-2 pr-2 text-xs text-gray-400">{v.created_at.slice(0, 10)}</td>
                <td className="py-2 pr-2">
                  <span className="block truncate max-w-[280px] text-gray-600" title={v.change_description}>
                    {v.change_description}
                  </span>
                </td>
                <td className="py-2 pr-2">{renderMetrics(v)}</td>
                <td className="py-2">
                  <div className="flex gap-1">
                    <button
                      className="btn text-xs py-1"
                      disabled={v.active}
                      title={v.active ? "当前已激活" : "激活该版本"}
                      onClick={() => handleActivate(v)}
                    >
                      <Power size={12} /> 激活
                    </button>
                    <button className="btn text-xs py-1" onClick={() => handleClone(v)}>
                      <Copy size={12} /> 克隆
                    </button>
                    <button className="btn text-xs py-1" onClick={() => setPicker({ version: v.version })}>
                      <Edit3 size={12} /> 编辑
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {versions.length === 0 && (
              <tr>
                <td colSpan={6} className="py-8 text-center text-gray-400">
                  {loading ? "加载中…" : "暂无 Prompt 版本"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 版本对比 */}
      <div className="card mb-4">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="section-title mb-0 mr-2">版本对比</div>
          <select className="input" value={compareA} onChange={(e) => setCompareA(e.target.value)}>
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                {v.version}
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-400">对比</span>
          <select className="input" value={compareB} onChange={(e) => setCompareB(e.target.value)}>
            {versions.map((v) => (
              <option key={v.version} value={v.version}>
                {v.version}
              </option>
            ))}
          </select>
          <button className="btn-primary" onClick={() => setShowCompare(true)}>
            对比
          </button>
          <button className="btn" onClick={() => setShowCompare(false)}>
            收起
          </button>
        </div>
        {showCompare && compareA && compareB && (
          <VersionCompare versionA={compareA} versionB={compareB} />
        )}
      </div>

      {/* 能力项管理 */}
      <div className="card">
        <div className="section-title">能力项管理</div>
        <div className="text-xs text-gray-400 mb-2">
          每行一个能力项，格式：名称：说明。生成量规时 tags 取值使用冒号前的名称。
        </div>
        <textarea
          className="input w-full font-mono text-xs"
          rows={10}
          value={capsText}
          onChange={(e) => setCapsText(e.target.value)}
        />
        <div className="mt-2 flex justify-end">
          <button className="btn-primary" disabled={capsSaving} onClick={handleSaveCaps}>
            <Save size={14} /> {capsSaving ? "保存中…" : "保存能力项"}
          </button>
        </div>
      </div>

      {/* 模块选择弹窗 */}
      {picker && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
          onClick={() => setPicker(null)}
        >
          <div
            className="bg-white rounded-lg shadow-xl w-[80%] max-w-3xl max-h-[85vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
              <div className="text-sm font-semibold text-gray-800">
                选择要编辑的模块（{picker.version}）
              </div>
              <button className="btn" onClick={() => setPicker(null)}>
                关闭
              </button>
            </div>
            <div className="p-4 overflow-auto">
              {pickerError && (
                <div className="text-sm text-red-600 mb-2">加载失败：{pickerError}</div>
              )}
              {pickerLoading && <div className="text-sm text-gray-400">加载中…</div>}
              {pickerDetail && (
                <div className="space-y-2">
                  {MODULE_ORDER.map((key) => (
                    <button
                      key={key}
                      className="w-full flex items-center justify-between px-3 py-2 border border-gray-200 rounded-md text-left hover:bg-gray-50"
                      onClick={() => handlePickModule(key)}
                    >
                      <span className="flex items-center gap-2 text-sm text-gray-700">
                        {MODULE_NAMES[key]}
                        <code className="text-xs text-gray-400">{key}</code>
                      </span>
                      <span className="text-xs text-gray-400">
                        {(pickerDetail.modules[key] ?? "").length} 字符
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 模块编辑弹窗 */}
      {editor && (
        <ModuleEditor
          {...editor}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            flash("模块已保存");
            load();
          }}
        />
      )}
    </div>
  );
}
