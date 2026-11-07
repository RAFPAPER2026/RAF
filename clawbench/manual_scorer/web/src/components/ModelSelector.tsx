// 左栏：模型卡片（run 下拉、per-run 统计、平均行、维度分）+ 新建/删除模型
import { useState, type FormEvent } from 'react'
import type { ModelSummary } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText, pct, pctRate } from '../lib/utils'
import Modal from './Modal'

interface Props {
  models: ModelSummary[]
  loading: boolean
  error: string | null
  selectedId: string | null
  onSelect: (id: string) => void
  runByModel: Record<string, string>
  onRunChange: (modelId: string, run: string) => void
  passThreshold: number
  onModelsChanged: () => void
}

interface RunStats {
  total: number
  scored: number
  passed: number
  avg_score: number | null
  pass_rate: number | null
  // 后端若额外返回维度均值（运行时字段），前端防御性展示
  avg_trace_dimensions?: Record<string, number>
  dimensions?: Record<string, number>
}

function extraDimensions(run: RunStats): Record<string, number> | null {
  return run.avg_trace_dimensions ?? run.dimensions ?? null
}

export default function ModelSelector({
  models,
  loading,
  error,
  selectedId,
  onSelect,
  runByModel,
  onRunChange,
  passThreshold,
  onModelsChanged,
}: Props) {
  const [showNew, setShowNew] = useState(false)
  const [deleting, setDeleting] = useState<ModelSummary | null>(null)

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-700">
            模型列表 <span className="ml-1 text-xs font-normal text-slate-400">{models.length} 个</span>
          </h2>
          <button
            onClick={() => setShowNew(true)}
            className="rounded-md bg-indigo-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-indigo-700"
          >
            + 新建模型
          </button>
        </div>
        {loading && <p className="mt-2 text-xs text-slate-400">加载中…</p>}
        {error && <p className="mt-2 text-xs text-red-500">{errText(error)}</p>}
      </div>

      <div className="flex-1 space-y-3 p-3">
        {models.map((m) => {
          const isSelected = m.id === selectedId
          const effectiveRun = runByModel[m.id] ?? m.default_run ?? 'run_1'
          const runs = m.runs.length ? m.runs : [effectiveRun]
          return (
            <div
              key={m.id}
              onClick={() => onSelect(m.id)}
              className={`cursor-pointer rounded-lg border p-3 transition-colors ${
                isSelected
                  ? 'border-indigo-400 bg-indigo-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              {/* 头部：别名 + 名称 + run 下拉 */}
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-bold text-slate-800">{m.alias || m.name}</span>
                    <span
                      className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        isSelected ? 'bg-indigo-200 text-indigo-700' : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      已选
                    </span>
                  </div>
                  <div className="mt-0.5 truncate text-[11px] text-slate-400" title={m.id}>
                    {m.name} · {m.id}
                  </div>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <select
                    value={effectiveRun}
                    onChange={(e) => onRunChange(m.id, e.target.value)}
                    className="rounded border border-slate-300 bg-white px-1.5 py-1 text-xs text-slate-700 outline-none focus:border-indigo-400"
                    title="选择 run"
                  >
                    {runs.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* per-run 统计表 */}
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[11px] text-slate-400">
                    <th className="pb-1 text-left font-normal">run</th>
                    <th className="pb-1 text-right font-normal">已打分</th>
                    <th className="pb-1 text-right font-normal">通过率</th>
                    <th className="pb-1 text-right font-normal">平均分</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => {
                    const st: RunStats | undefined = m.per_run_stats?.[r]
                    if (!st) {
                      return (
                        <tr key={r} className="border-t border-slate-100 text-slate-400">
                          <td className="py-1">{r}</td>
                          <td className="py-1 text-right">-</td>
                          <td className="py-1 text-right">-</td>
                          <td className="py-1 text-right">-</td>
                        </tr>
                      )
                    }
                    return (
                      <tr key={r} className="border-t border-slate-100">
                        <td className="py-1 font-medium text-slate-600">{r}</td>
                        <td className="py-1 text-right text-slate-600">
                          {st.scored}/{st.total}
                        </td>
                        <td className="py-1 text-right text-slate-600">{pctRate(st.pass_rate)}</td>
                        <td
                          className={`py-1 text-right font-medium ${
                            st.avg_score !== null && st.avg_score >= passThreshold
                              ? 'text-emerald-600'
                              : st.avg_score !== null
                                ? 'text-red-500'
                                : 'text-slate-400'
                          }`}
                        >
                          {pct(st.avg_score)}
                        </td>
                      </tr>
                    )
                  })}
                  {/* 平均行 */}
                  <tr className="border-t border-slate-200 bg-slate-50 text-[11px]">
                    <td className="py-1.5 font-semibold text-slate-500">平均</td>
                    <td className="py-1.5 text-right font-semibold text-slate-500">
                      {m.scored}/{m.total}
                    </td>
                    <td className="py-1.5 text-right font-semibold text-slate-500">{pctRate(m.pass_rate)}</td>
                    <td
                      className={`py-1.5 text-right font-bold ${
                        m.avg_score !== null && m.avg_score >= passThreshold
                          ? 'text-emerald-600'
                          : m.avg_score !== null
                            ? 'text-red-500'
                            : 'text-slate-400'
                      }`}
                    >
                      {pct(m.avg_score)}
                    </td>
                  </tr>
                </tbody>
              </table>

              {/* 维度分（后端有返回时展示；契约类型不含则自动隐藏） */}
              {runs.some((r) => extraDimensions((m.per_run_stats?.[r] as RunStats | undefined) ?? ({} as RunStats))) && (
                <div className="mt-2 border-t border-dashed border-slate-200 pt-2">
                  <div className="mb-1 text-[11px] font-medium text-slate-500">维度分</div>
                  {runs.map((r) => {
                    const dims = extraDimensions((m.per_run_stats?.[r] as RunStats | undefined) ?? ({} as RunStats))
                    if (!dims) return null
                    return (
                      <div key={r} className="mb-0.5 text-[11px] text-slate-600">
                        <span className="mr-1 font-medium text-slate-400">{r}</span>
                        {Object.entries(dims)
                          .map(([k, v]) => `${k} ${pct(v)}`)
                          .join(' · ')}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* 操作 */}
              <div className="mt-2 flex justify-end" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => setDeleting(m)}
                  className="rounded px-1.5 py-0.5 text-[11px] text-slate-400 hover:bg-red-50 hover:text-red-600"
                >
                  删除模型
                </button>
              </div>
            </div>
          )
        })}
        {!loading && models.length === 0 && (
          <p className="px-2 py-8 text-center text-xs text-slate-400">
            暂无模型。
            <br />
            点击右上角「新建模型」或使用上传导入结果。
          </p>
        )}
      </div>

      {showNew && (
        <NewModelDialog
          onClose={() => setShowNew(false)}
          onCreated={() => {
            setShowNew(false)
            onModelsChanged()
          }}
        />
      )}
      {deleting && (
        <DeleteModelDialog
          model={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null)
            onModelsChanged()
          }}
        />
      )}
    </div>
  )
}

// ============================================================
// 新建模型弹窗
// ============================================================
function NewModelDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [modelName, setModelName] = useState('')
  const [prefix, setPrefix] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await apiFetch('/models', {
        method: 'POST',
        body: JSON.stringify({ model_name: modelName.trim(), ...(prefix.trim() ? { prefix: prefix.trim() } : {}) }),
      })
      onCreated()
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="新建模型" onClose={busy ? undefined : onClose} size="md">
      <form onSubmit={submit} className="space-y-4 p-5">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            模型名称 <span className="text-red-500">*</span>
          </label>
          <input
            value={modelName}
            onChange={(e) => setModelName(e.target.value)}
            placeholder="如 glm-5"
            required
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">目录前缀（可选）</label>
          <input
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder="可选，如 my-run（将创建 {prefix}_{name}_{时间戳} 目录）"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            type="submit"
            disabled={busy || !modelName.trim()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? '创建中…' : '创建'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

// ============================================================
// 删除模型弹窗（confirm_name 必须等于 model_id）
// ============================================================
function DeleteModelDialog({
  model,
  onClose,
  onDeleted,
}: {
  model: ModelSummary
  onClose: () => void
  onDeleted: () => void
}) {
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const canDelete = confirm.trim() === model.id

  const doDelete = async () => {
    setBusy(true)
    setError(null)
    try {
      await apiFetch(`/model/${enc(model.id)}?confirm_name=${encodeURIComponent(model.id)}`, {
        method: 'DELETE',
      })
      onDeleted()
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title="删除模型" onClose={busy ? undefined : onClose} size="md">
      <div className="space-y-4 p-5">
        <p className="text-sm text-slate-600">
          即将删除模型 <b className="text-slate-800">{model.alias || model.name}</b>（{model.id}）及其全部结果目录，该操作不可恢复。
        </p>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-600">
            请输入模型 ID 以确认删除：
          </label>
          <input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={model.id}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-200"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消
          </button>
          <button
            onClick={doDelete}
            disabled={busy || !canDelete}
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {busy ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
