import { useEffect, useState, useCallback } from 'react'
import { Loader2, AlertCircle, Plus, X, Tag, Palette } from 'lucide-react'
import { api, KanbanLabel } from '../api'
import { useToast } from '../hooks/useToast'
import { CardGridSkeleton } from '../components/Skeleton'

const PRESET_COLORS = [
  '#0ea5e9', '#06b6d4', '#10b981', '#22c55e', '#84cc16',
  '#eab308', '#f97316', '#ef4444', '#ec4899', '#a855f7',
  '#8b5cf6', '#6366f1',
]

export default function LabelsPage() {
  const { addToast } = useToast()
  const [labels, setLabels] = useState<KanbanLabel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  // Create form
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('#0ea5e9')
  const [newDesc, setNewDesc] = useState('')
  const [saving, setSaving] = useState(false)

  // Edit form
  const [editName, setEditName] = useState('')
  const [editColor, setEditColor] = useState('')
  const [editDesc, setEditDesc] = useState('')

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await api.labels.list()
      setLabels(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    setSaving(true)
    try {
      await api.labels.create({ name: newName.trim(), color: newColor, description: newDesc.trim() })
      setNewName('')
      setNewColor('#0ea5e9')
      setNewDesc('')
      setShowCreate(false)
      await load()
    } catch (e: unknown) {
      addToast('❌', `Create failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleUpdate = async (id: string) => {
    if (!editName.trim()) return
    setSaving(true)
    try {
      await api.labels.update(id, { name: editName.trim(), color: editColor, description: editDesc.trim() })
      setEditingId(null)
      await load()
    } catch (e: unknown) {
      addToast('❌', `Update failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this label? It will be removed from all tasks.')) return
    try {
      await api.labels.delete(id)
      await load()
    } catch (e: unknown) {
      addToast('❌', `Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const startEdit = (label: KanbanLabel) => {
    setEditingId(label.id)
    setEditName(label.name)
    setEditColor(label.color)
    setEditDesc(label.description)
  }

  if (loading) return <CardGridSkeleton />

  return (
    <div className="p-4 md:p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Labels</h1>
          <p className="text-sm text-[var(--color-muted-foreground)]">
            Color-coded tags for organizing and filtering tasks
          </p>
        </div>
        <button onClick={() => setShowCreate(true)}
          className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
        ><Plus className="w-4 h-4" /> New Label</button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Create Dialog */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold flex items-center gap-2"><Tag className="w-4 h-4" /> New Label</h3>
              <button onClick={() => setShowCreate(false)} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="space-y-3">
              <input value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="Label name" autoFocus
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
              />
              <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Description (optional)"
                className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
              />
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
                  <Palette className="w-3 h-3" /> Color
                </p>
                <div className="flex flex-wrap gap-2">
                  {PRESET_COLORS.map(c => (
                    <button key={c} type="button" onClick={() => setNewColor(c)}
                      className={`w-7 h-7 rounded-full border-2 transition-all ${
                        newColor === c ? 'border-white scale-110' : 'border-transparent hover:scale-110'
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-3 pt-2">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium"
                  style={{ backgroundColor: newColor + '25', color: newColor, border: `1px solid ${newColor}50` }}>
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: newColor }} />
                  {newName || 'Preview'}
                </div>
                <span className="text-[10px] text-[var(--color-muted)] font-mono">{newColor}</span>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowCreate(false)}
                  className="text-sm px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/5 transition-colors">Cancel</button>
                <button type="submit" disabled={saving || !newName.trim()}
                  className="flex items-center gap-1 text-sm px-4 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors disabled:opacity-50">
                  {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Labels grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {labels.map(label => (
          <div key={label.id}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">

            {editingId === label.id ? (
              /* Edit mode */
              <div className="space-y-2">
                <input value={editName} onChange={(e) => setEditName(e.target.value)}
                  placeholder="Label name" autoFocus
                  className="w-full px-2 py-1.5 rounded bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
                />
                <input value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                  placeholder="Description"
                  className="w-full px-2 py-1.5 rounded bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
                />
                <div className="flex flex-wrap gap-1.5">
                  {PRESET_COLORS.map(c => (
                    <button key={c} type="button" onClick={() => setEditColor(c)}
                      className={`w-5 h-5 rounded-full border-2 transition-all ${
                        editColor === c ? 'border-white scale-110' : 'border-transparent'
                      }`}
                      style={{ backgroundColor: c }}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button onClick={() => handleUpdate(label.id)}
                    disabled={saving || !editName.trim()}
                    className="text-xs px-2 py-1 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors disabled:opacity-50"
                  >{saving ? 'Saving...' : 'Save'}</button>
                  <button onClick={() => setEditingId(null)}
                    className="text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/5 transition-colors">Cancel</button>
                </div>
              </div>
            ) : (
              /* Display mode */
              <>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: label.color }} />
                    <span className="text-sm font-medium">{label.name}</span>
                  </div>
                  <span className="text-[10px] font-mono text-[var(--color-muted)]">{label.color}</span>
                </div>
                {label.description && (
                  <p className="text-xs text-[var(--color-muted-foreground)]">{label.description}</p>
                )}
                <div className="flex items-center gap-2 pt-1 border-t border-[var(--color-border)]">
                  <button onClick={() => startEdit(label)}
                    className="text-xs px-2 py-1 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors">Edit</button>
                  <button onClick={() => handleDelete(label.id)}
                    className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto">Delete</button>
                </div>
              </>
            )}
          </div>
        ))}
        {labels.length === 0 && (
          <div className="col-span-full text-center py-12 text-sm text-[var(--color-muted)]">
            No labels yet. Create one to start organizing tasks.
          </div>
        )}
      </div>
    </div>
  )
}
