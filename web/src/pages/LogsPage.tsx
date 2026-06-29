import { useEffect, useState, useCallback } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import { api, LogEntry } from '../api'

const ACTION_COLORS: Record<string, string> = {
  created: 'text-blue-400',
  claimed: 'text-green-400',
  unclaimed: 'text-yellow-400',
  completed: 'text-emerald-400',
  blocked: 'text-red-400',
}

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await api.logs.list(undefined, 100)
      setLogs(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [load])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-[var(--color-muted)]" />
      </div>
    )
  }

  return (
    <div className="p-4 md:p-6 lg:p-8 space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Activity Log</h1>
        <p className="text-sm text-[var(--color-muted-foreground)]">
          Every claim, completion, and state change
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      <div className="space-y-1">
        {logs.map((log) => (
          <div key={log.id}
            className="flex items-center gap-3 px-4 py-2 rounded-lg hover:bg-white/[0.02] text-sm"
          >
            <span className={`text-xs font-mono w-20 flex-shrink-0 uppercase ${ACTION_COLORS[log.action] || 'text-[var(--color-muted)]'}`}>
              {log.action}
            </span>
            <span className="text-[var(--color-muted-foreground)] truncate font-mono text-xs w-20 flex-shrink-0">
              {log.task_id.slice(-12)}
            </span>
            {log.agent_id && (
              <span className="text-xs text-[var(--color-muted)] w-24 truncate flex-shrink-0">
                by {log.agent_id}
              </span>
            )}
            {log.notes && (
              <span className="text-xs text-[var(--color-muted-foreground)] truncate flex-1">
                {log.notes}
              </span>
            )}
            <span className="text-[10px] text-[var(--color-muted)] flex-shrink-0 w-14 text-right font-mono">
              {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        ))}
        {logs.length === 0 && (
          <div className="text-center py-12 text-sm text-[var(--color-muted)]">
            No activity yet. Create or claim a task to see logs.
          </div>
        )}
      </div>
    </div>
  )
}
