import { useState, useMemo } from 'react'
import {
  Play, CheckCircle2, Ban, RotateCcw, Trash2, Cpu,
  Github, CheckSquare, Square, Loader2,
  ArrowUpDown, ArrowUp, ArrowDown,
} from 'lucide-react'
import type { KanbanLabel, IssueLink } from '../api'
import type { Task } from '../hooks/useRealtimeTasks'
import { useLazyLoad } from '../hooks/useLazyLoad'
import { TableRowSkeleton } from './Skeleton'
import { PRIORITY_LABELS, STATUS_COLORS, PRIORITY_COLORS_VIBRANT } from './constants'

interface ListViewProps {
  tasks: Task[]
  loading: boolean
  selectedIds: Set<string>
  selectMode: boolean
  taskLabelMap: Map<string, KanbanLabel[]>
  issueLinks: Record<string, IssueLink>
  onToggleSelect: (id: string) => void
  onClaim: (id: string) => void
  onComplete: (id: string) => void
  onBlock: (id: string) => void
  onUnclaim: (id: string) => void
  onDelete: (id: string) => void
  onClick: (id: string) => void
}

type SortField = 'priority' | 'status' | 'repo' | 'assignedTo' | 'createdAt' | 'title'
type SortDir = 'asc' | 'desc'

export default function ListView({
  tasks, loading, selectedIds, selectMode,
  taskLabelMap, issueLinks,
  onToggleSelect, onClaim, onComplete, onBlock, onUnclaim, onDelete, onClick,
}: ListViewProps) {
  const [sortField, setSortField] = useState<SortField>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('asc')

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="w-3 h-3 opacity-40" />
    return sortDir === 'asc'
      ? <ArrowUp className="w-3 h-3 text-[var(--color-primary)]" />
      : <ArrowDown className="w-3 h-3 text-[var(--color-primary)]" />
  }

  const sorted = useMemo(() => {
    const copy = [...tasks]
    copy.sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'priority':
          cmp = a.priority - b.priority
          break
        case 'status': {
          const order = ['available', 'in_progress', 'blocked', 'done']
          cmp = order.indexOf(a.status) - order.indexOf(b.status)
          break
        }
        case 'repo':
          cmp = (a.repo || '').localeCompare(b.repo || '')
          break
        case 'assignedTo':
          cmp = (a.assignedTo || '').localeCompare(b.assignedTo || '')
          break
        case 'createdAt':
          cmp = Number(a.createdAt) - Number(b.createdAt)
          break
        case 'title':
          cmp = a.title.localeCompare(b.title)
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [tasks, sortField, sortDir])

  const { sentinelRef, count, hasMore } = useLazyLoad(sorted.length, 30, 20)

  const displayedTasks = sorted.slice(0, count)

  return (
    <div className="space-y-3">
      {/* Table wrapper — horizontal scroll on small screens */}
      <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--color-border)] bg-[var(--color-card)]">
              {selectMode && (
                <th className="py-2.5 px-3 text-left w-8">
                  <span className="text-[var(--color-muted)] text-xs">#</span>
                </th>
              )}
              <th className="py-2.5 px-3 text-left">
                <button
                  onClick={() => toggleSort('priority')}
                  className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  P <SortIcon field="priority" />
                </button>
              </th>
              <th className="py-2.5 px-3 text-left min-w-[200px]">
                <button
                  onClick={() => toggleSort('title')}
                  className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  Title <SortIcon field="title" />
                </button>
              </th>
              <th className="py-2.5 px-3 text-left">
                <button
                  onClick={() => toggleSort('status')}
                  className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  Status <SortIcon field="status" />
                </button>
              </th>
              <th className="py-2.5 px-3 text-left">
                <button
                  onClick={() => toggleSort('repo')}
                  className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  Project <SortIcon field="repo" />
                </button>
              </th>
              <th className="py-2.5 px-3 text-left">
                <button
                  onClick={() => toggleSort('assignedTo')}
                  className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  Assignee <SortIcon field="assignedTo" />
                </button>
              </th>
              <th className="py-2.5 px-3 text-left hidden md:table-cell">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  Labels
                </span>
              </th>
              <th className="py-2.5 px-3 text-left hidden md:table-cell">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  Links
                </span>
              </th>
              <th className="py-2.5 px-3 text-right w-[140px]">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  Actions
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && tasks.length === 0 ? (
              // Skeleton rows during initial load
              Array.from({ length: 8 }).map((_, i) => <TableRowSkeleton key={i} />)
            ) : displayedTasks.length === 0 ? (
              <tr>
                <td colSpan={selectMode ? 9 : 8} className="py-8 text-center text-sm text-[var(--color-muted)]">
                  No tasks match the current filters
                </td>
              </tr>
            ) : (
              displayedTasks.map((task) => (
                <tr
                  key={task.id}
                  onClick={() => onClick(task.id)}
                  className="border-b border-[var(--color-border)] hover:bg-white/[0.03] transition-colors cursor-pointer"
                >
                  {/* Checkbox column (select mode only) */}
                  {selectMode && (
                    <td className="py-2.5 px-3">
                      <button
                        onClick={(e) => { e.stopPropagation(); onToggleSelect(task.id) }}
                        className="text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                      >
                        {selectedIds.has(task.id)
                          ? <CheckSquare className="w-4 h-4 text-[var(--color-primary)]" />
                          : <Square className="w-4 h-4" />
                        }
                      </button>
                    </td>
                  )}

                  {/* Priority */}
                  <td className="py-2.5 px-3">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS_VIBRANT[task.priority] || ''}`}>
                      {PRIORITY_LABELS[task.priority] || task.priority}
                    </span>
                  </td>

                  {/* Title */}
                  <td className="py-2.5 px-3 max-w-[300px]">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{task.title}</span>
                      {task.dependsOn && (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-amber-500/15 text-amber-400/80 shrink-0" title="Has dependency">
                          ⬆
                        </span>
                      )}
                      {task.requiredSkills && (
                        <span className="text-[10px] px-1 py-0.5 rounded bg-cyan-500/15 text-cyan-400/80 shrink-0" title={`Skills: ${task.requiredSkills}`}>
                          <Cpu className="w-2.5 h-2.5 inline" />
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Status */}
                  <td className="py-2.5 px-3">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${STATUS_COLORS[task.status] || ''}`}>
                      {task.status.replace('_', ' ')}
                    </span>
                  </td>

                  {/* Repo/Project */}
                  <td className="py-2.5 px-3">
                    {task.repo ? (
                      <span className="text-xs text-[var(--color-muted)] font-medium">{task.repo}</span>
                    ) : (
                      <span className="text-xs text-[var(--color-muted)]">—</span>
                    )}
                  </td>

                  {/* Assignee */}
                  <td className="py-2.5 px-3">
                    {task.assignedTo ? (
                      <span className="text-xs text-[var(--color-muted)]">@{task.assignedTo}</span>
                    ) : (
                      <span className="text-xs text-[var(--color-muted)]">—</span>
                    )}
                  </td>

                  {/* Labels (desktop only) */}
                  <td className="py-2.5 px-3 hidden md:table-cell">
                    <div className="flex items-center gap-1 max-w-[120px]">
                      {(taskLabelMap.get(task.id) || []).slice(0, 2).map((lbl) => (
                        <span
                          key={lbl.id}
                          className="w-2 h-2 rounded-full shrink-0"
                          style={{ backgroundColor: lbl.color }}
                          title={lbl.name}
                        />
                      ))}
                      {(taskLabelMap.get(task.id) || []).length > 2 && (
                        <span className="text-[9px] text-[var(--color-muted)]">
                          +{(taskLabelMap.get(task.id) || []).length - 2}
                        </span>
                      )}
                    </div>
                  </td>

                  {/* Issue links (desktop only) */}
                  <td className="py-2.5 px-3 hidden md:table-cell">
                    {issueLinks[task.id] ? (
                      <a
                        href={issueLinks[task.id].html_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-[10px] px-1 py-0.5 rounded bg-emerald-500/20 text-emerald-400 hover:opacity-80 transition-opacity"
                      >
                        <Github className="w-2.5 h-2.5" />
                        #{issueLinks[task.id].issue_number}
                      </a>
                    ) : (
                      <span className="text-xs text-[var(--color-muted)]">—</span>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="py-2.5 px-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {task.status === 'available' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onClaim(task.id) }}
                          className="p-1 rounded text-green-400 hover:bg-green-500/20 transition-colors"
                          title="Claim"
                        >
                          <Play className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {task.status === 'in_progress' && (
                        <>
                          <button
                            onClick={(e) => { e.stopPropagation(); onComplete(task.id) }}
                            className="p-1 rounded text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                            title="Complete"
                          >
                            <CheckCircle2 className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); onBlock(task.id) }}
                            className="p-1 rounded text-amber-400 hover:bg-amber-500/20 transition-colors"
                            title="Block"
                          >
                            <Ban className="w-3.5 h-3.5" />
                          </button>
                        </>
                      )}
                      {task.status === 'blocked' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onUnclaim(task.id) }}
                          className="p-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
                          title="Release"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {task.status === 'done' && (
                        <button
                          onClick={(e) => { e.stopPropagation(); onDelete(task.id) }}
                          className="p-1 rounded text-red-400 hover:bg-red-500/20 transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Infinite scroll sentinel */}
      {!loading && sorted.length > 0 && (
        <>
          <div className="text-xs text-[var(--color-muted)] px-1">
            Showing {displayedTasks.length} of {sorted.length} tasks
          </div>
          {hasMore && (
            <div
              ref={sentinelRef}
              className="flex items-center justify-center py-4 text-[var(--color-muted)]"
            >
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          )}
        </>
      )}
    </div>
  )
}
