import { useState, useRef, useCallback } from 'react'
import {
  Plus, Play, CheckCircle2, Ban, RotateCcw, Trash2, Link, Cpu,
  Github, CheckSquare, Square,
  Loader2,
} from 'lucide-react'
import { CardSkeleton, CompactCardSkeleton } from './Skeleton'
import type { KanbanLabel, IssueLink } from '../api'
import type { Task, TaskStatus } from '../hooks/useRealtimeTasks'
import { PRIORITY_LABELS, PRIORITY_COLORS, STATUS_LABELS } from './constants'
import { useLazyLoad } from '../hooks/useLazyLoad'

// ---------- WIP Limits ----------
const DEFAULT_WIP_LIMITS: Record<string, number> = {
  'available': 50,
  'in_progress': 15,
  'blocked': 10,
  'done': Infinity,
}

function getEffectiveWipLimit(status: string): number {
  try {
    const stored = JSON.parse(localStorage.getItem('kanban-wip-limits') || '{}')
    if (stored[status] !== undefined && stored[status] >= 0) return stored[status]
  } catch { /* ignore corrupt localStorage */ }
  return DEFAULT_WIP_LIMITS[status] ?? Infinity
}

interface KanbanColumnProps {
  status: TaskStatus
  tasks: Task[]
  compactMode: boolean
  selectMode: boolean
  selectedIds: Set<string>
  taskLabelMap: Map<string, KanbanLabel[]>
  issueLinks: Record<string, IssueLink>
  draggedTaskId: string | null
  dragOverColumn: string | null
  dropOnTaskId: string | null
  collapsed: boolean
  onToggleCollapse: (status: string) => void
  onToggleSelect: (id: string) => void
  onClaim: (taskId: string, agentId: string) => void
  onComplete: (taskId: string) => void
  onBlock: (taskId: string) => void
  onUnclaim: (taskId: string) => void
  onDelete: (taskId: string) => void
  onClick: (id: string) => void
  onDragStart: (taskId: string) => void
  onDragEnd: () => void
  onDropOnColumn: (status: TaskStatus) => void
  onDropOnTask: (taskId: string) => void
  onSetDependency: (taskId: string) => void
  onSetSkills: (taskId: string) => void
  onQuickAdd: (status: string, title: string) => void
  setDragOverColumn: (status: string | null) => void
  setDropOnTaskId: (id: string | null) => void
}

export default function KanbanColumn({
  status, tasks, compactMode, selectMode, selectedIds,
  taskLabelMap, issueLinks, draggedTaskId, dragOverColumn, dropOnTaskId,
  collapsed, onToggleCollapse,
  onToggleSelect, onClaim, onComplete, onBlock, onUnclaim, onDelete, onClick,
  onDragStart, onDragEnd, onDropOnColumn, onDropOnTask,
  onSetDependency, onSetSkills, onQuickAdd,
  setDragOverColumn, setDropOnTaskId,
}: KanbanColumnProps) {
  // Per-column infinite scroll — load 20 initially, 15 more on scroll
  const { sentinelRef, count, hasMore } = useLazyLoad(tasks.length, 20, 15)
  const shownTasks = tasks.slice(0, count)

  const [quickAddTitle, setQuickAddTitle] = useState('')
  const [quickAddOpen, setQuickAddOpen] = useState(false)
  const quickAddRef = useRef<HTMLInputElement>(null)
  const isOver = dragOverColumn === status && draggedTaskId !== null

  // WIP limit computation
  const wipLimit = getEffectiveWipLimit(status)
  const totalCount = tasks.length
  const wipPercent = wipLimit === Infinity ? 0 : (totalCount / wipLimit) * 100
  const wipWarning = wipLimit !== Infinity && wipPercent > 80 && wipPercent < 100
  const wipCritical = wipLimit !== Infinity && totalCount >= wipLimit
  const wipAtLimit = wipLimit !== Infinity && totalCount >= wipLimit

  const handleQuickAdd = useCallback(() => {
    if (!quickAddTitle.trim()) return
    onQuickAdd(status, quickAddTitle.trim())
    setQuickAddTitle('')
    setQuickAddOpen(false)
  }, [quickAddTitle, status, onQuickAdd])

  const renderDependencyBadge = (depId: string | undefined) => {
    if (!depId) return null
    return (
      <span className="text-[10px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400/80" title={`Depends on: ${depId}`}>
        ⬆
      </span>
    )
  }

  const renderCard = (task: Task) => {
    if (compactMode) {
      return (
        <div key={task.id}
          draggable
          onDragStart={() => onDragStart(task.id)}
          onDragEnd={onDragEnd}
          onDragOver={(e) => { e.preventDefault(); setDropOnTaskId(task.id) }}
          onDragLeave={() => { if (dropOnTaskId === task.id) setDropOnTaskId(null) }}
          onDrop={() => onDropOnTask(task.id)}
          onClick={() => onClick(task.id)}
          className={`bg-[var(--color-card)] rounded border-l-4 border border-[var(--color-border)] py-1.5 px-2 cursor-pointer hover:border-[var(--color-ring)] transition-colors flex items-center gap-2 ${
            ({0: 'border-l-red-500', 1: 'border-l-orange-400', 2: 'border-l-blue-400', 3: 'border-l-slate-400'} as Record<number, string>)[task.priority] || 'border-l-slate-400'
          } ${
            draggedTaskId === task.id ? 'opacity-50' : ''
          } ${
            dropOnTaskId === task.id ? 'border-t-2 border-t-[var(--color-primary)]' : ''
          }`}
        >
          {selectMode && (
            <button
              onClick={(e) => { e.stopPropagation(); onToggleSelect(task.id) }}
              className="flex-shrink-0 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            >
              {selectedIds.has(task.id)
                ? <CheckSquare className="w-3.5 h-3.5 text-[var(--color-primary)]" />
                : <Square className="w-3.5 h-3.5" />
              }
            </button>
          )}
          <div className="min-w-0 flex-1 flex items-center gap-2">
            <span className="text-sm font-medium truncate">{task.title}</span>
            {task.assignedTo && (
              <span className="text-[10px] text-[var(--color-muted)] flex-shrink-0">@{task.assignedTo}</span>
            )}
            {task.repo && (
              <span className="text-[10px] px-1 py-0.5 rounded bg-white/8 text-[var(--color-muted)] font-medium flex-shrink-0">{task.repo}</span>
            )}
            {renderDependencyBadge(task.dependsOn)}
            {(taskLabelMap.get(task.id) || []).map(lbl => (
              <span key={lbl.id} className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: lbl.color }} title={lbl.name} />
            ))}
            {issueLinks[task.id] && (() => {
              const link = issueLinks[task.id]
              const closed = link.html_url?.includes('closed') || link.status === 'closed'
              return (
                <span className={`text-[10px] px-1 py-0.5 rounded font-medium flex-shrink-0 ${closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                  #{link.issue_number}
                </span>
              )
            })()}
            {task.dueBy != null && (() => {
              const now = Date.now()
              const overdue = now > Number(task.dueBy) && task.status !== 'done'
              return (
                <span className={`text-[10px] px-1 py-0.5 rounded font-medium flex-shrink-0 ${
                  overdue ? 'bg-red-500/20 text-red-400' : 'bg-white/8 text-[var(--color-muted)]'
                }`} title={new Date(Number(task.dueBy)).toLocaleString()}>
                  📅 {new Date(Number(task.dueBy)).toLocaleDateString()}
                </span>
              )
            })()}
            </div>
          <div className="flex items-center gap-0.5 flex-shrink-0">
            {task.status === 'available' && (
              <button onClick={(e) => { e.stopPropagation(); onClaim(task.id, 'web-user') }}
                className="text-xs px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors">Claim</button>
            )}
            {task.status === 'in_progress' && (
              <>
                <button onClick={(e) => { e.stopPropagation(); onComplete(task.id) }}
                  className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors">Done</button>
                <button onClick={(e) => { e.stopPropagation(); onBlock(task.id) }}
                  className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors">Block</button>
              </>
            )}
            {task.status === 'blocked' && (
              <button onClick={(e) => { e.stopPropagation(); onUnclaim(task.id) }}
                className="text-xs px-1.5 py-0.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors">Release</button>
            )}
            {task.status === 'done' && (
              <button onClick={(e) => { e.stopPropagation(); onDelete(task.id) }}
                className="text-xs px-1.5 py-0.5 rounded text-red-400 hover:bg-red-500/20 transition-colors">Del</button>
            )}
          </div>
        </div>
      )
    }

    // Detailed card
    return (
      <div key={task.id}
        draggable
        onDragStart={() => onDragStart(task.id)}
        onDragEnd={onDragEnd}
        onDragOver={(e) => { e.preventDefault(); setDropOnTaskId(task.id) }}
        onDragLeave={() => { if (dropOnTaskId === task.id) setDropOnTaskId(null) }}
        onDrop={() => onDropOnTask(task.id)}
        onClick={() => onClick(task.id)}
        className={`bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2 cursor-pointer hover:border-[var(--color-ring)] transition-colors ${
          draggedTaskId === task.id ? 'opacity-50 ring-2 ring-[var(--color-primary)]' : ''
        } ${
          dropOnTaskId === task.id ? 'border-t-2 border-t-[var(--color-primary)]' : ''
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            {selectMode && (
              <button
                onClick={(e) => { e.stopPropagation(); onToggleSelect(task.id) }}
                className="flex-shrink-0 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
              >
                {selectedIds.has(task.id)
                  ? <CheckSquare className="w-4 h-4 text-[var(--color-primary)]" />
                  : <Square className="w-4 h-4" />
                }
              </button>
            )}
            <span className={`text-xs px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${PRIORITY_COLORS[task.priority] || ''}`}>
              {PRIORITY_LABELS[task.priority] || task.priority}
            </span>
          </div>
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
            <span className="px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)] font-medium">{task.repo}</span>
          )}
          {task.branch && <span className="text-blue-400 truncate max-w-[120px]">:{task.branch}</span>}
          {task.roadmapItem && <span className="text-purple-400/70 truncate">{task.roadmapItem}</span>}
          {renderDependencyBadge(task.dependsOn)}
          {task.requiredSkills && (
            <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400/80 font-medium truncate max-w-[140px]" title={`Skills: ${task.requiredSkills}`}>
              <Cpu className="w-3 h-3 inline mr-0.5" />{task.requiredSkills}
            </span>
          )}
          {issueLinks[task.id] && (() => {
            const link = issueLinks[task.id]
            const closed = link.html_url?.includes('closed') || link.status === 'closed'
            return (
              <a href={link.html_url} target="_blank" rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium hover:opacity-80 transition-opacity ${
                  closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'
                }`}
              >
                <Github className="w-2.5 h-2.5" /> {link.repo.split('/').pop()}#{link.issue_number}
              </a>
            )
          })()}
          {task.dueBy != null && (() => {
            const now = Date.now()
            const overdue = now > Number(task.dueBy) && task.status !== 'done'
            return (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                overdue ? 'bg-red-500/20 text-red-400' : 'bg-white/8 text-[var(--color-muted)]'
              }`} title={new Date(Number(task.dueBy)).toLocaleString()}>
                📅 {new Date(Number(task.dueBy)).toLocaleDateString()}
              </span>
            )
          })()}
          {(taskLabelMap.get(task.id) || []).map(lbl => (
            <span key={lbl.id} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium truncate max-w-[100px]"
              style={{ backgroundColor: lbl.color + '20', color: lbl.color, border: `1px solid ${lbl.color}40` }}>
              <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: lbl.color }} />
              {lbl.name}
            </span>
          ))}
        </div>

        <div className="flex items-center gap-1 pt-1 border-t border-[var(--color-border)]">
          {task.status === 'available' && (
            <>
              <button onClick={() => onClaim(task.id, 'web-user')}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
              ><Play className="w-3 h-3" /> Claim</button>
              <button onClick={() => onSetDependency(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Link className="w-3 h-3" /> Dep</button>
              <button onClick={() => onSetSkills(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
              ><Cpu className="w-3 h-3" /> Skills</button>
            </>
          )}
          {task.status === 'in_progress' && (
            <>
              <button onClick={() => onComplete(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              ><CheckCircle2 className="w-3 h-3" /> Done</button>
              <button onClick={() => onBlock(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Ban className="w-3 h-3" /> Block</button>
              <button onClick={() => onSetDependency(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Link className="w-3 h-3" /> Dep</button>
            </>
          )}
          {task.status === 'blocked' && (
            <>
              <button onClick={() => onUnclaim(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
              ><RotateCcw className="w-3 h-3" /> Release</button>
              <button onClick={() => onSetDependency(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Link className="w-3 h-3" /> Dep</button>
            </>
          )}
          {task.status === 'done' && (
            <button onClick={() => onDelete(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            ><Trash2 className="w-3 h-3" /> Delete</button>
          )}
        </div>
      </div>
    )
  }

  // ---------- Collapsed column rendering ----------
  if (collapsed) {
    return (
      <div className="flex flex-col items-center min-h-0 h-full select-none cursor-pointer"
        onClick={() => onToggleCollapse(status)}
        title={`Expand ${STATUS_LABELS[status]} column`}
      >
        {/* Vertical label */}
        <div className="flex flex-col items-center gap-2 mb-3 pt-1">
          <button
            onClick={(e) => { e.stopPropagation(); onToggleCollapse(status) }}
            className="p-0.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            title="Expand"
          ><span className="text-xs">▶</span></button>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]"
            style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}>
            {STATUS_LABELS[status]}
          </span>
        </div>
        {/* Count badge */}
        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
          wipCritical
            ? 'bg-red-500/20 text-red-400'
            : wipWarning
              ? 'bg-amber-500/20 text-amber-400'
              : 'bg-[var(--color-card)] text-[var(--color-muted)]'
        }`}>
          {tasks.length}
        </span>
      </div>
    )
  }

  // ---------- Expanded column rendering ----------
  return (
    <div className="flex flex-col min-h-0">
      {/* Column header */}
      <div className="flex items-center justify-between mb-2 px-0.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <button
            onClick={() => onToggleCollapse(status)}
            className="p-0.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors flex-shrink-0"
            title="Collapse"
          ><span className="text-xs">▼</span></button>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] truncate">
            {STATUS_LABELS[status]}
            {wipLimit !== Infinity && (
              <span className="ml-1.5 font-normal normal-case">
                ({totalCount}/{wipLimit})
              </span>
            )}
          </h2>
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => { if (!wipAtLimit) setQuickAddOpen(o => !o) }}
            className={`p-0.5 rounded transition-colors ${
              wipAtLimit
                ? 'text-red-400/40 cursor-not-allowed'
                : 'hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
            }`}
            title={wipAtLimit ? `WIP limit reached (${totalCount}/${wipLimit})` : `Add task to ${STATUS_LABELS[status]}`}
            disabled={wipAtLimit}
          ><Plus className="w-3.5 h-3.5" /></button>
          <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
            wipCritical
              ? 'bg-red-500/20 text-red-400'
              : wipWarning
                ? 'bg-amber-500/20 text-amber-400'
                : 'bg-[var(--color-card)] text-[var(--color-muted)]'
          }`}>
            {shownTasks.length}/{tasks.length}
          </span>
        </div>
      </div>

      {/* Quick-add input */}
      {quickAddOpen && (
        <div className="flex items-center gap-1.5 mb-2">
          <input
            ref={quickAddRef}
            value={quickAddTitle}
            onChange={e => setQuickAddTitle(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') handleQuickAdd()
              if (e.key === 'Escape') { setQuickAddOpen(false); setQuickAddTitle('') }
            }}
            placeholder="Task title..."
            autoFocus
            className="flex-1 px-2 py-1 text-xs rounded border border-[var(--color-border)] bg-[var(--color-background)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
          />
          <button
            onClick={handleQuickAdd}
            disabled={!quickAddTitle.trim()}
            className="px-2 py-1 text-xs rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >Add</button>
        </div>
      )}

      {/* Scrollable card area */}
      <div
        className="flex-1 space-y-2 min-h-[120px] rounded-lg transition-colors overflow-y-auto"
        style={{ maxHeight: 'calc(100vh - 240px)' }}
        onDragOver={(e) => { e.preventDefault(); setDragOverColumn(status) }}
        onDragEnter={(e) => { e.preventDefault(); setDragOverColumn(status) }}
        onDragLeave={() => setDragOverColumn(null)}
        onDrop={() => onDropOnColumn(status)}
      >
        {shownTasks.map(renderCard)}
        {shownTasks.length === 0 && tasks.length === 0 && (
          <div className={`text-center py-6 text-xs border border-dashed rounded-lg transition-colors ${
            isOver
              ? 'text-[var(--color-primary)] border-[var(--color-primary)] bg-white/5'
              : 'text-[var(--color-muted)] border-[var(--color-border)]'
          }`}>
            {isOver ? 'Drop here' : 'Empty'}
          </div>
        )}

        {/* Lazy loading sentinel */}
        {hasMore && (
          <>
            <div ref={sentinelRef} className="h-2" />
            {compactMode
              ? Array.from({ length: 3 }).map((_, i) => <CompactCardSkeleton key={i} />)
              : Array.from({ length: 2 }).map((_, i) => <CardSkeleton key={i} />)
            }
          </>
        )}
        {!hasMore && shownTasks.length > 0 && tasks.length > 15 && (
          <div className="text-center py-2 text-[10px] text-[var(--color-muted)]">
            All {tasks.length} tasks loaded
          </div>
        )}
      </div>
    </div>
  )
}
