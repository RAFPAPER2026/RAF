// 右栏：任务详情（按 model-task-run 键控）
// 标题 + 存疑开关 + 工作区；prompt；AgentEvalPanel；Case标记；任务完成(仅 flat)；
// Rubric打分(tree/flat)；过程评价；会话轨迹
import { useMemo, useState } from 'react'
import type { TaskDetail as TaskDetailData, TaskSummary, TraceDimension } from '../types'
import { apiBlob, apiFetch, useTaskDetail } from '../hooks/useApi'
import { detectRubricFormat, extractRubricResults } from '../lib/scoring'
import { downloadBlob, enc, errText, pct } from '../lib/utils'
import TreeRubricScoringForm from './TreeRubricScoringForm'
import ScoringForm, { TraceQualityForm } from './ScoringForm'
import AgentEvalPanel from './AgentEvalPanel'
import WorkspaceModal from './WorkspaceModal'

interface Props {
  modelId: string
  taskName: string
  runId: string
  task: TaskSummary | null
  runs: string[]
  dimensions: TraceDimension[]
  refreshTasks: () => void
  refreshModels: () => void
}

export default function TaskDetail({
  modelId,
  taskName,
  runId,
  task,
  runs,
  dimensions,
  refreshTasks,
  refreshModels,
}: Props) {
  const { detail, loading, error, refresh: refreshDetail } = useTaskDetail(modelId, taskName, runId)
  const [showWorkspace, setShowWorkspace] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)

  // rubric 格式：config 嗅探优先，回退 TaskSummary.rubric_format
  const rubric = detail?.config?.rubric ?? null
  const rubricFormat = useMemo(() => {
    if (!rubric) return task?.rubric_format ?? null
    const detected = detectRubricFormat(rubric)
    if (detected) return detected
    return task?.rubric_format ?? null
  }, [rubric, task])

  const prompt = useMemo(() => getPrompt(detail), [detail])

  // 只 refetch 列表（保表单状态）：反馈 / 存疑
  const patchAndRefreshList = async (path: string, body: unknown, successText: string) => {
    try {
      await apiFetch(`/model/${enc(modelId)}/task/${enc(taskName)}${path}`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      })
      setMsg({ ok: true, text: successText })
      refreshTasks()
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    }
  }

  // 打分保存后：refetch tasks + detail + models
  const onScoreSaved = () => {
    refreshTasks()
    refreshDetail()
    refreshModels()
    setMsg({ ok: true, text: '打分已保存' })
  }

  const downloadWorkspace = async () => {
    try {
      const blob = await apiBlob(`/model/${enc(modelId)}/task/${enc(taskName)}/workspace?root=workspace&run_id=${encodeURIComponent(runId)}`)
      downloadBlob(blob, `${taskName}-workspace.zip`)
    } catch (e) {
      setMsg({ ok: false, text: errText(e) })
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-5">
      {/* 标题 + 存疑 + 工作区 */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold text-slate-800" title={taskName}>
              {taskName}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono">{runId}</span>
              <span>{task?.status ?? '-'}</span>
              {task?.rubric_format === 'tree' && (
                <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-600">树形 rubric</span>
              )}
              {task?.rubric_format === 'flat' && (
                <span className="rounded bg-teal-50 px-1.5 py-0.5 text-teal-600">平铺 rubric</span>
              )}
              <span className={task && task.score !== null ? 'font-bold text-slate-700' : 'text-slate-300'}>
                分数: {task && task.score !== null ? pct(task.score) : '未打分'}
              </span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {/* 存疑开关 */}
            <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={task?.doubtful ?? false}
                onChange={(e) =>
                  void patchAndRefreshList('/doubtful', { doubtful: e.target.checked }, '存疑标记已更新')
                }
                className="h-3.5 w-3.5 accent-amber-500"
              />
              存疑
            </label>
            <button
              onClick={downloadWorkspace}
              className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              title="下载工作区 ZIP"
            >
              ⬇ 下载 ZIP
            </button>
            <button
              onClick={() => setShowWorkspace(true)}
              className="rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
            >
              📁 工作区
            </button>
          </div>
        </div>
        {msg && (
          <p className={`mt-2 text-xs ${msg.ok ? 'text-emerald-600' : 'text-red-600'}`}>
            {msg.ok ? '✓ ' : '✗ '}
            {msg.text}
          </p>
        )}
      </div>

      {loading && <p className="py-8 text-center text-sm text-slate-400">加载任务详情…</p>}
      {error && <p className="rounded-lg bg-red-50 p-4 text-sm text-red-600">加载失败: {error}</p>}

      {detail && (
        <>
          {/* Prompt */}
          {prompt && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">任务提问（Prompt）</h3>
              <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-[13px] leading-relaxed text-slate-700">
                {prompt}
              </p>
            </section>
          )}

          {/* Agent 评测 */}
          <AgentEvalPanel
            modelId={modelId}
            taskName={taskName}
            runId={runId}
            runs={runs}
            onAdopted={() => {
              refreshTasks()
              refreshDetail()
              refreshModels()
            }}
          />

          {/* Case 标记 */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">Case 标记</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={() => void patchAndRefreshList('/manual-feedback', { manual_feedback: 1 }, '已标记为好案例')}
                className={`rounded-lg px-3 py-1.5 text-sm ${
                  task?.manual_feedback === 1
                    ? 'bg-pink-100 ring-2 ring-pink-400'
                    : 'bg-slate-50 text-slate-600 hover:bg-pink-50'
                }`}
              >
                🌸 好
              </button>
              <button
                onClick={() => void patchAndRefreshList('/manual-feedback', { manual_feedback: -1 }, '已标记为差案例')}
                className={`rounded-lg px-3 py-1.5 text-sm ${
                  task?.manual_feedback === -1
                    ? 'bg-purple-100 ring-2 ring-purple-400'
                    : 'bg-slate-50 text-slate-600 hover:bg-purple-50'
                }`}
              >
                👻 差
              </button>
              <button
                onClick={() => void patchAndRefreshList('/manual-feedback', { manual_feedback: 0 }, '已清除标记')}
                className="rounded-lg bg-slate-50 px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100"
              >
                清除
              </button>
            </div>
          </section>

          {/* 任务完成开关（仅 flat 显示；tree 由树推导） */}
          {rubricFormat === 'flat' && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">任务完成标记</h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    void patchAndRefreshList('/complete-flag', { complete_flag: 1 }, '已标记为完成')
                  }
                  className={`rounded-lg px-3 py-1.5 text-sm ${
                    task?.complete_flag === 1
                      ? 'bg-emerald-100 ring-2 ring-emerald-400'
                      : 'bg-slate-50 text-slate-600 hover:bg-emerald-50'
                  }`}
                >
                  ✓ 完成
                </button>
                <button
                  onClick={() =>
                    void patchAndRefreshList('/complete-flag', { complete_flag: 0 }, '已标记为未完成')
                  }
                  className={`rounded-lg px-3 py-1.5 text-sm ${
                    task?.complete_flag === 0
                      ? 'bg-red-100 ring-2 ring-red-300'
                      : 'bg-slate-50 text-slate-600 hover:bg-red-50'
                  }`}
                >
                  ✗ 未完成
                </button>
                <button
                  onClick={() =>
                    void patchAndRefreshList('/complete-flag', { complete_flag: null }, '已清除完成标记')
                  }
                  className="rounded-lg bg-slate-50 px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-100"
                >
                  清除
                </button>
              </div>
            </section>
          )}

          {/* Rubric 打分 */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">
              Rubric 打分
              <span className="ml-2 text-xs font-normal text-slate-400">
                {rubricFormat === 'tree' ? '树形（点击叶子勾选通过/失败）' : '平铺（点击项头切换完成）'}
              </span>
            </h3>
            {rubricFormat === 'tree' ? (
              <TreeRubricScoringForm
                modelId={modelId}
                taskName={taskName}
                runId={runId}
                rubric={rubric}
                initialResults={extractRubricResults(detail.score)}
                task={task}
                onSaved={onScoreSaved}
              />
            ) : rubricFormat === 'flat' ? (
              <ScoringForm
                modelId={modelId}
                taskName={taskName}
                runId={runId}
                rubric={rubric}
                initialScores={detail.score?.rubric_scores}
                task={task}
                onSaved={onScoreSaved}
              />
            ) : (
              <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-400">
                该任务无 rubric 配置，可直接在下方手动填写评分。
              </p>
            )}
          </section>

          {/* 过程评价 */}
          <TraceQualityForm
            modelId={modelId}
            taskName={taskName}
            runId={runId}
            dimensions={dimensions}
            initial={detail.score?.trace_quality?.dimensions}
          />

          {/* 会话轨迹 */}
          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h3 className="mb-2 text-sm font-semibold text-slate-700">
              会话轨迹
              <span className="ml-2 text-xs font-normal text-slate-400">{detail.sessions?.length ?? 0} 条事件</span>
            </h3>
            {detail.sessions && detail.sessions.length > 0 ? (
              <div className="space-y-1.5">
                {detail.sessions.map((s, i) => (
                  <SessionEvent key={i} event={s} index={i} />
                ))}
              </div>
            ) : (
              <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-400">无会话数据</p>
            )}
          </section>
        </>
      )}

      {showWorkspace && (
        <WorkspaceModal
          modelId={modelId}
          taskName={taskName}
          runId={runId}
          root="workspace"
          onClose={() => setShowWorkspace(false)}
        />
      )}
    </div>
  )
}

// ============================================================
// Prompt 提取：config 常见字段 → rubric.query → 首条会话用户消息
// ============================================================
function getPrompt(detail: TaskDetailData | null): string {
  if (!detail) return ''
  const config = detail.config ?? {}
  for (const key of ['prompt', 'prompt_text', 'query', 'prompt_template', 'description']) {
    const v = config[key]
    if (typeof v === 'string' && v.trim()) return v
  }
  const rubric = config.rubric
  if (rubric && typeof rubric === 'object' && !Array.isArray(rubric)) {
    const q = (rubric as Record<string, unknown>).query
    if (typeof q === 'string' && q.trim()) return q
  }
  for (const s of detail.sessions ?? []) {
    // 只看用户消息：sessions.json 现含 system/compaction 等原始记录，避免误取为任务提问
    const role = s?.message?.role ?? s?.role
    if (role === undefined ? s?.type !== 'user' : role !== 'user') continue
    const content = s?.message?.content ?? s?.content
    if (typeof content === 'string' && content.trim()) return content
    if (Array.isArray(content)) {
      const text = content
        .filter((b: any) => b?.type === 'text' && typeof b.text === 'string')
        .map((b: any) => b.text)
        .join('\n')
      if (text.trim()) return text
    }
  }
  return ''
}

// ============================================================
// 单条会话事件（可展开 JSON）
// sessions.json 存 openclaw 完整原始记录（type=message + message.role），
// 展示兼容 SDK 风格事件与原始记录两种形状。
// ============================================================
function sessionEventType(event: any): string {
  const type = typeof event?.type === 'string' ? event.type : ''
  if (type === 'message') {
    const role = event?.message?.role
    if (typeof role === 'string') return role === 'toolResult' ? 'tool_result' : role
  }
  return type || (typeof event?.role === 'string' ? event.role : 'event')
}

function sessionEventSummary(event: any): string {
  const msg = event?.message
  const content = msg?.content ?? event?.content
  if (Array.isArray(content)) {
    const parts: string[] = []
    for (const b of content) {
      if (!b || typeof b !== 'object') continue
      const block = b as Record<string, unknown>
      if (block.type === 'text' && typeof block.text === 'string' && block.text.trim()) {
        parts.push(block.text)
      } else if (block.type === 'toolCall' || block.type === 'tool_use') {
        parts.push(`🛠 ${String(block.name ?? 'tool')}`)
      } else if (block.type === 'tool_result') {
        const inner = block.content
        parts.push(typeof inner === 'string' ? `↩ ${inner.slice(0, 40)}` : '↩ tool_result')
      }
    }
    if (parts.length) return parts.join(' ').slice(0, 80)
  } else if (typeof content === 'string') {
    return content.slice(0, 80)
  }
  if (msg?.role) return `role: ${msg.role}`
  return ''
}

function SessionEvent({ event, index }: { event: any; index: number }) {
  const [open, setOpen] = useState(false)
  const label = `${index + 1}`
  const type = sessionEventType(event)
  const ts = event?.timestamp ?? event?.time ?? ''
  const summary = sessionEventSummary(event)
  const isError = event?.message?.isError ?? event?.is_error

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-slate-50 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100"
      >
        <span className="shrink-0 rounded bg-slate-200 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">{label}</span>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${
            isError ? 'bg-red-50 text-red-600' : 'bg-indigo-50 text-indigo-600'
          }`}
        >
          {type}
        </span>
        {ts && <span className="shrink-0 font-mono text-[10px] text-slate-400">{ts}</span>}
        <span className="min-w-0 flex-1 truncate text-slate-500">{summary}</span>
        <span className="shrink-0 text-slate-400">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <pre className="trace-json max-h-80 overflow-y-auto bg-slate-900 p-3 text-slate-200">
          {JSON.stringify(event, null, 2)}
        </pre>
      )}
    </div>
  )
}
