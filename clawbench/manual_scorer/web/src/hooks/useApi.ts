// fetch 封装 + 数据 hooks（本服务仅本机使用，不内置鉴权）
import { useCallback, useEffect, useState } from 'react'
import type { ModelSummary, TaskDetail, TaskSummary } from '../types'
import { enc } from '../lib/utils'

const BASE = '/api'

async function errorMessage(resp: Response): Promise<string> {
  let text = ''
  try {
    text = await resp.text()
  } catch {
    /* 忽略 */
  }
  let detail: unknown = text
  try {
    const j = JSON.parse(text)
    detail = (j && (j.detail ?? j.message)) ?? text
  } catch {
    /* 非 JSON */
  }
  if (typeof detail === 'string') return `${resp.status}: ${detail}`
  try {
    return `${resp.status}: ${JSON.stringify(detail)}`
  } catch {
    return `${resp.status}`
  }
}

/** JSON 请求封装 */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  }
  const isForm = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (options.body !== undefined && !isForm) {
    headers['Content-Type'] = 'application/json'
  }

  let resp: Response
  try {
    resp = await fetch(`${BASE}${path}`, { ...options, headers })
  } catch (e) {
    throw new Error(`网络请求失败: ${e instanceof Error ? e.message : String(e)}`)
  }

  if (!resp.ok) {
    throw new Error(await errorMessage(resp))
  }
  if (resp.status === 204) return undefined as T
  try {
    return (await resp.json()) as T
  } catch {
    return undefined as T
  }
}

/** 二进制请求封装（工作区文件 / ZIP 下载） */
export async function apiBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {}

  let resp: Response
  try {
    resp = await fetch(`${BASE}${path}`, { headers })
  } catch (e) {
    throw new Error(`网络请求失败: ${e instanceof Error ? e.message : String(e)}`)
  }
  if (!resp.ok) {
    throw new Error(await errorMessage(resp))
  }
  return resp.blob()
}

// ============================================================
// Hooks
// ============================================================

/** 模型列表（自动加载） */
export function useModels() {
  const [models, setModels] = useState<ModelSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<ModelSummary[]>('/models')
      setModels(data)
    } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { models, loading, error, refresh }
}

/** 任务列表（按 modelId + runId） */
export function useTasks(modelId: string | null, runId: string) {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!modelId) {
      setTasks([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<TaskSummary[]>(`/model/${enc(modelId)}/tasks?run_id=${encodeURIComponent(runId)}`)
      setTasks(data)
    } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [modelId, runId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { tasks, loading, error, refresh }
}

/** 任务详情（按 modelId + taskName + runId） */
export function useTaskDetail(modelId: string | null, taskName: string | null, runId: string) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!modelId || !taskName) {
      setDetail(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await apiFetch<TaskDetail>(
        `/model/${enc(modelId)}/task/${enc(taskName)}?run_id=${encodeURIComponent(runId)}`,
      )
      setDetail(data)
    } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [modelId, taskName, runId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { detail, loading, error, refresh }
}
