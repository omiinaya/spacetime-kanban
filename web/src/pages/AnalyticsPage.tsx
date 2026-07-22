import { useEffect, useState } from 'react'
import { api } from '../api'
import { BarChart3, CheckCircle2, Clock, Users, AlertCircle, Layers, Loader2, Download, Activity } from 'lucide-react'
import type { ComponentType } from 'react'

interface Overview {
  total: number
  by_status: Record<string, number>
  completed_today: number
  completed_week: number
  total_done: number
  repos: Record<string, { total: number; done: number; in_progress: number; blocked: number; available: number }>
  agent_count: number
  claims_last_hour?: number
  completions_last_hour?: number
  claim_complete_ratio?: number
}

interface ThroughputPoint { date: string; completed: number }
interface CycleTime { repo: string; count: number; avg_hours: number; min_hours: number; max_hours: number }
interface AgentStat { id: string; status: string; completed: number; blocked: number; capabilities: string | null; repo_focus: string | null; last_heartbeat: number }
interface BurndownDay { date: string; open: number; completed: number; ideal: number }
interface BurndownData { days: BurndownDay[]; total_open_start: number; total_completed: number; total_remaining: number; days_total: number }

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
  const [burndown, setBurndown] = useState<BurndownData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const [ov, tp, ct, as, bd] = await Promise.all([
          api.analytics.overview(),
          api.analytics.throughput(14),
          api.analytics.cycleTimes(),
          api.analytics.agents(),
          api.analytics.burndown(30),
        ])
        setOverview(ov)
        setThroughput(tp)
        setCycleTimes(ct)
        setAgentStats(as)
        setBurndown(bd)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }
    load()
    const interval = setInterval(() => {
      if (document.hidden) return
      load()
    }, 30000)
    const onVis = () => { if (document.hidden) clearInterval(interval) }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVis) }
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
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">Analytics</h1>
        </div>
        <div className="relative group">
          <button className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors">
            <Download className="w-3 h-3" /> Export
          </button>
          <div className="absolute right-0 top-full mt-1 w-24 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <button onClick={() => window.open(api.tasks.export('csv'), '_blank')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-t-lg">CSV</button>
            <button onClick={() => window.open(api.tasks.export('json'), '_blank')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-b-lg">JSON</button>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard icon={Layers} label="Total Tasks" value={overview.total} color="#3b82f6" />
        <StatCard icon={CheckCircle2} label="Completed" value={overview.total_done} sub={`${overview.completed_today} today · ${overview.completed_week} this week`} color="#8b5cf6" />
        <StatCard icon={Clock} label="Available" value={overview.by_status.available || 0} color="#22c55e" />
        <StatCard icon={Users} label="Agents" value={overview.agent_count} color="#f59e0b" />
        {overview.claim_complete_ratio !== undefined && (
          <StatCard
            icon={Activity}
            label="Claim:Complete (1h)"
            value={overview.claim_complete_ratio}
            sub={`${overview.claims_last_hour} claims · ${overview.completions_last_hour} done`}
            color={overview.claim_complete_ratio > 10 ? '#ef4444' : overview.claim_complete_ratio > 3 ? '#f59e0b' : '#22c55e'}
          />
        )}
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
                  {p.date}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Burndown SVG chart */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">Burndown (last 30 days)</h3>
        {!burndown || burndown.days.length === 0 ? (
          <p className="text-xs text-[var(--color-muted)]">No data yet.</p>
        ) : (() => {
          const W = 600, H = 300, ML = 55, MR = 20, MT = 25, MB = 45
          const PW = W - ML - MR, PH = H - MT - MB
          const days = burndown.days
          const maxVal = Math.max(...days.map(d => d.open), burndown.total_open_start, 1)
          const xScale = (i: number) => ML + (i / Math.max(days.length - 1, 1)) * PW
          const yScale = (v: number) => MT + PH - (v / maxVal) * PH

          // Compute cumulative completed
          let cum = 0
          const cumCompleted = days.map(d => { cum += d.completed; return cum })

          // Build SVG path strings
          const openPath = days.map((d, i) => `${i === 0 ? 'M' : 'L'}${xScale(i).toFixed(1)},${yScale(d.open).toFixed(1)}`).join(' ')
          const completedPath = days.map((_, i) => `${i === 0 ? 'M' : 'L'}${xScale(i).toFixed(1)},${yScale(cumCompleted[i]).toFixed(1)}`).join(' ')
          const idealPath = days.map((d, i) => `${i === 0 ? 'M' : 'L'}${xScale(i).toFixed(1)},${yScale(d.ideal).toFixed(1)}`).join(' ')

          // Y-axis ticks (5 ticks)
          const yTicks = Array.from({ length: 5 }, (_, i) => Math.round((maxVal / 4) * i))

          // X-axis labels — show ~6 labels evenly spaced
          const xLabelStep = Math.max(1, Math.floor(days.length / 6))
          const xLabels = days.filter((_, i) => i % xLabelStep === 0 || i === days.length - 1)

          return (
            <div className="overflow-x-auto">
              <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[600px] h-auto" xmlns="http://www.w3.org/2000/svg">
                {/* Grid lines (horizontal) */}
                {yTicks.map(v => (
                  <line key={v} x1={ML} y1={yScale(v)} x2={ML + PW} y2={yScale(v)} stroke="rgba(255,255,255,0.06)" strokeWidth={1} />
                ))}
                {/* Y-axis */}
                <line x1={ML} y1={MT} x2={ML} y2={MT + PH} stroke="rgba(255,255,255,0.15)" strokeWidth={1} />
                {yTicks.map(v => (
                  <text key={v} x={ML - 8} y={yScale(v) + 4} textAnchor="end" fill="rgba(255,255,255,0.4)" fontSize={10}>
                    {v}
                  </text>
                ))}
                {/* X-axis */}
                <line x1={ML} y1={MT + PH} x2={ML + PW} y2={MT + PH} stroke="rgba(255,255,255,0.15)" strokeWidth={1} />
                {xLabels.map((d, i) => (
                  <text key={i} x={xScale(days.indexOf(d))} y={MT + PH + 18} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize={9}>
                    {d.date.slice(5)}
                  </text>
                ))}
                {/* Ideal line (dashed gray) */}
                <path d={idealPath} fill="none" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5,4" />
                {/* Open line (blue) */}
                <path d={openPath} fill="none" stroke="#3b82f6" strokeWidth={2} />
                {/* Completed line (green) */}
                <path d={completedPath} fill="none" stroke="#22c55e" strokeWidth={2} />
                {/* Legend */}
                <rect x={ML + 8} y={MT - 18} rx={4} ry={4} fill="rgba(0,0,0,0.35)" width={250} height={16} />
                <line x1={ML + 14} y1={MT - 10} x2={ML + 24} y2={MT - 10} stroke="#3b82f6" strokeWidth={2} />
                <text x={ML + 28} y={MT - 6} fill="#3b82f6" fontSize={9}>Open</text>
                <line x1={ML + 76} y1={MT - 10} x2={ML + 86} y2={MT - 10} stroke="#22c55e" strokeWidth={2} />
                <text x={ML + 90} y={MT - 6} fill="#22c55e" fontSize={9}>Completed</text>
                <line x1={ML + 164} y1={MT - 10} x2={ML + 174} y2={MT - 10} stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="3,3" />
                <text x={ML + 178} y={MT - 6} fill="#94a3b8" fontSize={9}>Ideal</text>
              </svg>
            </div>
          )
        })()}
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

function StatCard({ icon: Icon, label, value, sub, color }: { icon: ComponentType<{ className?: string; style?: React.CSSProperties }>; label: string; value: number; sub?: string; color: string }) {
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
