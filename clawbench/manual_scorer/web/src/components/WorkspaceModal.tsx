// 工作区弹窗：左侧可拖拽文件树，右侧按类型分发预览（FilePreview）
// 文件 URL 带 ?token=；支持 root=workspace | judge
import { useCallback, useEffect, useState } from 'react'
import type { WorkspaceFile } from '../types'
import { apiBlob, apiFetch } from '../hooks/useApi'
import { downloadBlob, enc, errText, formatBytes } from '../lib/utils'
import Modal from './Modal'
import FilePreview, { type PreviewFile } from './FilePreview'

interface Props {
  modelId: string
  taskName: string
  runId: string
  root: 'workspace' | 'judge'
  onClose: () => void
}

interface PreviewState {
  path: string
  name: string
  blob: Blob | null
  loading: boolean
  error: string | null
}

export default function WorkspaceModal({ modelId, taskName, runId, root, onClose }: Props) {
  const [files, setFiles] = useState<WorkspaceFile[]>([])
  const [totalSize, setTotalSize] = useState(0)
  const [totalFiles, setTotalFiles] = useState(0)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [downloading, setDownloading] = useState(false)

  const openFile = useCallback(
    async (path: string, name: string) => {
      setPreview({ path, name, blob: null, loading: true, error: null })
      try {
        const q = `root=${root}&path=${encodeURIComponent(path)}&run_id=${encodeURIComponent(runId)}${token ? `&token=${encodeURIComponent(token)}` : ''}`
        const blob = await apiBlob(`/model/${enc(modelId)}/task/${enc(taskName)}/workspace/file?${q}`)
        setPreview({ path, name, blob, loading: false, error: null })
      } catch (e) {
        setPreview({ path, name, blob: null, loading: false, error: errText(e) })
      }
    },
    [modelId, taskName, root, token],
  )

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    apiFetch<{ files: WorkspaceFile[]; total_size: number; total_files: number; token?: string }>(
      `/model/${enc(modelId)}/task/${enc(taskName)}/workspace/files?root=${root}&run_id=${encodeURIComponent(runId)}`,
    )
      .then((resp) => {
        if (!alive) return
        setFiles(resp.files ?? [])
        setTotalSize(resp.total_size ?? 0)
        setTotalFiles(resp.total_files ?? 0)
        if (resp.token) setToken(resp.token)
        // judge 模式自动打开 agent_judge.jsonl 转录
        if (root === 'judge') {
          const jf = findFile(resp.files ?? [], 'agent_judge.jsonl')
          if (jf) void openFile(jf.path, jf.name)
        }
      })
      .catch((e) => alive && setError(errText(e)))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [modelId, taskName, root, openFile])

  const downloadZip = async () => {
    setDownloading(true)
    try {
      const blob = await apiBlob(`/model/${enc(modelId)}/task/${enc(taskName)}/workspace?root=${root}&run_id=${encodeURIComponent(runId)}`)
      downloadBlob(blob, `${taskName}-${root}.zip`)
    } catch (e) {
      setError(errText(e))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <Modal
      title={
        <span>
          工作区 <span className="ml-1 font-mono text-xs text-slate-400">{root}</span>
          <span className="ml-2 text-xs font-normal text-slate-400">
            {totalFiles} 个文件 · {formatBytes(totalSize)}
          </span>
        </span>
      }
      onClose={onClose}
      size="xl"
    >
      <div className="flex h-[70vh]">
        {/* 左侧文件树 */}
        <div className="flex w-64 shrink-0 flex-col border-r border-slate-200">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-[11px] font-semibold text-slate-500">文件树</span>
            <button
              onClick={downloadZip}
              disabled={downloading}
              className="rounded border border-slate-300 px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              {downloading ? '打包中…' : '⬇ ZIP'}
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {loading && <p className="p-3 text-xs text-slate-400">加载中…</p>}
            {error && <p className="p-3 text-xs text-red-500">{error}</p>}
            {!loading && !error && files.length === 0 && (
              <p className="p-3 text-xs text-slate-400">工作区为空</p>
            )}
            {!loading && !error && (
              <div className="space-y-0.5">
                {files.map((f) => (
                  <FileNode
                    key={f.path}
                    node={f}
                    depth={0}
                    selectedPath={preview?.path ?? null}
                    onOpen={openFile}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
        {/* 右侧预览 */}
        <div className="flex min-w-0 flex-1 flex-col p-3">
          {preview === null ? (
            <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-slate-200 text-xs text-slate-400">
              点击左侧文件进行预览
            </div>
          ) : preview.loading ? (
            <div className="flex flex-1 items-center justify-center text-xs text-slate-400">
              加载 {preview.name}…
            </div>
          ) : preview.error ? (
            <div className="flex flex-1 items-center justify-center rounded-lg bg-red-50 p-6 text-xs text-red-600">
              加载失败: {preview.error}
            </div>
          ) : preview.blob ? (
            <FilePreview
              file={{ name: preview.name, blob: preview.blob } satisfies PreviewFile}
              onDownload={() => downloadBlob(preview.blob!, preview.name)}
            />
          ) : null}
        </div>
      </div>
    </Modal>
  )
}

/** 递归查找文件（按名称） */
function findFile(nodes: WorkspaceFile[], name: string): WorkspaceFile | null {
  for (const n of nodes) {
    if (n.type === 'file' && n.name === name) return n
    if (n.children) {
      const hit = findFile(n.children, name)
      if (hit) return hit
    }
  }
  return null
}

function FileNode({
  node,
  depth,
  selectedPath,
  onOpen,
}: {
  node: WorkspaceFile
  depth: number
  selectedPath: string | null
  onOpen: (path: string, name: string) => void
}) {
  const isDir = node.type === 'dir' || (node.children !== undefined && node.children.length > 0)
  const [open, setOpen] = useState(depth === 0)
  const style = { paddingLeft: depth * 14 }

  if (isDir) {
    return (
      <div>
        <button
          onClick={() => setOpen(!open)}
          style={style}
          className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs text-slate-600 hover:bg-slate-100"
        >
          <span className="w-3 shrink-0 text-slate-400">{open ? '▾' : '▸'}</span>
          <span className="shrink-0 text-amber-500">📁</span>
          <span className="min-w-0 flex-1 truncate font-medium">{node.name}</span>
          {node.children && (
            <span className="shrink-0 text-[10px] text-slate-400">{node.children.length}</span>
          )}
        </button>
        {open && node.children && (
          <div className="space-y-0.5">
            {node.children.map((c) => (
              <FileNode key={c.path} node={c} depth={depth + 1} selectedPath={selectedPath} onOpen={onOpen} />
            ))}
          </div>
        )}
      </div>
    )
  }

  const selected = node.path === selectedPath
  return (
    <button
      onClick={() => onOpen(node.path, node.name)}
      style={style}
      className={`flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-xs transition-colors ${
        selected ? 'bg-indigo-100 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
      }`}
      title={node.path}
    >
      <span className="w-3 shrink-0" />
      <span className="shrink-0 text-slate-400">📄</span>
      <span className="min-w-0 flex-1 truncate">{node.name}</span>
      <span className="shrink-0 text-[10px] text-slate-400">{formatBytes(node.size)}</span>
    </button>
  )
}
