import { useEffect, useState, useCallback } from 'react'
import {
  Loader2, AlertCircle, Search, X, ChevronDown, Clock, Activity, Users, Filter, Check,
  PlusCircle, User, Undo2, CheckCircle2, Ban, Link2, Wrench, Bot, RefreshCw, ClipboardList,
} from 'lucide-react'
import { api, LogEntry, LogStats } from '../api'
import { ListViewSkeleton } from '../components/Skeleton'

const ACTION_ICONS: Record<string, React.ReactNode> = {
  created: <PlusCircle className="w-3.5 h-3.5" aria-hidden="true" />,
  claimed: <User className="w-3.5 h-3.5" aria-hidden="true" />,
  unclaimed: <Undo2 className="w-3.5 h-3.5" aria-hidden="true" />,
  completed: <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />,
  blocked: <Ban className="w-3.5 h-3.5" aria-hidden="true" />,
  dependency_set: <Link2 className="w-3.5 h-3.5" aria-hidden="true" />,
  skills_set: <Wrench className="w-3.5 h-3.5" aria-hidden="true" />,
  agent_registered: <Bot className="w-3.5 h-3.5" aria-hidden="true" />,
  agent_reconnected: <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />,
}

const ACTION_COLORS: Record<string, string> = {
  created: 'text-blue-400 bg-blue-500/10',
  claimed: 'text-green-400 bg-green-500/10',
  unclaimed: 'text-yellow-400 bg-yellow-500/10',
  completed: 'text-emerald-400 bg-emerald-500/10',
  blocked: 'text-red-400 bg-red-500/10',
  dependency_set: 'text-amber-400 bg-amber-500/10',
  skills_set: 'text-cyan-400 bg-cyan-500/10',
  agent_registered: 'text-purple-400 bg-purple-500/10',
  agent_reconnected: 'text-purple-400 bg-purple-500/10',
}

const ACTION_OPTIONS = [
  'created', 'claimed', 'unclaimed', 'completed', 'blocked',
  'dependency_set', 'skills_set', 'agent_registered', 'agent_reconnected',
]

const DATE_RANGES = [
  { label: '24h', ms: 86_400_000 },
  { label: '7d', ms: 7 * 86_400_000 },
  { label: '30d', ms: 30 * 86_400_000 },
  { label: 'All', ms: 0 },
]

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(ts).toLocaleDateString()
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)

  // Filters
  const [selectedActions, setSelectedActions] = useState<Set<string>>(new Set())
  const [agentFilter, setAgentFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [dateRange, setDateRange] = useState(0) // ms, 0 = all
  const [showActionDropdown, setShowActionDropdown] = useState(false)
  const [highlightedEvent, setHighlightedEvent] = useState<string | null>(null)

  const buildParams = useCallback((offset = 0) => {
    const params: Record<string, string | number | undefined> = { limit: 50, offset }
    if (selectedActions.size > 0) params.action = [...selectedActions].join(',')
    if (agentFilter) params.agent_id = agentFilter
    if (searchQuery) params.search = searchQuery
    if (dateRange > 0) params.since = Date.now() - dateRange
    return params
  }, [selectedActions, agentFilter, searchQuery, dateRange])

  const load = useCallback(async () => {
    try {
      setError(null)
      const [data, statsData] = await Promise.all([
        api.logs.list(buildParams(0)),
        api.logs.stats(),
      ])
      setLogs(data)
      setStats(statsData)
      setHasMore(data.length === 50)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [buildParams])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  const loadMore = async () => {
    setLoadingMore(true)
    try {
      const data = await api.logs.list(buildParams(logs.length))
      setLogs(prev => [...prev, ...data])
      setHasMore(data.length === 50)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingMore(false)
    }
  }

  const clearFilters = () => {
    setSelectedActions(new Set())
    setAgentFilter('')
    setSearchQuery('')
    setDateRange(0)
  }

  const hasActiveFilters = selectedActions.size > 0 || agentFilter || searchQuery || dateRange > 0

  // Extract unique agents from loaded logs for the dropdown
  const allAgents = [...new Set(logs.map(l => l.agent_id).filter(Boolean) as string[])].sort()

  return (
    <div className="p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Activity className="w-5 h-5 text-[var(--color-primary)]" /> Activity Log
        </h1>
        <p className="text-sm text-[var(--color-muted-foreground)]">
          Track every claim, completion, and state change
        </p>
      </div>

      {/* Stats Bar */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Clock className="w-3 h-3" /> Total Events
            </p>
            <p className="text-2xl font-semibold mt-1">{stats.total_events}</p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Today</p>
            <p className="text-2xl font-semibold mt-1">{stats.today_events}</p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Users className="w-3 h-3" /> Active Agents
            </p>
            <p className="text-2xl font-semibold mt-1">{stats.active_agents_today}</p>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Top Action</p>
            <p className="text-2xl font-semibold mt-1 capitalize">
              {Object.entries(stats.action_breakdown).sort((a, b) => b[1] - a[1])[0]?.[0]?.replace(/_/g, ' ') || '—'}
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Action type filter */}
          <div className="relative">
            <button onClick={() => setShowActionDropdown(!showActionDropdown)}
              className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
                selectedActions.size > 0
                  ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)] border border-[var(--color-primary)]/30'
                  : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 border border-transparent'
              }`}
            >
              <Filter className="w-3 h-3" />
              {selectedActions.size > 0 ? `${selectedActions.size} action(s)` : 'Actions'}
              <ChevronDown className="w-3 h-3" />
            </button>
            {showActionDropdown && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowActionDropdown(false)} />
                <div className="absolute left-0 top-full mt-1 w-48 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-xl z-20 py-1 max-h-60 overflow-y-auto">
                  {ACTION_OPTIONS.map(a => (
                    <button key={a} onClick={() => {
                      setSelectedActions(prev => {
                        const next = new Set(prev)
                        if (next.has(a)) next.delete(a); else next.add(a)
                        return next
                      })
                    }}
                      className={`w-full text-left text-xs px-3 py-1.5 hover:bg-white/5 transition-colors flex items-center gap-2 ${
                        selectedActions.has(a) ? 'text-white' : 'text-[var(--color-muted-foreground)]'
                      }`}
                    >
                      <span aria-hidden="true" className="text-sm">{ACTION_ICONS[a] || <ClipboardList className="w-3.5 h-3.5 inline" />}</span>
                      <span className="capitalize">{a.replace(/_/g, ' ')}</span>
                      {selectedActions.has(a) && <Check className="w-3 h-3 ml-auto text-[var(--color-primary)]" />}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* Agent filter */}
          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}
            className="text-xs px-2 py-1.5 rounded bg-white/5 border border-[var(--color-border)] text-[var(--color-muted-foreground)] appearance-none cursor-pointer"
          >
            <option value="">All agents</option>
            {allAgents.map(a => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>

          {/* Search */}
          <div className="relative flex-1 min-w-[120px] max-w-[240px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--color-muted)] pointer-events-none" />
            <input value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search logs..."
              className="w-full pl-7 pr-2 py-1.5 text-xs rounded bg-white/5 border border-[var(--color-border)] text-[var(--color-muted-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
          </div>

          {/* Date range */}
          <div className="flex gap-1">
            {DATE_RANGES.map(r => (
              <button key={r.label} onClick={() => setDateRange(r.ms)}
                className={`text-xs px-2 py-1.5 rounded transition-colors ${
                  dateRange === r.ms
                    ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]'
                    : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
                }`}
              >{r.label}</button>
            ))}
          </div>

          {/* Clear filters */}
          {hasActiveFilters && (
            <button onClick={clearFilters}
              className="flex items-center gap-1 text-xs px-2 py-1.5 rounded bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
            ><X className="w-3 h-3" /> Clear</button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20" role="alert">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Log timeline */}
      {loading ? <ListViewSkeleton /> : logs.length === 0 ? (
        <div className="text-center py-12 text-sm text-[var(--color-muted)]">
          {hasActiveFilters ? 'No logs match your filters.' : 'No activity yet. Create or claim a task to see logs.'}
        </div>
      ) : (
        <div className="space-y-1">
          {logs.map((log) => {
            const actionColor = ACTION_COLORS[log.action] || 'text-[var(--color-muted-foreground)] bg-white/[0.02]'
            const isHighlighted = highlightedEvent === log.id
            return (
              <div key={log.id}
                onClick={() => setHighlightedEvent(isHighlighted ? null : log.id)}
                className={`flex items-start gap-3 px-4 py-2.5 rounded-lg transition-colors cursor-pointer ${
                  isHighlighted ? 'bg-white/[0.04] ring-1 ring-[var(--color-ring)]' : 'hover:bg-white/[0.02]'
                }`}
              >
                <span aria-hidden="true" className="text-lg shrink-0 mt-0.5">{ACTION_ICONS[log.action] || <ClipboardList className="w-4 h-4 inline" />}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${actionColor}`}>
                      {log.action.replace(/_/g, ' ')}
                    </span>
                    <code className="text-[10px] font-mono text-[var(--color-muted)]"
                      title={log.task_id}
                    >{log.task_id.slice(-12)}</code>
                    {log.agent_id && (
                      <span className="text-xs text-[var(--color-muted)]">
                        by <strong>{log.agent_id}</strong>
                      </span>
                    )}
                  </div>
                  {log.notes && (
                    <p className="text-xs text-[var(--color-muted-foreground)] mt-1 line-clamp-2">{log.notes}</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-0.5 shrink-0">
                  <span className="text-[10px] font-mono text-[var(--color-muted)]"
                    title={new Date(log.timestamp).toLocaleString()}
                  >{relativeTime(log.timestamp)}</span>
                  <span className="text-[9px] text-[var(--color-muted)]/60 font-mono">
                    {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              </div>
            )
          })}

          {/* Load more */}
          {hasMore && (
            <div className="flex justify-center pt-4">
              <button onClick={loadMore} disabled={loadingMore}
                className="flex items-center gap-1 text-xs px-4 py-2 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors disabled:opacity-50"
              >
                {loadingMore ? <Loader2 className="w-3 h-3 animate-spin" /> : <ChevronDown className="w-3 h-3" />}
                {loadingMore ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}

          {/* Count summary */}
          <div className="text-center text-[10px] text-[var(--color-muted)] pt-1">
            Showing {logs.length} of {stats?.total_events || logs.length} events
          </div>
        </div>
      )}

      {/* Action breakdown */}
      {stats && Object.keys(stats.action_breakdown).length > 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2">Event Distribution</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.action_breakdown)
              .sort((a, b) => b[1] - a[1])
              .map(([action, count]) => {
                const pct = Math.round((count / stats.total_events) * 100)
                const colorClass = ACTION_COLORS[action] || 'text-white bg-white/5'
                return (
                  <div key={action}
                    className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded ${colorClass}`}
                    onClick={() => {
                      setSelectedActions(prev => {
                        const next = new Set(prev)
                        if (next.has(action)) next.delete(action); else next.add(action)
                        return next
                      })
                    }}
                  >
                    <span aria-hidden="true" className="text-sm">{ACTION_ICONS[action] || <ClipboardList className="w-3.5 h-3.5 inline" />}</span>
                    <span className="capitalize">{action.replace(/_/g, ' ')}</span>
                    <span className="font-semibold">{count}</span>
                    <span className="opacity-60">({pct}%)</span>
                  </div>
                )
              })}
          </div>
        </div>
      )}
    </div>
  )
}
