// 顶栏统计 + 三栏布局
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ModelSummary, Stats, TraceConfig } from './types'
import { apiFetch, useModels, useTasks } from './hooks/useApi'
import { errText } from './lib/utils'
import ModelSelector from './components/ModelSelector'
import TaskList from './components/TaskList'
import TaskDetail from './components/TaskDetail'

export default function App() {
  const { models, loading: modelsLoading, error: modelsError, refresh: refreshModels } = useModels()
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null)
  const [selectedTaskName, setSelectedTaskName] = useState<string | null>(null)
  // per-model run 记忆
  const [runByModel, setRunByModel] = useState<Record<string, string>>({})
  const [stats, setStats] = useState<Stats | null>(null)
  const [traceConfig, setTraceConfig] = useState<TraceConfig | null>(null)

  // 有效模型：优先选中项，否则自动选首个
  const selectedModel: ModelSummary | null = useMemo(() => {
    if (!models.length) return null
    return models.find((m) => m.id === selectedModelId) ?? models[0]
  }, [models, selectedModelId])

  // 有效 run：per-model 记忆 → default_run → run_1
  const runId = useMemo(() => {
    if (!selectedModel) return 'run_1'
    return runByModel[selectedModel.id] ?? selectedModel.default_run ?? 'run_1'
  }, [selectedModel, runByModel])

  const { tasks, loading: tasksLoading, refresh: refreshTasks } = useTasks(selectedModel?.id ?? null, runId)

  // 当前任务：优先选中项，否则首个
  const activeTaskName = useMemo(() => {
    if (!tasks.length) return null
    if (selectedTaskName && tasks.some((t) => t.task_name === selectedTaskName)) return selectedTaskName
    return tasks[0]?.task_name ?? null
  }, [tasks, selectedTaskName])

  const loadStats = useCallback(async () => {
    try {
      setStats(await apiFetch<Stats>('/stats'))
    } catch {
      /* 顶栏统计失败不阻塞 */
    }
  }, [])

  const loadTraceConfig = useCallback(async () => {
    try {
      setTraceConfig(await apiFetch<TraceConfig>('/trace-config'))
    } catch {
      /* 无配置时使用默认 */
    }
  }, [])

  useEffect(() => {
    void loadStats()
    void loadTraceConfig()
  }, [loadStats, loadTraceConfig])

  const refreshAll = useCallback(() => {
    void refreshModels()
    void loadStats()
  }, [refreshModels, loadStats])

  const passThreshold = traceConfig?.pass_threshold ?? 0.75
  const activeTask = tasks.find((t) => t.task_name === activeTaskName) ?? null

  return (
    <div className="flex h-full flex-col">
      {/* 顶栏统计 */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-700 bg-slate-800 px-5 py-3 text-white">
        <div className="flex items-baseline gap-3">
          <h1 className="text-lg font-bold">人工打分平台</h1>
          <span className="text-xs text-slate-400">Manual Scorer</span>
        </div>
        <div className="flex items-center gap-4 text-sm">
          <span>
            模型 <b className="text-indigo-300">{stats?.total_models ?? models.length}</b>
          </span>
          <span>
            任务 <b className="text-indigo-300">{stats?.total_tasks ?? '-'}</b>
          </span>
          <span>
            已打分 <b className="text-emerald-300">{stats?.total_scored ?? '-'}</b>
          </span>
          <span>
            未打分 <b className="text-amber-300">{stats?.total_unscored ?? '-'}</b>
          </span>
        </div>
      </header>

      {/* 三栏布局 */}
      <div className="flex min-h-0 flex-1">
        {/* 左栏：模型选择 */}
        <aside className="w-[280px] shrink-0 overflow-y-auto border-r border-slate-200 bg-white">
          <ModelSelector
            models={models}
            loading={modelsLoading}
            error={modelsError}
            selectedId={selectedModel?.id ?? null}
            onSelect={setSelectedModelId}
            runByModel={runByModel}
            onRunChange={(modelId, run) => setRunByModel((prev) => ({ ...prev, [modelId]: run }))}
            passThreshold={passThreshold}
            onModelsChanged={refreshAll}
          />
        </aside>

        {/* 中栏：任务列表 */}
        <section className="w-[360px] shrink-0 overflow-y-auto border-r border-slate-200 bg-slate-50">
          <TaskList
            modelId={selectedModel?.id ?? null}
            runId={runId}
            tasks={tasks}
            loading={tasksLoading}
            selectedTask={activeTaskName}
            onSelectTask={setSelectedTaskName}
            refreshTasks={refreshTasks}
            refreshModels={refreshAll}
            passThreshold={passThreshold}
            runs={selectedModel?.runs ?? []}
          />
        </section>

        {/* 右栏：任务详情 */}
        <main className="min-w-0 flex-1 overflow-y-auto bg-slate-100">
          {selectedModel && activeTaskName ? (
            <TaskDetail
              key={`${selectedModel.id}|${activeTaskName}|${runId}`}
              modelId={selectedModel.id}
              taskName={activeTaskName}
              runId={runId}
              task={activeTask}
              runs={selectedModel.runs}
              dimensions={traceConfig?.dimensions ?? []}
              refreshTasks={refreshTasks}
              refreshModels={refreshAll}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              {models.length === 0 ? '暂无模型，请先创建或上传' : '请选择任务'}
            </div>
          )}
        </main>
      </div>

      {/* 全局错误提示（模型加载失败） */}
      {modelsError && (
        <div className="fixed bottom-4 right-4 z-50 rounded-lg bg-red-600 px-4 py-2 text-sm text-white shadow-lg">
          模型加载失败: {errText(modelsError)}
        </div>
      )}
    </div>
  )
}
