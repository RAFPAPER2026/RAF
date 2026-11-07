// 中栏：任务卡片列表 + 筛选 + 批量评测 + 上传入口
import { useMemo, useState } from 'react'
import type { TaskSummary } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct } from '../lib/utils'
import BatchEvalModal from './BatchEvalModal'
import UploadResultsModal from './UploadResultsModal'

interface Props {
  modelId: string | null
  runId: string
  tasks: TaskSummary[]
  loading: boolean
  selectedTask: string | null
  onSelectTask: (name: string) => void
  refreshTasks: () => void
  refreshModels: () => void
  passThreshold: number
  runs: string[]
}

type Filter = 'all' | 'unscored' | 'scored'

const STATUS_TEXT: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  running: '运行中',
  queued: '排队中',
  timeout: '超时',
}

export default function TaskList({
  modelId,
  runId,
  tasks,
  loading,
  selectedTask,
  onSelectTask,
  refreshTasks,
  refreshModels,
  passThreshold,
  runs,
}: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const [showBatch, setShowBatch] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  const [busyDelete, setBusyDelete] = useState<string | null>(null)

  const filtered = useMemo(() => {
    switch (filter) {
      case 'unscored':
        return tasks.filter((t) => t.score === null)
      case 'scored':
        return tasks.filter((t) => t.score !== null)
      default:
        return tasks
    }
  }, [tasks, filter])

  const deleteTask = async (name: string) => {
    if (!modelId) return
    if (!window.confirm(`确认删除任务 ${name} 的全部结果目录？此操作不可恢复。`)) return
    setBusyDelete(name)
    try {
      await apiFetch(`/model/${enc(modelId)}/task/${enc(name)}`, { method: 'DELETE' })
      refreshTasks()
      refreshModels()
    } catch (e) {
      window.alert(`删除失败: ${errText(e)}`)
    } finally {
      setBusyDelete(null)
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            任务列表
            <span className="ml-1 text-xs font-normal text-slate-400">
              {filtered.length}/{tasks.length} · run {runId}
            </span>
          </h2>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowBatch(true)}
              disabled={!modelId}
              className="rounded-md bg-amber-500 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-40"
              title="批量 Agent 评测"
            >
              ⚡ 批量评测
            </button>
            <button
              onClick={() => setShowUpload(true)}
              disabled={!modelId}
              className="rounded-md bg-slate-700 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-40"
              title="上传结果 / 用例"
            >
              上传
            </button>
          </div>
        </div>
        {/* 筛选 */}
        <div className="flex gap-1 text-xs">
          {(
            [
              ['all', '全部'],
              ['unscored', '未打分'],
              ['scored', '已打分'],
            ] as Array<[Filter, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`rounded-full px-2.5 py-1 font-medium transition-colors ${
                filter === key ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 space-y-2 p-3">
        {loading && <p className="px-2 py-6 text-center text-xs text-slate-400">加载中…</p>}
        {!loading && filtered.length === 0 && (
          <p className="px-2 py-6 text-center text-xs text-slate-400">没有符合条件的任务</p>
        )}
        {filtered.map((t) => {
          const isSelected = t.task_name === selectedTask
          const isScored = t.score !== null
          return (
            <div
              key={t.task_name}
              onClick={() => onSelectTask(t.task_name)}
              className={`group relative cursor-pointer rounded-lg border p-3 transition-colors ${
                isSelected
                  ? 'border-indigo-400 bg-indigo-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span
                  className={`truncate text-[13px] font-medium ${
                    isScored ? 'text-slate-800' : 'text-slate-500'
                  }`}
                  title={t.task_name}
                >
                  {t.task_name}
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  {/* 反馈标记 */}
                  {t.manual_feedback === 1 && (
                    <span title="人工反馈：好">🌸</span>
                  )}
                  {t.manual_feedback === -1 && (
                    <span title="人工反馈：差">👻</span>
                  )}
                  {/* 完成标记 */}
                  {t.complete_flag === 1 && (
                    <span className="rounded bg-emerald-100 px-1 py-0.5 text-[10px] font-bold text-emerald-700">✓</span>
                  )}
                  {t.complete_flag === 0 && (
                    <span className="rounded bg-slate-100 px-1 py-0.5 text-[10px] font-bold text-slate-400">✗</span>
                  )}
                  {t.doubtful && (
                    <span className="rounded bg-amber-100 px-1 py-0.5 text-[10px] font-bold text-amber-700" title="存疑">
                      ⚠ 存疑
                    </span>
                  )}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">
                  {STATUS_TEXT[t.status] ?? t.status} · {t.rubric_format === 'tree' ? '树形' : t.rubric_format === 'flat' ? '平铺' : '无 rubric'}
                </span>
                <span
                  className={`font-bold ${
                    isScored
                      ? t.complete_flag === 1 || (t.score ?? 0) >= passThreshold
                        ? 'text-emerald-600'
                        : 'text-red-500'
                      : 'text-slate-300'
                  }`}
                >
                  {isScored ? pct(t.score) : '未打分'}
                </span>
              </div>
              {t.completion_rate !== null && (
                <div className="mt-1 text-[10px] text-slate-400">完成度 {pct(t.completion_rate)}</div>
              )}
              {/* 删除任务 */}
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  void deleteTask(t.task_name)
                }}
                disabled={busyDelete === t.task_name}
                title="删除任务"
                className="absolute right-1.5 top-1.5 hidden rounded p-1 text-xs text-slate-300 hover:bg-red-50 hover:text-red-500 group-hover:block"
              >
                {busyDelete === t.task_name ? '…' : '✕'}
              </button>
            </div>
          )
        })}
      </div>

      {showBatch && modelId && (
        <BatchEvalModal
          modelId={modelId}
          tasks={tasks}
          runs={runs.length ? runs : ['run_1']}
          onClose={() => setShowBatch(false)}
          onDone={() => {
            setShowBatch(false)
            refreshTasks()
            refreshModels()
          }}
        />
      )}
      {showUpload && modelId && (
        <UploadResultsModal
          modelId={modelId}
          runs={runs.length ? runs : ['run_1']}
          onClose={() => setShowUpload(false)}
          onDone={() => {
            setShowUpload(false)
            refreshTasks()
            refreshModels()
          }}
        />
      )}
    </div>
  )
}
