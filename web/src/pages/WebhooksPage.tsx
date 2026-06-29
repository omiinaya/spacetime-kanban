import { useEffect, useState } from 'react'
import { api, type Webhook } from '../api'
import {
  WebhookIcon, Plus, Loader2, AlertCircle, Trash2, Send,
  CheckCircle2, XCircle, X, ExternalLink, Zap, Edit3
} from 'lucide-react'

const WEBHOOK_TYPES = ['discord', 'slack', 'telegram', 'generic']
const ALL_EVENTS = ['created', 'claimed', 'unclaimed', 'completed', 'blocked', 'linked']
const EVENT_COLORS: Record<string, string> = {
  created: 'bg-indigo-500/15 text-indigo-400',
  claimed: 'bg-yellow-500/15 text-yellow-400',
  unclaimed: 'bg-slate-500/15 text-slate-400',
  completed: 'bg-green-500/15 text-green-400',
  blocked: 'bg-red-500/15 text-red-400',
  linked: 'bg-cyan-500/15 text-cyan-400',
}

export default function WebhooksPage() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editEvents, setEditEvents] = useState<string[]>([])
  const [editLabel, setEditLabel] = useState('')

  // Create form state
  const [createUrl, setCreateUrl] = useState('')
  const [createType, setCreateType] = useState('discord')
  const [createEvents, setCreateEvents] = useState<string[]>(['created', 'claimed', 'completed', 'blocked'])

  const load = async () => {
    try {
      const whs = await api.webhooks.list()
      setWebhooks(whs)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    if (!createUrl.trim()) return
    try {
      await api.webhooks.create({
        url: createUrl.trim(),
        type: createType,
        events: createEvents,
      })
      setShowCreate(false)
      setCreateUrl('')
      setCreateType('discord')
      setCreateEvents(['created', 'claimed', 'completed', 'blocked'])
      await load()
    } catch (e: any) {
      alert(`Create failed: ${e.message}`)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Remove this webhook?')) return
    try {
      await api.webhooks.delete(id)
      setTestResults(prev => { const r = { ...prev }; delete r[id]; return r })
      await load()
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`)
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await api.webhooks.test(id)
      setTestResults(prev => ({ ...prev, [id]: { ok: true, msg: `HTTP ${result.response_code}` } }))
    } catch (e: any) {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, msg: e.message } }))
    } finally {
      setTestingId(null)
    }
  }

  const startEdit = (wh: Webhook) => {
    setEditingId(wh.id)
    setEditEvents([...wh.events])
    setEditLabel(wh.label)
  }

  const saveEdit = async (id: string) => {
    try {
      await api.webhooks.update(id, { events: editEvents, label: editLabel || undefined })
      setEditingId(null)
      await load()
    } catch (e: any) {
      alert(`Update failed: ${e.message}`)
    }
  }

  const toggleEvent = (event: string, list: string[], setter: (v: string[]) => void) => {
    if (list.includes(event)) {
      setter(list.filter(e => e !== event))
    } else {
      setter([...list, event])
    }
  }

  if (loading) return (
    <div className="p-8 flex items-center justify-center gap-2 text-[var(--color-muted)]">
      <Loader2 className="w-4 h-4 animate-spin" /> Loading webhooks...
    </div>
  )

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <WebhookIcon className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg sm:text-xl font-semibold">Webhooks</h1>
          <span className="text-xs text-[var(--color-muted)] bg-white/5 px-2 py-0.5 rounded-full">{webhooks.length}</span>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
        >
          {showCreate ? <X className="w-3.5 h-3.5" /> : <Plus className="w-3.5 h-3.5" />}
          {showCreate ? 'Cancel' : 'Add Webhook'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" /> {error}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-4">
          <h3 className="text-sm font-semibold">New Webhook</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="sm:col-span-2 space-y-1.5">
              <label className="text-xs text-[var(--color-muted)]">Webhook URL</label>
              <input
                value={createUrl}
                onChange={e => setCreateUrl(e.target.value)}
                placeholder="https://discord.com/api/webhooks/..."
                className="w-full px-3 py-2 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-background)] focus:outline-none focus:border-[var(--color-primary)] placeholder:text-[var(--color-muted)]"
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-[var(--color-muted)]">Type</label>
              <select
                value={createType}
                onChange={e => setCreateType(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-background)] focus:outline-none focus:border-[var(--color-primary)]"
              >
                {WEBHOOK_TYPES.map(t => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label className="text-xs text-[var(--color-muted)]">Events</label>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {ALL_EVENTS.map(ev => (
                  <button
                    key={ev}
                    onClick={() => toggleEvent(ev, createEvents, setCreateEvents)}
                    className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                      createEvents.includes(ev)
                        ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-[var(--color-primary)]'
                        : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                    }`}
                  >
                    {ev}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={handleCreate}
              disabled={!createUrl.trim()}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-md bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
            >
              <Zap className="w-3.5 h-3.5" /> Create Webhook
            </button>
          </div>
        </div>
      )}

      {/* Empty state */}
      {webhooks.length === 0 && !error && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-8 text-center space-y-2">
          <WebhookIcon className="w-8 h-8 mx-auto text-[var(--color-muted)]" />
          <p className="text-sm text-[var(--color-muted)]">No webhooks configured.</p>
          <p className="text-xs text-[var(--color-muted)]">Add a webhook to receive task notifications on Discord, Slack, Telegram, or any HTTP endpoint.</p>
        </div>
      )}

      {/* Webhook list */}
      <div className="space-y-3">
        {webhooks.map(wh => (
          <div
            key={wh.id}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3"
          >
            {/* Top row */}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-1">
                {editingId === wh.id ? (
                  <input
                    value={editLabel}
                    onChange={e => setEditLabel(e.target.value)}
                    className="w-full px-2 py-1 text-sm rounded border border-[var(--color-border)] bg-[var(--color-background)] focus:outline-none focus:border-[var(--color-primary)]"
                    placeholder="Webhook label"
                  />
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium truncate">{wh.label || wh.url}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full uppercase font-medium ${
                      wh.type === 'discord' ? 'bg-indigo-500/15 text-indigo-400' :
                      wh.type === 'slack' ? 'bg-green-500/15 text-green-400' :
                      wh.type === 'telegram' ? 'bg-sky-500/15 text-sky-400' :
                      'bg-slate-500/15 text-slate-400'
                    }`}>
                      {wh.type}
                    </span>
                  </div>
                )}
                <p className="text-xs text-[var(--color-muted)] truncate" title={wh.url}>{wh.url}</p>
                {wh.created_at > 0 && (
                  <p className="text-[10px] text-[var(--color-muted)]/60">
                    Created {new Date(wh.created_at).toLocaleDateString()}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                {/* Test */}
                <button
                  onClick={() => handleTest(wh.id)}
                  disabled={testingId === wh.id}
                  className="p-1.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-green-400 transition-colors disabled:opacity-40"
                  title="Send test notification"
                >
                  {testingId === wh.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
                {/* Edit */}
                {editingId === wh.id ? (
                  <button
                    onClick={() => saveEdit(wh.id)}
                    className="p-1.5 rounded hover:bg-white/10 text-green-400 transition-colors"
                    title="Save"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                  </button>
                ) : (
                  <button
                    onClick={() => startEdit(wh)}
                    className="p-1.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                    title="Edit events/label"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>
                )}
                {/* Delete */}
                <button
                  onClick={() => handleDelete(wh.id)}
                  className="p-1.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-red-400 transition-colors"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Events (editable) */}
            {editingId === wh.id ? (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {ALL_EVENTS.map(ev => (
                    <button
                      key={ev}
                      onClick={() => toggleEvent(ev, editEvents, setEditEvents)}
                      className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                        editEvents.includes(ev)
                          ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-[var(--color-primary)]'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                      }`}
                    >
                      {ev}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setEditingId(null)}
                  className="text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {wh.events.map(ev => (
                  <span
                    key={ev}
                    className={`text-[10px] px-1.5 py-0.5 rounded-full ${EVENT_COLORS[ev] || 'bg-white/10 text-[var(--color-muted)]'}`}
                  >
                    {ev}
                  </span>
                ))}
              </div>
            )}

            {/* Test result */}
            {testResults[wh.id] && (
              <div className={`flex items-center gap-1.5 text-xs ${
                testResults[wh.id].ok ? 'text-green-400' : 'text-red-400'
              }`}>
                {testResults[wh.id].ok
                  ? <CheckCircle2 className="w-3.5 h-3.5" />
                  : <XCircle className="w-3.5 h-3.5" />
                }
                {testResults[wh.id].msg}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
