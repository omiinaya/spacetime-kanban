import { useState, useEffect } from 'react'
import { api, type SchemaMigration } from '../api'
import { Database, Loader2, AlertCircle, Plus } from 'lucide-react'
import { ListViewSkeleton } from '../components/Skeleton'

export default function SchemaMigrationsPage() {
  const [migrations, setMigrations] = useState<SchemaMigration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [version, setVersion] = useState('')
  const [description, setDescription] = useState('')
  const [appliedBy, setAppliedBy] = useState('')
  const [checksum, setChecksum] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')

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

  const handleRecord = async () => {
    if (!version.trim()) return
    setSaving(true)
    setSaveMsg('')
    try {
      await api.migrations.create({
        version: version.trim(),
        description: description.trim(),
        applied_by: appliedBy.trim() || undefined,
        checksum: checksum.trim() || undefined,
      })
      setVersion('')
      setDescription('')
      setAppliedBy('')
      setChecksum('')
      setShowForm(false)
      setSaveMsg('Migration recorded successfully')
      await loadMigrations()
    } catch (e: unknown) {
      setSaveMsg(`Error: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const formatTs = (ts: number) => {
    if (!ts) return '—'
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
        <div className="flex items-center gap-2">
          <button onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
          >
            <Plus className="w-3 h-3" />
            {showForm ? 'Cancel' : 'Record'}
          </button>
          <button onClick={loadMigrations}
            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-card)] border border-[var(--color-border)] hover:bg-[var(--color-border)] transition-colors"
          >
            <Loader2 className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {saveMsg && (
        <div className={`text-sm p-3 rounded-lg border ${saveMsg.startsWith('Error') ? 'bg-red-500/10 text-red-400 border-red-500/20' : 'bg-green-500/10 text-green-400 border-green-500/20'}`}>
          {saveMsg}
        </div>
      )}

      {showForm && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-sm font-medium">Record New Migration</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[var(--color-muted)] block mb-1">Version *</label>
              <input value={version} onChange={e => setVersion(e.target.value)}
                className="w-full text-xs px-3 py-1.5 rounded border border-[var(--color-border)] bg-[var(--color-background)]"
                placeholder="v2.1.0" />
            </div>
            <div>
              <label className="text-xs text-[var(--color-muted)] block mb-1">Applied By</label>
              <input value={appliedBy} onChange={e => setAppliedBy(e.target.value)}
                className="w-full text-xs px-3 py-1.5 rounded border border-[var(--color-border)] bg-[var(--color-background)]"
                placeholder="agent-name" />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs text-[var(--color-muted)] block mb-1">Description</label>
              <input value={description} onChange={e => setDescription(e.target.value)}
                className="w-full text-xs px-3 py-1.5 rounded border border-[var(--color-border)] bg-[var(--color-background)]"
                placeholder="What this migration does" />
            </div>
            <div className="sm:col-span-2">
              <label className="text-xs text-[var(--color-muted)] block mb-1">Checksum (optional)</label>
              <input value={checksum} onChange={e => setChecksum(e.target.value)}
                className="w-full text-xs px-3 py-1.5 rounded border border-[var(--color-border)] bg-[var(--color-background)] font-mono"
                placeholder="sha256:..." />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button onClick={() => setShowForm(false)}
              className="text-xs px-3 py-1.5 rounded border border-[var(--color-border)] hover:bg-[var(--color-border)] transition-colors">Cancel</button>
            <button onClick={handleRecord} disabled={saving || !version.trim()}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              {saving ? 'Saving...' : 'Record Migration'}
            </button>
          </div>
        </div>
      )}

      {loading ? <ListViewSkeleton /> : migrations.length === 0 ? (
        <div className="text-center py-12 text-[var(--color-muted)]">
          <Database className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No schema migrations recorded.</p>
          <p className="text-xs mt-1">Click <strong>Record</strong> to add the first migration entry.</p>
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
