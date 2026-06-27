export interface Task {
  id: string
  title: string
  description: string
  priority: number
  status: 'available' | 'in_progress' | 'done' | 'blocked'
  assigned_to: string | null
  repo: string
  branch: string | null
  roadmap_item: string
  created_by: string
  created_at: number
  updated_at: number
}

export interface LogEntry {
  id: string
  task_id: string
  action: string
  agent_id: string | null
  notes: string | null
  timestamp: number
}

const BASE = '/api'

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text.slice(0, 100)}`)
  }
  return res.json()
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text.slice(0, 100)}`)
  }
  return res.json()
}

async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text.slice(0, 100)}`)
  }
  return res.json()
}

async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${text.slice(0, 100)}`)
  }
  return res.json()
}

export const api = {
  tasks: {
    list: (params?: { status?: string; repo?: string }) => {
      const qs = new URLSearchParams()
      if (params?.status) qs.set('status', params.status)
      if (params?.repo) qs.set('repo', params.repo)
      const q = qs.toString()
      return apiGet<Task[]>(`/tasks${q ? `?${q}` : ''}`)
    },
    get: (id: string) => apiGet<Task>(`/tasks/${id}`),
    create: (body: { title: string; description?: string; priority?: number; repo?: string; roadmap_item?: string }) =>
      apiPost<Task>('/tasks', body),
    update: (id: string, body: { title?: string; description?: string; priority?: number; branch?: string }) =>
      apiPatch<Task>(`/tasks/${id}`, body),
    claim: (id: string, agent_id: string) =>
      apiPost<{ status: string; task_id: string; assigned_to: string }>(`/tasks/${id}/claim`, { agent_id }),
    unclaim: (id: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/unclaim`),
    complete: (id: string, result_notes?: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/complete`, { result_notes }),
    block: (id: string, reason?: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/block`, { reason }),
    delete: (id: string) =>
      apiDelete<{ status: string }>(`/tasks/${id}`),
    seed: () => apiPost<{ status: string }>('/tasks/seed'),
  },
  logs: {
    list: (task_id?: string, limit?: number) => {
      const qs = new URLSearchParams()
      if (task_id) qs.set('task_id', task_id)
      if (limit) qs.set('limit', String(limit))
      const q = qs.toString()
      return apiGet<LogEntry[]>(`/logs${q ? `?${q}` : ''}`)
    },
  },
  agents: {
    list: () => apiGet<{ agents: string[] }>('/agents'),
  },
}
