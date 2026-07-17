import { useState, useRef, useCallback } from 'react'
import { Plus, Archive } from 'lucide-react'
import { CardSkeleton, CompactCardSkeleton } from './Skeleton'
import type { KanbanLabel, IssueLink } from '../api'
import type { Task, TaskStatus } from '../hooks/useRealtimeTasks'
import { STATUS_LABELS } from './constants'
import { useLazyLoad } from '../hooks/useLazyLoad'
import TaskCard from './board/TaskCard'

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
  onArchive?: (taskId: string) => void
  onArchiveAll?: (status: string) => void
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
  onToggleSelect, onClaim, onComplete, onBlock, onUnclaim, onDelete, onArchive, onArchiveAll, onClick,
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

  const renderCard = (task: Task) => (
    <TaskCard
      key={task.id}
      task={task}
      compact={compactMode}
      selectMode={selectMode}
      selected={selectedIds.has(task.id)}
      labels={taskLabelMap.get(task.id) || []}
      issueLink={issueLinks[task.id]}
      draggedTaskId={draggedTaskId}
      dropOnTaskId={dropOnTaskId}
      onToggleSelect={onToggleSelect}
      onClaim={onClaim}
      onComplete={onComplete}
      onBlock={onBlock}
      onUnclaim={onUnclaim}
      onDelete={onDelete}
      onArchive={onArchive}
      onClick={onClick}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDropOnTask={onDropOnTask}
      onSetDependency={onSetDependency}
      onSetSkills={onSetSkills}
      setDropOnTaskId={setDropOnTaskId}
    />
  )

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
          {status === 'done' && tasks.length > 0 && onArchiveAll && (
            <button
              onClick={() => onArchiveAll(status)}
              className="p-0.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
              title={`Archive all ${tasks.length} done task(s) — hides them from the board`}
            ><Archive className="w-3.5 h-3.5" /></button>
          )}
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
