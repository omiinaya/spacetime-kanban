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
  depends_on: string | null
  required_skills: string | null
  score: number
  position: number | null
  due_by: number | null
}

export interface LogEntry {
  id: string
  task_id: string
  action: string
  agent_id: string | null
  notes: string | null
  timestamp: number
}

export interface LogStats {
  total_events: number
  today_events: number
  active_agents_today: number
  action_breakdown: Record<string, number>
  top_agents: Record<string, number>
}

export interface Agent {
  id: string
  host: string
  capabilities: string | null
  repo_focus: string | null
  current_task_id: string | null
  status: string
  last_heartbeat: number
  first_seen: number
}

export interface SuggestResult {
  task: Task
  score: number
  reason: string
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

export interface IssueLink {
  kanban_task_id: string
  issue_number: number
  repo: string
  issue_url: string
  html_url: string
  status: string
  linked_at: number
}

export interface AgentHealth {
  id: string
  host: string
  status: string
  capabilities: string | null
  repo_focus: string | null
  current_task: {
    id: string
    title: string
    status: string
    priority: number
    repo: string
  } | null
  last_heartbeat: number
  heartbeat_age_seconds: number
  stale: boolean
  first_seen: number
}

export interface Webhook {
  id: string
  url: string
  type: string
  events: string[]
  label: string
  created_at: number
}

export interface WebhookDelivery {
  id: string
  webhook_id: string
  event: string
  url: string
  status_code: number
  response_body: string
  success: boolean
  delivered_at: number
}

export interface KanbanLabel {
  id: string
  name: string
  color: string
  description: string
  created_at: number
}

export interface TaskComment {
  id: string
  task_id: string
  author: string
  body: string
  created_at: number
}

export interface ChecklistItem {
  id: string
  task_id: string
  text: string
  completed: boolean
  position: number
  created_at: number
}

export interface TaskLabelAssign {
  label_ids: string[]
}

export interface Project {
  id: string
  name: string
  description: string
  color: string
  priority: number
  active: boolean
  created_at: number
  updated_at: number
}

export interface ApiKeyItem {
  id: string
  name: string
  permissions: string
  scope: string
  key_prefix: string
  created_at: number
  last_used_at: number
  revoked: boolean
}

export interface ApiKeyItemFull extends ApiKeyItem {
  full_key: string
}

export interface TaskRelation {
  id: string
  task_id: string
  related_task_id: string
  relation_type: string
  created_at: number
}

export const api = {
  tasks: {
    list: (params?: { status?: string; repo?: string; label?: string }) => {
      const qs = new URLSearchParams()
      if (params?.status) qs.set('status', params.status)
      if (params?.repo) qs.set('repo', params.repo)
      if (params?.label) qs.set('label', params.label)
      const q = qs.toString()
      return apiGet<Task[]>(`/tasks${q ? `?${q}` : ''}`)
    },
    get: (id: string) => apiGet<Task>(`/tasks/${id}`),
    create: (body: { title: string; description?: string; priority?: number; repo?: string; roadmap_item?: string; required_skills?: string; status?: string; due_by?: number | null }) =>
      apiPost<Task>('/tasks', body),
    update: (id: string, body: { title?: string; description?: string; priority?: number; branch?: string; due_by?: number | null }) =>
      apiPatch<Task>(`/tasks/${id}`, body),
    claim: (id: string, agent_id: string) =>
      apiPost<{ status: string; task_id: string; assigned_to: string }>(`/tasks/${id}/claim`, { agent_id }),
    unclaim: (id: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/unclaim`),
    complete: (id: string, result_notes?: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/complete`, { result_notes }),
    block: (id: string, reason?: string) =>
      apiPost<{ status: string; task_id: string }>(`/tasks/${id}/block`, { reason }),
    setDependency: (id: string, depends_on: string) =>
      apiPost<{ status: string; task_id: string; depends_on: string | null }>(`/tasks/${id}/dependency`, { depends_on }),
    setSkills: (id: string, skills: string) =>
      apiPost<{ status: string; task_id: string; skills: string | null }>(`/tasks/${id}/skills`, { skills }),
    delete: (id: string) =>
      apiDelete<{ status: string }>(`/tasks/${id}`),
    seed: () => apiPost<{ status: string }>('/tasks/seed'),
    reorder: (task_id: string, position: number) =>
      apiPost<{ status: string; task_id: string; position: number }>('/tasks/reorder', { task_id, position }),
    bulkReorder: (items: { task_id: string; position: number }[]) =>
      apiPost<{ status: string; count: number }>('/tasks/bulk-reorder', { items }),
    export: (format?: string, status?: string, repo?: string) => {
      const qs = new URLSearchParams()
      if (format) qs.set('format', format)
      if (status) qs.set('status', status)
      if (repo) qs.set('repo', repo)
      return `${BASE}/tasks/export?${qs.toString()}`
    },
    batch: {
      labels: (task_ids: string[], label_ids: string[]) =>
        apiPost<{ status: string }>('/tasks/batch/labels', { task_ids, label_ids }),
      unlabels: (task_ids: string[], label_ids: string[]) =>
        apiPost<{ status: string }>('/tasks/batch/unlabels', { task_ids, label_ids }),
    },
  },
  logs: {
    list: (params?: {
      task_id?: string; action?: string; agent_id?: string;
      search?: string; since?: number; until?: number;
      offset?: number; limit?: number;
    }) => {
      const qs = new URLSearchParams()
      if (params?.task_id) qs.set('task_id', params.task_id)
      if (params?.action) qs.set('action', params.action)
      if (params?.agent_id) qs.set('agent_id', params.agent_id)
      if (params?.search) qs.set('search', params.search)
      if (params?.since) qs.set('since', String(params.since))
      if (params?.until) qs.set('until', String(params.until))
      if (params?.offset) qs.set('offset', String(params.offset))
      if (params?.limit) qs.set('limit', String(params.limit))
      const q = qs.toString()
      return apiGet<LogEntry[]>(`/logs${q ? `?${q}` : ''}`)
    },
    stats: () => apiGet<LogStats>('/logs/stats'),
  },
  agents: {
    list: () => apiGet<Agent[]>('/agents'),
    get: (id: string) => apiGet<Agent>(`/agents/${id}`),
    register: (body: { agent_id: string; host?: string; capabilities?: string; repo_focus?: string }) =>
      apiPost<{ status: string }>('/agents/register', body),
    heartbeat: (agent_id: string, body: { status?: string; current_task_id?: string }) =>
      apiPost<{ status: string }>(`/agents/${agent_id}/heartbeat`, body),
    setCapabilities: (agent_id: string, body: { capabilities?: string; repo_focus?: string }) =>
      apiPost<{ status: string }>(`/agents/${agent_id}/capabilities`, body),
    health: () => apiGet<AgentHealth[]>('/agents/health'),
  },
  suggest: {
    list: (params?: { agent_id?: string; limit?: number }) => {
      const qs = new URLSearchParams()
      if (params?.agent_id) qs.set('agent_id', params.agent_id)
      if (params?.limit) qs.set('limit', String(params.limit))
      const q = qs.toString()
      return apiGet<SuggestResult[]>(`/tasks/suggest${q ? `?${q}` : ''}`)
    },
  },
  analytics: {
    overview: () => apiGet<{
      total: number
      by_status: Record<string, number>
      completed_today: number
      completed_week: number
      total_done: number
      repos: Record<string, { total: number; done: number; in_progress: number; blocked: number; available: number }>
      agent_count: number
    }>('/analytics/overview'),
    throughput: (days?: number) => apiGet<{ date: string; completed: number }[]>(`/analytics/throughput${days ? `?days=${days}` : ''}`),
    cycleTimes: () => apiGet<{ repo: string; count: number; avg_hours: number; min_hours: number; max_hours: number }[]>('/analytics/cycle-times'),
    agents: () => apiGet<{ id: string; status: string; completed: number; blocked: number; capabilities: string | null; repo_focus: string | null; last_heartbeat: number }[]>('/analytics/agents'),
    burndown: (days?: number) => apiGet<{
      days: { date: string; open: number; completed: number; ideal: number }[]
      total_open_start: number
      total_completed: number
      total_remaining: number
      days_total: number
    }>(`/analytics/burndown${days ? `?days=${days}` : ''}`),
  },
  issues: {
    list: (repo?: string) => {
      const qs = repo ? `?repo=${encodeURIComponent(repo)}` : ''
      return apiGet<IssueLink[]>(`/issues${qs}`)
    },
    get: (taskId: string) => apiGet<IssueLink>(`/issues/${taskId}`),
    link: (taskId: string, repo: string, issueNumber: number) =>
      apiPost<IssueLink>('/issues/link', { task_id: taskId, repo, issue_number: issueNumber }),
    unlink: (taskId: string) =>
      apiPost<{ status: string }>(`/issues/unlink?task_id=${taskId}`),
    create: (taskId: string, repo?: string, labels?: string, assignee?: string) =>
      apiPost<{ status: string; task_id: string; issue_number: number; html_url: string }>('/issues/create', {
        task_id: taskId, repo: repo || '', labels: labels || '', assignee: assignee || '',
      }),
  },
  webhooks: {
    list: () => apiGet<Webhook[]>('/webhooks'),
    get: (id: string) => apiGet<Webhook>(`/webhooks/${id}`),
    create: (body: { url: string; type?: string; events?: string[]; label?: string }) =>
      apiPost<Webhook>('/webhooks', body),
    update: (id: string, body: { url?: string; type?: string; events?: string[]; label?: string }) =>
      apiPatch<Webhook>(`/webhooks/${id}`, body),
    delete: (id: string) =>
      apiDelete<{ status: string }>(`/webhooks/${id}`),
    test: (id: string) =>
      apiPost<{ status: string; webhook_id: string; response_code: number }>(`/webhooks/${id}/test`),
    deliveries: (id: string, limit?: number) => {
      const qs = limit ? `?limit=${limit}` : ''
      return apiGet<WebhookDelivery[]>(`/webhooks/${id}/deliveries${qs}`)
    },
  },
  labels: {
    list: () => apiGet<KanbanLabel[]>('/labels'),
    create: (body: { name: string; color?: string; description?: string }) =>
      apiPost<KanbanLabel>('/labels', body),
    update: (id: string, body: { name?: string; color?: string; description?: string }) =>
      apiPatch<KanbanLabel>(`/labels/${id}`, body),
    delete: (id: string) =>
      apiDelete<{ status: string }>(`/labels/${id}`),
    getForTask: (taskId: string) =>
      apiGet<KanbanLabel[]>(`/tasks/${taskId}/labels`),
    setForTask: (taskId: string, body: TaskLabelAssign) =>
      apiPost<{ status: string; assigned: string[] }>(`/tasks/${taskId}/labels`, body),
  },
  projects: {
    list: () => apiGet<Project[]>('/projects'),
    get: (id: string) => apiGet<Project>(`/projects/${id}`),
    create: (body: { id: string; name?: string; description?: string; color?: string; priority?: number; active?: boolean }) =>
      apiPost<Project>('/projects', body),
    update: (id: string, body: { name?: string; description?: string; color?: string; priority?: number; active?: boolean }) =>
      apiPatch<Project>(`/projects/${id}`, body),
    delete: (id: string) =>
      apiDelete<{ status: string }>(`/projects/${id}`),
  },
  crossProject: {
    get: () => apiGet<Record<string, {
      project: any;
      total: number;
      by_status: Record<string, number>;
      by_priority: Record<string, number>;
      sprints: string[];
    }>>('/analytics/cross-project'),
  },
  calendar: {
    get: (year?: number, month?: number) => {
      const qs = new URLSearchParams()
      if (year) qs.set('year', String(year))
      if (month) qs.set('month', String(month))
      const q = qs.toString()
      return apiGet<{ year: number; month: number; tasks: Task[] }>(`/analytics/calendar${q ? `?${q}` : ''}`)
    },
  },
  apiKeys: {
    list: () => apiGet<ApiKeyItem[]>('/api-keys'),
    create: (body: { name: string; permissions?: string; scope?: string }) =>
      apiPost<ApiKeyItemFull>('/api-keys', body),
    revoke: (keyId: string) =>
      apiPost<{ status: string }>(`/api-keys/${keyId}/revoke`),
    delete: (keyId: string) =>
      apiDelete<{ status: string }>(`/api-keys/${keyId}`),
  },
  taskRelations: {
    list: (taskId: string) =>
      apiGet<TaskRelation[]>(`/tasks/${taskId}/relations`),
    add: (taskId: string, body: { related_task_id: string; relation_type: string }) =>
      apiPost<TaskRelation>(`/tasks/${taskId}/relations`, body),
    remove: (taskId: string, relationId: string) =>
      apiDelete<{ status: string }>(`/tasks/${taskId}/relations/${relationId}`),
  },
  comments: {
    list: (taskId: string) =>
      apiGet<TaskComment[]>(`/tasks/${taskId}/comments`),
    add: (taskId: string, body: string, author?: string) =>
      apiPost<{ status: string; id: string }>(`/tasks/${taskId}/comments`, { body, author: author || 'web-user' }),
    remove: (taskId: string, commentId: string) =>
      apiDelete<{ status: string }>(`/tasks/${taskId}/comments/${commentId}`),
  },
  checklist: {
    list: (taskId: string) =>
      apiGet<ChecklistItem[]>(`/tasks/${taskId}/checklist`),
    add: (taskId: string, text: string) =>
      apiPost<{ status: string; id: string }>(`/tasks/${taskId}/checklist`, { text }),
    toggle: (taskId: string, itemId: string) =>
      apiPost<{ status: string }>(`/tasks/${taskId}/checklist/${itemId}/toggle`),
    remove: (taskId: string, itemId: string) =>
      apiDelete<{ status: string }>(`/tasks/${taskId}/checklist/${itemId}`),
    reorder: (taskId: string, itemId: string, newPosition: number) =>
      apiPost<{ status: string }>(`/tasks/${taskId}/checklist/${itemId}/reorder`, { new_position: newPosition }),
  },
}
