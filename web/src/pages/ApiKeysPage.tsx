import { useState, useEffect } from 'react'
import { api, type ApiKeyItem, type ApiKeyItemFull } from '../api'
import { Key, Loader2, AlertCircle, Plus, Trash2, Copy, Check, X } from 'lucide-react'

export default function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newKey, setNewKey] = useState({ name: '', permissions: 'read', scope: '*' })
  const [creating, setCreating] = useState(false)
  const [createdKey, setCreatedKey] = useState<ApiKeyItemFull | null>(null)
  const [copied, setCopied] = useState(false)

  const loadKeys = async () => {
    try {
      setLoading(true)
      const result = await api.apiKeys.list()
      setKeys(result)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadKeys() }, [])

  const handleCreate = async () => {
    if (!newKey.name.trim()) return
    setCreating(true)
    try {
      const result = await api.apiKeys.create(newKey)
      setCreatedKey(result)
      setShowCreate(false)
      setNewKey({ name: '', permissions: 'read', scope: '*' })
      loadKeys()
    } catch (e: unknown) {
      alert(`Failed to create key: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (keyId: string) => {
    if (!confirm('Revoke this API key? This cannot be undone.')) return
    try {
      await api.apiKeys.revoke(keyId)
      loadKeys()
    } catch (e: unknown) {
      alert(`Failed to revoke: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Key className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">API Keys</h1>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
        >
          <Plus className="w-3 h-3" /> Create Key
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Created key notification */}
      {createdKey && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium text-emerald-400">✅ API Key Created</p>
            <button onClick={() => setCreatedKey(null)}
              className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
            ><X className="w-4 h-4" /></button>
          </div>
          <p className="text-xs text-[var(--color-muted-foreground)]">
            This is the only time you'll see the full key. Copy it now and store it securely.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-black/30 px-3 py-2 rounded border border-[var(--color-border)] break-all">
              {createdKey.full_key}
            </code>
            <button onClick={() => copyToClipboard(createdKey.full_key)}
              className="flex items-center gap-1 text-xs px-2.5 py-2 rounded bg-white/10 hover:bg-white/20 transition-colors shrink-0"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            </button>
          </div>
          <p className="text-[10px] text-[var(--color-muted)]">
            Name: {createdKey.name} · Permissions: {createdKey.permissions} · Scope: {createdKey.scope}
          </p>
        </div>
      )}

      {/* Create dialog */}
      {showCreate && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
          <h3 className="text-sm font-medium">New API Key</h3>
          <div className="space-y-2">
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Name</label>
              <input value={newKey.name} onChange={e => setNewKey(p => ({ ...p, name: e.target.value }))}
                placeholder="My API Key"
                className="w-full px-3 py-1.5 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)] mt-1"
                autoFocus
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Permissions</label>
                <select value={newKey.permissions} onChange={e => setNewKey(p => ({ ...p, permissions: e.target.value }))}
                  className="w-full px-3 py-1.5 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)] mt-1"
                >
                  <option value="read">Read Only</option>
                  <option value="write">Read + Write</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Scope</label>
                <input value={newKey.scope} onChange={e => setNewKey(p => ({ ...p, scope: e.target.value }))}
                  placeholder="* (all repos)"
                  className="w-full px-3 py-1.5 text-xs rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-ring)] mt-1"
                />
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 justify-end">
            <button onClick={() => setShowCreate(false)}
              className="text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
            >Cancel</button>
            <button onClick={handleCreate} disabled={!newKey.name.trim() || creating}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
              Create
            </button>
          </div>
        </div>
      )}

      {/* Keys list */}
      {loading ? (
        <div className="flex items-center justify-center gap-2 text-[var(--color-muted)] py-12">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading API keys...
        </div>
      ) : keys.length === 0 ? (
        <div className="text-center py-12 text-[var(--color-muted)]">
          <Key className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No API keys yet.</p>
          <p className="text-xs mt-1">Create one to access the API programmatically.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {keys.map(key => (
            <div key={key.id}
              className={`rounded-lg border p-4 flex items-start gap-3 ${
                key.revoked
                  ? 'border-red-500/20 bg-red-500/5 opacity-60'
                  : 'border-[var(--color-border)] bg-[var(--color-card)]'
              }`}
            >
              <Key className={`w-4 h-4 mt-0.5 ${key.revoked ? 'text-red-400' : 'text-[var(--color-primary)]'}`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium">{key.name}</span>
                  {key.revoked && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">Revoked</span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1 text-[10px] text-[var(--color-muted)]">
                  <code className="font-mono">{key.key_prefix}</code>
                  <span>Permissions: {key.permissions}</span>
                  <span>Scope: {key.scope}</span>
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-[10px] text-[var(--color-muted)]">
                  <span>Created: {new Date(key.created_at).toLocaleDateString()}</span>
                  {key.last_used_at > 0 && (
                    <span>Last used: {new Date(key.last_used_at).toLocaleDateString()}</span>
                  )}
                </div>
              </div>
              {!key.revoked && (
                <button onClick={() => handleRevoke(key.id)}
                  className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded text-red-400 hover:bg-red-500/20 transition-colors shrink-0"
                  title="Revoke key"
                >
                  <Trash2 className="w-3 h-3" /> Revoke
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
