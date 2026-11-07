// 优化运行工作台：运行列表、轮次流程（生成→评分→指标→诊断→采纳）、建议采纳与中止判断
import { useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, FlaskConical, Play, RefreshCw, Trash2, XCircle } from "lucide-react";
import RubricBatchPreview from "../components/RubricBatchPreview";
import StepIndicator from "../components/StepIndicator";
import * as api from "../lib/api";
import {
  BatchGenerateStatus,
  OptimizationRun,
  PromptVersionSummary,
  QueryItem,
  RoundResult,
  ScoreEntry,
  StoppingCheck,
} from "../lib/types";

const ROUND_STEPS = ["生成量规", "提交评分", "计算指标", "RIFT 诊断", "采纳精炼", "中止判断"];

const STATUS_LABELS: Record<string, string> = {
  generating: "生成中",
  generated: "已生成",
  rejected: "初筛否决",
  scored: "已评分",
  metrics: "已算指标",
  analyzed: "已诊断",
  refined: "已精炼",
  generate_error: "生成失败",
};

const RUN_STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  converged: "已收敛",
  stopped: "已停止",
};

const PATTERN_NAMES: Record<string, string> = {
  subjective: "主观",
  non_atomic: "非原子",
  ungrounded: "无依据",
  misaligned: "目标-过程混淆",
  missing_criteria: "意图遗漏",
  hackable: "可hack",
  low_signal: "低区分",
  redundant: "冗余",
};

function stepIndexForStatus(status: string): number {
  switch (status) {
    case "generating":
      return 0;
    case "generated":
    case "scored":
      return 1;
    case "metrics":
      return 2;
    case "rejected":
    case "analyzed":
      return 3;
    case "refined":
      return 4;
    default:
      return 0;
  }
}

function bumpVersion(v: string): string {
  const m = v.match(/^v(\d+)\.(\d+)$/);
  if (!m) return `${v}.1`;
  return `v${m[1]}.${Number(m[2]) + 1}`;
}

interface ScoreDraft {
  gold: string;
  raters: Record<string, string>;
}

function buildDrafts(round: RoundResult, run: OptimizationRun): Record<string, ScoreDraft> {
  const nonGold = run.rater_ids.filter((r) => r !== "gold");
  const drafts: Record<string, ScoreDraft> = {};
  for (const rubric of round.rubrics ?? []) {
    const entry = round.score_sheet.entries.find((e) => e.rubric_id === rubric.id);
    const raters: Record<string, string> = {};
    for (const r of nonGold) raters[r] = entry?.rater_scores[r]?.toString() ?? "";
    drafts[rubric.id] = { gold: entry?.gold_score?.toString() ?? "", raters };
  }
  return drafts;
}

export default function OptimizePage() {
  const [runs, setRuns] = useState<OptimizationRun[]>([]);
  const [run, setRun] = useState<OptimizationRun | null>(null);
  const [versions, setVersions] = useState<PromptVersionSummary[]>([]);
  const [queries, setQueries] = useState<QueryItem[]>([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyMsg, setBusyMsg] = useState("");

  // 新建运行表单
  const [formName, setFormName] = useState("");
  const [formVersion, setFormVersion] = useState("");
  const [formQueryIds, setFormQueryIds] = useState<Set<string>>(new Set());
  const [formRaters, setFormRaters] = useState("gold,rater1,rater2");

  // 轮次交互
  const [roundNo, setRoundNo] = useState(0);
  const [drafts, setDrafts] = useState<Record<string, ScoreDraft>>({});
  const [acceptedIds, setAcceptedIds] = useState<Set<string>>(new Set());
  const [newVersion, setNewVersion] = useState("");
  const [reviewComment, setReviewComment] = useState("");
  const [stopCheck, setStopCheck] = useState<StoppingCheck | null>(null);
  const [taskStatus, setTaskStatus] = useState<BatchGenerateStatus | null>(null);

  const flash = (msg: string) => {
    setMessage(msg);
    window.setTimeout(() => setMessage(""), 5000);
  };

  const loadRuns = async () => {
    setRuns(await api.listOptimizationRuns());
  };

  const loadRun = async (id: string) => {
    const detail = await api.getOptimizationRun(id);
    setRun(detail);
  };

  const currentRound = run?.rounds.find((r) => r.round_number === roundNo) ?? null;

  // 初始加载
  useEffect(() => {
    (async () => {
      setError("");
      try {
        const [vs, qs, rs] = await Promise.all([
          api.listPromptVersions(),
          api.listQueries(),
          api.listOptimizationRuns(),
        ]);
        setVersions(vs.versions);
        setFormVersion(vs.active);
        setQueries(qs);
        setRuns(rs);
        if (rs.length > 0) await loadRun(rs[0].run_id);
      } catch (e) {
        setError(String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // run 变化时同步轮次选择与草稿
  useEffect(() => {
    if (!run) return;
    const rounds = run.rounds;
    if (rounds.length === 0) {
      setRoundNo(0);
      return;
    }
    const exists = rounds.some((r) => r.round_number === roundNo);
    if (!exists) {
      const latest = rounds[rounds.length - 1].round_number;
      setRoundNo(latest);
      return;
    }
    const round = rounds.find((r) => r.round_number === roundNo);
    if (round) {
      setDrafts(buildDrafts(round, run));
      setAcceptedIds(new Set(round.suggestions.filter((s) => s.accepted).map((s) => s.id)));
      setNewVersion(bumpVersion(round.prompt_version));
      setReviewComment(round.quality_review?.comment ?? "");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id, run?.rounds, roundNo]);

  // 生成中轮询（3 秒）
  useEffect(() => {
    if (!run) return;
    const generatingRound = run.rounds.find((r) => r.status === "generating");
    if (!generatingRound) {
      setTaskStatus(null);
      return;
    }
    const tick = async () => {
      if (!run) return;
      try {
        await loadRun(run.run_id);
        if (generatingRound.generation_task_id) {
          setTaskStatus(await api.getGenerateStatus(generatingRound.generation_task_id));
        }
      } catch {
        // 轮询失败静默，等待下一轮
      }
    };
    tick();
    const timer = window.setInterval(tick, 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.run_id, run?.rounds]);

  const act = async (fn: () => Promise<unknown>, okMsg?: string, busyMsg = "") => {
    setBusy(true);
    setBusyMsg(busyMsg);
    setError("");
    try {
      await fn();
      if (okMsg) flash(okMsg);
      if (run) await loadRun(run.run_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setBusyMsg("");
    }
  };

  // ---------- 操作 ----------

  const handleCreateRun = async () => {
    if (formQueryIds.size === 0) {
      setError("请至少选择一个 query");
      return;
    }
    const raters = formRaters.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    if (raters.length === 0) {
      setError("请至少填写一个评分者（含 gold）");
      return;
    }
    await act(async () => {
      const created = await api.createOptimizationRun({
        name: formName.trim(),
        query_ids: [...formQueryIds],
        rater_ids: raters,
        prompt_version: formVersion,
      });
      await loadRuns();
      await loadRun(created.run_id);
    }, "运行已创建");
  };

  const handleStartRound = () => {
    if (!run) return;
    act(() => api.startOptimizationRound(run.run_id), "新轮次已开始，正在后台批量生成 rubric…");
  };

  const handleSaveScores = () => {
    if (!run || !currentRound) return;
    const rubrics = currentRound.rubrics ?? [];
    if (rubrics.length === 0) {
      setError("该轮次没有 rubric（生成可能失败）");
      return;
    }
    const entries: ScoreEntry[] = [];
    for (const rubric of rubrics) {
      const draft = drafts[rubric.id];
      if (!draft || draft.gold.trim() === "") {
        setError(`请填写所有 rubric 的 gold 分数（缺少：${rubric.query.slice(0, 30)}…）`);
        return;
      }
      const gold = Number(draft.gold);
      if (Number.isNaN(gold) || gold < 0 || gold > 1) {
        setError("gold 分数必须是 0-1 之间的数字");
        return;
      }
      const rater_scores: Record<string, number> = {};
      for (const [rater, val] of Object.entries(draft.raters)) {
        if (val.trim() === "") continue;
        const n = Number(val);
        if (Number.isNaN(n) || n < 0 || n > 1) {
          setError(`评分者「${rater}」的分数必须是 0-1 之间的数字`);
          return;
        }
        rater_scores[rater] = n;
      }
      entries.push({ rubric_id: rubric.id, gold_score: gold, rater_scores });
    }
    act(() => api.submitRoundScores(run.run_id, roundNo, entries), "评分已提交");
  };

  const handleCheckStop = () => {
    if (!run) return;
    act(async () => {
      setStopCheck(await api.checkOptimizationStop(run.run_id));
    }, undefined);
  };

  const handleDeleteRun = (target: OptimizationRun) => {
    if (!window.confirm(`删除运行「${target.name || target.run_id}」？其全部轮次记录将一并删除且不可恢复。`)) {
      return;
    }
    act(async () => {
      await api.deleteOptimizationRun(target.run_id);
      const rest = await api.listOptimizationRuns();
      setRuns(rest);
      if (run?.run_id === target.run_id) {
        setStopCheck(null);
        setTaskStatus(null);
        if (rest.length > 0) {
          await loadRun(rest[0].run_id);
        } else {
          setRun(null);
          setRoundNo(0);
        }
      }
    }, "运行已删除");
  };

  const handleReviewQuality = (decision: "approved" | "rejected") => {
    if (!run || !currentRound) return;
    act(
      () => api.reviewRoundQuality(run.run_id, roundNo, decision, reviewComment.trim()),
      decision === "approved"
        ? "初筛通过：可填写评分表进入正常流程"
        : "初筛否决：跳过评分与指标，可直接点「RIFT 诊断」"
    );
  };

  // ---------- 渲染 ----------

  const nonGoldRaters = run ? run.rater_ids.filter((r) => r !== "gold") : [];
  const round = currentRound;
  const generating = run?.rounds.some((r) => r.status === "generating") ?? false;
  // 人工质量初筛：闸门可编辑窗口（初筛/改判），进入评分或诊断后锁定
  const gateEditable =
    !!round &&
    (round.rubrics?.length ?? 0) > 0 &&
    (round.status === "generated" || round.status === "generate_error" || round.status === "rejected");
  // 粘性否决：否决轮诊断后 status 变 analyzed，评分/指标仍要锁
  const reviewRejected = round?.quality_review?.decision === "rejected";

  return (
    <div>
      <div className="page-title flex items-center gap-2">
        <FlaskConical size={20} /> 优化实验（PROMPT-R）
      </div>

      {error && (
        <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">{error}</div>
      )}
      {message && (
        <div className="mb-4 px-3 py-2 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">{message}</div>
      )}
      {busy && busyMsg && (
        <div className="mb-4 px-3 py-2 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">
          处理中… {busyMsg}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 items-start">
        {/* 左：运行列表 + 新建 */}
        <div className="space-y-4">
          <div className="card">
            <div className="section-title">运行列表（{runs.length}）</div>
            <div className="space-y-1.5 max-h-72 overflow-auto">
              {runs.map((r) => (
                <div key={r.run_id} className="flex items-start gap-1 group">
                  <button
                    onClick={() => {
                      setStopCheck(null);
                      act(() => loadRun(r.run_id));
                    }}
                    className={`flex-1 min-w-0 text-left px-2.5 py-2 rounded-md border text-sm transition-colors ${
                      run?.run_id === r.run_id
                        ? "border-blue-300 bg-blue-50 text-blue-700"
                        : "border-gray-200 hover:border-blue-200 hover:bg-gray-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{r.name}</span>
                      <span className="text-[11px] text-gray-400 shrink-0">
                        {RUN_STATUS_LABELS[r.status] ?? r.status}
                      </span>
                    </div>
                    <div className="text-[11px] text-gray-400 mt-0.5">
                      {r.current_prompt_version} · {r.rounds.length} 轮 · {r.query_ids.length} queries
                    </div>
                  </button>
                  <button
                    title="删除运行"
                    disabled={busy}
                    onClick={() => handleDeleteRun(r)}
                    className="p-1.5 mt-1 rounded-md text-gray-300 hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-colors shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {runs.length === 0 && <div className="text-xs text-gray-400">暂无运行，请在右侧『新建运行』表单创建</div>}
            </div>
          </div>

          <div className="card">
            <div className="section-title">新建运行</div>
            <div className="space-y-2.5">
              <div>
                <label className="block text-xs text-gray-500 mb-1">名称（可选）</label>
                <input className="input w-full" value={formName} placeholder="如：v5.9 调优实验" onChange={(e) => setFormName(e.target.value)} />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">初始 prompt 版本</label>
                <select className="input w-full" value={formVersion} onChange={(e) => setFormVersion(e.target.value)}>
                  {versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      {v.version}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">query（勾选）</label>
                <div className="max-h-40 overflow-auto border border-gray-200 rounded-md p-2 space-y-1">
                  {queries.map((q) => (
                    <label key={q.id} className="flex items-start gap-2 text-xs cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5">
                      <input
                        type="checkbox"
                        className="mt-0.5 accent-blue-600"
                        checked={formQueryIds.has(q.id)}
                        onChange={(e) => {
                          const next = new Set(formQueryIds);
                          if (e.target.checked) next.add(q.id);
                          else next.delete(q.id);
                          setFormQueryIds(next);
                        }}
                      />
                      <span className="line-clamp-2 text-gray-600">{q.text}</span>
                    </label>
                  ))}
                  {queries.length === 0 && <div className="text-xs text-gray-400">暂无 query，请先在「Query 管理」页创建</div>}
                </div>
                {formQueryIds.size < 2 && formQueryIds.size > 0 && (
                  <div className="text-[11px] text-amber-600 mt-1">
                    一致性指标需要至少 2 条 rubric 评分（2 个 query）；单 query 仅能走「质量初筛 → 直接诊断」分支
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">评分者（逗号分隔，含 gold）</label>
                <input className="input w-full" value={formRaters} onChange={(e) => setFormRaters(e.target.value)} />
              </div>
              <button className="btn-primary w-full justify-center" disabled={busy} onClick={handleCreateRun}>
                <Play size={14} /> 创建运行
              </button>
            </div>
          </div>
        </div>

        {/* 右：运行详情 */}
        <div className="xl:col-span-3 space-y-4">
          {!run && <div className="card text-sm text-gray-400">选择一个运行或新建一个运行开始 PROMPT-R 优化循环。</div>}

          {run && (
            <>
              <div className="card">
                <div className="flex items-center justify-between flex-wrap gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-800">{run.name}</span>
                      <span className={`tag ${run.status === "converged" ? "bg-green-50 text-green-700" : "bg-blue-50 text-blue-700"}`}>
                        {RUN_STATUS_LABELS[run.status] ?? run.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400 mt-1">
                      {run.run_id} · {run.created_at.slice(0, 16)} · queries={run.query_ids.length} · 评分者：{run.rater_ids.join(", ")}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="btn" disabled={busy || generating} onClick={() => act(() => loadRuns().then(() => run && loadRun(run.run_id)))} title="刷新">
                      <RefreshCw size={14} /> 刷新
                    </button>
                    <button className="btn" disabled={busy} onClick={handleCheckStop}>
                      中止判断
                    </button>
                    <button className="btn-primary" disabled={busy || generating} onClick={handleStartRound}>
                      <Play size={14} /> 开始新轮次
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {run.rounds.map((r) => (
                    <button
                      key={r.round_number}
                      onClick={() => setRoundNo(r.round_number)}
                      className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                        r.round_number === roundNo
                          ? "border-blue-300 bg-blue-50 text-blue-700 font-medium"
                          : "border-gray-200 text-gray-500 hover:border-blue-200"
                      }`}
                    >
                      Round {r.round_number} · {r.prompt_version} · {STATUS_LABELS[r.status] ?? r.status}
                    </button>
                  ))}
                </div>
              </div>

              {stopCheck && (
                <div className={`card border-l-4 ${stopCheck.should_stop ? "border-l-green-500" : "border-l-amber-400"}`}>
                  <div className="flex items-center gap-2 text-sm">
                    {stopCheck.should_stop ? (
                      <CheckCircle2 size={16} className="text-green-600" />
                    ) : (
                      <RefreshCw size={16} className="text-amber-500" />
                    )}
                    <span className={`font-medium ${stopCheck.should_stop ? "text-green-700" : "text-amber-700"}`}>
                      中止判断：{stopCheck.should_stop ? "建议停止" : "继续优化"} — {stopCheck.reason}
                    </span>
                  </div>
                  {stopCheck.metrics?.composite != null && (
                    <div className="text-xs text-gray-400 mt-1">
                      最新 composite={stopCheck.metrics.composite.toFixed(3)}（阈值：r≥{stopCheck.thresholds.pearson_r_target}、qwk≥{stopCheck.thresholds.qwk_target}、δ≥{stopCheck.thresholds.min_delta}、最大 {stopCheck.thresholds.max_rounds} 轮）
                    </div>
                  )}
                </div>
              )}

              {round && (
                <div className="card">
                  <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                    <StepIndicator steps={ROUND_STEPS} current={stepIndexForStatus(round.status)} />
                    <span className="text-xs text-gray-400">
                      当前 prompt 版本：<span className="tag">{round.prompt_version}</span>
                      {round.refined_prompt_version && (
                        <>
                          {" → "}
                          <span className="tag bg-green-50 text-green-700">{round.refined_prompt_version}</span>
                        </>
                      )}
                    </span>
                  </div>

                  {/* 初筛结论徽标（已进入评分/诊断/精炼的已审轮） */}
                  {!gateEditable && round.quality_review && (
                    <div className="mb-3 flex items-center gap-2 flex-wrap">
                      {round.quality_review.decision === "approved" ? (
                        <span className="tag bg-green-50 text-green-700">初筛：尚可</span>
                      ) : (
                        <span className="tag bg-red-50 text-red-700">初筛：否决（跳过评分）</span>
                      )}
                      {round.quality_review.comment && (
                        <span className="text-xs text-gray-500">备注：{round.quality_review.comment}</span>
                      )}
                    </div>
                  )}

                  {round.status === "generating" && (
                    <div className="mb-3 px-3 py-2 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">
                      正在批量生成 rubric…（3 秒自动刷新）
                      {taskStatus && (
                        <span className="ml-2 text-xs">
                          进度：{Object.values(taskStatus.progress).filter((s) => s === "done").length}/{taskStatus.total}
                          {Object.values(taskStatus.progress).filter((s) => s === "error").length > 0 &&
                            ` · 失败 ${Object.values(taskStatus.progress).filter((s) => s === "error").length}`}
                        </span>
                      )}
                    </div>
                  )}
                  {round.status === "generate_error" && (
                    <div className="mb-3 px-3 py-2 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
                      批量生成全部失败，请检查 llm_config.json 后重新开始轮次
                    </div>
                  )}

                  {/* 人工质量初筛闸门（生成后整批粗看，一次判断） */}
                  {gateEditable && (
                    <div className="mb-4 border border-amber-200 rounded-md overflow-hidden">
                      <div className="px-3 py-2 bg-amber-50 border-b border-amber-200 flex items-center justify-between gap-2 flex-wrap">
                        <div className="text-sm font-medium text-amber-800 flex items-center gap-1.5">
                          <ClipboardCheck size={15} /> 人工质量初筛（整批粗看，一次判断）
                        </div>
                        {round.quality_review && (
                          <span className="text-[11px] text-amber-600">
                            已有结论：{round.quality_review.decision === "approved" ? "尚可" : "否决"}（
                            {round.quality_review.created_at.slice(0, 16)}）；进入评分/诊断前可改判
                          </span>
                        )}
                      </div>
                      <div className="p-3 bg-white">
                        <RubricBatchPreview rubrics={round.rubrics ?? []} />
                        <textarea
                          className="input w-full mt-3"
                          rows={2}
                          placeholder="备注（可选）：整批 rubric 的总体印象 / 主要问题……"
                          value={reviewComment}
                          onChange={(e) => setReviewComment(e.target.value)}
                        />
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            className={round.quality_review?.decision === "approved" ? "btn-primary" : "btn"}
                            disabled={busy}
                            onClick={() => handleReviewQuality("approved")}
                            title="质量尚可：进入正常流程（评分 → 指标 → 诊断）"
                          >
                            <CheckCircle2 size={14} /> 尚可，进入评分
                          </button>
                          <button
                            className={
                              round.quality_review?.decision === "rejected"
                                ? "btn border-red-300 bg-red-50 text-red-700 hover:border-red-400"
                                : "btn border-red-200 text-red-600 hover:border-red-400 hover:bg-red-50"
                            }
                            disabled={busy}
                            onClick={() => handleReviewQuality("rejected")}
                            title="质量不行：跳过评分与指标，直接进入 RIFT 诊断"
                          >
                            <XCircle size={14} /> 不行，跳过评分直接诊断
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 评分表（初筛否决轮不提供） */}
                  {(round.rubrics?.length ?? 0) > 0 && round.status !== "generating" && !reviewRejected && (
                    <div className="mb-4">
                      <div className="section-title">评分表（gold + 评分者，0-1 连续分数）</div>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm border border-gray-200 rounded-md">
                          <thead>
                            <tr className="text-left text-xs text-gray-400 bg-gray-50 border-b border-gray-200">
                              <th className="py-2 px-2 font-medium">rubric（query）</th>
                              <th className="py-2 px-2 font-medium w-24">gold</th>
                              {nonGoldRaters.map((r) => (
                                <th key={r} className="py-2 px-2 font-medium w-24">
                                  {r}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {(round.rubrics ?? []).map((rubric) => {
                              const draft = drafts[rubric.id] ?? { gold: "", raters: {} };
                              return (
                                <tr key={rubric.id} className="border-b border-gray-100 last:border-b-0">
                                  <td className="py-1.5 px-2">
                                    <span className="line-clamp-2 text-gray-600 text-xs" title={rubric.query}>
                                      {rubric.query}
                                    </span>
                                  </td>
                                  <td className="py-1.5 px-2">
                                    <input
                                      className="input w-full py-1"
                                      value={draft.gold}
                                      placeholder="0-1"
                                      onChange={(e) =>
                                        setDrafts((prev) => ({
                                          ...prev,
                                          [rubric.id]: { ...prev[rubric.id], gold: e.target.value },
                                        }))
                                      }
                                    />
                                  </td>
                                  {nonGoldRaters.map((rater) => (
                                    <td key={rater} className="py-1.5 px-2">
                                      <input
                                        className="input w-full py-1"
                                        value={draft.raters[rater] ?? ""}
                                        placeholder="0-1"
                                        onChange={(e) =>
                                          setDrafts((prev) => ({
                                            ...prev,
                                            [rubric.id]: {
                                              ...prev[rubric.id],
                                              raters: { ...prev[rubric.id].raters, [rater]: e.target.value },
                                            },
                                          }))
                                        }
                                      />
                                    </td>
                                  ))}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      <div className="mt-2 flex gap-2">
                        <button
                          className="btn-primary"
                          disabled={busy || reviewRejected}
                          title={reviewRejected ? "该轮已被初筛否决，不能评分" : undefined}
                          onClick={handleSaveScores}
                        >
                          保存评分
                        </button>
                      </div>
                    </div>
                  )}

                  {/* 操作按钮 */}
                  <div className="flex flex-wrap gap-2 mb-4">
                    <button
                      className="btn"
                      disabled={busy || round.score_sheet.entries.length === 0 || reviewRejected}
                      title={reviewRejected ? "该轮已被初筛否决，已跳过指标计算" : undefined}
                      onClick={() => act(() => api.computeRoundMetrics(run.run_id, roundNo), "指标已计算（不调 LLM）")}
                    >
                      计算指标
                    </button>
                    <button
                      className="btn"
                      disabled={busy || !(round.metrics || reviewRejected || round.status === "rejected")}
                      title={round.metrics ? undefined : reviewRejected || round.status === "rejected" ? "该轮已跳过评分，直接诊断本批 rubric" : "请先完成评分并计算指标"}
                      onClick={() => act(() => api.analyzeRound(run.run_id, roundNo), "RIFT 诊断完成",
                        "RIFT 诊断：对每条 rubric 调用 LLM 分析并聚合（通常 1-5 分钟），请勿关闭页面")}
                    >
                      RIFT 诊断
                    </button>
                    <button
                      className="btn"
                      disabled={busy || !round.diagnosis}
                      onClick={() => act(() => api.reDiagnoseRound(run.run_id, roundNo), "重新诊断完成",
                        "重新诊断：再次调用 LLM 分析（通常 1-5 分钟），请勿关闭页面")}
                    >
                      重新诊断
                    </button>
                  </div>

                  {/* 指标 */}
                  {round.metrics && (
                    <div className="mb-4">
                      <div className="section-title">一致性指标</div>
                      {round.metrics.error && <div className="text-xs text-amber-600 mb-2">{round.metrics.error}</div>}
                      <div className="grid grid-cols-4 gap-2 mb-3">
                        {[
                          { label: "Pearson r", value: round.metrics.pearson_r },
                          { label: "Spearman ρ", value: round.metrics.spearman_rho },
                          { label: "QWK", value: round.metrics.qwk },
                          { label: "Composite", value: round.metrics.composite },
                        ].map((m) => (
                          <div key={m.label} className="border border-gray-200 rounded-md px-3 py-2 text-center">
                            <div className="text-lg font-bold text-gray-800">
                              {m.value == null ? "—" : m.value.toFixed(3)}
                            </div>
                            <div className="text-xs text-gray-400">{m.label}</div>
                          </div>
                        ))}
                      </div>
                      {Object.keys(round.metrics.per_query_deviation).length > 0 && (
                        <div className="max-h-40 overflow-auto">
                          <table className="w-full text-xs border border-gray-200 rounded-md">
                            <thead>
                              <tr className="text-left text-gray-400 bg-gray-50 border-b border-gray-200">
                                <th className="py-1.5 px-2 font-medium">rubric</th>
                                <th className="py-1.5 px-2 font-medium w-28">偏差（评分者均值 − gold）</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(round.metrics.per_query_deviation).map(([rubricId, dev]) => (
                                <tr key={rubricId} className="border-b border-gray-100 last:border-b-0">
                                  <td className="py-1.5 px-2 text-gray-600">
                                    <span className="line-clamp-1">
                                      {(round.rubrics ?? []).find((r) => r.id === rubricId)?.query ?? rubricId}
                                    </span>
                                  </td>
                                  <td className={`py-1.5 px-2 font-medium ${Math.abs(dev) > 0.2 ? "text-red-600" : "text-gray-600"}`}>
                                    {dev >= 0 ? "+" : ""}
                                    {dev.toFixed(3)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 诊断 */}
                  {round.diagnosis && (
                    <div className="mb-4">
                      <div className="section-title">RIFT 诊断（{round.diagnosis.findings.length} 条 finding）</div>
                      {round.diagnosis.aggregated && (
                        <div className="text-sm text-gray-600 bg-gray-50 border border-gray-200 rounded-md px-3 py-2 mb-2 whitespace-pre-wrap">
                          {round.diagnosis.aggregated}
                        </div>
                      )}
                      {round.diagnosis.errors.length > 0 && (
                        <div className="text-xs text-amber-600 mb-2">
                          {round.diagnosis.errors.map((e, i) => (
                            <div key={i}>
                              {e.rubric_id ? `${e.rubric_id}：` : ""}
                              {e.error}
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="max-h-56 overflow-auto">
                        <table className="w-full text-xs border border-gray-200 rounded-md">
                          <thead>
                            <tr className="text-left text-gray-400 bg-gray-50 border-b border-gray-200">
                              <th className="py-1.5 px-2 font-medium">失败模式</th>
                              <th className="py-1.5 px-2 font-medium">节点</th>
                              <th className="py-1.5 px-2 font-medium w-20">范畴</th>
                              <th className="py-1.5 px-2 font-medium w-16">严重度</th>
                              <th className="py-1.5 px-2 font-medium">证据与建议</th>
                            </tr>
                          </thead>
                          <tbody>
                            {round.diagnosis.findings.map((f, i) => (
                              <tr key={i} className="border-b border-gray-100 last:border-b-0 align-top">
                                <td className="py-1.5 px-2">
                                  <span className="tag bg-purple-50 text-purple-700">{PATTERN_NAMES[f.pattern] ?? f.pattern}</span>
                                </td>
                                <td className="py-1.5 px-2 text-gray-600">{f.node_name}</td>
                                <td className="py-1.5 px-2 text-gray-500">{f.category === "completion" ? "完成" : "质量"}</td>
                                <td className="py-1.5 px-2">
                                  <span className={f.severity === "high" ? "text-red-600 font-medium" : f.severity === "medium" ? "text-amber-600" : "text-gray-500"}>
                                    {f.severity}
                                  </span>
                                </td>
                                <td className="py-1.5 px-2 text-gray-500">
                                  <div>{f.evidence}</div>
                                  {f.suggestion && <div className="text-blue-600 mt-0.5">建议：{f.suggestion}</div>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* 建议采纳 */}
                  {round.suggestions.length > 0 && (
                    <div className="mb-4">
                      <div className="section-title">优化建议（勾选采纳）</div>
                      <div className="space-y-2">
                        {round.suggestions.map((s) => (
                          <label
                            key={s.id}
                            className={`flex items-start gap-2.5 border rounded-md px-3 py-2 cursor-pointer transition-colors ${
                              s.accepted ? "border-green-300 bg-green-50/50" : "border-gray-200 hover:border-blue-200"
                            }`}
                          >
                            <input
                              type="checkbox"
                              className="mt-1 accent-blue-600"
                              checked={s.accepted || acceptedIds.has(s.id)}
                              disabled={s.accepted}
                              onChange={(e) => {
                                const next = new Set(acceptedIds);
                                if (e.target.checked) next.add(s.id);
                                else next.delete(s.id);
                                setAcceptedIds(next);
                              }}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="tag bg-indigo-50 text-indigo-700">{s.module}</span>
                                {s.accepted && (
                                  <span className="text-xs text-green-600 font-medium">
                                    <CheckCircle2 size={12} className="inline mr-0.5" />
                                    已采纳
                                  </span>
                                )}
                              </div>
                              <div className="text-sm text-gray-700 mt-1">{s.problem}</div>
                              <div className="text-xs text-blue-600 mt-0.5">{s.suggestion}</div>
                            </div>
                          </label>
                        ))}
                      </div>
                      {round.status !== "refined" && (
                        <div className="mt-3 flex items-center gap-2">
                          <span className="text-xs text-gray-500 shrink-0">精炼为新版本：</span>
                          <input
                            className="input w-32"
                            value={newVersion}
                            placeholder="如 v5.10"
                            onChange={(e) => setNewVersion(e.target.value)}
                          />
                          <button
                            className="btn-primary"
                            disabled={busy || acceptedIds.size === 0 || newVersion.trim() === ""}
                            onClick={() => act(() => api.applyRoundSuggestions(run.run_id, roundNo, [...acceptedIds], newVersion.trim()), `已精炼并保存为 ${newVersion.trim()}，进入下一轮时使用`,
                              "正在调用 LLM 精炼 prompt 模块（通常 1-3 分钟），请勿关闭页面")}
                          >
                            采纳并精炼
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {round.status === "rejected" && round.suggestions.length === 0 && (
                    <div className="text-xs text-gray-400">
                      该轮已初筛否决：跳过评分与指标，直接点「RIFT 诊断」分析本批 rubric 的系统性问题，出建议后勾选采纳精炼新版本。
                    </div>
                  )}
                  {round.status === "generated" && round.suggestions.length === 0 && !reviewRejected && (
                    <div className="text-xs text-gray-400">
                      初筛通过后填写评分表并点击「计算指标」→「RIFT 诊断」生成优化建议。
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
