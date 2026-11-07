// 人工审核页：查看量规树并提交完成量规 / 质量量规的人工评分与备注
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Send } from "lucide-react";
import * as api from "../lib/api";
import { QueryRubric, RubricReview } from "../lib/types";
import RubricTree from "../components/RubricTree";
import StarRating from "../components/StarRating";

// 把任意长度的字符串数组补齐为恰好 3 个备注
function padNotes(src: string[]): [string, string, string] {
  return [src[0] ?? "", src[1] ?? "", src[2] ?? ""];
}

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [rubric, setRubric] = useState<QueryRubric | null>(null);
  const [review, setReview] = useState<RubricReview | null>(null);
  const [completionScore, setCompletionScore] = useState(3);
  const [qualityScore, setQualityScore] = useState(3);
  const [notes, setNotes] = useState<[string, string, string]>(["", "", ""]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 4000);
  };

  const updateNote = (i: number, value: string) => {
    setNotes((prev) => {
      const next: [string, string, string] = [...prev];
      next[i] = value;
      return next;
    });
  };

  useEffect(() => {
    const load = async () => {
      if (!id) {
        setError("无效的 URL：缺少量规 ID");
        return;
      }
      setLoading(true);
      setError("");
      try {
        const r = await api.getRubric(id);
        setRubric(r);
        try {
          const rev = await api.getReviewForRubric(id);
          setReview(rev);
          setCompletionScore(rev.completion_score);
          setQualityScore(rev.quality_score);
          setNotes(padNotes(rev.notes));
        } catch {
          // 尚无审核（404），保持 review 为 null，不显示错误
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const handleSubmit = async () => {
    if (!rubric) return;
    setSubmitting(true);
    setError("");
    try {
      await api.submitReview({
        rubric_id: rubric.id,
        completion_score: completionScore,
        quality_score: qualityScore,
        notes,
      });
      flash("审核已提交");
      const rev = await api.getReviewForRubric(rubric.id);
      setReview(rev);
      setCompletionScore(rev.completion_score);
      setQualityScore(rev.quality_score);
      setNotes(padNotes(rev.notes));
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="text-gray-400">加载中…</div>;
  if (error && !rubric) {
    return <div className="px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>;
  }
  if (!rubric) return null;

  return (
    <div>
      {error && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>
      )}
      {message && (
        <div className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
          {message}
        </div>
      )}

      {/* 标题行 */}
      <div className="flex items-center gap-2 mb-4">
        <button className="btn" onClick={() => navigate(-1)} title="返回">
          <ArrowLeft size={14} /> 返回
        </button>
        <h1 className="page-title mb-0 flex-1 min-w-0 truncate">{rubric.query}</h1>
        <span className="tag shrink-0">{rubric.prompt_version}</span>
      </div>

      {/* 只读量规树 */}
      <div className="grid grid-cols-2 gap-4">
        <div className="card">
          <div className="section-title">完成量规</div>
          <RubricTree nodes={rubric.completion_rubric} mode="view" />
        </div>
        <div className="card">
          <div className="section-title">质量量规</div>
          <div className="space-y-3">
            {rubric.quality_rubric.map((item) => (
              <div key={item.node.id}>
                <span className="tag bg-amber-50 text-amber-700 mb-1">权重 {item.weight}</span>
                <RubricTree nodes={[item.node]} mode="view" />
              </div>
            ))}
            {rubric.quality_rubric.length === 0 && (
              <div className="text-xs text-gray-400">（暂无质量量规项）</div>
            )}
          </div>
        </div>
      </div>

      {/* 人工审核 */}
      <div className="card mt-4">
        <div className="section-title flex items-center gap-1.5">
          <CheckCircle2 size={15} className="text-blue-600" /> 人工审核
        </div>
        {review && (
          <div className="text-xs text-gray-400 mb-3">
            已有审核（{review.created_at.slice(0, 16)}），重新提交将覆盖
          </div>
        )}
        <div className="space-y-3">
          <StarRating value={completionScore} onChange={setCompletionScore} label="完成量规评分" />
          <StarRating value={qualityScore} onChange={setQualityScore} label="质量量规评分" />
          {[0, 1, 2].map((i) => (
            <div key={i}>
              <label className="block text-sm text-gray-600 mb-1">备注 {i + 1}</label>
              <textarea
                className="input w-full"
                rows={2}
                value={notes[i]}
                placeholder={`备注 ${i + 1}（可选）`}
                onChange={(e) => updateNote(i, e.target.value)}
              />
            </div>
          ))}
          <div className="flex justify-end pt-1">
            <button className="btn-primary" onClick={handleSubmit} disabled={submitting}>
              <Send size={14} /> {submitting ? "提交中…" : "提交审核"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
