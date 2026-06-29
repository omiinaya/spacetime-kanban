import { useEffect, useState } from 'react'
import { api } from '../api'
import { BarChart3, CheckCircle2, Clock, Users, AlertCircle, Layers, Loader2 } from 'lucide-react'

interface Overview {
  total: number
  by_status: Record<string, number>
  completed_today: number
  completed_week: number
  total_done: number
  repos: Record<string, { total: number; done: number; in_progress: number; blocked: number; available: number }>
  agent_count: number
}

interface ThroughputPoint { date: string; completed: number }
interface CycleTime { repo: string; count: number; avg_hours: number; min_hours: number; max_hours: number }
interface AgentStat { id: string; status: string; completed: number; blocked: number; capabilities: string | null; repo_focus: string | null; last_heartbeat: number }

const STATUS_COLORS: Record<string, string> = {
  available: '#3b82f6',
  in_progress: '#22c55e',
  blocked: '#ef4444',
  done: '#8b5cf6',
}

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<Overview | null>(null)
  const [throughput, setThroughput] = useState<ThroughputPoint[]>([])
  const [cycleTimes, setCycleTimes] = useState<CycleTime[]>([])
  const [agentStats, setAgentStats] = useState<AgentStat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const [ov, tp, ct, as] = await Promise.all([
          api.analytics.overview(),
          api.analytics.throughput(14),
          api.analytics.cycleTimes(),
          api.analytics.agents(),
        ])
        setOverview(ov)
        setThroughput(tp)
        setCycleTimes(ct)
        setAgentStats(as)
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
      <Loader2 className="w-4 h-4 animate-spin" /> Loading analytics...
    </div>
  )

  if (error) return (
    <div className="p-8">
      <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
        <AlertCircle className="w-4 h-4" /> Analytics error: {error}
      </div>
    </div>
  )

  if (!overview) return null

  const maxThroughput = Math.max(...throughput.map(p => p.completed), 1)

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      <div className="flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-[var(--color-primary)]" />
        <h1 className="text-lg sm:text-xl font-semibold">Analytics</h1>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={Layers} label="Total Tasks" value={overview.total} color="#3b82f6" />
        <StatCard icon={CheckCircle2} label="Completed" value={overview.total_done} sub={`${overview.completed_today} today · ${overview.completed_week} this week`} color="#8b5cf6" />
        <StatCard icon={Clock} label="Available" value={overview.by_status.available || 0} color="#22c55e" />
        <StatCard icon={Users} label="Agents" value={overview.agent_count} color="#f59e0b" />
      </div>

      {/* Status breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Status distribution */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Status Distribution</h3>
          <div className="space-y-2">
            {Object.entries(overview.by_status).map(([status, count]) => {
              const pct = overview.total > 0 ? (count / overview.total) * 100 : 0
              return (
                <div key={status}>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-[var(--color-muted-foreground)] capitalize">{status.replace('_', ' ')}</span>
                    <span className="font-medium">{count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: STATUS_COLORS[status] || '#666' }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Repo breakdown */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">By Repository</h3>
          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {Object.entries(overview.repos).sort(([,a], [,b]) => b.total - a.total).map(([repo, stats]) => (
              <div key={repo} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-[var(--color-muted-foreground)] truncate max-w-[120px]" title={repo}>{repo}</span>
                  <span className="font-medium">{stats.total} tasks</span>
                </div>
                <div className="flex gap-0.5 h-2 rounded-full overflow-hidden">
                  {stats.available > 0 && <div style={{ width: `${(stats.available/stats.total)*100}%`, backgroundColor: '#3b82f6' }} />}
                  {stats.in_progress > 0 && <div style={{ width: `${(stats.in_progress/stats.total)*100}%`, backgroundColor: '#22c55e' }} />}
                  {stats.blocked > 0 && <div style={{ width: `${(stats.blocked/stats.total)*100}%`, backgroundColor: '#ef4444' }} />}
                  {stats.done > 0 && <div style={{ width: `${(stats.done/stats.total)*100}%`, backgroundColor: '#8b5cf6' }} />}
                </div>
                <div className="flex gap-2 text-[10px] text-[var(--color-muted)]">
                  <span className="text-blue-400">{stats.available} avail</span>
                  <span className="text-green-400">{stats.in_progress} prog</span>
                  <span className="text-red-400">{stats.blocked} blkd</span>
                  <span className="text-purple-400">{stats.done} done</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Throughput bar chart */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Throughput (last 14 days)</h3>
        {throughput.length === 0 ? (
          <p className="text-xs text-[var(--color-muted)]">No completion data yet.</p>
        ) : (
          <div className="flex items-end gap-1 h-24">
            {throughput.map((p, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div
                  className="w-full rounded-t transition-all hover:opacity-80 cursor-pointer"
                  style={{
                    height: `${Math.max((p.completed / maxThroughput) * 100, p.completed > 0 ? 8 : 2)}%`,
                    backgroundColor: p.completed > 0 ? '#8b5cf6' : '#ffffff08',
                    minHeight: p.completed > 0 ? 8 : 2,
                  }}
                  title={`${p.date}: ${p.completed} completed`}
                />
                <span className="text-[9px] text-[var(--color-muted)] -rotate-45 origin-left whitespace-nowrap">
                  {p.date === 'today' ? 'now' : p.date.replace('d ago', 'd')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Cycle times + Agent stats */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Cycle times */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Cycle Times (by repo)</h3>
          {cycleTimes.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No completed tasks yet to measure cycle time.</p>
          ) : (
            <div className="space-y-2">
              {cycleTimes.map(ct => (
                <div key={ct.repo} className="text-xs space-y-1">
                  <div className="flex justify-between">
                    <span className="text-[var(--color-muted-foreground)]">{ct.repo}</span>
                    <span className="font-medium">{ct.avg_hours}h avg</span>
                  </div>
                  <div className="flex gap-2 text-[10px] text-[var(--color-muted)]">
                    <span>min: {ct.min_hours}h</span>
                    <span>max: {ct.max_hours}h</span>
                    <span>{ct.count} tasks</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                    <div className="h-full rounded-full bg-purple-500" style={{ width: `${Math.min((ct.avg_hours / 72) * 100, 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Agent stats */}
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Agent Performance</h3>
          {agentStats.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No agents registered in the swarm.</p>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {agentStats.map(a => (
                <div key={a.id} className="flex items-start gap-3 p-2 rounded bg-white/[0.03]">
                  <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${a.status === 'online' || a.status === 'busy' ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{a.id}</span>
                      <span className="text-xs px-1 py-0.5 rounded bg-green-500/15 text-green-400">{a.completed} done</span>
                      {a.blocked > 0 && <span className="text-xs px-1 py-0.5 rounded bg-red-500/15 text-red-400">{a.blocked} blkd</span>}
                    </div>
                    {a.capabilities && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {a.capabilities.split(',').map((c, i) => (
                          <span key={i} className="text-[10px] px-1 py-0.25 rounded bg-cyan-500/10 text-cyan-400/80">{c.trim()}</span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color }: { icon: any; label: string; value: number; sub?: string; color: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-4 h-4" style={{ color }} />
        <span className="text-xs text-[var(--color-muted)]">{label}</span>
      </div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-[10px] text-[var(--color-muted)] mt-1">{sub}</div>}
    </div>
  )
}
