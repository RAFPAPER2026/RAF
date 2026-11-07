// flat rubric 打分表单：
// 每项卡片点击头部切换完成(0/1)，完成时展开质量档位（键如 1.0/0.75/0.5/0.25/0.0 带描述）降序；
// 实时总分预览（score = mean(completion × quality_score)）+ 备注 + 打分人
// 同文件含 TraceQualityForm（过程评价）：每维度按 dim.levels 生成档位按钮，avg_score = mean
import { useMemo, useState } from 'react'
import type { TaskSummary, TraceDimension } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct } from '../lib/utils'

interface Props {
  modelId: string
  taskName: string
  runId: string
  rubric: unknown
  initialScores?: Array<{ completion: number; quality_score: number }>
  task: TaskSummary | null
  onSaved: () => void
}

interface FlatItem {
  index: number
  name: string
  levels: Array<{ key: string; label: string }>
  tags: string[]
}

/** 解析 flat rubric 项：[{completion_rubric, quality_rubric: {score: desc}, tags?}] */
function parseFlatItems(rubric: unknown): FlatItem[] {
  if (!Array.isArray(rubric)) return []
  return rubric
    .map((raw, index) => {
      const item = (raw ?? {}) as Record<string, unknown>
      const name = firstString(item.completion_rubric, item.name, item.title, item.id, `检查项 ${index + 1}`)
      return { index, name, levels: parseLevels(item.quality_rubric), tags: parseTags(item.tags) }
    })
    .filter((it) => it.name !== '')
}

function firstString(...candidates: Array<unknown | undefined>): string {
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim()
  }
  return ''
}

function parseTags(tags: unknown): string[] {
  if (!Array.isArray(tags)) return []
  return tags.filter((t): t is string => typeof t === 'string')
}

/** 质量档位：{score: desc} 字典（键为数值字符串）或 [{score, label}] 数组；按分数降序 */
function parseLevels(qr: unknown): Array<{ key: string; label: string }> {
  if (qr && typeof qr === 'object' && !Array.isArray(qr)) {
    const entries = Object.entries(qr as Record<string, unknown>)
    if (entries.length > 0) {
      const levels = entries
        .map(([key, v]) => ({ key, label: levelLabel(v) }))
        .filter((l) => Number.isFinite(parseFloat(l.key)))
        .sort((a, b) => parseFloat(b.key) - parseFloat(a.key))
      if (levels.length > 0) return levels
    }
  }
  if (Array.isArray(qr)) {
    const levels = qr
      .map((raw) => {
        const it = (raw ?? {}) as Record<string, unknown>
        const key = typeof it.score === 'number' ? String(it.score) : typeof it.key === 'string' ? it.key : ''
        return { key, label: typeof it.label === 'string' ? it.label : typeof it.description === 'string' ? it.description : '' }
      })
      .filter((l) => l.key !== '' && Number.isFinite(parseFloat(l.key)))
      .sort((a, b) => parseFloat(b.key) - parseFloat(a.key))
    if (levels.length > 0) return levels
  }
  // 兜底：无档位配置时生成标准 5 档
  return [
    { key: '1.0', label: '' },
    { key: '0.75', label: '' },
    { key: '0.5', label: '' },
    { key: '0.25', label: '' },
    { key: '0.0', label: '' },
  ]
}

function levelLabel(v: unknown): string {
  if (typeof v === 'string') return v
  if (v && typeof v === 'object') {
    const o = v as Record<string, unknown>
    for (const k of ['description', 'desc', 'label', 'name']) {
      if (typeof o[k] === 'string') return o[k] as string
    }
  }
  return ''
}

export default function ScoringForm({ modelId, taskName, runId, rubric, initialScores, task, onSaved }: Props) {
  const items = useMemo(() => parseFlatItems(rubric), [rubric])
  const [completion, setCompletion] = useState<Record<number, 0 | 1>>(() => {
    const c: Record<number, 0 | 1> = {}
    items.forEach((it) => {
      c[it.index] = initialScores?.[it.index]?.completion === 1 ? 1 : 0
    })
    return c
  })
  const [quality, setQuality] = useState<Record<number, number | null>>(() => {
    const q: Record<number, number | null> = {}
    items.forEach((it) => {
      const v = initialScores?.[it.index]?.quality_score
      q[it.index] = typeof v === 'number' ? v : null
    })
    return q
  })
  const [comment, setComment] = useState('')
  const [scoredBy, setScoredBy] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // 实时总分：score = mean(completion × quality_score)；未选档位按 0 计
  const score = useMemo(() => {
    if (items.length === 0) return 0
    let sum = 0
    for (const it of items) {
      const c = completion[it.index] ?? 0
      const q = quality[it.index]
      sum += c * (q ?? 0)
    }
    return sum / items.length
  }, [items, completion, quality])

  const completionRate = useMemo(() => {
    if (items.length === 0) return 0
    return items.filter((it) => (completion[it.index] ?? 0) === 1).length / items.length
  }, [items, completion])

  const toggleCompletion = (index: number) => {
    setCompletion((prev) => ({ ...prev, [index]: prev[index] === 1 ? 0 : 1 }))
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
            rubric_scores: items.map((it) => ({
              completion: completion[it.index] ?? 0,
              quality_score: quality[it.index] ?? 0,
            })),
            score: Math.round(score * 10000) / 10000,
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

  if (items.length === 0) {
    return (
      <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-400">
        该任务无平铺 rubric 检查项，可直接保存分数。
      </p>
    )
  }

  return (
    <div>
      {/* 实时总分预览 */}
      <div className="mb-3 flex items-center justify-between rounded-lg bg-slate-50 p-3">
        <div className="text-xs text-slate-500">
          完成 {items.filter((it) => (completion[it.index] ?? 0) === 1).length}/{items.length} 项 · 完成率{' '}
          {pct(completionRate)}
        </div>
        <div className="text-sm">
          <span className="text-slate-400">实时总分 </span>
          <span className={`text-lg font-bold ${score > 0 ? 'text-indigo-600' : 'text-slate-400'}`}>
            {pct(score)}
          </span>
        </div>
      </div>

      {/* 检查项卡片 */}
      <div className="space-y-2">
        {items.map((it) => {
          const done = (completion[it.index] ?? 0) === 1
          const q = quality[it.index]
          return (
            <div
              key={it.index}
              className={`rounded-lg border transition-colors ${
                done ? 'border-emerald-300 bg-emerald-50/40' : 'border-slate-200 bg-white'
              }`}
            >
              {/* 头部：点击切换完成 */}
              <button
                onClick={() => toggleCompletion(it.index)}
                className="flex w-full items-start gap-2 px-3 py-2 text-left"
                title="点击切换完成/未完成"
              >
                <span
                  className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${
                    done ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-500'
                  }`}
                >
                  {done ? '已完成' : '未完成'}
                </span>
                <span className={`min-w-0 flex-1 text-xs ${done ? 'text-emerald-900' : 'text-slate-700'}`}>
                  {it.name}
                </span>
                {it.tags.length > 0 && (
                  <span className="flex shrink-0 flex-wrap gap-0.5">
                    {it.tags.map((t) => (
                      <span key={t} className="rounded bg-slate-200/70 px-1 py-0.5 text-[9px] text-slate-500">
                        {t}
                      </span>
                    ))}
                  </span>
                )}
              </button>
              {/* 完成时展开质量档位 */}
              {done && (
                <div className="border-t border-emerald-100 px-3 py-2">
                  <div className="mb-1.5 text-[10px] font-medium text-slate-400">质量档位（点击选择）</div>
                  <div className="flex flex-wrap gap-1.5">
                    {it.levels.map((lv) => {
                      const val = parseFloat(lv.key)
                      const selected = q === val
                      return (
                        <button
                          key={lv.key}
                          onClick={() => {
                            setQuality((prev) => ({ ...prev, [it.index]: selected ? null : val }))
                            setSavedMsg(null)
                          }}
                          className={`rounded-md border px-2 py-1 text-left text-[11px] transition-colors ${
                            selected
                              ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-400'
                              : 'border-slate-200 bg-white hover:border-indigo-300'
                          }`}
                        >
                          <span className={`font-bold ${selected ? 'text-indigo-700' : 'text-slate-600'}`}>
                            {pct(val)}
                          </span>
                          {lv.label && (
                            <span className="mt-0.5 block max-w-52 text-[10px] leading-tight text-slate-500">
                              {lv.label}
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                  <div className="mt-1.5 text-[10px] text-slate-400">
                    本项得分: {pct((done ? 1 : 0) * (q ?? 0))}
                    {q === null && '（未选档位按 0 计）'}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 备注 + 打分人 + 保存 */}
      <div className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3">
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
// 过程评价（TraceQualityForm）
// ============================================================
export function TraceQualityForm({
  modelId,
  taskName,
  runId,
  dimensions,
  initial,
}: {
  modelId: string
  taskName: string
  runId: string
  dimensions: TraceDimension[]
  initial?: Record<string, number>
}) {
  const [values, setValues] = useState<Record<string, number | null>>(() => {
    const v: Record<string, number | null> = {}
    for (const d of dimensions) v[d.key] = initial?.[d.key] ?? null
    return v
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  /** 按档位数生成档位值：levels=5 → 0.0/0.25/0.5/0.75/1.0；levels=3 → 0.0/0.5/1.0 */
  const stepsFor = (levels: number): number[] => {
    const n = Math.max(2, Math.min(11, Math.round(levels) || 5))
    const arr: number[] = []
    for (let i = 0; i < n; i++) {
      arr.push(Math.round((i / (n - 1)) * 100) / 100)
    }
    return arr
  }

  const selectedValues = Object.values(values).filter((v): v is number => v !== null)
  const avg = selectedValues.length > 0 ? selectedValues.reduce((a, b) => a + b, 0) / selectedValues.length : null

  const save = async () => {
    const dims: Record<string, number> = {}
    for (const d of dimensions) {
      const v = values[d.key]
      if (v !== null) dims[d.key] = v
    }
    setSaving(true)
    setMsg(null)
    try {
      const res = await apiFetch<{ success: boolean }>(
        `/model/${enc(modelId)}/task/${enc(taskName)}/trace-quality`,
        { method: 'POST', body: JSON.stringify({ dimensions: dims }) },
      )
      setMsg({ ok: res.success, text: res.success ? '过程评价已保存' : '保存失败' })
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    } finally {
      setSaving(false)
    }
  }

  if (dimensions.length === 0) {
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-700">过程评价</h3>
        <p className="mt-2 rounded-lg bg-slate-50 p-3 text-xs text-slate-400">暂无过程评价维度配置</p>
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">
          过程评价
          <span className="ml-2 text-xs font-normal text-slate-400">
            各维度档位 · 平均 {avg !== null ? pct(avg) : '-'}
          </span>
        </h3>
        <button
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? '保存中…' : '保存'}
        </button>
      </div>
      {msg && (
        <p className={`mb-2 text-xs ${msg.ok ? 'text-emerald-600' : 'text-red-600'}`}>
          {msg.ok ? '✓ ' : '✗ '}
          {msg.text}
        </p>
      )}
      <div className="space-y-2.5">
        {dimensions.map((d) => {
          const current = values[d.key]
          return (
            <div key={d.key} className="flex flex-wrap items-center gap-2">
              <span className="w-24 shrink-0 text-xs font-medium text-slate-600">{d.name}</span>
              <div className="flex flex-wrap gap-1">
                {stepsFor(d.levels).map((s) => {
                  const selected = current === s
                  return (
                    <button
                      key={s}
                      onClick={() => {
                        setValues((prev) => ({ ...prev, [d.key]: selected ? null : s }))
                        setMsg(null)
                      }}
                      className={`rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
                        selected
                          ? 'border-indigo-500 bg-indigo-50 text-indigo-700 ring-1 ring-indigo-400'
                          : 'border-slate-200 bg-white text-slate-500 hover:border-indigo-300'
                      }`}
                    >
                      {pct(s)}
                    </button>
                  )
                })}
              </div>
              <span className="text-[10px] text-slate-400">{current !== null ? pct(current) : '未评'}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}
