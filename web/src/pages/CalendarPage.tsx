import { useState, useEffect, useMemo } from 'react'
import { api, type Task } from '../api'
import { CalendarDays, Loader2, AlertCircle, ChevronLeft, ChevronRight, Clock } from 'lucide-react'
import { PRIORITY_LABELS, PRIORITY_COLORS } from '../components/constants'

const STATUS_COLORS: Record<string, string> = {
  available: '#3b82f6',
  in_progress: '#22c55e',
  blocked: '#ef4444',
  done: '#8b5cf6',
}

const STATUS_BG: Record<string, string> = {
  available: 'bg-blue-500/20 text-blue-400',
  in_progress: 'bg-emerald-500/20 text-emerald-400',
  blocked: 'bg-red-500/20 text-red-400',
  done: 'bg-purple-500/20 text-purple-400',
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

export default function CalendarPage() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const result = await api.calendar.get(year, month)
        setTasks(result.tasks)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [year, month])

  const daysInMonth = new Date(year, month, 0).getDate()
  const firstDayOfWeek = new Date(year, month - 1, 1).getDay() // 0=Sun

  // Build day cells
  const cells = useMemo(() => {
    const result: { day: number; tasks: Task[] }[] = []
    // Empty cells before first day
    for (let i = 0; i < firstDayOfWeek; i++) {
      result.push({ day: 0, tasks: [] })
    }
    // Actual days
    for (let d = 1; d <= daysInMonth; d++) {
      const dateStart = new Date(year, month - 1, d).getTime()
      const dateEnd = dateStart + 86400000
      const dayTasks = tasks.filter(t => {
        const due = t.due_by || 0
        return due >= dateStart && due < dateEnd
      })
      result.push({ day: d, tasks: dayTasks })
    }
    return result
  }, [year, month, daysInMonth, firstDayOfWeek, tasks])

  const prevMonth = () => {
    if (month === 1) { setYear(y => y - 1); setMonth(12) }
    else setMonth(m => m - 1)
  }

  const nextMonth = () => {
    if (month === 12) { setYear(y => y + 1); setMonth(1) }
    else setMonth(m => m + 1)
  }

  const today = new Date()
  const isToday = (d: number) =>
    d === today.getDate() && month === today.getMonth() + 1 && year === today.getFullYear()

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8">
      <div className="flex items-center justify-between gap-3 mb-6">
        <div className="flex items-center gap-2">
          <CalendarDays className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">Calendar</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={prevMonth}
            className="p-1.5 rounded hover:bg-white/10 transition-colors text-[var(--color-muted)]"
          ><ChevronLeft className="w-4 h-4" /></button>
          <span className="text-sm font-medium min-w-[140px] text-center">
            {MONTH_NAMES[month - 1]} {year}
          </span>
          <button onClick={nextMonth}
            className="p-1.5 rounded hover:bg-white/10 transition-colors text-[var(--color-muted)]"
          ><ChevronRight className="w-4 h-4" /></button>
          <button onClick={() => { setYear(today.getFullYear()); setMonth(today.getMonth() + 1) }}
            className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/20 transition-colors ml-2"
          >Today</button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center gap-2 text-[var(--color-muted)] py-12">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading...
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      ) : (
        <>
          {/* Calendar grid */}
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden">
            {/* Day headers */}
            <div className="grid grid-cols-7 border-b border-[var(--color-border)]">
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
                <div key={d} className="text-center text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] py-2">
                  {d}
                </div>
              ))}
            </div>

            {/* Day cells */}
            <div className="grid grid-cols-7">
              {cells.map((cell, idx) => (
                <div key={idx}
                  className={`min-h-[80px] sm:min-h-[100px] border-b border-r border-[var(--color-border)] p-1 ${
                    cell.day === 0 ? 'bg-white/[0.02]' : 'hover:bg-white/[0.04] cursor-pointer'
                  } ${isToday(cell.day) ? 'bg-blue-500/5' : ''}`}
                  onClick={() => {
                    if (cell.day > 0 && cell.tasks.length > 0) {
                      setSelectedTask(cell.tasks[0])
                    }
                  }}
                >
                  {cell.day > 0 && (
                    <>
                      <span className={`inline-flex items-center justify-center w-5 h-5 text-[10px] rounded-full ${
                        isToday(cell.day) ? 'bg-blue-500 text-white font-bold' : 'text-[var(--color-muted)]'
                      }`}>
                        {cell.day}
                      </span>
                      <div className="space-y-0.5 mt-0.5">
                        {cell.tasks.slice(0, 3).map(t => (
                          <div key={t.id}
                            className="text-[8px] sm:text-[9px] px-1 py-0.5 rounded truncate cursor-pointer hover:opacity-80"
                            style={{
                              backgroundColor: (STATUS_COLORS[t.status] || '#666') + '30',
                              borderLeft: `2px solid ${STATUS_COLORS[t.status] || '#666'}`,
                            }}
                            title={t.title}
                            onClick={(e) => { e.stopPropagation(); setSelectedTask(t) }}
                          >
                            {t.title}
                          </div>
                        ))}
                        {cell.tasks.length > 3 && (
                          <div className="text-[8px] text-[var(--color-muted)] pl-1">
                            +{cell.tasks.length - 3} more
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div className="flex items-center gap-4 mt-3 text-[11px] text-[var(--color-muted)]">
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: STATUS_COLORS.available }} />
              Available
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: STATUS_COLORS.in_progress }} />
              In Progress
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: STATUS_COLORS.blocked }} />
              Blocked
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded" style={{ backgroundColor: STATUS_COLORS.done }} />
              Done
            </span>
          </div>

          {/* Task detail panel */}
          {selectedTask && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setSelectedTask(null)}>
              <div className="bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 max-w-md w-full mx-4" onClick={e => e.stopPropagation()}>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS[selectedTask.priority] || ''}`}>
                      {PRIORITY_LABELS[selectedTask.priority] || selectedTask.priority}
                    </span>
                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${STATUS_BG[selectedTask.status] || ''}`}>
                      {selectedTask.status.replace('_', ' ')}
                    </span>
                    {selectedTask.repo && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)]">{selectedTask.repo}</span>
                    )}
                  </div>
                  <button onClick={() => setSelectedTask(null)} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
                    ✕
                  </button>
                </div>
                <h3 className="text-sm font-semibold mb-2">{selectedTask.title}</h3>
                {selectedTask.description && (
                  <p className="text-xs text-[var(--color-muted-foreground)] mb-3">{selectedTask.description}</p>
                )}
                {selectedTask.due_by && (
                  <div className="flex items-center gap-1 text-xs text-[var(--color-muted)] mb-2">
                    <Clock className="w-3 h-3" />
                    Due: {new Date(selectedTask.due_by).toLocaleDateString()}
                    {Date.now() > selectedTask.due_by && selectedTask.status !== 'done' && (
                      <span className="text-red-400 font-medium"> (Overdue)</span>
                    )}
                  </div>
                )}
                <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                  <span>ID: <code className="text-[10px] font-mono">{selectedTask.id.slice(0, 20)}...</code></span>
                  {selectedTask.assigned_to && <span>· Agent: {selectedTask.assigned_to}</span>}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
