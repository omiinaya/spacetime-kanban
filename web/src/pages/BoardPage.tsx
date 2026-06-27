import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Plus, Loader2, AlertCircle, Trash2, Play, CheckCircle2,
  Ban, RotateCcw, ChevronDown, RefreshCw
} from 'lucide-react'
import { api, Task } from '../api'

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Urgent',
  1: 'High',
  2: 'Medium',
  3: 'Low',
}

const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-red-500/20 text-red-400',
  1: 'bg-orange-500/20 text-orange-400',
  2: 'bg-blue-500/20 text-blue-400',
  3: 'bg-slate-500/20 text-slate-400',
}

const STATUS_COLUMNS = ['available', 'in_progress', 'blocked', 'done'] as const
const STATUS_LABELS: Record<string, string> = {
  available: 'Available',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  done: 'Done',
}

export default function BoardPage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [claiming, setClaiming] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await api.tasks.list()
      setTasks(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 3000)
    return () => clearInterval(interval)
  }, [load])

  const handleClaim = async (taskId: string, agentId: string) => {
    setClaiming(taskId)
    try {
      await api.tasks.claim(taskId, agentId)
      await load()
    } catch (e: any) {
      alert(`Claim failed: ${e.message}`)
    } finally {
      setClaiming(null)
    }
  }

  const handleUnclaim = async (taskId: string) => {
    try {
      await api.tasks.unclaim(taskId)
      await load()
    } catch (e: any) {
      alert(`Unclaim failed: ${e.message}`)
    }
  }

  const handleComplete = async (taskId: string) => {
    try {
      await api.tasks.complete(taskId, 'Done via web UI')
      await load()
    } catch (e: any) {
      alert(`Complete failed: ${e.message}`)
    }
  }

  const handleBlock = async (taskId: string) => {
    const reason = prompt('Block reason:')
    if (reason === null) return
    try {
      await api.tasks.block(taskId, reason || 'Blocked via web UI')
      await load()
    } catch (e: any) {
      alert(`Block failed: ${e.message}`)
    }
  }

  const handleDelete = async (taskId: string) => {
    if (!confirm('Delete this task?')) return
    try {
      await api.tasks.delete(taskId)
      await load()
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`)
    }
  }

  const renderTaskCard = (task: Task) => (
    <div key={task.id} className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS[task.priority] || ''}`}>
          {PRIORITY_LABELS[task.priority] || task.priority}
        </span>
        {task.assigned_to && (
          <span className="text-xs text-[var(--color-muted)] truncate max-w-[100px]">
            {task.assigned_to}
          </span>
        )}
      </div>

      <p className="text-sm font-medium leading-snug">{task.title}</p>

      {task.description && (
        <p className="text-xs text-[var(--color-muted-foreground)] line-clamp-2">{task.description}</p>
      )}

      <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
        {task.repo && <span className="truncate">{task.repo}</span>}
        {task.branch && <span className="truncate text-blue-400">:{task.branch}</span>}
        {task.roadmap_item && <span className="truncate text-purple-400">{task.roadmap_item}</span>}
      </div>

      {/* Action buttons */}
      <div className="flex items-center gap-1 pt-1 border-t border-[var(--color-border)]">
        {task.status === 'available' && (
          <>
            <button onClick={() => handleClaim(task.id, 'web-user')}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
            ><Play className="w-3 h-3" /> Claim</button>
            <button onClick={() => handleDelete(task.id)}
              className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
            ><Trash2 className="w-3 h-3" /></button>
          </>
        )}
        {task.status === 'in_progress' && (
          <>
            <button onClick={() => handleComplete(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
            ><CheckCircle2 className="w-3 h-3" /> Done</button>
            <button onClick={() => handleBlock(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
            ><Ban className="w-3 h-3" /> Block</button>
            <button onClick={() => handleUnclaim(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors ml-auto"
            ><RotateCcw className="w-3 h-3" /></button>
          </>
        )}
        {task.status === 'blocked' && (
          <button onClick={() => handleUnclaim(task.id)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
          ><RotateCcw className="w-3 h-3" /> Release</button>
        )}
        {task.status === 'done' && (
          <button onClick={() => handleDelete(task.id)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
          ><Trash2 className="w-3 h-3" /> Delete</button>
        )}
      </div>
    </div>
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-muted)]" />
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            Kanban Board
            <span className="flex items-center gap-1 text-xs text-emerald-400 font-normal">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse" />
              LIVE
            </span>
          </h1>
          <p className="text-sm text-[var(--color-muted-foreground)]">
            Multi-agent task coordination — auto-refreshes every 3s
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => api.tasks.seed().then(load)}
            className="text-xs px-3 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors"
          >Seed Samples</button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
          ><Plus className="w-4 h-4" /> New Task</button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Create Task Dialog */}
      {showCreate && (
        <CreateTaskDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load() }}
        />
      )}

      {/* Kanban Columns */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {STATUS_COLUMNS.map((status) => {
          const colTasks = tasks.filter((t) => t.status === status)
          return (
            <div key={status} className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  {STATUS_LABELS[status]}
                </h2>
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-[var(--color-card)] text-[var(--color-muted)]">
                  {colTasks.length}
                </span>
              </div>
              <div className="space-y-2 min-h-[200px]">
                {colTasks.map(renderTaskCard)}
                {colTasks.length === 0 && (
                  <div className="text-center py-8 text-xs text-[var(--color-muted)] border border-dashed border-[var(--color-border)] rounded-lg">
                    No tasks
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CreateTaskDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState(2)
  const [repo, setRepo] = useState('')
  const [roadmap, setRoadmap] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.tasks.create({
        title: title.trim(),
        description,
        priority,
        repo,
        roadmap_item: roadmap,
      })
      onCreated()
    } catch (e: any) {
      alert(`Create failed: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">New Task</h3>
          <button onClick={onClose} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title"
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            autoFocus
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] resize-none"
          />
          <div className="grid grid-cols-3 gap-2">
            <select
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm"
            >
              <option value={0}>Urgent</option>
              <option value={1}>High</option>
              <option value={2}>Medium</option>
              <option value={3}>Low</option>
            </select>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="Repo slug"
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <input
              value={roadmap}
              onChange={(e) => setRoadmap(e.target.value)}
              placeholder="Roadmap item"
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="text-sm px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/5 transition-colors"
            >Cancel</button>
            <button type="submit" disabled={saving || !title.trim()}
              className="flex items-center gap-1 text-sm px-4 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors disabled:opacity-50"
            >{saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Create</button>
          </div>
        </form>
      </div>
    </div>
  )
}
