// 树形 rubric 打分表单：
// 完成树与质量树共享一个 {leaf_id: boolean} map；递归 NodeView 折叠 AND/OR 组、
// 通过/失败着色、显示 tags；完成度由树推导（「任务完成」按钮在 tree 下隐藏）；
// 保存 POST {rubric_results, completion_rate, score, complete_flag, comment, scored_by, run_id}
import { useMemo, useState } from 'react'
import type { QueryRubric, RubricNode, TaskSummary, WeightedItem } from '../types'
import {
  collectLeaves,
  computeTreeScore,
  nodePassed,
  nodeScore,
  SCORING_MODES,
  type ScoringMode,
} from '../lib/scoring'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct } from '../lib/utils'

interface Props {
  modelId: string
  taskName: string
  runId: string
  rubric: unknown
  initialResults?: Record<string, boolean>
  task: TaskSummary | null
  onSaved: () => void
}

/** 把 config.rubric 规范化为 QueryRubric（对象形式；数组/缺失视为空） */
function normalizeRubric(rubric: unknown): QueryRubric {
  if (rubric && typeof rubric === 'object' && !Array.isArray(rubric)) {
    return rubric as QueryRubric
  }
  return {}
}

export default function TreeRubricScoringForm({
  modelId,
  taskName,
  runId,
  rubric,
  initialResults,
  task,
  onSaved,
}: Props) {
  const normalized = useMemo(() => normalizeRubric(rubric), [rubric])
  const completionNodes = normalized.completion_rubric ?? []
  const qualityItems = normalized.quality_rubric ?? []
  const allLeaves = useMemo(
    () => collectLeaves([...completionNodes, ...qualityItems.map((i) => i.node)]),
    [completionNodes, qualityItems],
  )

  // 共享 {leaf_id: boolean} map（完成树 + 质量树共用）
  const [results, setResults] = useState<Record<string, boolean>>(() => {
    const r: Record<string, boolean> = {}
    for (const leaf of allLeaves) {
      r[leaf.id] = initialResults?.[leaf.id] === true
    }
    return r
  })
  const [comment, setComment] = useState('')
  const [scoredBy, setScoredBy] = useState('')
  const [saving, setSaving] = useState(false)
  const [scoringMode, setScoringMode] = useState<ScoringMode>('paper')
  const [savedMsg, setSavedMsg] = useState<{ ok: boolean; text: string } | null>(null)

  const derived = useMemo(
    () => computeTreeScore(normalized, results, scoringMode),
    [normalized, results, scoringMode],
  )

  const toggle = (id: string, v: boolean) => {
    setResults((prev) => ({ ...prev, [id]: v }))
    setSavedMsg(null)
  }

  const save = async () => {
    setSaving(true)
    setSavedMsg(null)
    try {
      const res = await apiFetch<{ success: boolean; message: string; score: number }>(
        `/model/${enc(modelId)}/task/${enc(taskName)}/score`,
        {
          method: 'POST',
          body: JSON.stringify({
            rubric_results: results,
            completion_rate: derived.completion_rate,
            score: Math.round(derived.score * 10000) / 10000,
            complete_flag: derived.complete_flag,
            scoring_mode: scoringMode,
            comment: comment.trim() ? comment.trim() : undefined,
            scored_by: scoredBy.trim() ? scoredBy.trim() : undefined,
            run_id: runId,
          }),
        },
      )
      setSavedMsg({ ok: res.success, text: res.message || (res.success ? '保存成功' : '保存失败') })
      if (res.success) onSaved()
    } catch (e) {
      setSavedMsg({ ok: false, text: errText(e) })
    } finally {
      setSaving(false)
    }
  }

  const completionLeaves = useMemo(() => collectLeaves(completionNodes), [completionNodes])
  const passedCompletionLeaves = completionLeaves.filter((l) => results[l.id]).length

  return (
    <div>
      {/* 评分口径 */}
      <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
        <span>质量分口径</span>
        <select
          value={scoringMode}
          onChange={(e) => setScoringMode(e.target.value as ScoringMode)}
          className="rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-500"
        >
          {SCORING_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {mode === 'paper' ? '论文口径（AND 组全过才得分）' : '兼容口径（AND 组取均值）'}
            </option>
          ))}
        </select>
      </div>
      {/* 实时摘要 */}
      <div className="mb-3 grid grid-cols-4 gap-2 text-center text-xs">
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-slate-400">完成度</div>
          <div className="mt-0.5 text-sm font-bold text-slate-700">
            {pct(completionLeaves.length > 0 ? passedCompletionLeaves / completionLeaves.length : 0)}
          </div>
          <div className="text-[10px] text-slate-400">
            {passedCompletionLeaves}/{completionLeaves.length} 叶子
          </div>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-slate-400">质量分</div>
          <div className="mt-0.5 text-sm font-bold text-indigo-600">{pct(derived.score)}</div>
          <div className="text-[10px] text-slate-400">加权平均</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-slate-400">完成标记</div>
          <div className={`mt-0.5 text-sm font-bold ${derived.complete_flag === 1 ? 'text-emerald-600' : 'text-slate-400'}`}>
            {derived.complete_flag === 1 ? '✓ 完成' : '✗ 未完成'}
          </div>
          <div className="text-[10px] text-slate-400">由树推导</div>
        </div>
        <div className="rounded-lg bg-slate-50 p-2">
          <div className="text-slate-400">已保存分数</div>
          <div className="mt-0.5 text-sm font-bold text-slate-700">
            {task && task.score !== null ? pct(task.score) : '-'}
          </div>
          <div className="text-[10px] text-slate-400">服务端</div>
        </div>
      </div>

      {/* 完成树 */}
      {completionNodes.length > 0 ? (
        <div className="mb-4">
          <div className="mb-1.5 text-xs font-semibold text-slate-500">完成判定树（全部通过即完成）</div>
          <div className="space-y-1.5 rounded-lg border border-slate-100 bg-slate-50/50 p-2">
            {completionNodes.map((n) => (
              <NodeView key={n.id} node={n} results={results} onToggle={toggle} depth={0} />
            ))}
          </div>
        </div>
      ) : (
        <p className="mb-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-400">无完成判定树</p>
      )}

      {/* 质量树 */}
      {qualityItems.length > 0 && (
        <div className="mb-4">
          <div className="mb-1.5 text-xs font-semibold text-slate-500">质量评分树（加权平均）</div>
          <div className="space-y-2">
            {qualityItems.map((item) => (
              <QualityItemView
                key={item.node.id}
                item={item}
                results={results}
                onToggle={toggle}
                scoringMode={scoringMode}
              />
            ))}
          </div>
        </div>
      )}

      {/* 备注 + 打分人 + 保存 */}
      <div className="space-y-2 rounded-lg bg-slate-50 p-3">
        <div className="flex gap-2">
          <input
            value={scoredBy}
            onChange={(e) => setScoredBy(e.target.value)}
            placeholder="打分人（可选）"
            className="w-32 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500"
          />
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="备注（可选）"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-500"
          />
          <button
            onClick={save}
            disabled={saving}
            className="shrink-0 rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saving ? '保存中…' : '保存打分'}
          </button>
        </div>
        {savedMsg && (
          <p className={`text-xs ${savedMsg.ok ? 'text-emerald-600' : 'text-red-600'}`}>
            {savedMsg.ok ? '✓ ' : '✗ '}
            {savedMsg.text}
          </p>
        )}
      </div>
    </div>
  )
}

// ============================================================
// 递归节点视图
// ============================================================
function NodeView({
  node,
  results,
  onToggle,
  depth,
}: {
  node: RubricNode
  results: Record<string, boolean>
  onToggle: (id: string, v: boolean) => void
  depth: number
}) {
  const [open, setOpen] = useState(true)
  const isLeaf = node.type === 'leaf' || !node.children || node.children.length === 0

  if (isLeaf) {
    const passed = results[node.id] === true
    return (
      <div className="flex items-start gap-2" style={{ paddingLeft: depth * 16 }}>
        <button
          onClick={() => onToggle(node.id, !passed)}
          aria-pressed={passed}
          className={`flex min-w-0 flex-1 items-start gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs transition-colors ${
            passed
              ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
          }`}
          title={passed ? '点击改为失败' : '点击改为通过'}
        >
          <span className={`mt-0.5 shrink-0 font-bold ${passed ? 'text-emerald-600' : 'text-red-400'}`}>
            {passed ? '✓' : '✗'}
          </span>
          <span className="min-w-0 flex-1">{node.name || node.id}</span>
        </button>
        {node.tags && node.tags.length > 0 && (
          <span className="mt-0.5 flex shrink-0 flex-wrap gap-0.5">
            {node.tags.map((t) => (
              <span key={t} className="rounded bg-slate-200/70 px-1 py-0.5 text-[9px] text-slate-500">
                {t}
              </span>
            ))}
          </span>
        )}
      </div>
    )
  }

  const passed = nodePassed(node, results)
  return (
    <div style={{ paddingLeft: depth * 16 }}>
      <button
        onClick={() => setOpen(!open)}
        className={`flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs font-medium ${
          passed
            ? 'border-emerald-200 bg-emerald-50/60 text-emerald-800'
            : 'border-slate-200 bg-slate-50 text-slate-700'
        }`}
      >
        <span className="shrink-0 text-slate-400">{open ? '▾' : '▸'}</span>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
            node.combinator === 'or' ? 'bg-orange-100 text-orange-600' : 'bg-blue-100 text-blue-600'
          }`}
        >
          {node.combinator === 'or' ? 'OR' : 'AND'}
        </span>
        <span className="min-w-0 flex-1 truncate">{node.name || node.id}</span>
        <span className={`shrink-0 font-bold ${passed ? 'text-emerald-600' : 'text-red-400'}`}>
          {passed ? '✓ 通过' : '✗ 未通过'}
        </span>
      </button>
      {open && node.children && (
        <div className="mt-1 space-y-1.5">
          {node.children.map((c) => (
            <NodeView key={c.id ?? c.name} node={c} results={results} onToggle={onToggle} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================================
// 质量顶层项（带权重 + 实时该项得分）
// ============================================================
function QualityItemView({
  item,
  results,
  onToggle,
  scoringMode,
}: {
  item: WeightedItem
  results: Record<string, boolean>
  onToggle: (id: string, v: boolean) => void
  scoringMode: ScoringMode
}) {
  const score = nodeScore(item.node, results, scoringMode)
  return (
    <div className="rounded-lg border border-slate-200 p-2">
      <div className="mb-1.5 flex items-center gap-2 text-xs">
        <span className="rounded bg-indigo-100 px-1.5 py-0.5 font-bold text-indigo-700">权重 {item.weight}</span>
        <span className="min-w-0 flex-1 truncate font-medium text-slate-600">{item.node.name}</span>
        <span className={`shrink-0 font-bold ${score >= 0.5 ? 'text-emerald-600' : 'text-red-400'}`}>
          {pct(score)}
        </span>
      </div>
      <NodeView node={item.node} results={results} onToggle={onToggle} depth={0} />
    </div>
  )
}
