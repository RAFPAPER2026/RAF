// 上传结果弹窗（config → checking → conflict → uploading → done）
// 无冲突时快路径直连 confirm（透传服务端解析的 run_id）；
// 冲突步显示已存在/新增列表 + 覆盖/跳过单选
import { useState } from 'react'
import type { UploadCheckResponse } from '../types'
import { apiFetch } from '../hooks/useApi'
import { enc, errText } from '../lib/utils'
import Modal from './Modal'

interface Props {
  modelId: string
  runs: string[]
  onClose: () => void
  onDone: () => void
}

type Step = 'config' | 'checking' | 'conflict' | 'uploading' | 'done'

export default function UploadResultsModal({ modelId, runs, onClose, onDone }: Props) {
  const [step, setStep] = useState<Step>('config')
  const [file, setFile] = useState<File | null>(null)
  const [runChoice, setRunChoice] = useState<'new' | string>('new')
  const [checkResp, setCheckResp] = useState<UploadCheckResponse | null>(null)
  const [resultsOverwrite, setResultsOverwrite] = useState(true)
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const runOptions = ['new', ...runs]

  const check = async () => {
    if (!file) return
    setBusy(true)
    setError(null)
    setStep('checking')
    try {
      const fd = new FormData()
      fd.append('file', file)
      fd.append('run_id', runChoice)
      const resp = await apiFetch<UploadCheckResponse>(`/model/${enc(modelId)}/upload/check`, {
        method: 'POST',
        body: fd,
      })
      setCheckResp(resp)
      if (!resp.has_conflicts) {
        // 快路径：无冲突 → 直连 confirm（透传服务端解析的 run_id）
        await confirm(resp, true)
      } else {
        setStep('conflict')
        setBusy(false)
      }
    } catch (e) {
      setError(errText(e))
      setStep('config')
      setBusy(false)
    }
  }

  const confirm = async (resp: UploadCheckResponse, resultsOverwriteVal: boolean) => {
    setBusy(true)
    setError(null)
    setStep('uploading')
    try {
      const res = await apiFetch<{ success: boolean; message: string }>(`/model/${enc(modelId)}/upload/confirm`, {
        method: 'POST',
        body: JSON.stringify({
          session_id: resp.session_id,
          results_overwrite: resultsOverwriteVal,
          run_id: resp.run_id,
        }),
      })
      setResult(res)
      setStep('done')
    } catch (e) {
      setError(errText(e))
      setStep('conflict')
    } finally {
      setBusy(false)
    }
  }

  const cancelSession = async () => {
    if (!checkResp) return
    try {
      await apiFetch(`/model/${enc(modelId)}/upload/cancel`, {
        method: 'DELETE',
        body: JSON.stringify({ session_id: checkResp.session_id }),
      })
    } catch {
      /* 忽略取消失败 */
    }
  }

  const closeWithCancel = async () => {
    if (step === 'checking' || step === 'conflict' || step === 'uploading') {
      await cancelSession()
    }
    if (step === 'done') onDone()
    onClose()
  }

  return (
    <Modal title="上传结果" onClose={busy ? undefined : () => void closeWithCancel()} size="lg">
      <div className="space-y-4 p-5">
        {/* 步骤指示 */}
        {(() => {
          const steps = ['配置', '解析', '冲突', '导入', '完成'] as const
          const order: Step[] = ['config', 'checking', 'conflict', 'uploading', 'done']
          const currentIdx = order.indexOf(step)
          return (
            <div className="flex items-center gap-1 text-[11px] text-slate-400">
              {steps.map((label, i) => (
                <span key={label} className="flex items-center gap-1">
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                      i === currentIdx
                        ? 'bg-indigo-600 text-white'
                        : i < currentIdx
                          ? 'bg-indigo-100 text-indigo-600'
                          : 'bg-slate-100 text-slate-400'
                    }`}
                  >
                    {i + 1}
                  </span>
                  <span>{label}</span>
                  {i < steps.length - 1 && <span className="mx-0.5 text-slate-300">→</span>}
                </span>
              ))}
            </div>
          )
        })()}

        {/* 1. 配置 */}
        {step === 'config' && (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">
                结果压缩包（.zip / .rar）<span className="text-red-500">*</span>
              </label>
              <input
                type="file"
                accept=".zip,.rar"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-indigo-50 file:px-3 file:py-2 file:text-xs file:font-medium file:text-indigo-600 hover:file:bg-indigo-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">目标 run</label>
              <select
                value={runChoice}
                onChange={(e) => setRunChoice(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs outline-none focus:border-indigo-500"
              >
                {runOptions.map((r) => (
                  <option key={r} value={r}>
                    {r === 'new' ? '新建 run（自动分配）' : r}
                  </option>
                ))}
              </select>
            </div>
            {error && <p className="rounded bg-red-50 p-2 text-xs text-red-600">{error}</p>}
            <div className="flex justify-end">
              <button
                onClick={check}
                disabled={busy || !file}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                解析并检查冲突
              </button>
            </div>
          </div>
        )}

        {/* 2. 解析中 */}
        {step === 'checking' && (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-slate-500">
            <span className="text-2xl">⏳</span>
            <p>正在解析压缩包、扫描冲突（大文件可能需要一点时间）…</p>
            {error && <p className="text-xs text-red-600">{error}</p>}
          </div>
        )}

        {/* 3. 冲突 */}
        {step === 'conflict' && checkResp && (
          <div className="space-y-4">
            <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-700">
              检测到冲突，请确认导入方式。目标 run: <b className="font-mono">{checkResp.run_id}</b>
            </p>

            <ConflictSection
              toImport={checkResp.results_to_import}
              conflicts={checkResp.results_conflicts}
              overwrite={resultsOverwrite}
              onOverwriteChange={setResultsOverwrite}
            />

            {error && <p className="rounded bg-red-50 p-2 text-xs text-red-600">{error}</p>}

            <div className="flex justify-end gap-2">
              <button
                onClick={() => void closeWithCancel()}
                className="rounded-lg border border-slate-300 px-4 py-2 text-xs text-slate-600 hover:bg-slate-50"
              >
                取消（删除暂存）
              </button>
              <button
                onClick={() => void confirm(checkResp, resultsOverwrite)}
                disabled={busy}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {busy ? '导入中…' : '确认导入'}
              </button>
            </div>
          </div>
        )}

        {/* 4. 导入中 */}
        {step === 'uploading' && (
          <div className="flex flex-col items-center gap-3 py-10 text-sm text-slate-500">
            <span className="text-2xl">⏳</span>
            <p>正在导入结果…</p>
            {error && <p className="text-xs text-red-600">{error}</p>}
          </div>
        )}

        {/* 5. 完成 */}
        {step === 'done' && result && (
          <div className="space-y-4">
            <div
              className={`rounded-lg p-3 text-sm ${
                result.success ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
              }`}
            >
              <p className="font-bold">{result.success ? '✓ 导入成功' : '✗ 导入失败'}</p>
              <p className="mt-1 whitespace-pre-wrap text-xs">{result.message}</p>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  onDone()
                  onClose()
                }}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-700"
              >
                关闭并刷新
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}

// ============================================================
// 冲突区块：新增 / 已存在列表 + 覆盖/跳过单选
// ============================================================
function ConflictSection({
  toImport,
  conflicts,
  overwrite,
  onOverwriteChange,
}: {
  toImport: string[]
  conflicts: string[]
  overwrite: boolean
  onOverwriteChange: (v: boolean) => void
}) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-600">结果（result）</span>
        {conflicts.length > 0 && (
          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            <label className="flex cursor-pointer items-center gap-1">
              <input
                type="radio"
                checked={overwrite}
                onChange={() => onOverwriteChange(true)}
                className="h-3 w-3 accent-indigo-600"
              />
              覆盖已存在
            </label>
            <label className="flex cursor-pointer items-center gap-1">
              <input
                type="radio"
                checked={!overwrite}
                onChange={() => onOverwriteChange(false)}
                className="h-3 w-3 accent-indigo-600"
              />
              跳过已存在
            </label>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 text-[11px]">
        <div>
          <p className="mb-1 font-medium text-emerald-600">新增 {toImport.length} 项</p>
          <div className="max-h-24 space-y-0.5 overflow-y-auto rounded bg-emerald-50/50 p-1.5">
            {toImport.length === 0 ? (
              <p className="text-slate-400">无</p>
            ) : (
              toImport.map((n) => (
                <p key={n} className="truncate text-slate-600" title={n}>
                  {n}
                </p>
              ))
            )}
          </div>
        </div>
        <div>
          <p className="mb-1 font-medium text-amber-600">已存在 {conflicts.length} 项</p>
          <div className="max-h-24 space-y-0.5 overflow-y-auto rounded bg-amber-50/50 p-1.5">
            {conflicts.length === 0 ? (
              <p className="text-slate-400">无</p>
            ) : (
              conflicts.map((n) => (
                <p key={n} className="truncate text-slate-600" title={n}>
                  {n}
                </p>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
