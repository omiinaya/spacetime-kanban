import type { KanbanLabel } from '../../api'
import type { Task } from '../../hooks/useRealtimeTasks'
import { PRIORITY_LABELS } from '../constants'

interface AdvancedFiltersProps {
  tasks: Task[]
  allLabels: KanbanLabel[]
  filterPriorities: Set<number>
  setFilterPriorities: (v: Set<number>) => void
  filterAssignees: Set<string>
  setFilterAssignees: (v: Set<string>) => void
  filterLabels: Set<string>
  setFilterLabels: (v: Set<string>) => void
}

function toggleIn<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

export function AdvancedFilters({
  tasks, allLabels,
  filterPriorities, setFilterPriorities,
  filterAssignees, setFilterAssignees,
  filterLabels, setFilterLabels,
}: AdvancedFiltersProps) {
  const hasActive = filterPriorities.size > 0 || filterAssignees.size > 0 || filterLabels.size > 0

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        {/* Priority filter */}
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Priority</p>
          <div className="flex flex-wrap gap-1.5">
            {[0, 1, 2, 3].map(p => {
              const active = filterPriorities.has(p)
              return (
                <button key={p}
                  onClick={() => setFilterPriorities(toggleIn(filterPriorities, p))}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                    active
                      ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-white'
                      : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                  }`}
                >
                  {active ? '✓ ' : ''}{PRIORITY_LABELS[p] || p}
                </button>
              )
            })}
          </div>
        </div>

        {/* Assignee filter */}
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Assignee</p>
          <div className="flex flex-wrap gap-1.5">
            {['unassigned', ...new Set(tasks.map(t => t.assignedTo).filter(Boolean) as string[])].map(a => {
              const active = filterAssignees.has(a)
              return (
                <button key={a}
                  onClick={() => setFilterAssignees(toggleIn(filterAssignees, a))}
                  className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                    active
                      ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-white'
                      : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                  }`}
                >
                  {active ? '✓ ' : ''}{a === 'unassigned' ? 'Unassigned' : a}
                </button>
              )
            })}
          </div>
        </div>

        {/* Label filter */}
        {allLabels.length > 0 && (
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Labels</p>
            <div className="flex flex-wrap gap-1.5">
              {allLabels.map(lbl => {
                const active = filterLabels.has(lbl.id)
                return (
                  <button key={lbl.id}
                    onClick={() => setFilterLabels(toggleIn(filterLabels, lbl.id))}
                    className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border transition-colors ${
                      active
                        ? 'border-white/50 text-white'
                        : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                    }`}
                    style={active ? { backgroundColor: lbl.color + '30', borderColor: lbl.color + '60' } : {}}
                  >
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: lbl.color }} />
                    {active ? '✓ ' : ''}{lbl.name}
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* Clear filters */}
      {hasActive && (
        <div className="flex items-center justify-between pt-1 border-t border-[var(--color-border)]">
          <span className="text-xs text-[var(--color-muted)]">Active filters</span>
          <button
            onClick={() => { setFilterPriorities(new Set()); setFilterAssignees(new Set()); setFilterLabels(new Set()) }}
            className="text-xs px-2 py-1 rounded bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
          >Clear all filters</button>
        </div>
      )}
    </div>
  )
}
