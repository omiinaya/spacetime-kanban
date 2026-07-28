import { useState, useEffect } from 'react'
import { api, type SchemaMigration } from '../api'
import { Database, Loader2, AlertCircle } from 'lucide-react'

export default function SchemaMigrationsPage() {
  const [migrations, setMigrations] = useState<SchemaMigration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadMigrations = async () => {
    try {
      setLoading(true)
      const result = await api.migrations.list()
      setMigrations(result)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadMigrations() }, [])

  const formatTs = (ts: number) => {
    if (!ts) return '—'
    // u64 timestamp in milliseconds
    const d = new Date(Number(ts) / 1000)
    return d.toLocaleString()
  }

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">Schema Migrations</h1>
        </div>
        <button onClick={loadMigrations}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
        >
          <Loader2 className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 text-[var(--color-muted)] py-12">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading migrations...
        </div>
      ) : migrations.length === 0 ? (
        <div className="text-center py-12 text-[var(--color-muted)]">
          <Database className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No schema migrations recorded.</p>
          <p className="text-xs mt-1">Migrations will appear here once applied.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] bg-[var(--color-card)]">
                <th className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Version</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Description</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Applied By</th>
                <th className="text-right px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Applied At</th>
                <th className="text-left px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Checksum</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {migrations.map((m) => (
                <tr key={m.version} className="hover:bg-[var(--color-card)]/50 transition-colors">
                  <td className="px-4 py-3 font-mono text-xs">{m.version}</td>
                  <td className="px-4 py-3 text-[var(--color-foreground)]">{m.description || '—'}</td>
                  <td className="px-4 py-3 text-[var(--color-muted)]">{m.applied_by || '—'}</td>
                  <td className="px-4 py-3 text-right text-[var(--color-muted)] text-xs whitespace-nowrap">
                    {formatTs(m.applied_at)}
                  </td>
                  <td className="px-4 py-3 font-mono text-[10px] text-[var(--color-muted)] max-w-[120px] truncate" title={m.checksum ?? ''}>
                    {m.checksum || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
