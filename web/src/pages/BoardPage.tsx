import { useState, useCallback, useEffect } from 'react'
import {
  Plus, Loader2, AlertCircle, Trash2, Play, CheckCircle2,
  Ban, RotateCcw, ChevronDown, Wifi, WifiOff, Link, Lightbulb,
  Users, Cpu
} from 'lucide-react'
import { api, type SuggestResult, type Agent, type Task as ApiTask } from '../api'
import { useRealtimeTasks, type TaskStatus, type Task } from '../hooks/useRealtimeTasks'

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

const STATUS_COLUMNS: TaskStatus[] = ['available', 'in_progress', 'blocked', 'done']
const STATUS_LABELS: Record<string, string> = {
  available: 'Available',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  done: 'Done',
}

export default function BoardPage() {
  const { tasks, connected, error: stdbError } = useRealtimeTasks()
  const [showCreate, setShowCreate] = useState(false)
  const [claiming, setClaiming] = useState<string | null>(null)
  const [repoFilter, setRepoFilter] = useState<string>('')
  const [mobileStatusTab, setMobileStatusTab] = useState<TaskStatus>('available')
  const [suggestions, setSuggestions] = useState<SuggestResult[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [showPanel, setShowPanel] = useState<'none' | 'suggestions' | 'agents'>('none')

  // Build a lookup map: taskId -> task title
  const taskTitleMap = new Map(tasks.map(t => [t.id, t.title]))

  // Extract unique repos sorted by frequency
  const repos = [...new Set(tasks.map(t => t.repo).filter(Boolean))]
  repos.sort((a, b) => {
    const ca = tasks.filter(t => t.repo === a).length
    const cb = tasks.filter(t => t.repo === b).length
    return cb - ca
  })

  const handleClaim = async (taskId: string, agentId: string) => {
    setClaiming(taskId)
    try {
      await api.tasks.claim(taskId, agentId)
      // STDB subscription will push the update — no manual refresh needed
    } catch (e: any) {
      alert(`Claim failed: ${e.message}`)
    } finally {
      setClaiming(null)
    }
  }

  const handleUnclaim = async (taskId: string) => {
    try {
      await api.tasks.unclaim(taskId)
    } catch (e: any) {
      alert(`Unclaim failed: ${e.message}`)
    }
  }

  const handleComplete = async (taskId: string) => {
    try {
      await api.tasks.complete(taskId, 'Done via web UI')
    } catch (e: any) {
      alert(`Complete failed: ${e.message}`)
    }
  }

  const handleBlock = async (taskId: string) => {
    const reason = prompt('Block reason:')
    if (reason === null) return
    try {
      await api.tasks.block(taskId, reason || 'Blocked via web UI')
    } catch (e: any) {
      alert(`Block failed: ${e.message}`)
    }
  }

  const handleDelete = async (taskId: string) => {
    if (!confirm('Delete this task?')) return
    try {
      await api.tasks.delete(taskId)
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`)
    }
  }

  const handleSetDependency = async (taskId: string) => {
    const depId = prompt('Enter the ID of the task this task depends on (leave empty to clear):')
    if (depId === null) return
    try {
      await api.tasks.setDependency(taskId, depId.trim())
    } catch (e: any) {
      alert(`Set dependency failed: ${e.message}`)
    }
  }

  const handleSetSkills = async (taskId: string) => {
    const skills = prompt('Enter required skills (comma-separated, e.g. rust,typescript,react):')
    if (skills === null) return
    try {
      await api.tasks.setSkills(taskId, skills.trim())
    } catch (e: any) {
      alert(`Set skills failed: ${e.message}`)
    }
  }

  // Load suggestions and agents periodically
  useEffect(() => {
    const load = async () => {
      try {
        const [s, a] = await Promise.all([
          api.suggest.list({ limit: 3 }),
          api.agents.list(),
        ])
        setSuggestions(s)
        setAgents(a)
      } catch {}
    }
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  const renderDependencyBadge = (depId: string | null | undefined) => {
    if (!depId) return null
    const depTitle = taskTitleMap.get(depId)
    return (
      <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400/80 font-medium truncate max-w-[180px]" title={depId}>
        ⬆ {depTitle || depId}
      </span>
    )
  }

  const renderTaskCard = (task: Task) => (
    <div key={task.id} className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS[task.priority] || ''}`}>
          {PRIORITY_LABELS[task.priority] || task.priority}
        </span>
        {task.assignedTo && (
          <span className="text-xs text-[var(--color-muted)] truncate max-w-[100px]">
            {task.assignedTo}
          </span>
        )}
      </div>

      <p className="text-sm font-medium leading-snug">{task.title}</p>

      {task.description && (
        <p className="text-xs text-[var(--color-muted-foreground)] line-clamp-2">{task.description}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {task.repo && (
          <span className="px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)] font-medium">
            {task.repo}
          </span>
        )}
        {task.branch && <span className="text-blue-400 truncate max-w-[120px]">:{task.branch}</span>}
        {task.roadmapItem && <span className="text-purple-400/70 truncate">{task.roadmapItem}</span>}
        {renderDependencyBadge(task.dependsOn)}
        {task.requiredSkills && (
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400/80 font-medium truncate max-w-[140px]" title={`Skills: ${task.requiredSkills}`}>
            <Cpu className="w-3 h-3 inline mr-0.5" />{task.requiredSkills}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1 pt-1 border-t border-[var(--color-border)]">
        {task.status === 'available' && (
          <>
            <button onClick={() => handleClaim(task.id, 'web-user')}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
            ><Play className="w-3 h-3" /> Claim</button>
            <button onClick={() => handleSetDependency(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
            ><Link className="w-3 h-3" /> Dep</button>
            <button onClick={() => handleSetSkills(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
            ><Cpu className="w-3 h-3" /> Skills</button>
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

  // Sort: priority asc, then createdAt desc
  const sorted = [...tasks].sort((a, b) => a.priority - b.priority || Number(b.createdAt - a.createdAt))
  const filtered = repoFilter ? sorted.filter(t => t.repo === repoFilter) : sorted

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
            Board
            {connected ? (
              <span className="flex items-center gap-1 text-xs text-emerald-400 font-normal">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse" />
                LIVE
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs text-amber-400 font-normal">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
                FALLBACK
              </span>
            )}
          </h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Repo filter */}
          {repos.length > 0 && (
            <select
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
              className="text-xs px-2 py-1.5 rounded bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-muted-foreground)] appearance-none cursor-pointer"
            >
              <option value="">All repos</option>
              {repos.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          )}
          {connected
            ? <Wifi className="w-3.5 h-3.5 text-emerald-400 hidden sm:block" />
            : <WifiOff className="w-3.5 h-3.5 text-amber-400 hidden sm:block" />
          }
          <button onClick={() => setShowPanel(showPanel === 'suggestions' ? 'none' : 'suggestions')}
            className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
              showPanel === 'suggestions' ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
            }`}
          ><Lightbulb className="w-3 h-3" /> Suggest</button>
          <button onClick={() => setShowPanel(showPanel === 'agents' ? 'none' : 'agents')}
            className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
              showPanel === 'agents' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
            }`}
          ><Users className="w-3 h-3" /> Agents</button>
          <button onClick={() => api.tasks.seed()}
            className="text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors hidden sm:inline-block"
          >Seed</button>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
          ><Plus className="w-4 h-4" /> New</button>
        </div>
      </div>

      {(stdbError || !filtered.length) && !stdbError && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {stdbError || 'No tasks found. Seed some sample data or create a new task.'}
        </div>
      )}

      {/* Smart Suggestions Panel */}
      {showPanel === 'suggestions' && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Lightbulb className="w-3 h-3 text-amber-400" /> Smart Suggestions
            </h3>
            <span className="text-[10px] text-[var(--color-muted)]">Refreshes every 30s</span>
          </div>
          {suggestions.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No suggestions available. All tasks may be claimed or blocked.</p>
          ) : (
            <div className="space-y-1.5">
              {suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] hover:bg-white/[0.06] transition-colors cursor-pointer" onClick={() => handleClaim(s.task.id, 'web-user')}>
                  <span className="text-lg mt-0.5">{['🥇', '🥈', '🥉'][i] || '📋'}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{s.task.title}</span>
                      <span className="text-xs px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted-foreground)] font-mono">{s.score}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-[var(--color-muted)] mt-0.5">
                      <span className={`px-1 py-0.25 rounded text-[10px] ${PRIORITY_COLORS[s.task.priority] || ''}`}>
                        {PRIORITY_LABELS[s.task.priority] || s.task.priority}
                      </span>
                      <span>{s.reason}</span>
                      {s.task.required_skills && <span className="text-cyan-400">Skills: {s.task.required_skills}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Agent Panel */}
      {showPanel === 'agents' && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Users className="w-3 h-3 text-cyan-400" /> Swarm Agents
            </h3>
            <span className="text-[10px] text-[var(--color-muted)]">{agents.length} agent(s)</span>
          </div>
          {agents.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No agents registered. Run <code className="px-1 py-0.5 rounded bg-white/10">kanban register --capabilities=...</code> to join the swarm.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {agents.map((a) => {
                const isOnline = a.status === 'online' || a.status === 'busy'
                const agentAge = Math.floor((Date.now() - a.last_heartbeat) / 1000)
                const isStale = agentAge > 60
                return (
                  <div key={a.id} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] border border-[var(--color-border)]">
                    <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${isStale ? 'bg-red-500' : isOnline ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium truncate">{a.id}</span>
                        {a.repo_focus && <span className="text-[10px] px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted)]">{a.repo_focus}</span>}
                      </div>
                      {a.capabilities && (
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {a.capabilities.split(',').map((c, j) => (
                            <span key={j} className="text-[10px] px-1 py-0.25 rounded bg-cyan-500/10 text-cyan-400/80">{c.trim()}</span>
                          ))}
                        </div>
                      )}
                      <div className="text-[10px] text-[var(--color-muted)] mt-0.5">
                        {a.host} · {isStale ? 'stale' : a.status} · {Math.floor(agentAge / 60)}m ago
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Mobile status tabs */}
      <div className="flex gap-1 overflow-x-auto sm:hidden">
        {STATUS_COLUMNS.map((status) => {
          const count = filtered.filter(t => t.status === status).length
          return (
            <button
              key={status}
              onClick={() => setMobileStatusTab(status)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                mobileStatusTab === status
                  ? 'bg-white/10 text-[var(--color-foreground)]'
                  : 'bg-[var(--color-card)] text-[var(--color-muted)]'
              }`}
            >
              {STATUS_LABELS[status]}
              <span className="px-1 rounded bg-white/5 text-[var(--color-muted)]">{count}</span>
            </button>
          )
        })}
      </div>

      {/* Create Task Dialog */}
      {showCreate && (
        <CreateTaskDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => setShowCreate(false)}
        />
      )}

      {/* Kanban Columns — single for mobile, 2 for tablet, 4 for desktop */}
      <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STATUS_COLUMNS.map((status) => {
          const colTasks = filtered.filter((t) => t.status === status)
          return (
            <div key={status} className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  {STATUS_LABELS[status]}
                </h2>
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-[var(--color-card)] text-[var(--color-muted)]">
                  {colTasks.length}
                </span>
              </div>
              <div className="space-y-2 min-h-[120px]">
                {colTasks.map(renderTaskCard)}
                {colTasks.length === 0 && (
                  <div className="text-center py-6 text-xs text-[var(--color-muted)] border border-dashed border-[var(--color-border)] rounded-lg">
                    Empty
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Mobile: single column for selected status */}
      <div className="sm:hidden space-y-2">
        {filtered.filter(t => t.status === mobileStatusTab).map(renderTaskCard)}
        {filtered.filter(t => t.status === mobileStatusTab).length === 0 && (
          <div className="text-center py-12 text-sm text-[var(--color-muted)]">
            No {STATUS_LABELS[mobileStatusTab].toLowerCase()} tasks
            {repoFilter ? ` in ${repoFilter}` : ''}
          </div>
        )}
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
