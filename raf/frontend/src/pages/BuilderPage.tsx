// 量规构建 / 编辑页：基本信息 + 完成量规（二元判定）+ 质量量规（加权评分）
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import * as api from "../lib/api";
import { PromptVersionSummary, RubricNode, WeightedItem } from "../lib/types";
import { newLeaf } from "../lib/tree";
import RubricTree from "../components/RubricTree";

const WEIGHT_OPTIONS = [1, 2, 3, 4, 6];

export default function BuilderPage() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [query, setQuery] = useState("");
  const [promptVersion, setPromptVersion] = useState("");
  const [completion, setCompletion] = useState<RubricNode[]>([]);
  const [quality, setQuality] = useState<WeightedItem[]>([]);
  const [versions, setVersions] = useState<PromptVersionSummary[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setError("");
      try {
        const pvRes = await api.listPromptVersions();
        if (cancelled) return;
        setVersions(pvRes.versions);
        setPromptVersion((prev) => prev || pvRes.active);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
      try {
        const caps = await api.getCapabilities();
        if (!cancelled) setCapabilities(caps.capabilities);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
      if (id) {
        try {
          const r = await api.getRubric(id);
          if (cancelled) return;
          setQuery(r.query);
          setPromptVersion(r.prompt_version);
          setCompletion(r.completion_rubric);
          setQuality(r.quality_rubric);
        } catch (e) {
          if (!cancelled) setError(String(e));
        }
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const handleAddQuality = () => {
    setQuality((prev) => [...prev, { weight: 1, node: newLeaf("新检查项") }]);
  };

  const handleRemoveQuality = (idx: number) => {
    if (!window.confirm("删除该质量项？")) return;
    setQuality((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setError("");
    if (!query.trim()) {
      setError("Query 不能为空");
      return;
    }
    if (quality.length === 0) {
      if (!window.confirm("质量量规为空，仍要保存吗？")) return;
    }
    const payload = {
      query: query.trim(),
      prompt_version: promptVersion,
      completion_rubric: completion,
      quality_rubric: quality,
    };
    setSaving(true);
    try {
      if (id) await api.updateRubric(id, payload);
      else await api.createRubric(payload);
      navigate("/list");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="page-title mb-0">{id ? "编辑量规" : "量规构建"}</div>
        <button className="btn" onClick={() => navigate("/list")}>
          <ArrowLeft size={14} /> 返回列表
        </button>
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* 基本信息 */}
        <div className="card">
          <div className="section-title">基本信息</div>
          <div className="space-y-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Query 文本</label>
              <textarea
                className="input w-full"
                rows={3}
                value={query}
                placeholder="输入要评估的 query 文本"
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Prompt 版本</label>
              <select
                className="input w-full"
                value={promptVersion}
                onChange={(e) => setPromptVersion(e.target.value)}
              >
                {versions.map((v) => (
                  <option key={v.version} value={v.version}>
                    {v.version}
                    {v.active ? "（活跃）" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* 完成量规 */}
        <div className="card">
          <div className="section-title">完成量规 completion_rubric</div>
          <div className="text-xs text-gray-400 mb-2">
            二元判定：所有顶层项全部通过才算任务完成。顶层项 2-4 个，无权重。
          </div>
          <RubricTree nodes={completion} onChange={setCompletion} mode="edit" capabilities={capabilities} />
        </div>

        {/* 质量量规 */}
        <div className="card">
          <div className="section-title">质量量规 quality_rubric</div>
          <div className="text-xs text-gray-400 mb-2">
            加权评分：权重 = 重要性(1/2/3) × 难度(1/2)，合法值 {"{1, 2, 3, 4, 6}"}。AND 组取平均、OR 组取最大值。
          </div>
          <div className="space-y-2">
            {quality.map((item, idx) => (
              <div key={item.node.id} className="flex items-start gap-2">
                <label className="shrink-0 flex items-center gap-1 mt-2 text-sm text-gray-600">
                  权重
                  <select
                    className="input"
                    value={item.weight}
                    onChange={(e) => {
                      const w = Number(e.target.value);
                      setQuality((prev) =>
                        prev.map((it, i) => (i === idx ? { ...it, weight: w } : it))
                      );
                    }}
                  >
                    {WEIGHT_OPTIONS.map((w) => (
                      <option key={w} value={w}>
                        {w}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex-1">
                  <RubricTree
                    nodes={[item.node]}
                    onChange={(nodes) =>
                      setQuality((prev) =>
                        prev.map((it, i) => (i === idx ? { ...it, node: nodes[0] } : it))
                      )
                    }
                    mode="edit"
                    capabilities={capabilities}
                  />
                </div>
                <button
                  className="btn-danger shrink-0 mt-2"
                  title="删除该质量项"
                  onClick={() => handleRemoveQuality(idx)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {quality.length === 0 && (
              <div className="text-xs text-gray-400 pl-1">（暂无质量项）</div>
            )}
          </div>
          <div className="mt-3">
            <button className="btn" onClick={handleAddQuality}>
              <Plus size={14} /> 添加质量项
            </button>
          </div>
        </div>

        {/* 底部保存 */}
        <div className="flex justify-end">
          <button className="btn-primary" disabled={saving} onClick={handleSave}>
            <Save size={14} /> {saving ? "保存中…" : "保存量规"}
          </button>
        </div>
      </div>
    </div>
  );
}
