import { Lightbulb, Users } from 'lucide-react'
import type { SuggestResult, Agent } from '../../api'
import { PRIORITY_LABELS, PRIORITY_COLORS } from '../constants'

export function SuggestionsPanel({ suggestions, onClaim }: {
  suggestions: SuggestResult[]
  onClaim: (taskId: string) => void
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
          <Lightbulb className="w-3 h-3 text-amber-400" /> Smart Suggestions
        </h3>
        <span className="text-[10px] text-[var(--color-muted)]">Refreshes every 30s</span>
      </div>
      {suggestions.length === 0 ? (
        <p className="text-xs text-[var(--color-muted)]">No suggestions available. All tasks may be claimed or blocked.</p>
      ) : (
        <div className="space-y-1.5">
          {suggestions.map((s, i) => (
            <div key={i} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] hover:bg-white/[0.06] transition-colors cursor-pointer" onClick={() => onClaim(s.task.id)}>
              <span className="text-lg mt-0.5">{['🥇', '🥈', '🥉'][i] || '📋'}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{s.task.title}</span>
                  <span className="text-xs px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted-foreground)] font-mono">{s.score}</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[var(--color-muted)] mt-0.5">
                  <span className={`px-1 py-0.25 rounded text-[10px] ${PRIORITY_COLORS[s.task.priority] || ''}`}>
                    {PRIORITY_LABELS[s.task.priority] || s.task.priority}
                  </span>
                  <span>{s.reason}</span>
                  {s.task.required_skills && <span className="text-cyan-400">Skills: {s.task.required_skills}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function AgentsPanel({ agents }: { agents: Agent[] }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
          <Users className="w-3 h-3 text-cyan-400" /> Swarm Agents
        </h3>
        <span className="text-[10px] text-[var(--color-muted)]">{agents.length} agent(s)</span>
      </div>
      {agents.length === 0 ? (
        <p className="text-xs text-[var(--color-muted)]">No agents registered. Run <code className="px-1 py-0.5 rounded bg-white/10">kanban register --capabilities=...</code> to join the swarm.</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {agents.map((a) => {
            const isOnline = a.status === 'online' || a.status === 'busy'
            const agentAge = Math.floor((Date.now() - a.last_heartbeat) / 1000)
            const isStale = agentAge > 60
            return (
              <div key={a.id} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] border border-[var(--color-border)]">
                <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${isStale ? 'bg-red-500' : isOnline ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-medium truncate">{a.id}</span>
                    {a.repo_focus && <span className="text-[10px] px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted)]">{a.repo_focus}</span>}
                  </div>
                  {a.capabilities && (
                    <div className="flex flex-wrap gap-1 mt-0.5">
                      {a.capabilities.split(',').map((c, j) => (
                        <span key={j} className="text-[10px] px-1 py-0.25 rounded bg-cyan-500/10 text-cyan-400/80">{c.trim()}</span>
                      ))}
                    </div>
                  )}
                  <div className="text-[10px] text-[var(--color-muted)] mt-0.5">
                    {a.host} · {isStale ? 'stale' : a.status} · {Math.floor(agentAge / 60)}m ago
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
