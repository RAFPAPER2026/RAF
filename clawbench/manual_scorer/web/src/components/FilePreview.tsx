// 文件预览：按类型分发渲染
// agent_judge.jsonl → Transcript；图片 → <img>；html → 沙箱 iframe；
// md → react-markdown；csv/tsv → papaparse；xlsx → SheetJS；pdf → iframe；
// docx → mammoth + DOMPurify；代码 → Prism；其余仅下载
import { useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import Papa from 'papaparse'
import * as XLSX from 'xlsx'
import mammoth from 'mammoth'
import DOMPurify from 'dompurify'
import Prism from 'prismjs'
import 'prismjs/components/prism-typescript'
import 'prismjs/components/prism-jsx'
import 'prismjs/components/prism-tsx'
import 'prismjs/components/prism-python'
import 'prismjs/components/prism-bash'
import 'prismjs/components/prism-json'
import 'prismjs/components/prism-yaml'
import 'prismjs/components/prism-markup'
import 'prismjs/components/prism-css'
import 'prismjs/components/prism-scss'
import 'prismjs/components/prism-sql'
import 'prismjs/components/prism-java'
import 'prismjs/components/prism-go'
import 'prismjs/components/prism-rust'
import 'prismjs/components/prism-c'
import 'prismjs/components/prism-cpp'
import 'prismjs/components/prism-csharp'
import 'prismjs/components/prism-docker'
import 'prismjs/components/prism-ini'
import 'prismjs/components/prism-toml'
import 'prismjs/components/prism-markdown'
import 'prismjs/components/prism-diff'
import { downloadBlob, errText, formatBytes } from '../lib/utils'

export interface PreviewFile {
  name: string
  blob: Blob
}

const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']

const CODE_LANGS: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  pyw: 'python',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  html: 'markup',
  htm: 'markup',
  xml: 'markup',
  svg: 'markup',
  css: 'css',
  scss: 'scss',
  less: 'css',
  sql: 'sql',
  java: 'java',
  go: 'go',
  rs: 'rust',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cc: 'cpp',
  hpp: 'cpp',
  cs: 'csharp',
  md: 'markdown',
  markdown: 'markdown',
  dockerfile: 'docker',
  ini: 'ini',
  cfg: 'ini',
  toml: 'toml',
  diff: 'diff',
}

const TEXT_EXTS = ['txt', 'log', 'jsonl', 'conf', 'env', 'gitignore', 'properties', 'csv', 'tsv']

type Kind =
  | 'transcript'
  | 'image'
  | 'html'
  | 'markdown'
  | 'csv'
  | 'tsv'
  | 'xlsx'
  | 'pdf'
  | 'docx'
  | 'code'
  | 'text'
  | 'binary'

function classifyFile(name: string): Kind {
  const lower = name.toLowerCase()
  if (lower === 'agent_judge.jsonl') return 'transcript'
  const ext = lower.split('.').pop() ?? ''
  if (IMAGE_EXTS.includes(ext)) return 'image'
  if (ext === 'html' || ext === 'htm') return 'html'
  if (ext === 'md' || ext === 'markdown') return 'markdown'
  if (ext === 'csv') return 'csv'
  if (ext === 'tsv') return 'tsv'
  if (ext === 'xlsx' || ext === 'xls') return 'xlsx'
  if (ext === 'pdf') return 'pdf'
  if (ext === 'docx') return 'docx'
  if (CODE_LANGS[ext]) return 'code'
  if (TEXT_EXTS.includes(ext)) return 'text'
  return 'binary'
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 读取文本（二进制安全） */
function readText(blob: Blob): Promise<string> {
  return blob.text()
}

export default function FilePreview({ file, onDownload }: { file: PreviewFile; onDownload?: () => void }) {
  const kind = classifyFile(file.name)
  const download = () => downloadBlob(file.blob, file.name)

  const header = (
    <div className="mb-2 flex items-center justify-between">
      <span className="min-w-0 truncate font-mono text-xs text-slate-600" title={file.name}>
        {file.name} <span className="ml-1 text-slate-400">({formatBytes(file.blob.size)})</span>
      </span>
      <button
        onClick={onDownload ?? download}
        className="shrink-0 rounded border border-slate-300 px-2 py-1 text-[11px] text-slate-600 hover:bg-slate-50"
      >
        ⬇ 下载
      </button>
    </div>
  )

  switch (kind) {
    case 'transcript':
      return (
        <div className="flex h-full flex-col">
          {header}
          <TranscriptView file={file} />
        </div>
      )
    case 'image':
      return (
        <div className="flex h-full flex-col">
          {header}
          <ImageView blob={file.blob} name={file.name} />
        </div>
      )
    case 'html':
      return (
        <div className="flex h-full flex-col">
          {header}
          <HtmlView file={file} />
        </div>
      )
    case 'markdown':
      return (
        <div className="flex h-full flex-col">
          {header}
          <MarkdownView file={file} />
        </div>
      )
    case 'csv':
    case 'tsv':
      return (
        <div className="flex h-full flex-col">
          {header}
          <CsvView file={file} sep={kind === 'tsv' ? '\t' : ','} />
        </div>
      )
    case 'xlsx':
      return (
        <div className="flex h-full flex-col">
          {header}
          <XlsxView file={file} />
        </div>
      )
    case 'pdf':
      return (
        <div className="flex h-full flex-col">
          {header}
          <PdfView blob={file.blob} />
        </div>
      )
    case 'docx':
      return (
        <div className="flex h-full flex-col">
          {header}
          <DocxView file={file} />
        </div>
      )
    case 'code':
      return (
        <div className="flex h-full flex-col">
          {header}
          <CodeView file={file} lang={CODE_LANGS[file.name.toLowerCase().split('.').pop() ?? ''] ?? 'text'} />
        </div>
      )
    case 'text':
      return (
        <div className="flex h-full flex-col">
          {header}
          <TextView file={file} />
        </div>
      )
    default:
      return (
        <div className="flex h-full flex-col">
          {header}
          <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-sm text-slate-400">
            <p>该文件类型暂不支持在线预览</p>
            <button
              onClick={download}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-700"
            >
              ⬇ 下载文件
            </button>
          </div>
        </div>
      )
  }
}

// ============================================================
// 各类型渲染
// ============================================================

function ImageView({ blob, name }: { blob: Blob; name: string }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    const u = URL.createObjectURL(blob)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [blob])
  return (
    <div className="flex flex-1 items-start justify-center overflow-auto rounded-lg bg-slate-100 p-3">
      {url && <img src={url} alt={name} className="max-h-[60vh] max-w-full object-contain" />}
    </div>
  )
}

function HtmlView({ file }: { file: PreviewFile }) {
  const [srcDoc, setSrcDoc] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob).then((t) => {
      if (alive) setSrcDoc(DOMPurify.sanitize(t))
    })
    return () => {
      alive = false
    }
  }, [file])
  return (
    <div className="flex-1 overflow-auto rounded-lg border border-slate-200">
      {srcDoc === null ? (
        <p className="p-6 text-center text-xs text-slate-400">加载中…</p>
      ) : (
        <iframe sandbox="" srcDoc={srcDoc} title={file.name} className="h-[60vh] w-full" />
      )}
    </div>
  )
}

function MarkdownView({ file }: { file: PreviewFile }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob).then((t) => alive && setText(t))
    return () => {
      alive = false
    }
  }, [file])
  if (text === null) return <p className="p-6 text-center text-xs text-slate-400">加载中…</p>
  return (
    <div className="flex-1 overflow-auto rounded-lg border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-700">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  )
}

function CsvView({ file, sep }: { file: PreviewFile; sep: string }) {
  const [rows, setRows] = useState<string[][] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob)
      .then((t) => {
        const r = Papa.parse<string[]>(t, { delimiter: sep, skipEmptyLines: true })
        if (alive) setRows(r.data)
      })
      .catch((e) => alive && setErr(errText(e)))
    return () => {
      alive = false
    }
  }, [file, sep])
  if (err) return <p className="rounded bg-red-50 p-3 text-xs text-red-600">解析失败: {err}</p>
  if (!rows) return <p className="p-6 text-center text-xs text-slate-400">解析中…</p>
  return <DataTable rows={rows} />
}

function DataTable({ rows }: { rows: string[][] }) {
  const [showAll, setShowAll] = useState(false)
  if (rows.length === 0) return <p className="p-6 text-center text-xs text-slate-400">空文件</p>
  const displayRows = showAll ? rows : rows.slice(0, 200)
  const maxCols = Math.max(...rows.map((r) => r.length))
  return (
    <div className="flex-1 overflow-auto rounded-lg border border-slate-200">
      <table className="w-full border-collapse text-[11px]">
        <thead className="sticky top-0 bg-slate-100">
          <tr>
            {Array.from({ length: maxCols }).map((_, i) => (
              <th key={i} className="border border-slate-200 px-2 py-1 text-left font-semibold text-slate-600">
                {i === 0 ? '#' : `列 ${i}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((r, i) => (
            <tr key={i} className={i % 2 ? 'bg-white' : 'bg-slate-50/50'}>
              {Array.from({ length: maxCols }).map((_, j) => (
                <td key={j} className="border border-slate-200 px-2 py-1 text-slate-600">
                  {r[j] ?? ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > 200 && (
        <div className="sticky bottom-0 border-t border-slate-200 bg-white p-2 text-center text-[11px] text-slate-400">
          {showAll ? '已显示全部' : `仅显示前 200 行 / 共 ${rows.length} 行`}
          <button onClick={() => setShowAll(!showAll)} className="ml-2 text-indigo-600 hover:underline">
            {showAll ? '收起' : '显示全部'}
          </button>
        </div>
      )}
    </div>
  )
}

function XlsxView({ file }: { file: PreviewFile }) {
  const [rows, setRows] = useState<string[][] | null>(null)
  const [sheetName, setSheetName] = useState('')
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void file.blob
      .arrayBuffer()
      .then((buf) => {
        const wb = XLSX.read(buf, { type: 'array' })
        const name = wb.SheetNames[0] ?? ''
        const sheet = wb.Sheets[name]
        if (alive) {
          setSheetName(name)
          if (sheet) {
            const arr = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1 })
            setRows(
              arr.map((r) =>
                (Array.isArray(r) ? r : []).map((c) =>
                  c === null || c === undefined ? '' : String(c),
                ),
              ),
            )
          } else {
            setRows([])
          }
        }
      })
      .catch((e) => alive && setErr(errText(e)))
    return () => {
      alive = false
    }
  }, [file])
  if (err) return <p className="rounded bg-red-50 p-3 text-xs text-red-600">解析失败: {err}</p>
  if (!rows) return <p className="p-6 text-center text-xs text-slate-400">解析中…</p>
  return (
    <div className="flex-1">
      <p className="mb-1 text-[11px] text-slate-400">
        工作表: <b className="text-slate-600">{sheetName}</b>（仅显示首个 sheet）
      </p>
      <DataTable rows={rows} />
    </div>
  )
}

function PdfView({ blob }: { blob: Blob }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    const u = URL.createObjectURL(blob)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [blob])
  return url ? (
    <iframe src={url} title="PDF 预览" className="h-[62vh] w-full rounded-lg border border-slate-200" />
  ) : (
    <p className="p-6 text-center text-xs text-slate-400">加载中…</p>
  )
}

function DocxView({ file }: { file: PreviewFile }) {
  const [html, setHtml] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void file.blob
      .arrayBuffer()
      .then((buf) => mammoth.convertToHtml({ arrayBuffer: buf }))
      .then((r) => {
        if (alive) setHtml(DOMPurify.sanitize(r.value))
      })
      .catch((e) => alive && setErr(errText(e)))
    return () => {
      alive = false
    }
  }, [file])
  if (err) return <p className="rounded bg-red-50 p-3 text-xs text-red-600">解析失败: {err}</p>
  if (html === null) return <p className="p-6 text-center text-xs text-slate-400">解析中…</p>
  return (
    <div
      className="flex-1 overflow-auto rounded-lg border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-700"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

function CodeView({ file, lang }: { file: PreviewFile; lang: string }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob).then((t) => alive && setText(t))
    return () => {
      alive = false
    }
  }, [file])
  const html = useMemo(() => {
    if (text === null) return ''
    const grammar = Prism.languages[lang]
    if (grammar) {
      try {
        return Prism.highlight(text, grammar, lang)
      } catch {
        return escapeHtml(text)
      }
    }
    return escapeHtml(text)
  }, [text, lang])
  if (text === null) return <p className="p-6 text-center text-xs text-slate-400">加载中…</p>
  return (
    <pre className="flex-1 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed">
      <code className={`language-${lang}`} dangerouslySetInnerHTML={{ __html: html }} />
    </pre>
  )
}

function TextView({ file }: { file: PreviewFile }) {
  const [text, setText] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob).then((t) => alive && setText(t))
    return () => {
      alive = false
    }
  }, [file])
  if (text === null) return <p className="p-6 text-center text-xs text-slate-400">加载中…</p>
  return (
    <pre className="flex-1 overflow-auto rounded-lg bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
      {text}
    </pre>
  )
}

// ============================================================
// agent_judge.jsonl 转录视图
// ============================================================

const TYPE_STYLES: Record<string, string> = {
  user: 'bg-blue-100 text-blue-700',
  assistant: 'bg-emerald-100 text-emerald-700',
  system: 'bg-slate-200 text-slate-600',
  toolresult: 'bg-orange-100 text-orange-700',
  result: 'bg-purple-100 text-purple-700',
}

function TranscriptView({ file }: { file: PreviewFile }) {
  const [entries, setEntries] = useState<Array<{ i: number; parsed: Record<string, unknown> | null; raw: string }>>([])
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let alive = true
    void readText(file.blob)
      .then((t) => {
        const list = t
          .split('\n')
          .filter((l) => l.trim())
          .map((line, i) => {
            try {
              return { i, parsed: JSON.parse(line) as Record<string, unknown>, raw: line }
            } catch {
              return { i, parsed: null, raw: line }
            }
          })
        if (alive) setEntries(list)
      })
      .catch((e) => alive && setErr(errText(e)))
    return () => {
      alive = false
    }
  }, [file])

  if (err) return <p className="rounded bg-red-50 p-3 text-xs text-red-600">解析失败: {err}</p>

  return (
    <div className="flex-1 space-y-2 overflow-auto">
      {entries.length === 0 && <p className="p-6 text-center text-xs text-slate-400">空转录</p>}
      {entries.map(({ i, parsed, raw }) =>
        parsed ? (
          <TranscriptEntry key={i} entry={parsed} />
        ) : (
          <pre key={i} className="whitespace-pre-wrap rounded-lg bg-slate-100 p-2 text-xs text-slate-500">
            {raw}
          </pre>
        ),
      )}
    </div>
  )
}

function TranscriptEntry({ entry }: { entry: Record<string, unknown> }) {
  const type = typeof entry.type === 'string' ? entry.type : 'unknown'
  const ts = typeof entry.timestamp === 'string' ? entry.timestamp : ''
  const msg = (entry.message ?? entry) as Record<string, unknown>
  const content: unknown = Array.isArray(msg.content) ? msg.content : msg.content ?? entry.content
  const model = typeof msg.model === 'string' ? msg.model : undefined
  const [open, setOpen] = useState(true)

  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-1.5">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${TYPE_STYLES[type] ?? 'bg-slate-100 text-slate-500'}`}>
          {type}
        </span>
        {model && <span className="text-[10px] text-slate-400">{model}</span>}
        {ts && <span className="font-mono text-[10px] text-slate-400">{ts}</span>}
        <span className="flex-1" />
        <button onClick={() => setOpen(!open)} className="text-[10px] text-slate-400">
          {open ? '收起' : '展开'}
        </button>
      </div>
      {open && (
        <div className="p-3 text-xs leading-relaxed text-slate-700">
          <MessageContent content={content} entry={entry} />
        </div>
      )}
    </div>
  )
}

function MessageContent({ content, entry }: { content: unknown; entry: Record<string, unknown> }) {
  // result 末条：展示统计
  if (entry.type === 'result') {
    const extra: string[] = []
    for (const k of ['duration_ms', 'total_cost_usd', 'num_turns', 'is_error'] as const) {
      if (entry[k] !== undefined) extra.push(`${k}: ${String(entry[k])}`)
    }
    return (
      <div>
        {extra.length > 0 && (
          <p className="mb-1 font-mono text-[10px] text-purple-500">{extra.join(' · ')}</p>
        )}
        <MessageContentInner value={content} />
      </div>
    )
  }
  return <MessageContentInner value={content} />
}

function MessageContentInner({ value }: { value: unknown }) {
  if (typeof value === 'string') {
    return <p className="whitespace-pre-wrap">{value}</p>
  }
  if (Array.isArray(value)) {
    return (
      <div className="space-y-1.5">
        {value.map((b, i) => {
          const block = b as Record<string, unknown>
          const bt = block.type
          if (bt === 'text' && typeof block.text === 'string') {
            return (
              <p key={i} className="whitespace-pre-wrap">
                {block.text}
              </p>
            )
          }
          if (bt === 'thinking' && typeof block.thinking === 'string') {
            return (
              <p key={i} className="whitespace-pre-wrap italic text-slate-400">
                💭 {block.thinking}
              </p>
            )
          }
          if (bt === 'tool_use') {
            return (
              <div key={i} className="rounded-md border border-blue-200 bg-blue-50/50 p-2">
                <p className="mb-1 font-mono text-[11px] font-bold text-blue-700">
                  🛠 {String(block.name ?? 'tool')}
                </p>
                <pre className="trace-json overflow-x-auto text-slate-600">
                  {JSON.stringify(block.input ?? {}, null, 2)}
                </pre>
              </div>
            )
          }
          if (bt === 'tool_result') {
            return (
              <div key={i} className="rounded-md border border-orange-200 bg-orange-50/40 p-2">
                <p className="mb-1 text-[10px] font-bold text-orange-600">工具结果</p>
                <div className="text-slate-600">
                  <MessageContentInner value={block.content} />
                </div>
              </div>
            )
          }
          return (
            <pre key={i} className="trace-json overflow-x-auto text-slate-500">
              {JSON.stringify(block, null, 2)}
            </pre>
          )
        })}
      </div>
    )
  }
  if (value !== null && value !== undefined) {
    return <pre className="trace-json overflow-x-auto">{JSON.stringify(value, null, 2)}</pre>
  }
  return <p className="text-slate-400">（无内容）</p>
}
