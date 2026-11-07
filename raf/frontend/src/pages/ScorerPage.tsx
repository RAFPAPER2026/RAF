// 评分页：加载 rubric，逐叶子勾选，实时显示完成度 / 质量分并提交
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, RotateCcw, Send } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import * as api from "../lib/api";
import { QueryRubric } from "../lib/types";
import { collectLeafIds, SCORING_MODES, ScoringMode } from "../lib/scoring";
import { useScorerState } from "../hooks/useScorerState";
import RubricTree from "../components/RubricTree";
import ScoreRing from "../components/ScoreRing";

export default function ScorerPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [rubric, setRubric] = useState<QueryRubric | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { results, completion, quality, toggle, reset, scoringMode, setScoringMode } =
    useScorerState(rubric);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 4000);
  };

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .getRubric(id)
      .then((r) => {
        if (cancelled) return;
        setRubric(r);
        reset();
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id, reset]);

  const leafCount = useMemo(() => {
    if (!rubric) return 0;
    return (
      collectLeafIds(rubric.completion_rubric).length +
      collectLeafIds(rubric.quality_rubric.map((item) => item.node)).length
    );
  }, [rubric]);

  const handleSubmit = async () => {
    if (!rubric) return;
    setSubmitting(true);
    try {
      const res = await api.scoreRubric(rubric.id, results, scoringMode);
      flash(`提交成功：完成度 ${res.completion.passed}/${res.completion.total}，质量分 ${res.quality.score.toFixed(2)}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  // 无 id：引导提示
  if (!id) {
    return (
      <div>
        <div className="page-title">评分</div>
        <div className="card">
          <p className="text-sm text-gray-600 mb-3">请从量规列表选择一条量规进入评分页</p>
          <button className="btn-primary" onClick={() => navigate("/list")}>
            前往列表
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="text-sm text-gray-400">加载中…</div>;
  }

  if (error) {
    return (
      <div>
        <div className="page-title">评分</div>
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
        <button className="btn" onClick={() => navigate(-1)}>
          返回
        </button>
      </div>
    );
  }

  // rubric 为 null 的中间态（loading / error 已处理，此处兜底）
  if (!rubric) {
    return <div className="text-sm text-gray-400">加载中…</div>;
  }

  return (
    <div>
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

      {/* 标题行 */}
      <div className="flex items-center gap-3 mb-4">
        <button className="btn shrink-0" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} /> 返回
        </button>
        <h1 className="font-medium text-gray-800 truncate min-w-0" title={rubric.query}>
          {rubric.query}
        </h1>
        <span className="tag shrink-0">{rubric.prompt_version}</span>
        <span className="ml-auto text-xs text-gray-400 shrink-0">{rubric.id}</span>
      </div>

      {/* 顶部汇总 */}
      <div className="card mb-4 flex items-center gap-6">
        <ScoreRing
          value={completion ? (completion.total ? completion.passed / completion.total : 0) : 0}
          label="完成量规"
          sublabel={`${completion?.passed ?? 0}/${completion?.total ?? 0} 通过`}
        />
        <ScoreRing value={quality?.score ?? 0} label="质量量规" sublabel="加权平均" />
        <div className="flex-1">
          {completion?.completed ? (
            <span className="tag bg-green-50 text-green-700 border border-green-200">全部通过 ✓</span>
          ) : (
            <span className="tag bg-gray-50 text-gray-500 border border-gray-200">未全部通过</span>
          )}
          <div className="text-sm text-gray-600 mt-2">共 {leafCount} 个检查叶子</div>
        </div>
        <div className="flex gap-2">
          <select
            className="input text-xs"
            value={scoringMode}
            onChange={(e) => setScoringMode(e.target.value as ScoringMode)}
            title="质量分口径"
          >
            {SCORING_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {mode === "paper" ? "论文口径（AND 组全过才得分）" : "兼容口径（AND 组取均值）"}
              </option>
            ))}
          </select>
          <button className="btn-primary" disabled={submitting} onClick={handleSubmit}>
            <Send size={14} /> 提交评分
          </button>
          <button className="btn" onClick={reset}>
            <RotateCcw size={14} /> 重置勾选
          </button>
        </div>
      </div>

      {/* 两列：完成量规 / 质量量规 */}
      <div className="grid grid-cols-2 gap-4 items-start">
        <div className="card">
          <div className="section-title">完成量规</div>
          <RubricTree nodes={rubric.completion_rubric} mode="score" results={results} onToggle={toggle} />
        </div>
        <div className="card">
          <div className="section-title">质量量规</div>
          {rubric.quality_rubric.map((item, idx) => {
            const itemScore = quality?.itemScores.find((s) => s.nodeId === item.node.id)?.score ?? 0;
            return (
              <div key={item.node.id} className={idx > 0 ? "mt-4" : ""}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="tag bg-amber-50 text-amber-700 border border-amber-200">
                    权重 {item.weight}
                  </span>
                  <span className="text-xs text-gray-400">当前得分 {itemScore.toFixed(2)}</span>
                </div>
                <RubricTree nodes={[item.node]} mode="score" results={results} onToggle={toggle} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
