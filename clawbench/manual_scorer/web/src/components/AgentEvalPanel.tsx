// Agent 评测面板：发起评测（evaluate_trace 开关、run 选择）、3 秒状态轮询、
// 完成后采纳分数（POST adopt）、「查看评测轨迹」窗口（workspace root=judge）
import { useCallback, useEffect, useRef, useState } from 'react'
import type { AgentEvalSessionInfo } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct } from '../lib/utils'
import WorkspaceModal from './WorkspaceModal'

interface Props {
  modelId: string
  taskName: string
  runId: string
  runs: string[]
  onAdopted: () => void
}

const POLL_MS = 3000

const STATUS_STYLES: Record<string, string> = {
  none: 'bg-slate-100 text-slate-500',
  pending: 'bg-amber-100 text-amber-700',
  running: 'bg-blue-100 text-blue-700',
  completed: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  timeout: 'bg-orange-100 text-orange-700',
}

export default function AgentEvalPanel({ modelId, taskName, runId, runs, onAdopted }: Props) {
  const [session, setSession] = useState<AgentEvalSessionInfo | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [evaluateTrace, setEvaluateTrace] = useState(false)
  const [evalRunId, setEvalRunId] = useState(runId)
  const [starting, setStarting] = useState(false)
  const [adopting, setAdopting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [adoptMsg, setAdoptMsg] = useState<string | null>(null)
  const [adoptedScore, setAdoptedScore] = useState<number | null>(null)
  const [showJudge, setShowJudge] = useState(false)
  const pollRef = useRef<number | null>(null)

  const isRunning = session !== null && (session.status === 'pending' || session.status === 'running')

  const fetchStatus = useCallback(async () => {
    try {
      const s = await apiFetch<AgentEvalSessionInfo>(
        `/model/${enc(modelId)}/task/${enc(taskName)}/agent-eval`,
      )
      setSession(s.status === 'none' ? null : s)
      return s
    } catch (e) {
      setError(errText(e))
      return null
    }
  }, [modelId, taskName])

  // 初始加载
  useEffect(() => {
    let alive = true
    void fetchStatus().then(() => alive && setLoaded(true))
    return () => {
      alive = false
    }
  }, [fetchStatus])

  // 3 秒轮询（pending/running 期间）
  useEffect(() => {
    if (!isRunning) {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }
    pollRef.current = window.setInterval(() => {
      void fetchStatus()
    }, POLL_MS)
    return () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [isRunning, fetchStatus])

  const start = async () => {
    setStarting(true)
    setError(null)
    setAdoptMsg(null)
    setAdoptedScore(null)
    try {
      const res = await apiFetch<AgentEvalSessionInfo>(
        `/model/${enc(modelId)}/task/${enc(taskName)}/agent-eval`,
        {
          method: 'POST',
          body: JSON.stringify({ evaluate_trace: evaluateTrace, run_id: evalRunId }),
        },
      )
      setSession(res)
    } catch (e) {
      const msg = errText(e)
      // 409 = 已有运行中的评测
      if (msg.startsWith('409')) {
        setError('已有运行中的评测，请稍候或刷新状态')
      } else {
        setError(msg)
      }
      // 无论结果如何，刷新一次状态
      void fetchStatus()
    } finally {
      setStarting(false)
    }
  }

  const adopt = async () => {
    setAdopting(true)
    setError(null)
    setAdoptMsg(null)
    try {
      const res = await apiFetch<{ success: boolean; message: string; score?: number }>(
        `/model/${enc(modelId)}/task/${enc(taskName)}/agent-eval/adopt`,
        { method: 'POST', body: JSON.stringify({ run_id: session?.run_id ?? evalRunId }) },
      )
      if (res.success) {
        setAdoptMsg(res.message || '采纳成功')
        setAdoptedScore(res.score ?? null)
        onAdopted()
      } else {
        setAdoptMsg(res.message || '采纳失败')
      }
    } catch (e) {
      setError(errText(e))
    } finally {
      setAdopting(false)
    }
  }

  const completed = session?.status === 'completed'

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Agent 评测</h3>
        {session && (
          <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${STATUS_STYLES[session.status] ?? ''}`}>
            {session.status === 'none' ? '未评测' : session.status === 'pending' ? '排队中' : session.status === 'running' ? '评测中…' : session.status === 'completed' ? '已完成' : session.status === 'timeout' ? '超时' : '失败'}
          </span>
        )}
      </div>

      {/* 发起评测表单 */}
      {!session && (
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={evaluateTrace}
              onChange={(e) => setEvaluateTrace(e.target.checked)}
              className="h-3.5 w-3.5 accent-indigo-600"
            />
            过程评价（trace_quality）
          </label>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            run
            <select
              value={evalRunId}
              onChange={(e) => setEvalRunId(e.target.value)}
              className="rounded border border-slate-300 px-1.5 py-1 text-xs outline-none focus:border-indigo-400"
            >
              {(runs.length ? runs : [runId]).map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={start}
            disabled={starting}
            className="rounded-lg bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {starting ? '发起中…' : '⚡ 发起评测'}
          </button>
          {error && <span className="text-xs text-red-600">{error}</span>}
        </div>
      )}

      {/* 评测状态 */}
      {session && (
        <div className="space-y-2 text-xs">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-slate-500">
            <span>
              任务: <b className="font-mono">{session.task_key}</b>
            </span>
            {session.run_id && (
              <span>
                run: <b className="font-mono">{session.run_id}</b>
              </span>
            )}
            {session.started_at && <span>开始: {session.started_at}</span>}
            {session.finished_at && <span>结束: {session.finished_at}</span>}
          </div>
          {session.error && (
            <p className="rounded bg-red-50 p-2 text-red-600">错误: {session.error}</p>
          )}
          {isRunning && <p className="text-amber-600">评测进行中（每 3 秒自动刷新）…</p>}
          {completed && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-emerald-600">评测已完成</span>
              <button
                onClick={adopt}
                disabled={adopting}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {adopting ? '采纳中…' : '✓ 采纳评分'}
              </button>
              <button
                onClick={() => setShowJudge(true)}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                📄 查看评测轨迹
              </button>
              <button
                onClick={() => {
                  setSession(null)
                  void fetchStatus()
                }}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-50"
              >
                刷新状态
              </button>
            </div>
          )}
          {session.status === 'failed' || session.status === 'timeout' ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  setSession(null)
                  void fetchStatus()
                }}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                重新发起
              </button>
              <button
                onClick={() => setShowJudge(true)}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              >
                📄 查看评测轨迹
              </button>
            </div>
          ) : null}
          {adoptMsg && <p className="text-emerald-600">✓ {adoptMsg}</p>}
          {adoptedScore !== null && (
            <p className="font-bold text-slate-700">
              已采纳分数: <span className="text-indigo-600">{pct(adoptedScore)}</span>
            </p>
          )}
          {error && <p className="text-red-600">{error}</p>}
        </div>
      )}

      {!loaded && <p className="text-xs text-slate-400">加载状态…</p>}

      {showJudge && (
        <WorkspaceModal
          modelId={modelId}
          taskName={taskName}
          runId={session?.run_id ?? runId}
          root="judge"
          onClose={() => setShowJudge(false)}
        />
      )}
    </section>
  )
}
