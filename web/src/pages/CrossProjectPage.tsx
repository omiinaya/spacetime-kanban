import { useEffect, useState } from 'react'
import { api } from '../api'
import { LayoutDashboard, Loader2, AlertCircle, Layers, CheckCircle2, Clock, Ban, Archive } from 'lucide-react'
import { PRIORITY_LABELS, PRIORITY_COLORS } from '../components/constants'

const STATUS_COLORS: Record<string, string> = {
  available: '#3b82f6',
  in_progress: '#22c55e',
  blocked: '#ef4444',
  done: '#8b5cf6',
}

interface CrossProjectData {
  project: any
  total: number
  by_status: Record<string, number>
  by_priority: Record<string, number>
  sprints: string[]
}

export default function CrossProjectPage() {
  const [data, setData] = useState<Record<string, CrossProjectData> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const result = await api.crossProject.get()
        setData(result)
      } catch (e: any) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  if (loading) return (
    <div className="p-8 flex items-center justify-center gap-2 text-[var(--color-muted)]">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading cross-project data...
    </div>
  )

  if (error) return (
    <div className="p-8">
      <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
        <AlertCircle className="w-4 h-4" /> Error: {error}
      </div>
    </div>
  )

  if (!data) return null

  const entries = Object.entries(data).sort(([, a], [, b]) => b.total - a.total)
  const totalTasks = entries.reduce((sum, [, d]) => sum + d.total, 0)

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      <div className="flex items-center gap-2 mb-2">
        <LayoutDashboard className="w-5 h-5 text-[var(--color-primary)]" />
        <h1 className="text-lg sm:text-xl font-semibold">Cross-Project Dashboard</h1>
        <span className="text-xs text-[var(--color-muted)] ml-auto">{totalTasks} total tasks across {entries.length} repos</span>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Layers className="w-4 h-4 text-blue-400" />
            <span className="text-xs text-[var(--color-muted)]">Total Repos</span>
          </div>
          <div className="text-2xl font-bold">{entries.length}</div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle2 className="w-4 h-4 text-purple-400" />
            <span className="text-xs text-[var(--color-muted)]">Total Tasks</span>
          </div>
          <div className="text-2xl font-bold">{totalTasks}</div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-green-400" />
            <span className="text-xs text-[var(--color-muted)]">In Progress</span>
          </div>
          <div className="text-2xl font-bold">
            {entries.reduce((sum, [, d]) => sum + (d.by_status.in_progress || 0), 0)}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
          <div className="flex items-center gap-2 mb-2">
            <Ban className="w-4 h-4 text-red-400" />
            <span className="text-xs text-[var(--color-muted)]">Blocked</span>
          </div>
          <div className="text-2xl font-bold">
            {entries.reduce((sum, [, d]) => sum + (d.by_status.blocked || 0), 0)}
          </div>
        </div>
      </div>

      {/* Per-repo tiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {entries.map(([repo, repoData]) => {
          const projectColor = repoData.project?.color || '#6b7280'
          const maxStatus = Math.max(...Object.values(repoData.by_status), 1)

          return (
            <div key={repo}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden hover:border-white/20 transition-colors"
            >
              {/* Header */}
              <div className="px-4 py-3 border-b border-[var(--color-border)] flex items-center gap-2"
                style={{ borderLeftColor: projectColor, borderLeftWidth: 3 }}
              >
                <Archive className="w-4 h-4" style={{ color: projectColor }} />
                <span className="font-medium text-sm">{repoData.project?.name || repo}</span>
                <span className="text-xs text-[var(--color-muted)] ml-auto">{repoData.total} tasks</span>
              </div>

              <div className="p-4 space-y-4">
                {/* Status bars */}
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2">By Status</p>
                  <div className="space-y-1.5">
                    {Object.entries(repoData.by_status)
                      .sort(([, a], [, b]) => b - a)
                      .map(([status, count]) => {
                        const pct = (count / maxStatus) * 100
                        return (
                          <div key={status} className="flex items-center gap-2">
                            <span className="text-[10px] w-20 text-[var(--color-muted)] capitalize truncate">
                              {status.replace('_', ' ')}
                            </span>
                            <div className="flex-1 h-2 rounded-full bg-white/5 overflow-hidden">
                              <div className="h-full rounded-full transition-all"
                                style={{ width: `${pct}%`, backgroundColor: STATUS_COLORS[status] || '#666' }}
                              />
                            </div>
                            <span className="text-[10px] font-medium w-6 text-right">{count}</span>
                          </div>
                        )
                      })}
                  </div>
                </div>

                {/* Priority distribution */}
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2">By Priority</p>
                  <div className="flex flex-wrap gap-1.5">
                    {[0, 1, 2, 3].map(p => {
                      const count = repoData.by_priority[p] || 0
                      if (count === 0) return null
                      return (
                        <span key={p} className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${PRIORITY_COLORS[p] || ''}`}>
                          {PRIORITY_LABELS[p] || p}: {count}
                        </span>
                      )
                    })}
                  </div>
                </div>

                {/* Sprints */}
                {repoData.sprints.length > 0 && (
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2">Sprints</p>
                    <div className="flex flex-wrap gap-1">
                      {repoData.sprints.map(s => (
                        <span key={s} className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400">
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {entries.length === 0 && (
        <div className="text-center py-12 text-[var(--color-muted)]">
          <Layers className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No tasks or projects yet.</p>
        </div>
      )}
    </div>
  )
}
