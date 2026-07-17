import { useEffect, useState } from 'react'
import { api, type AgentHealth } from '../api'
import { useNavigate } from 'react-router-dom'
import {
  Activity, Cpu, Loader2, AlertCircle, Wifi, WifiOff,
  Clock, Circle, CheckCircle2, ExternalLink, RefreshCw
} from 'lucide-react'

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  online: { color: '#22c55e', label: 'Online' },
  busy: { color: '#f59e0b', label: 'Busy' },
  idle: { color: '#3b82f6', label: 'Idle' },
  offline: { color: '#64748b', label: 'Offline' },
}

const TASK_STATUS_COLORS: Record<string, string> = {
  available: '#3b82f6',
  in_progress: '#22c55e',
  blocked: '#ef4444',
  done: '#8b5cf6',
}

function formatDuration(seconds: number): string {
  if (seconds < 0) return 'never'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m ago`
}

export default function AgentHealthPage() {
  const navigate = useNavigate()
  const [agents, setAgents] = useState<AgentHealth[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [refreshing, setRefreshing] = useState(false)

  const load = async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const data = await api.agents.health()
      setAgents(data)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
    const interval = setInterval(() => {
      if (document.hidden) return
      load(true)
    }, 15000)
    const onVis = () => { if (document.hidden) clearInterval(interval) }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    load(true)
  }

  const onlineCount = agents.filter(a => a.status === 'online' || a.status === 'busy').length
  const staleCount = agents.filter(a => a.stale).length
  const workingCount = agents.filter(a => a.current_task).length

  if (loading) return (
    <div className="p-8 flex items-center justify-center gap-2 text-[var(--color-muted)]">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading agents...
    </div>
  )

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">Agents</h1>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--color-border)] hover:bg-white/5 transition-colors disabled:opacity-40"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* Stat bar */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 text-center">
          <div className="flex items-center justify-center gap-1.5 text-2xl font-bold">
            <Wifi className="w-4 h-4 text-green-400" />
            {onlineCount}
          </div>
          <div className="text-[10px] text-[var(--color-muted)] uppercase tracking-wider mt-0.5">Online</div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 text-center">
          <div className="flex items-center justify-center gap-1.5 text-2xl font-bold">
            <Clock className="w-4 h-4 text-amber-400" />
            {workingCount}
          </div>
          <div className="text-[10px] text-[var(--color-muted)] uppercase tracking-wider mt-0.5">Working</div>
        </div>
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 text-center">
          <div className="flex items-center justify-center gap-1.5 text-2xl font-bold">
            <WifiOff className={`w-4 h-4 ${staleCount > 0 ? 'text-red-400' : 'text-green-400'}`} />
            {staleCount}
          </div>
          <div className="text-[10px] text-[var(--color-muted)] uppercase tracking-wider mt-0.5">Stale</div>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {/* Agent cards grid */}
      {agents.length === 0 && !error ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-8 text-center space-y-2">
          <Cpu className="w-8 h-8 mx-auto text-[var(--color-muted)]" />
          <p className="text-sm text-[var(--color-muted)]">No agents registered.</p>
          <p className="text-xs text-[var(--color-muted)]">
            Agents appear here when they send their first heartbeat to the kanban swarm.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {agents.map(agent => {
            const statusCfg = STATUS_CONFIG[agent.status] || STATUS_CONFIG.offline
            const ageDisplay = formatDuration(agent.heartbeat_age_seconds)

            return (
              <div
                key={agent.id}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3"
              >
                {/* Agent header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Circle
                        className="w-2.5 h-2.5 flex-shrink-0"
                        fill={statusCfg.color}
                        color={statusCfg.color}
                        style={{ opacity: agent.stale ? 0.35 : 1 }}
                      />
                      <span className="text-sm font-semibold truncate">{agent.id}</span>
                      <span
                        className={`text-[10px] px-1.5 py-0.25 rounded-full ${
                          agent.stale ? 'bg-amber-500/15 text-amber-400' :
                          agent.status === 'busy' ? 'bg-orange-500/15 text-orange-400' :
                          'bg-emerald-500/15 text-emerald-400'
                        }`}
                      >
                        {agent.stale ? 'Stale' : statusCfg.label}
                      </span>
                    </div>
                    {agent.host && (
                      <p className="text-xs text-[var(--color-muted)] mt-0.5 truncate">{agent.host}</p>
                    )}
                  </div>
                  {agent.current_task && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                      style={{
                        backgroundColor: `${TASK_STATUS_COLORS[agent.current_task.status] || '#666'}20`,
                        color: TASK_STATUS_COLORS[agent.current_task.status] || '#666',
                      }}
                    >
                      Working
                    </span>
                  )}
                </div>

                {/* Capabilities */}
                {agent.capabilities && (
                  <div className="flex flex-wrap gap-1">
                    {agent.capabilities.split(',').map((c, i) => (
                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400/80">
                        {c.trim()}
                      </span>
                    ))}
                  </div>
                )}

                {/* Current task */}
                {agent.current_task ? (
                  <div
                    className="rounded bg-white/[0.04] p-2 space-y-1 cursor-pointer hover:bg-white/[0.07] transition-colors"
                    onClick={() => navigate('/')}
                    title="View on board"
                  >
                    <div className="flex items-center gap-1.5 text-xs">
                      <CheckCircle2 className="w-3 h-3 text-green-400 flex-shrink-0" />
                      <span className="font-medium truncate">{agent.current_task.title}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[10px] text-[var(--color-muted)]">
                      <span>{agent.current_task.repo || '—'}</span>
                      <span className="capitalize">{agent.current_task.status.replace('_', ' ')}</span>
                      <ExternalLink className="w-2.5 h-2.5 ml-auto" />
                    </div>
                  </div>
                ) : (
                  <div className="text-[11px] text-[var(--color-muted)] italic">
                    No current task
                  </div>
                )}

                {/* Heartbeat info */}
                <div className="flex items-center justify-between text-[10px] text-[var(--color-muted)] pt-1 border-t border-[var(--color-border)]">
                  <span className="flex items-center gap-1" title={`Last heartbeat: ${new Date(agent.last_heartbeat).toLocaleString()}`}>
                    <Clock className="w-3 h-3" />
                    {ageDisplay}
                  </span>
                  <span>
                    Seen {new Date(agent.first_seen).toLocaleDateString()}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Auto-refresh note */}
      <p className="text-[10px] text-[var(--color-muted)] text-center">
        Auto-refreshes every 15 seconds
      </p>
    </div>
  )
}
