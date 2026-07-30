import { useEffect, useState } from 'react'
import { api, type Webhook, type WebhookDelivery } from '../api'
import {
  WebhookIcon, Plus, Loader2, AlertCircle, Trash2, Send,
  CheckCircle2, XCircle, X, Zap, Edit3, History, ChevronDown, ChevronUp
} from 'lucide-react'
import { useToast } from '../hooks/useToast'
import { useConfirm } from '../components/ConfirmDialog'
import { PageSkeleton } from '../components/Skeleton'

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
  const { addToast } = useToast()
  const { confirm } = useConfirm()
  const [webhooks, setWebhooks] = useState<Webhook[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({})
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editEvents, setEditEvents] = useState<string[]>([])
  const [editLabel, setEditLabel] = useState('')
  const [deliveries, setDeliveries] = useState<Record<string, WebhookDelivery[]>>({})
  const [loadingDeliveries, setLoadingDeliveries] = useState<Set<string>>(new Set())
  const [showDelivery, setShowDelivery] = useState<Set<string>>(new Set())

  // Create form state
  const [createUrl, setCreateUrl] = useState('')
  const [createType, setCreateType] = useState('discord')
  const [createEvents, setCreateEvents] = useState<string[]>(['created', 'claimed', 'completed', 'blocked'])

  const load = async () => {
    try {
      const whs = await api.webhooks.list()
      setWebhooks(whs)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
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
    } catch (e: unknown) {
      addToast('❌', `Create failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleDelete = async (id: string) => {
    const ok = await confirm({ title: 'Remove Webhook', message: 'Remove this webhook?', confirmLabel: 'Remove', variant: 'danger' })
    if (!ok) return
    try {
      await api.webhooks.delete(id)
      setTestResults(prev => { const r = { ...prev }; delete r[id]; return r })
      await load()
    } catch (e: unknown) {
      addToast('❌', `Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleTest = async (id: string) => {
    setTestingId(id)
    try {
      const result = await api.webhooks.test(id)
      setTestResults(prev => ({ ...prev, [id]: { ok: true, msg: `HTTP ${result.response_code}` } }))
    } catch (e: unknown) {
      setTestResults(prev => ({ ...prev, [id]: { ok: false, msg: e instanceof Error ? e.message : String(e) } }))
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
    } catch (e: unknown) {
      addToast('❌', `Update failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const toggleDeliveries = async (id: string) => {
    const next = new Set(showDelivery)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
      // Load deliveries if not already loaded
      if (!deliveries[id]) {
        setLoadingDeliveries(prev => new Set(prev).add(id))
        try {
          const data = await api.webhooks.deliveries(id, 10)
          setDeliveries(prev => ({ ...prev, [id]: data }))
        } catch { /* ignore fetch errors */ }
        setLoadingDeliveries(prev => { const n = new Set(prev); n.delete(id); return n })
      }
    }
    setShowDelivery(next)
  }

  const toggleEvent = (event: string, list: string[], setter: (v: string[]) => void) => {
    if (list.includes(event)) {
      setter(list.filter(e => e !== event))
    } else {
      setter([...list, event])
    }
  }

  if (loading) return <PageSkeleton rows={4} />

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
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20" role="alert">
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
                type="url"
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

            {/* Delivery history toggle */}
            <button onClick={() => toggleDeliveries(wh.id)}
              className="flex items-center gap-1 text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            >
              <History className="w-3 h-3" />
              {showDelivery.has(wh.id) ? 'Hide' : 'Show'} delivery history
              {showDelivery.has(wh.id) ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            {/* Delivery history */}
            {showDelivery.has(wh.id) && (
              <div className="space-y-1 border-t border-[var(--color-border)] pt-2">
                {loadingDeliveries.has(wh.id) ? (
                  <div className="flex items-center gap-2 py-2 text-xs text-[var(--color-muted)]">
                    <Loader2 className="w-3 h-3 animate-spin" /> Loading...
                  </div>
                ) : !deliveries[wh.id] || deliveries[wh.id].length === 0 ? (
                  <p className="text-xs text-[var(--color-muted)] py-1">No delivery history yet.</p>
                ) : (
                  deliveries[wh.id].map(d => (
                    <div key={d.id}
                      className="flex items-start gap-2 py-1.5 text-xs border-b border-[var(--color-border)] last:border-0"
                    >
                      {d.success
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-green-400 shrink-0 mt-0.5" />
                        : <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                      }
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className={`text-[10px] px-1 py-0.5 rounded font-medium ${
                            d.success ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'
                          }`}>
                            HTTP {d.status_code || 'ERR'}
                          </span>
                          <span className="text-[var(--color-muted-foreground)] capitalize">{d.event}</span>
                        </div>
                        {d.response_body && (
                          <p className="text-[10px] text-[var(--color-muted)] truncate mt-0.5" title={d.response_body}>
                            {d.response_body.slice(0, 120)}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] text-[var(--color-muted)] shrink-0">
                        {new Date(d.delivered_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
