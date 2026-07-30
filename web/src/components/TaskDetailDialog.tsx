import { useState, useEffect } from 'react'
import { Plus, Loader2, Trash2, Play, CheckCircle2,
  Ban, RotateCcw, Link,
  Cpu, History, GitBranch, ExternalLink, X, Github,
  Tag, Archive,
  User, Undo2, Wrench, Bot, RefreshCw, ClipboardList, Calendar, Pencil, PlusCircle, Check,
} from 'lucide-react'
import { api, type KanbanLabel, type LogEntry } from '../api'
import { type Task } from '../hooks/useRealtimeTasks'
import { Link as RouterLink } from 'react-router-dom'
import { PRIORITY_LABELS, PRIORITY_COLORS, STATUS_LABELS } from './constants'
import { TaskComments } from './board/TaskComments'
import { TaskChecklist } from './board/TaskChecklist'
import { useToast } from '../hooks/useToast'
import { useConfirm } from './ConfirmDialog'

/** Convert epoch ms to YYYY-MM-DD for a date input. */
function epochMsToDateInput(ms: number | null | undefined): string {
  if (!ms) return ''
  const d = new Date(ms)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** Convert YYYY-MM-DD from a date input to epoch ms (start of that day in local timezone). */
function dateInputToEpochMs(val: string): number | null {
  if (!val) return null
  const d = new Date(val + 'T00:00:00')
  return d.getTime()
}

function DueDateEditor({ taskId, dueBy, taskStatus }: { taskId: string; dueBy?: number | null; taskStatus: string }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(epochMsToDateInput(dueBy))
  const [saving, setSaving] = useState(false)
  const { addToast } = useToast()

  const handleSave = async () => {
    setSaving(true)
    try {
      const ms = dateInputToEpochMs(value)
      await api.tasks.update(taskId, { due_by: ms ?? null })
      setEditing(false)
    } catch (e: unknown) {
      addToast('❌', `Failed to update due date: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    setSaving(true)
    try {
      await api.tasks.update(taskId, { due_by: null })
      setValue('')
      setEditing(false)
    } catch (e: unknown) {
      addToast('❌', `Failed to clear due date: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input type="date" value={value} onChange={e => setValue(e.target.value)}
          className="w-full px-1.5 py-1 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)]"
          autoFocus
        />
        <button onClick={handleSave} disabled={saving}
          className="text-[10px] px-1.5 py-1 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
        >{saving ? '...' : <Check className="w-3 h-3" />}</button>
        <button onClick={() => { setEditing(false); setValue(epochMsToDateInput(dueBy)) }}
          aria-label="Cancel"
          className="text-[10px] px-1.5 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
        ><X className="w-3 h-3" /></button>
      </div>
    )
  }

  if (!dueBy) {
    return (
      <button onClick={() => setEditing(true)}
        className="text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
      >+ Set due date</button>
    )
  }

  const now = Date.now()
  const overdue = now > dueBy && taskStatus !== 'done'

  return (
    <div className="flex items-center gap-1">
      <span className={`text-xs ${overdue ? 'text-red-400 font-medium' : 'text-[var(--color-muted-foreground)]'}`}
        title={new Date(dueBy).toLocaleString()}>
        <Calendar className="w-3 h-3 inline mr-0.5 text-[var(--color-muted)]" /> {new Date(dueBy).toLocaleDateString()}
      </span>
      <button onClick={() => { setEditing(true); setValue(epochMsToDateInput(dueBy)) }}
        aria-label="Edit due date"
        className="text-[10px] text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
      ><Pencil className="w-3 h-3" /></button>
      <button onClick={handleClear} disabled={saving}
        aria-label="Clear due date"
        className="text-[10px] text-red-400/60 hover:text-red-400 transition-colors"
      ><X className="w-3 h-3" /></button>
    </div>
  )
}

export function TaskDetailDialog({
  taskId, tasks, onClose,
  onClaim, onUnclaim, onComplete, onBlock, onDelete, onArchive,
  onSetDependency, onSetSkills,
  allLabels = [], taskLabelMap = new Map(),
}: {
  taskId: string
  tasks: Task[]
  onClose: () => void
  onClaim: (id: string) => void
  onUnclaim: (id: string) => void
  onComplete: (id: string) => void
  onBlock: (id: string) => void
  onDelete: (id: string) => void
  onArchive?: (id: string) => void
  onSetDependency: (id: string) => void
  onSetSkills: (id: string) => void
  allLabels?: KanbanLabel[]
  taskLabelMap?: Map<string, KanbanLabel[]>
}) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [issueLink, setIssueLink] = useState<{ html_url: string; issue_number: number; repo: string; status?: string } | null>(null)
  const [loadingIssue, setLoadingIssue] = useState(true)
  const [currentLabelIds, setCurrentLabelIds] = useState<Set<string>>(new Set())
  const [labelSaving, setLabelSaving] = useState(false)
  const [showIssueForm, setShowIssueForm] = useState(false)
  const [issueRepo, setIssueRepo] = useState('')
  const [issueLabels, setIssueLabels] = useState('')
  const { addToast } = useToast()
  const { confirm } = useConfirm()

  const task = tasks.find(t => t.id === taskId)
  const downstream = tasks.filter(t => t.dependsOn === taskId)
  const upstream = task?.dependsOn ? tasks.find(t => t.id === task.dependsOn) : null

  useEffect(() => {
    let cancelled = false
    setLoadingLogs(true)
    api.logs.list({ task_id: taskId, limit: 20 }).then(l => {
      if (!cancelled) { setLogs(l); setLoadingLogs(false) }
    }).catch(() => { if (!cancelled) setLoadingLogs(false) })
    return () => { cancelled = true }
  }, [taskId])

  useEffect(() => {
    let cancelled = false
    setLoadingIssue(true)
    api.issues.get(taskId).then(link => {
      if (!cancelled) { setIssueLink(link); setLoadingIssue(false) }
    }).catch(() => { if (!cancelled) setLoadingIssue(false) })
    return () => { cancelled = true }
  }, [taskId])

  // Initialize label IDs from taskLabelMap
  useEffect(() => {
    const labels = taskLabelMap.get(taskId) || []
    setCurrentLabelIds(new Set(labels.map(l => l.id)))
  }, [taskId, taskLabelMap])

  const toggleLabel = async (labelId: string) => {
    setLabelSaving(true)
    const next = new Set(currentLabelIds)
    if (next.has(labelId)) {
      next.delete(labelId)
    } else {
      next.add(labelId)
    }
    try {
      await api.labels.setForTask(taskId, { label_ids: [...next] })
      setCurrentLabelIds(next)
    } catch (e: unknown) {
      addToast('❌', `Failed to update labels: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setLabelSaving(false)
    }
  }

  const actionIcons: Record<string, React.ReactNode> = {
    created: <PlusCircle className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    claimed: <User className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    unclaimed: <Undo2 className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    completed: <CheckCircle2 className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    blocked: <Ban className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    dependency_set: <Link className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    skills_set: <Wrench className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    agent_registered: <Bot className="w-3.5 h-3.5 inline" aria-hidden="true" />,
    agent_reconnected: <RefreshCw className="w-3.5 h-3.5 inline" aria-hidden="true" />,
  }

  if (!task) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose} role="dialog" aria-modal="true">
      <div className="bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6" onClick={e => e.stopPropagation()}>
        <p className="text-sm text-[var(--color-muted)]">Task not found. It may have been deleted.</p>
        <button onClick={onClose} aria-label="Close dialog" className="mt-3 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white">Close</button>
      </div>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-8 sm:pt-16 pb-8 overflow-y-auto bg-black/50" onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-2xl bg-[var(--color-card)] rounded-xl border border-[var(--color-border)]" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-4 sm:p-6 border-b border-[var(--color-border)]">
          <div className="min-w-0 space-y-2 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS[task.priority] || ''}`}>
                {PRIORITY_LABELS[task.priority] || task.priority}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                task.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' :
                task.status === 'in_progress' ? 'bg-blue-500/20 text-blue-400' :
                task.status === 'blocked' ? 'bg-red-500/20 text-red-400' :
                'bg-slate-500/20 text-slate-400'
              }`}>{STATUS_LABELS[task.status]}</span>
              {task.repo && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)]">{task.repo}</span>
              )}
              {task.score > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 font-mono">Score: {task.score}</span>
              )}
            </div>
            <h2 className="text-base sm:text-lg font-semibold leading-snug">{task.title}</h2>
          </div>
          <button onClick={onClose} aria-label="Close dialog" className="flex-shrink-0 p-1 rounded hover:bg-white/10 transition-colors">
            <X className="w-4 h-4 text-[var(--color-muted)]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 sm:p-6 space-y-4">
          {/* Description */}
          {task.description && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-1">Description</p>
              <p className="text-sm text-[var(--color-muted-foreground)]">{task.description}</p>
            </div>
          )}

          {/* Metadata grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">ID</p>
              <p className="text-xs font-mono text-[var(--color-muted-foreground)] truncate" title={task.id}>{task.id.slice(0, 28)}...</p>
            </div>
            {task.assignedTo && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Agent</p>
                <p className="text-xs text-[var(--color-foreground)]">{task.assignedTo}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Roadmap</p>
              <p className="text-xs text-[var(--color-muted-foreground)] truncate">{task.roadmapItem || '—'}</p>
            </div>
            {task.branch && (
              <div className="col-span-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Branch</p>
                <p className="text-xs font-mono text-blue-400 truncate"><GitBranch className="w-3 h-3 inline mr-0.5" />{task.branch}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Created</p>
              <p className="text-xs text-[var(--color-muted-foreground)]">{new Date(Number(task.createdAt)).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Updated</p>
              <p className="text-xs text-[var(--color-muted-foreground)]">{new Date(Number(task.updatedAt)).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Due Date</p>
              <DueDateEditor taskId={task.id} dueBy={task.dueBy != null ? Number(task.dueBy) : null} taskStatus={task.status} />
            </div>
            {task.requiredSkills && (
              <div className="col-span-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Required Skills</p>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {task.requiredSkills.split(',').map((s: string, i: number) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400"><Cpu className="w-2.5 h-2.5 inline mr-0.5" />{s.trim()}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Labels */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Tag className="w-3 h-3" /> Labels
            </p>
            {allLabels.length === 0 ? (
              <p className="text-xs text-[var(--color-muted)]">No labels defined. <RouterLink to="/labels" className="text-blue-400 hover:text-blue-300 underline underline-offset-2">Create labels</RouterLink> to organize tasks.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {allLabels.map(lbl => {
                  const active = currentLabelIds.has(lbl.id)
                  return (
                    <button key={lbl.id} onClick={() => toggleLabel(lbl.id)}
                      disabled={labelSaving}
                      className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border transition-all ${
                        active
                          ? 'border-white/50 text-white font-medium'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                      } disabled:opacity-50`}
                      style={active ? { backgroundColor: lbl.color + '30', borderColor: lbl.color + '60' } : {}}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: lbl.color }} />
                      {active && <Check className="w-3 h-3 inline mr-0.5" />}{lbl.name}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* GitHub Issue */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Github className="w-3 h-3" /> GitHub Issue
            </p>
            {loadingIssue ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                <Loader2 className="w-3 h-3 animate-spin" /> Checking...
              </div>
            ) : issueLink ? (
              <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-background)] border border-[var(--color-border)]">
                <Github className="w-4 h-4 text-[var(--color-muted)] shrink-0" />
                <span className="text-sm text-[var(--color-foreground)]">
                  <a href={issueLink.html_url} target="_blank" rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 underline underline-offset-2">
                    {issueLink.repo}#{issueLink.issue_number}
                  </a>
                </span>
                <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                  issueLink.html_url.includes('closed') || issueLink.status === 'closed'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-emerald-500/20 text-emerald-400'
                }`}>{issueLink.status}</span>
                <a href={issueLink.html_url} target="_blank" rel="noopener noreferrer"
                  aria-label="Open in new tab"
                  className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xs text-[var(--color-muted)]">No GitHub issue linked</p>
                {!showIssueForm ? (
                  <button onClick={() => { setShowIssueForm(true); setIssueRepo(task.repo || ''); setIssueLabels('') }}
                    className="text-xs px-2 py-1 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
                  >
                    <Plus className="w-3 h-3 inline mr-0.5" /> Create Issue
                  </button>
                ) : (
                  <div className="space-y-2 p-3 rounded bg-[var(--color-background)] border border-[var(--color-border)]">
                    <input
                      value={issueRepo}
                      onChange={e => setIssueRepo(e.target.value)}
                      placeholder="GitHub repo (owner/repo)"
                      className="w-full px-2 py-1.5 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)]"
                      autoFocus
                    />
                    <input
                      value={issueLabels}
                      onChange={e => setIssueLabels(e.target.value)}
                      placeholder="Labels (optional, comma-separated)"
                      className="w-full px-2 py-1.5 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)]"
                    />
                    <div className="flex items-center gap-2">
                      <button onClick={async () => {
                        const repo = issueRepo.trim()
                        if (!repo) { addToast('❌', 'Repository name is required'); return }
                        try {
                          const result = await api.issues.create(task.id, repo, issueLabels.trim())
                          setIssueLink({ html_url: result.html_url, issue_number: result.issue_number, repo })
                          setShowIssueForm(false)
                        } catch (e: unknown) {
                          addToast('❌', `Failed to create issue: ${e instanceof Error ? e.message : String(e)}`)
                        }
                      }}
                        className="text-xs px-2 py-1 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
                      ><Plus className="w-3 h-3 inline mr-0.5" /> Create</button>
                      <button onClick={() => setShowIssueForm(false)}
                        className="text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
                      >Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Dependency Chain */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Link className="w-3 h-3" /> Dependency Chain
            </p>
            <div className="space-y-1.5">
              {upstream && (
                <div className="flex items-center gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20">
                  <span className="text-xs text-amber-400 font-medium shrink-0">Depends on:</span>
                  <span className="text-sm truncate">{upstream.title}</span>
                  <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                    upstream.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                  }`}>{upstream.status}</span>
                </div>
              )}
              {!upstream && (
                <p className="text-xs text-[var(--color-muted)]">No dependencies — can be claimed freely</p>
              )}
              {downstream.length > 0 && (
                <div className="space-y-1 mt-2">
                  <p className="text-xs text-[var(--color-muted)]">Blocks {downstream.length} task(s):</p>
                  {downstream.slice(0, 5).map(dt => (
                    <div key={dt.id} className="flex items-center gap-2 p-1.5 rounded bg-white/[0.03]">
                      <span className="text-sm truncate">{dt.title}</span>
                      <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                        dt.status === 'blocked' ? 'bg-red-500/20 text-red-400' :
                        dt.status === 'available' ? 'bg-blue-500/20 text-blue-400' :
                        'bg-emerald-500/20 text-emerald-400'
                      }`}>{dt.status}</span>
                    </div>
                  ))}
                  {downstream.length > 5 && (
                    <p className="text-[10px] text-[var(--color-muted)]">...and {downstream.length - 5} more</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Activity Log */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <History className="w-3 h-3" /> Activity Log
            </p>
            {loadingLogs ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] py-2">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading...
              </div>
            ) : logs.length === 0 ? (
              <p className="text-xs text-[var(--color-muted)] py-2">No activity recorded.</p>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {logs.map((log: LogEntry) => (
                  <div key={log.id} className="flex items-start gap-2 py-1.5 border-b border-[var(--color-border)] last:border-0">
                    <span className="shrink-0">{actionIcons[log.action] || <ClipboardList className="w-3.5 h-3.5 text-[var(--color-muted)]" />}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium capitalize">{log.action.replace(/_/g, ' ')}</span>
                        {log.agent_id && <span className="text-[10px] text-[var(--color-muted)]">by {log.agent_id}</span>}
                      </div>
                      {log.notes && <p className="text-[11px] text-[var(--color-muted-foreground)] truncate">{log.notes}</p>}
                    </div>
                    <span className="text-[10px] text-[var(--color-muted)] shrink-0">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Comments */}
          <TaskComments taskId={task.id} />

          {/* Checklist / Subtasks */}
          <TaskChecklist taskId={task.id} />
        </div>

        {/* Action Footer */}
        <div className="flex items-center gap-2 p-4 sm:p-6 border-t border-[var(--color-border)]">
          {task.status === 'available' && (
            <>
              <button onClick={() => onClaim(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
              ><Play className="w-3 h-3" /> Claim</button>
              <button onClick={() => onSetDependency(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Link className="w-3 h-3" /> Set Dep</button>
              <button onClick={() => onSetSkills(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
              ><Cpu className="w-3 h-3" /> Set Skills</button>
              <button onClick={async () => { const ok = await confirm({ title: 'Delete Task', message: 'Delete this task?', confirmLabel: 'Delete', variant: 'danger' }); if (ok) onDelete(task.id) }}
                className="text-xs px-3 py-1.5 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
              ><Trash2 className="w-3 h-3" /> Delete</button>
            </>
          )}
          {task.status === 'in_progress' && (
            <>
              <button onClick={() => onComplete(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              ><CheckCircle2 className="w-3 h-3" /> Complete</button>
              <button onClick={() => onBlock(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Ban className="w-3 h-3" /> Block</button>
              <button onClick={() => onUnclaim(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors ml-auto"
              ><RotateCcw className="w-3 h-3" /> Release</button>
            </>
          )}
          {task.status === 'blocked' && (
            <button onClick={() => onUnclaim(task.id)}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
            ><RotateCcw className="w-3 h-3" /> Release back to available</button>
          )}
          {task.status === 'done' && (
            <>
              {onArchive && (
                <button onClick={() => onArchive(task.id)}
                  className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-white/10 text-[var(--color-muted-foreground)] hover:bg-white/15 transition-colors"
                ><Archive className="w-3 h-3" /> Archive</button>
              )}
              <button onClick={async () => { const ok = await confirm({ title: 'Delete Task', message: 'Delete this task?', confirmLabel: 'Delete', variant: 'danger' }); if (ok) onDelete(task.id) }}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
              ><Trash2 className="w-3 h-3" /> Delete</button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
