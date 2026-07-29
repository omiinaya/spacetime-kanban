import {
  Play, CheckCircle2, Ban, RotateCcw, Trash2, Link, Cpu,
  Github, CheckSquare, Square, Archive,
} from 'lucide-react'
import type { KanbanLabel, IssueLink } from '../../api'
import type { Task } from '../../hooks/useRealtimeTasks'
import { PRIORITY_LABELS, PRIORITY_COLORS } from '../constants'

export interface TaskCardProps {
  task: Task
  compact: boolean
  selectMode: boolean
  selected: boolean
  labels: KanbanLabel[]
  issueLink?: IssueLink
  draggedTaskId: string | null
  dropOnTaskId: string | null
  onToggleSelect: (id: string) => void
  onClaim: (taskId: string, agentId: string) => void
  onComplete: (taskId: string) => void
  onBlock: (taskId: string) => void
  onUnclaim: (taskId: string) => void
  onDelete: (taskId: string) => void
  onArchive?: (taskId: string) => void
  onClick: (id: string) => void
  onDragStart: (taskId: string) => void
  onDragEnd: () => void
  onDropOnTask: (taskId: string) => void
  onSetDependency: (taskId: string) => void
  onSetSkills: (taskId: string) => void
  setDropOnTaskId: (id: string | null) => void
}

function DependencyBadge({ depId }: { depId: string | undefined }) {
  if (!depId) return null
  return (
    <span className="text-[10px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400/80" title={`Depends on: ${depId}`}>
      <span aria-hidden="true">⬆</span>
    </span>
  )
}

export default function TaskCard({
  task, compact, selectMode, selected, labels, issueLink,
  draggedTaskId, dropOnTaskId,
  onToggleSelect, onClaim, onComplete, onBlock, onUnclaim, onDelete, onArchive, onClick,
  onDragStart, onDragEnd, onDropOnTask,
  onSetDependency, onSetSkills,
  setDropOnTaskId,
}: TaskCardProps) {
  const dragProps = {
    draggable: true,
    onDragStart: () => onDragStart(task.id),
    onDragEnd,
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setDropOnTaskId(task.id) },
    onDragLeave: () => { if (dropOnTaskId === task.id) setDropOnTaskId(null) },
    onDrop: () => onDropOnTask(task.id),
  }

  if (compact) {
    return (
      <div
        {...dragProps}
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
            {selected
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
          <DependencyBadge depId={task.dependsOn} />
          {labels.map(lbl => (
            <span key={lbl.id} className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: lbl.color }} title={lbl.name} />
          ))}
          {issueLink && (() => {
            const closed = issueLink.html_url?.includes('closed') || issueLink.status === 'closed'
            return (
              <span className={`text-[10px] px-1 py-0.5 rounded font-medium flex-shrink-0 ${closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                #{issueLink.issue_number}
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
                <span aria-hidden="true">📅</span> {new Date(Number(task.dueBy)).toLocaleDateString()}
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
          {task.status === 'done' && onArchive && (
            <button onClick={(e) => { e.stopPropagation(); onArchive(task.id) }}
              title="Archive task"
              className="text-xs px-1.5 py-0.5 rounded text-slate-400 hover:bg-white/10 transition-colors">Arc</button>
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
    <div
      {...dragProps}
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
              {selected
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
        <DependencyBadge depId={task.dependsOn} />
        {task.requiredSkills && (
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400/80 font-medium truncate max-w-[140px]" title={`Skills: ${task.requiredSkills}`}>
            <Cpu className="w-3 h-3 inline mr-0.5" />{task.requiredSkills}
          </span>
        )}
        {issueLink && (() => {
          const closed = issueLink.html_url?.includes('closed') || issueLink.status === 'closed'
          return (
            <a href={issueLink.html_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium hover:opacity-80 transition-opacity ${
                closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'
              }`}
            >
              <Github className="w-2.5 h-2.5" /> {issueLink.repo.split('/').pop()}#{issueLink.issue_number}
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
              <span aria-hidden="true">📅</span> {new Date(Number(task.dueBy)).toLocaleDateString()}
            </span>
          )
        })()}
        {labels.map(lbl => (
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
          <>
            {onArchive && (
              <button onClick={() => onArchive(task.id)}
                className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-slate-500/20 text-slate-400 hover:bg-slate-500/30 transition-colors"
              ><Archive className="w-3 h-3" /> Archive</button>
            )}
            <button onClick={() => onDelete(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            ><Trash2 className="w-3 h-3" /> Delete</button>
          </>
        )}
      </div>
    </div>
  )
}
