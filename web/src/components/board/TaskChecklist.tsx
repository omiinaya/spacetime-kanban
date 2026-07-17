import { useState, useEffect } from 'react'
import { Loader2, Plus, Trash2, CheckSquare } from 'lucide-react'
import { api, type ChecklistItem } from '../../api'

export function TaskChecklist({ taskId }: { taskId: string }) {
  const [checklist, setChecklist] = useState<ChecklistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [newText, setNewText] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.checklist.list(taskId).then(items => {
      if (!cancelled) { setChecklist(items); setLoading(false) }
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [taskId])

  const handleAdd = async () => {
    const text = newText.trim()
    if (!text) return
    setSaving(true)
    try {
      const result = await api.checklist.add(taskId, text)
      if (result.id) {
        setChecklist(prev => [...prev, {
          id: result.id,
          task_id: taskId,
          text,
          completed: false,
          position: prev.length,
          created_at: Date.now(),
        }])
        setNewText('')
      }
    } catch (e: unknown) {
      alert(`Failed to add checklist item: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (itemId: string) => {
    setChecklist(prev => prev.map(i => i.id === itemId ? { ...i, completed: !i.completed } : i))
    try {
      await api.checklist.toggle(taskId, itemId)
    } catch (e: unknown) {
      // Revert on failure
      setChecklist(prev => prev.map(i => i.id === itemId ? { ...i, completed: !i.completed } : i))
      alert(`Failed to toggle: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleRemove = async (itemId: string) => {
    if (!confirm('Remove this checklist item?')) return
    setChecklist(prev => prev.filter(i => i.id !== itemId))
    try {
      await api.checklist.remove(taskId, itemId)
    } catch (e: unknown) {
      alert(`Failed to remove: ${e instanceof Error ? e.message : String(e)}`)
      // Reload on failure
      api.checklist.list(taskId).then(items => setChecklist(items))
    }
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
        <CheckSquare className="w-3 h-3" /> Checklist
        {checklist.length > 0 && (
          <span className="text-[10px] text-[var(--color-muted)] font-normal">
            {checklist.filter(i => i.completed).length}/{checklist.length}
          </span>
        )}
      </p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] py-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading...
        </div>
      ) : (
        <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
          {checklist.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)] py-1">No checklist items.</p>
          ) : (
            checklist.map(item => (
              <div key={item.id} className="flex items-start gap-2 px-1 py-1 rounded hover:bg-white/[0.03] group">
                <button
                  onClick={() => handleToggle(item.id)}
                  className={`mt-0.5 shrink-0 rounded transition-colors ${
                    item.completed ? 'text-emerald-400' : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
                  }`}
                >
                  <CheckSquare className={`w-4 h-4 ${item.completed ? 'fill-emerald-400/20' : ''}`} />
                </button>
                <span className={`flex-1 text-sm ${item.completed ? 'line-through text-[var(--color-muted)]' : 'text-[var(--color-muted-foreground)]'}`}>
                  {item.text}
                </span>
                <button
                  onClick={() => handleRemove(item.id)}
                  className="opacity-0 group-hover:opacity-100 text-[var(--color-muted)] hover:text-red-400 transition-all shrink-0"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </div>
            ))
          )}
        </div>
      )}
      <div className="flex items-center gap-2">
        <input
          value={newText}
          onChange={e => setNewText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault()
              handleAdd()
            }
          }}
          placeholder="Add checklist item..."
          className="flex-1 px-3 py-1.5 text-xs rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] placeholder:text-[var(--color-muted)]"
        />
        <button
          onClick={handleAdd}
          disabled={!newText.trim() || saving}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Add
        </button>
      </div>
    </div>
  )
}
