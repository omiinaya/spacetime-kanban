import { useState, useCallback } from 'react'
import { Plus, Loader2 } from 'lucide-react'
import { api } from '../api'
import { PRIORITY_LABELS, PRIORITY_COLORS, type TaskTemplate, BUILT_IN_TEMPLATES } from './constants'

export function CreateTaskDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [selectedTemplate, setSelectedTemplate] = useState<TaskTemplate | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [priority, setPriority] = useState(2)
  const [repo, setRepo] = useState('')
  const [roadmap, setRoadmap] = useState('')
  const [skills, setSkills] = useState('')
  const [saving, setSaving] = useState(false)

  const applyTemplate = (tpl: TaskTemplate) => {
    setSelectedTemplate(tpl)
    setTitle(tpl.title)
    setDescription(tpl.description)
    setPriority(tpl.priority)
    setRepo(tpl.repo)
    setRoadmap(tpl.roadmap)
    setSkills(tpl.skills)
  }

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.task.insert({ title: title.trim(), description, priority, repo: repo || null, roadmap: roadmap || null, skills: skills || null, status: 'available' })
      onCreated()
      onClose()
    } catch (err) {
      console.error('Failed to create task', err)
    } finally {
      setSaving(false)
    }
  }, [title, description, priority, repo, roadmap, skills, onClose, onCreated])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-[var(--color-card)] border border-[var(--color-border)] rounded-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="p-5 space-y-4">
          <h2 className="text-lg font-semibold">Create Task</h2>
          <div className="flex flex-wrap gap-1.5">
            {BUILT_IN_TEMPLATES.map(tpl => (
              <button key={tpl.name} type="button" onClick={() => applyTemplate(tpl)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  selectedTemplate?.name === tpl.name
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                    : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-ring)]'
                }`}
              >{tpl.name}</button>
            ))}
          </div>
          <form onSubmit={handleSubmit} className="space-y-3">
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Task title" required
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="Description (optional)" rows={4}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] resize-none"
            />
            <select value={priority} onChange={e => setPriority(Number(e.target.value))}
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm"
            >
              {Object.entries(PRIORITY_LABELS).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
            <input value={repo} onChange={e => setRepo(e.target.value)} placeholder="Repo slug"
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <input value={roadmap} onChange={e => setRoadmap(e.target.value)} placeholder="Roadmap item"
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <input value={skills} onChange={e => setSkills(e.target.value)} placeholder="Skills (e.g. rust,python)"
              className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose}
                className="text-sm px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/5 transition-colors"
              >Cancel</button>
              <button type="submit" disabled={saving || !title.trim()}
                className="flex items-center gap-1 text-sm px-4 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors disabled:opacity-50"
              >{saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />} Create</button>
            </div>
          </form>
        </div>
      </div>
    </div>
  )
}
