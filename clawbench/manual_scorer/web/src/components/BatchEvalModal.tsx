// 批量 Agent 评测弹窗：
// 任务多选、evaluate_trace、skip_existing(默认 true)、auto_adopt、concurrency(默认 32, 1..128)、run 选择；
// 进度列表（每任务状态/分数/错误）、取消按钮；3 秒轮询 batch 会话；
// 打开时尝试恢复该模型最近一次未结束的批次
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { BatchEvalSession, BatchStartResponse, BatchTaskStatus, TaskSummary } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct } from '../lib/utils'
import Modal from './Modal'

interface Props {
  modelId: string
  tasks: TaskSummary[]
  runs: string[]
  onClose: () => void
  onDone: () => void
}

const POLL_MS = 3000

const STATUS_META: Record<string, { label: string; cls: string }> = {
  queued: { label: '排队中', cls: 'bg-slate-100 text-slate-500' },
  running: { label: '运行中', cls: 'bg-blue-100 text-blue-700' },
  completed: { label: '完成', cls: 'bg-emerald-100 text-emerald-700' },
  failed: { label: '失败', cls: 'bg-red-100 text-red-700' },
  timeout: { label: '超时', cls: 'bg-orange-100 text-orange-700' },
  cancelled: { label: '已取消', cls: 'bg-slate-200 text-slate-500' },
}

function isTerminal(status: string): boolean {
  return status !== 'queued' && status !== 'running'
}

export default function BatchEvalModal({ modelId, tasks, runs, onClose, onDone }: Props) {
  const [selected, setSelected] = useState<Set<string>>(() => new Set(tasks.map((t) => t.task_name)))
  const [evaluateTrace, setEvaluateTrace] = useState(false)
  const [skipExisting, setSkipExisting] = useState(true)
  const [autoAdopt, setAutoAdopt] = useState(false)
  const [concurrency, setConcurrency] = useState('32')
  const [runId, setRunId] = useState(runs.includes('run_1') ? 'run_1' : runs[0] ?? 'run_1')

  const [session, setSession] = useState<BatchEvalSession | null>(null)
  const [startResp, setStartResp] = useState<BatchStartResponse | null>(null)
  const [starting, setStarting] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resumed, setResumed] = useState(false)

  const batchId = session?.batch_id ?? startResp?.batch_id ?? null
  const allDone = useMemo(() => {
    if (!session) return false
    return session.tasks.every((t) => isTerminal(t.status))
  }, [session])

  const fetchSession = useCallback(async () => {
    if (!batchId) return
    try {
      const s = await apiFetch<BatchEvalSession>(`/model/${enc(modelId)}/batch-agent-eval/${enc(batchId)}`)
      setSession(s)
    } catch (e) {
      setError(errText(e))
    }
  }, [modelId, batchId])

  // 打开时恢复最近一次未结束的批次
  useEffect(() => {
    let alive = true
    apiFetch<BatchEvalSession | null>('/model/' + enc(modelId) + '/batch-agent-eval')
      .then((latest) => {
        if (!alive || !latest) return
        if (latest.tasks.some((t) => !isTerminal(t.status))) {
          setSession(latest)
          setResumed(true)
        }
      })
      .catch(() => {
        /* 无批次或失败时忽略 */
      })
    return () => {
      alive = false
    }
  }, [modelId])

  // 3 秒轮询
  useEffect(() => {
    if (!batchId) return
    const timer = window.setInterval(() => {
      void fetchSession()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [batchId, fetchSession])

  const toggleTask = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const start = async () => {
    const concurrencyNum = Math.max(1, Math.min(128, Math.round(Number(concurrency)) || 32))
    setStarting(true)
    setError(null)
    try {
      const res = await apiFetch<BatchStartResponse>(`/model/${enc(modelId)}/batch-agent-eval`, {
        method: 'POST',
        body: JSON.stringify({
          task_names: Array.from(selected),
          evaluate_trace: evaluateTrace,
          skip_existing: skipExisting,
          auto_adopt: autoAdopt,
          concurrency: concurrencyNum,
          run_id: runId,
        }),
      })
      setStartResp(res)
      setConcurrency(String(concurrencyNum))
      void fetchSession()
    } catch (e) {
      setError(errText(e))
    } finally {
      setStarting(false)
    }
  }

  const cancel = async () => {
    if (!batchId) return
    setCancelling(true)
    setError(null)
    try {
      await apiFetch(`/model/${enc(modelId)}/batch-agent-eval/${enc(batchId)}/cancel`, { method: 'POST' })
      void fetchSession()
    } catch (e) {
      setError(errText(e))
    } finally {
      setCancelling(false)
    }
  }

  const displayTasks: BatchTaskStatus[] =
    session?.tasks ??
    startResp?.tasks ??
    (batchId
      ? selected.size > 0
        ? Array.from(selected).map((name) => ({
            task_key: `${modelId}::${name}::${runId}`,
            task_name: name,
            run_id: runId,
            status: 'queued' as const,
          }))
        : []
      : [])

  const summary = session?.summary ?? null

  return (
    <Modal title="⚡ 批量 Agent 评测" onClose={onClose} size="lg">
      <div className="space-y-4 p-5">
        {!session && !startResp && (
          <>
            {/* 配置区 */}
            <div>
              <div className="mb-1.5 text-xs font-semibold text-slate-500">选择任务（{selected.size}/{tasks.length}）</div>
              <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
                {tasks.map((t) => {
                  const checked = selected.has(t.task_name)
                  return (
                    <label
                      key={t.task_name}
                      className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-xs hover:bg-slate-50"
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTask(t.task_name)}
                        className="h-3.5 w-3.5 accent-indigo-600"
                      />
                      <span className="min-w-0 flex-1 truncate text-slate-600">{t.task_name}</span>
                      <span
                        className={`shrink-0 rounded px-1 py-0.5 text-[9px] ${
                          t.rubric_format === 'tree'
                            ? 'bg-indigo-50 text-indigo-600'
                            : 'bg-slate-100 text-slate-400'
                        }`}
                      >
                        {t.rubric_format === 'tree' ? 'tree' : '跳过'}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
              <label className="flex cursor-pointer items-center gap-1.5 text-slate-600">
                <input
                  type="checkbox"
                  checked={evaluateTrace}
                  onChange={(e) => setEvaluateTrace(e.target.checked)}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                过程评价（trace_quality）
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-slate-600">
                <input
                  type="checkbox"
                  checked={skipExisting}
                  onChange={(e) => setSkipExisting(e.target.checked)}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                跳过已评测任务（skip_existing）
              </label>
              <label className="flex cursor-pointer items-center gap-1.5 text-slate-600">
                <input
                  type="checkbox"
                  checked={autoAdopt}
                  onChange={(e) => setAutoAdopt(e.target.checked)}
                  className="h-3.5 w-3.5 accent-indigo-600"
                />
                完成后自动采纳（auto_adopt）
              </label>
              <div className="flex items-center gap-1.5 text-slate-600">
                <span className="shrink-0">并发度</span>
                <input
                  type="number"
                  min={1}
                  max={128}
                  value={concurrency}
                  onChange={(e) => setConcurrency(e.target.value)}
                  className="w-20 rounded border border-slate-300 px-2 py-1 text-xs outline-none focus:border-indigo-400"
                />
                <span className="text-slate-400">(1-128)</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-600">
                <span className="shrink-0">run</span>
                <select
                  value={runId}
                  onChange={(e) => setRunId(e.target.value)}
                  className="rounded border border-slate-300 px-1.5 py-1 text-xs outline-none focus:border-indigo-400"
                >
                  {runs.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {error && <p className="text-xs text-red-600">{error}</p>}

            <div className="flex justify-end gap-2">
              <button
                onClick={onClose}
                className="rounded-lg border border-slate-300 px-4 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                关闭
              </button>
              <button
                onClick={start}
                disabled={starting || selected.size === 0}
                className="rounded-lg bg-amber-500 px-4 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
              >
                {starting ? '发起中…' : '⚡ 开始批量评测'}
              </button>
            </div>
          </>
        )}

        {/* 进度区 */}
        {(session || startResp) && (
          <>
            {resumed && (
              <p className="rounded-lg bg-indigo-50 p-2 text-xs text-indigo-600">
                已恢复上一次未完成的批量评测（{batchId}），继续轮询进度。
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className="rounded bg-slate-100 px-2 py-1 font-mono text-[11px] text-slate-600">{batchId}</span>
              <span className="text-slate-500">
                总计 {session?.total ?? startResp?.total ?? displayTasks.length} · 跳过 {session?.skipped ?? startResp?.skipped ?? 0} · 开始{' '}
                {session?.started ?? startResp?.started ?? 0}
              </span>
              {session?.cancelled && <span className="font-bold text-red-500">已取消</span>}
              {summary && (
                <span className="text-slate-400">
                  排队 {summary.queued} · 运行 {summary.running} · 完成 {summary.completed} · 失败{' '}
                  {summary.failed} · 超时 {summary.timeout} · 取消 {summary.cancelled}
                </span>
              )}
            </div>

            {/* 任务进度列表 */}
            <div className="max-h-64 space-y-1 overflow-y-auto rounded-lg border border-slate-200 p-2">
              {displayTasks.map((t) => {
                const meta = STATUS_META[t.status] ?? { label: t.status, cls: 'bg-slate-100 text-slate-500' }
                return (
                  <div key={t.task_key} className="flex items-center gap-2 rounded px-1.5 py-1 text-xs">
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${meta.cls}`}>
                      {meta.label}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-slate-600" title={t.task_name}>
                      {t.task_name}
                    </span>
                    {t.retried && (
                      <span className="shrink-0 rounded bg-amber-50 px-1 text-[9px] text-amber-600">重试</span>
                    )}
                    {t.score !== null && t.score !== undefined && (
                      <span className="shrink-0 font-bold text-slate-700">{pct(t.score)}</span>
                    )}
                    {t.error && (
                      <span className="shrink-0 max-w-40 truncate text-[10px] text-red-500" title={t.error}>
                        {t.error}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>

            {error && <p className="text-xs text-red-600">{error}</p>}

            <div className="flex justify-end gap-2">
              {!allDone && !session?.cancelled && (
                <button
                  onClick={cancel}
                  disabled={cancelling}
                  className="rounded-lg border border-red-300 px-4 py-1.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  {cancelling ? '取消中…' : '取消评测'}
                </button>
              )}
              <button
                onClick={() => {
                  onClose()
                  onDone()
                }}
                disabled={!allDone && !session?.cancelled}
                className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
              >
                {allDone || session?.cancelled ? '完成' : '评测进行中…'}
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
