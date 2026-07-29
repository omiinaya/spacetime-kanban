import { X, Keyboard, Save, Bookmark } from 'lucide-react'
import type { SavedFilterView } from '../../hooks/useSavedViews'

export function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose} role="dialog" aria-modal="true">
      <div className="w-full max-w-md bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold flex items-center gap-2"><Keyboard className="w-4 h-4" /> Keyboard Shortcuts</h3>
          <button onClick={onClose} aria-label="Close shortcuts" className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-1.5">
          {[
            ['n', 'New task'],
            ['s / /', 'Search tasks'],
            ['c', 'Toggle compact view'],
            ['f', 'Toggle filters'],
            ['b', 'Toggle select mode'],
            ['g', 'Toggle dependency graph'],
            ['e', 'Export as CSV'],
            ['1-4', 'Switch column tab (mobile)'],
            ['?', 'Show this help'],
            ['Esc', 'Close / deselect'],
          ].map(([key, desc]) => (
            <div key={key} className="flex items-center justify-between py-1.5">
              <span className="text-sm text-[var(--color-muted-foreground)]">{desc}</span>
              <kbd className="text-xs px-2 py-0.5 rounded bg-white/10 text-[var(--color-muted)] font-mono border border-[var(--color-border)]">{key}</kbd>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-[var(--color-muted)] text-center pt-1">
          Shortcuts don't work when typing in input fields
        </p>
      </div>
    </div>
  )
}

export function SavedViewsPills({ savedViews, onLoad, onDelete }: {
  savedViews: SavedFilterView[]
  onLoad: (view: SavedFilterView) => void
  onDelete: (id: string) => void
}) {
  if (savedViews.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Bookmark className="w-3 h-3 text-[var(--color-muted)]" />
      {savedViews.map(view => (
        <div key={view.id} className="group relative">
          <button
            onClick={() => onLoad(view)}
            className="text-xs px-2 py-1 rounded-full bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] transition-colors"
          >{view.name}</button>
          <button
            onClick={() => onDelete(view.id)}
            className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-red-500/80 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
            title="Delete view"
            aria-label="Delete view"
          ><X className="w-2 h-2" /></button>
        </div>
      ))}
    </div>
  )
}

export function SaveViewDialog({ name, setName, onSave, onClose }: {
  name: string
  setName: (v: string) => void
  onSave: () => void
  onClose: () => void
}) {
  return (
    <div className="relative">
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute left-0 z-50 mt-1 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 shadow-xl space-y-2">
        <p className="text-xs font-medium text-[var(--color-muted)] flex items-center gap-1">
          <Save className="w-3 h-3" /> Save current filters as
        </p>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') onSave(); if (e.key === 'Escape') onClose() }}
          placeholder="View name..."
          autoFocus
          className="w-full px-2 py-1.5 text-xs rounded border border-[var(--color-border)] bg-[var(--color-background)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
        />
        <div className="flex items-center gap-2">
          <button onClick={onSave} disabled={!name.trim()}
            className="flex-1 text-xs px-2 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >Save</button>
          <button onClick={onClose}
            className="flex-1 text-xs px-2 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors"
          >Cancel</button>
        </div>
      </div>
    </div>
  )
}
