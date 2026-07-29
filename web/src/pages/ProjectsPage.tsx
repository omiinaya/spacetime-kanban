import { useEffect, useState, useCallback } from 'react'
import { Loader2, AlertCircle, Plus, FolderKanban, ChevronUp, ChevronDown, Eye, EyeOff, Trash2, Save } from 'lucide-react'
import { api, Project } from '../api'
import { useToast } from '../hooks/useToast'
import { CardGridSkeleton } from '../components/Skeleton'

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Urgent',
  1: 'High',
  2: 'Medium',
  3: 'Low',
}

const PRIORITY_COLORS: Record<number, string> = {
  0: 'text-red-400 border-red-500/30',
  1: 'text-orange-400 border-orange-500/30',
  2: 'text-blue-400 border-blue-500/30',
  3: 'text-slate-400 border-slate-500/30',
}

const PRIORITY_BG: Record<number, string> = {
  0: 'bg-red-500/10',
  1: 'bg-orange-500/10',
  2: 'bg-blue-500/10',
  3: 'bg-slate-500/10',
}

export default function ProjectsPage() {
  const { addToast } = useToast()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [saving, setSaving] = useState(false)

  // Create form
  const [newId, setNewId] = useState('')
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState('#0ea5e9')
  const [newPriority, setNewPriority] = useState(2)

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await api.projects.list()
      setProjects(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newId.trim()) return
    setSaving(true)
    try {
      await api.projects.create({
        id: newId.trim(),
        name: newName.trim() || newId.trim(),
        color: newColor,
        priority: newPriority,
        description: '',
      })
      setNewId('')
      setNewName('')
      setNewColor('#0ea5e9')
      setNewPriority(2)
      setShowCreate(false)
      await load()
    } catch (e: unknown) {
      addToast('❌', `Create failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSaving(false)
    }
  }

  const handlePriorityUp = async (p: Project) => {
    const newPrio = Math.max(0, p.priority - 1)
    try {
      await api.projects.update(p.id, { priority: newPrio })
      await load()
    } catch (e: unknown) {
      addToast('❌', `Update failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handlePriorityDown = async (p: Project) => {
    const newPrio = Math.min(3, p.priority + 1)
    try {
      await api.projects.update(p.id, { priority: newPrio })
      await load()
    } catch (e: unknown) {
      addToast('❌', `Update failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleToggleActive = async (p: Project) => {
    try {
      await api.projects.update(p.id, { active: !p.active })
      await load()
    } catch (e: unknown) {
      addToast('❌', `Update failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleDelete = async (p: Project) => {
    if (!confirm(`Delete project "${p.name}"? This only removes the project registration, not tasks.`)) return
    try {
      await api.projects.delete(p.id)
      await load()
    } catch (e: unknown) {
      addToast('❌', `Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const sorted = [...projects].sort((a, b) => a.priority - b.priority || a.name.localeCompare(b.name))

  if (loading) return <CardGridSkeleton />

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            <FolderKanban className="w-5 h-5 text-[var(--color-primary)]" />
            Projects
          </h1>
          <p className="text-sm text-[var(--color-muted)] mt-0.5">
            Manage project priorities and visibility — {projects.length} registered
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
        >
          <Plus className="w-3.5 h-3.5" />
          New Project
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 mb-4 rounded bg-red-500/10 text-red-400 text-sm" role="alert">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="mb-6 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-[var(--color-muted)] mb-1">Repo slug *</label>
              <input
                value={newId}
                onChange={(e) => setNewId(e.target.value)}
                placeholder="sample-repo-p"
                className="w-full px-2.5 py-1.5 text-sm rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                required
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--color-muted)] mb-1">Display name</label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="SpacetimeAB"
                className="w-full px-2.5 py-1.5 text-sm rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              />
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div>
              <label className="block text-xs text-[var(--color-muted)] mb-1">Color</label>
              <input
                type="color"
                value={newColor}
                onChange={(e) => setNewColor(e.target.value)}
                className="w-8 h-8 rounded cursor-pointer border border-[var(--color-border)] bg-transparent"
              />
            </div>
            <div>
              <label className="block text-xs text-[var(--color-muted)] mb-1">Priority</label>
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(Number(e.target.value))}
                className="px-2.5 py-1.5 text-sm rounded bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              >
                <option value={0}>0 — Urgent</option>
                <option value={1}>1 — High</option>
                <option value={2}>2 — Medium</option>
                <option value={3}>3 — Low</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={saving || !newId.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium bg-[var(--color-primary)] text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
              Create
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="px-3 py-1.5 rounded text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Project grid */}
      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 text-[var(--color-muted)]">
          <FolderKanban className="w-10 h-10 mb-3 opacity-40" />
          <p className="text-sm">No projects registered yet.</p>
          <p className="text-xs mt-1">Register projects to set priorities and track progress.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {sorted.map((p) => (
            <div
              key={p.id}
              className={`rounded-lg border ${PRIORITY_COLORS[p.priority]} ${PRIORITY_BG[p.priority]} p-4 transition-colors ${
                !p.active ? 'opacity-50' : ''
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: p.color }}
                  />
                  <h3 className="font-medium text-sm truncate">{p.name}</h3>
                </div>
                <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full border ${PRIORITY_COLORS[p.priority]}`}>
                  P{p.priority}
                </span>
              </div>
              <p className="text-xs text-[var(--color-muted)] mb-3 truncate font-mono">{p.id}</p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handlePriorityUp(p)}
                  disabled={p.priority <= 0}
                  className="p-1 rounded hover:bg-white/10 disabled:opacity-30 transition-colors"
                  title="Increase priority"
                >
                  <ChevronUp className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handlePriorityDown(p)}
                  disabled={p.priority >= 3}
                  className="p-1 rounded hover:bg-white/10 disabled:opacity-30 transition-colors"
                  title="Decrease priority"
                >
                  <ChevronDown className="w-3.5 h-3.5" />
                </button>
                <div className="flex-1" />
                <button
                  onClick={() => handleToggleActive(p)}
                  className={`p-1 rounded hover:bg-white/10 transition-colors ${p.active ? 'text-green-400' : 'text-[var(--color-muted)]'}`}
                  title={p.active ? 'Deactivate project' : 'Activate project'}
                >
                  {p.active ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                </button>
                <button
                  onClick={() => handleDelete(p)}
                  className="p-1 rounded hover:bg-white/10 text-red-400 hover:text-red-300 transition-colors"
                  title="Delete project"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="mt-6 p-3 rounded border border-[var(--color-border)] bg-[var(--color-card)]">
        <p className="text-xs text-[var(--color-muted)] mb-2 font-medium">Priority Legend</p>
        <div className="flex flex-wrap gap-3">
          {[0, 1, 2, 3].map((p) => (
            <span key={p} className={`text-xs px-2 py-0.5 rounded-full border ${PRIORITY_COLORS[p]}`}>
              P{p} — {PRIORITY_LABELS[p]}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
