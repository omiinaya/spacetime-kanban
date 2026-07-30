import type { Ref } from 'react'
import {
  Plus, Wifi, WifiOff, Lightbulb, Users, Search, Download,
  CheckSquare, LayoutGrid, List, SlidersHorizontal, Save, Map,
} from 'lucide-react'

interface BoardToolbarProps {
  taskCount: number
  connected: boolean
  repos: string[]
  repoFilter: string
  setRepoFilter: (v: string) => void
  searchQuery: string
  setSearchQuery: (v: string) => void
  searchRef: Ref<HTMLInputElement>
  showPanel: 'none' | 'suggestions' | 'agents'
  setShowPanel: (v: 'none' | 'suggestions' | 'agents') => void
  showFilters: boolean
  setShowFilters: (v: boolean) => void
  hasActiveFilters: boolean
  onSaveView: () => void
  selectMode: boolean
  setSelectMode: (v: boolean) => void
  viewMode: 'board' | 'list'
  setViewMode: (v: 'board' | 'list') => void
  compactMode: boolean
  setCompactMode: (v: boolean) => void
  onShowGraph: () => void
  onSeed: () => void
  onExport: (format: 'csv' | 'json') => void
  onShowCreate: () => void
}

export function BoardToolbar({
  taskCount, connected, repos, repoFilter, setRepoFilter,
  searchQuery, setSearchQuery, searchRef,
  showPanel, setShowPanel, showFilters, setShowFilters, hasActiveFilters,
  onSaveView, selectMode, setSelectMode,
  viewMode, setViewMode, compactMode, setCompactMode,
  onShowGraph, onSeed, onExport, onShowCreate,
}: BoardToolbarProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
          Board
          <span className="text-xs px-1.5 py-0.5 rounded-full bg-white/5 text-[var(--color-muted)] font-normal">{taskCount}</span>
          {connected ? (
            <span className="flex items-center gap-1 text-xs text-emerald-400 font-normal">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block animate-pulse" />
              LIVE
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-amber-400 font-normal">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
              FALLBACK
            </span>
          )}
          <span className="text-[10px] text-[var(--color-muted)] font-normal hidden sm:inline">Drag cards between columns</span>
        </h1>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        {/* Repo filter */}
        {repos.length > 0 && (
          <select
            value={repoFilter}
            onChange={(e) => setRepoFilter(e.target.value)}
            className="text-xs px-2 py-1.5 rounded bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-muted-foreground)] appearance-none cursor-pointer"
          >
            <option value="">All repos</option>
            {repos.map(r => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        )}
        {/* Search */}
        <div className="relative flex-1 min-w-[120px] max-w-[200px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--color-muted)] pointer-events-none" />
          <input
            ref={searchRef}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tasks..."
            className="w-full pl-7 pr-2 py-1.5 text-xs rounded bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-muted-foreground)] placeholder:text-[var(--color-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
          />
        </div>
        {connected
          ? <Wifi className="w-3.5 h-3.5 text-emerald-400 hidden sm:block" />
          : <WifiOff className="w-3.5 h-3.5 text-amber-400 hidden sm:block" />
        }
        <button onClick={() => setShowPanel(showPanel === 'suggestions' ? 'none' : 'suggestions')}
          className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
            showPanel === 'suggestions' ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
          }`}
        ><Lightbulb className="w-3 h-3" /> Suggest</button>
        <button onClick={() => setShowFilters(!showFilters)}
          className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded transition-colors ${
            showFilters || hasActiveFilters
              ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]'
              : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
          }`}
        ><SlidersHorizontal className="w-3 h-3" /> Filters</button>
        <button onClick={onSaveView}
          className="flex items-center gap-1 text-xs px-2.5 py-1 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors"
          title="Save current filter as a view"
        ><Save className="w-3 h-3" /> Save</button>
        <button onClick={() => setShowPanel(showPanel === 'agents' ? 'none' : 'agents')}
          className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
            showPanel === 'agents' ? 'bg-cyan-500/20 text-cyan-400' : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
          }`}
        ><Users className="w-3 h-3" /> Agents</button>
        <button onClick={() => setSelectMode(!selectMode)}
          className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded transition-colors ${
            selectMode ? 'bg-amber-500/20 text-amber-400' : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
          }`}
        ><CheckSquare className="w-3 h-3" /> Select</button>
        <div className="flex items-center gap-0.5 bg-white/5 rounded-lg p-0.5 hidden sm:inline-flex">
          <button onClick={() => { setViewMode('board'); setCompactMode(false) }}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${
              viewMode === 'board' && !compactMode
                ? 'bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm'
                : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
            }`}
            title="Card view (detailed)"
            aria-label="Card view (detailed)"
          ><LayoutGrid className="w-3 h-3" /></button>
          <button onClick={() => { setViewMode('board'); setCompactMode(true) }}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${
              viewMode === 'board' && compactMode
                ? 'bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm'
                : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
            }`}
            title="Card view (compact)"
            aria-label="Card view (compact)"
          ><List className="w-3 h-3" /></button>
          <button onClick={() => setViewMode('list')}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${
              viewMode === 'list'
                ? 'bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm'
                : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
            }`}
            title="Table / list view"
            aria-label="Table / list view"
          ><List className="w-3 h-3" /></button>
        </div>
        <button onClick={onShowGraph}
          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-violet-500/15 text-violet-400 hover:bg-violet-500/30 transition-colors"
        ><Map className="w-3.5 h-3.5" /> Graph</button>
        <button onClick={onSeed}
          className="text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors hidden sm:inline-block"
        >Seed</button>
        <div className="relative group hidden sm:inline-block">
          <button className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors">
            <Download className="w-3 h-3" /> Export
          </button>
          <div className="absolute right-0 top-full mt-1 w-24 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <button onClick={() => onExport('csv')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-t-lg">CSV</button>
            <button onClick={() => onExport('json')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-b-lg">JSON</button>
          </div>
        </div>
        <button onClick={onShowCreate}
          className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
        ><Plus className="w-4 h-4" /> New</button>
      </div>
    </div>
  )
}
