import { useEffect, useMemo, useState } from 'react'
import {
  RefreshCw, RotateCcw, Archive, ChevronDown, ChevronRight,
  AlertTriangle, CheckCircle2,
} from 'lucide-react'
import { api, type Task } from '../api'

/** Normalize a fail_reason into a cluster key by stripping volatile counters/ids. */
function clusterKey(reason: string | null | undefined): string {
  if (!reason) return 'No reason recorded'
  return reason
    .replace(/\(\d+\/\d+\)/g, '(n/m)') // (4/3) attempt counters
    .replace(/cycled \d+x/g, 'cycled Nx') // cycle counters
    .replace(/task_[a-f0-9]+/gi, 'task_…') // task ids
    .replace(/^Split into \d+ subtask\(s\):.*$/i, 'Split into subtasks (parent closed)') // split parents
    .trim()
}

function ageLabel(ms: number): string {
  const h = Math.floor(ms / 3600000)
  if (h < 1) return `${Math.floor(ms / 60000)}m`
  if (h < 48) return `${h}h`
  return `${Math.floor(h / 24)}d`
}

interface Cluster {
  key: string
  tasks: Task[]
  repos: Record<string, number>
  oldest: number // ms age of oldest block
}

export default function TriagePage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<string | null>(null) // cluster key or task id in flight
  const [notice, setNotice] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const blocked = await api.tasks.list({ status: 'blocked' })
      setTasks(blocked.filter(t => !t.archived))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const clusters = useMemo<Cluster[]>(() => {
    const map = new Map<string, Task[]>()
    for (const t of tasks) {
      const key = clusterKey(t.fail_reason)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(t)
    }
    const now = Date.now()
    return [...map.entries()]
      .map(([key, ts]) => {
        const repos: Record<string, number> = {}
        let oldest = 0
        for (const t of ts) {
          if (t.repo) repos[t.repo] = (repos[t.repo] || 0) + 1
          oldest = Math.max(oldest, now - (t.updated_at || t.created_at))
        }
        // Sort tasks inside a cluster: highest fail_count first
        ts.sort((a, b) => (b.fail_count ?? 0) - (a.fail_count ?? 0))
        return { key, tasks: ts, repos, oldest }
      })
      .sort((a, b) => b.tasks.length - a.tasks.length)
  }, [tasks])

  const retryTasks = async (ids: string[], label: string) => {
    if (!confirm(`Retry ${ids.length} task(s) from "${label}"?\n\nThey will return to Available with fail counts reset.`)) return
    setBusy(label)
    setNotice(null)
    try {
      const res = await api.tasks.bulkRetry(ids, true)
      setNotice(`✅ Retried ${res.retried} task(s)${res.failed.length ? ` — ${res.failed.length} failed` : ''}`)
      await load()
    } catch (e: unknown) {
      setNotice(`❌ Retry failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(null)
    }
  }

  const archiveTasks = async (ids: string[], label: string) => {
    if (!confirm(`Archive ${ids.length} task(s) from "${label}"?\n\nArchived tasks disappear from the board.`)) return
    setBusy(label)
    setNotice(null)
    try {
      const res = await api.tasks.bulkArchive(ids)
      setNotice(`✅ Archived ${res.archived} task(s)${res.failed.length ? ` — ${res.failed.length} failed` : ''}`)
      await load()
    } catch (e: unknown) {
      setNotice(`❌ Archive failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy(null)
    }
  }

  const toggleExpanded = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const now = Date.now()

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            Blocked Triage
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-white/5 text-[var(--color-muted)] font-normal">
              {tasks.length}
            </span>
          </h1>
          <p className="text-xs text-[var(--color-muted)] mt-1">
            Blocked tasks grouped by failure reason. Retry sends them back to Available with fail counts reset; archive removes them from the board.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {notice && (
        <div className="text-sm p-3 rounded-lg bg-white/5 border border-[var(--color-border)] flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 flex-shrink-0" /> {notice}
        </div>
      )}

      {error && (
        <div className="text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          Failed to load blocked tasks: {error}
        </div>
      )}

      {!loading && tasks.length === 0 && !error && (
        <div className="text-sm p-6 text-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          🎉 No blocked tasks — the board is clean.
        </div>
      )}

      {/* Clusters */}
      <div className="space-y-3">
        {clusters.map(cluster => {
          const isOpen = expanded.has(cluster.key)
          const ids = cluster.tasks.map(t => t.id)
          const isBusy = busy === cluster.key
          return (
            <div key={cluster.key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden">
              {/* Cluster header */}
              <div className="flex items-center gap-3 p-3">
                <button onClick={() => toggleExpanded(cluster.key)} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors">
                  {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{cluster.key}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-400 font-medium">
                      {cluster.tasks.length}
                    </span>
                    <span className="text-[10px] text-[var(--color-muted)]">oldest: {ageLabel(cluster.oldest)}</span>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                    {Object.entries(cluster.repos).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([repo, n]) => (
                      <span key={repo} className="text-[10px] px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)]">
                        {repo} ×{n}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => retryTasks(ids, cluster.key)}
                    disabled={isBusy}
                    className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-40"
                  >
                    <RotateCcw className="w-3 h-3" /> Retry all
                  </button>
                  <button
                    onClick={() => archiveTasks(ids, cluster.key)}
                    disabled={isBusy}
                    className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors disabled:opacity-40"
                  >
                    <Archive className="w-3 h-3" /> Archive all
                  </button>
                </div>
              </div>

              {/* Expanded task list */}
              {isOpen && (
                <div className="border-t border-[var(--color-border)] divide-y divide-[var(--color-border)]/50">
                  {cluster.tasks.map(t => (
                    <div key={t.id} className="flex items-center gap-3 px-3 py-2 pl-10 hover:bg-white/[0.03] transition-colors">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm truncate">{t.title}</p>
                        <p className="text-[10px] text-[var(--color-muted)]">
                          {t.repo || 'no-repo'} · fails: {t.fail_count ?? 0}/{t.max_attempts ?? 3} · blocked {ageLabel(now - (t.updated_at || t.created_at))} ago · {t.id.slice(0, 18)}…
                        </p>
                      </div>
                      <button
                        onClick={() => retryTasks([t.id], t.title.slice(0, 40))}
                        disabled={busy !== null}
                        className="text-xs px-2 py-1 rounded bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors disabled:opacity-40"
                      >Retry</button>
                      <button
                        onClick={() => archiveTasks([t.id], t.title.slice(0, 40))}
                        disabled={busy !== null}
                        className="text-xs px-2 py-1 rounded bg-white/5 text-[var(--color-muted)] hover:bg-white/10 transition-colors disabled:opacity-40"
                      >Archive</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
