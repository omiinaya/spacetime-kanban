import { useState, useEffect, useRef, useMemo } from 'react'
import { AlertCircle } from 'lucide-react'

import { api, type SuggestResult, type Agent, type KanbanLabel, type IssueLink } from '../api'
import { useRealtimeTasks, type TaskStatus } from '../hooks/useRealtimeTasks'
import KanbanColumn from '../components/KanbanColumn'
import { KanbanBoardSkeleton, ListViewSkeleton } from '../components/Skeleton'
import ListView from '../components/ListView'
import DependencyGraph from './DependencyGraph'
import { STATUS_COLUMNS, STATUS_LABELS } from '../components/constants'
import { CreateTaskDialog } from '../components/CreateTaskDialog'
import { TaskDetailDialog } from '../components/TaskDetailDialog'
import { BoardToolbar } from '../components/board/BoardToolbar'
import { AdvancedFilters } from '../components/board/AdvancedFilters'
import { SuggestionsPanel, AgentsPanel } from '../components/board/SidePanels'
import { BulkActionBar, type BatchAction } from '../components/board/BulkActionBar'
import { ShortcutsDialog, SavedViewsPills, SaveViewDialog } from '../components/board/BoardDialogs'
import { useSavedViews } from '../hooks/useSavedViews'
import { useTaskActions } from '../hooks/useTaskActions'
import { useBoardToasts } from '../hooks/useBoardToasts'

export default function BoardPage() {
  const { tasks, connected, loading } = useRealtimeTasks()
  const [showCreate, setShowCreate] = useState(false)
  const [repoFilter, setRepoFilter] = useState<string>('')
  const [mobileStatusTab, setMobileStatusTab] = useState<TaskStatus>('available')
  const [suggestions, setSuggestions] = useState<SuggestResult[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [showPanel, setShowPanel] = useState<'none' | 'suggestions' | 'agents'>('none')
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null)
  const [showGraph, setShowGraph] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)
  const [dropOnTaskId, setDropOnTaskId] = useState<string | null>(null)
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchProcessing, setBatchProcessing] = useState(false)
  const [showLabelPicker, setShowLabelPicker] = useState(false)
  const [selectedLabelIds, setSelectedLabelIds] = useState<Set<string>>(new Set())
  const [compactMode, setCompactMode] = useState(false)

  // Column collapse/expand state (stored per-column key in localStorage)
  const [collapsedColumns, setCollapsedColumns] = useState<Set<string>>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('kanban_collapsed_columns') || '[]')
      return new Set(stored)
    } catch { return new Set() }
  })

  // Column ordering state (stored in localStorage)
  const [columnOrder, setColumnOrder] = useState<string[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('kanban_column_order') || 'null')
      if (Array.isArray(stored) && stored.length === STATUS_COLUMNS.length &&
          stored.every((s: string) => STATUS_COLUMNS.includes(s as TaskStatus)))
        return stored
    } catch { /* ignore invalid stored value */ }
    return [...STATUS_COLUMNS]
  })

  // Column drag-reorder state
  const [draggedColumnIdx, setDraggedColumnIdx] = useState<number | null>(null)
  const [viewMode, setViewMode] = useState<'board' | 'list'>('list')
  const [showFilters, setShowFilters] = useState(false)
  const [filterPriorities, setFilterPriorities] = useState<Set<number>>(new Set())
  const [filterAssignees, setFilterAssignees] = useState<Set<string>>(new Set())
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set())
  const [allLabels, setAllLabels] = useState<KanbanLabel[]>([])
  const [taskLabelMap] = useState<Map<string, KanbanLabel[]>>(new Map())
  const [issueLinks, setIssueLinks] = useState<Record<string, IssueLink>>({})
  const [showShortcuts, setShowShortcuts] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)

  // ── Extracted hooks ──────────────────────────────────────────────
  const {
    savedViews, showSaveDialog, setShowSaveDialog,
    saveViewName, setSaveViewName,
    saveCurrentView, loadSavedView, deleteSavedView,
  } = useSavedViews(
    { searchQuery, repoFilter, filterPriorities, filterAssignees, filterLabels },
    { setSearchQuery, setRepoFilter, setFilterPriorities, setFilterAssignees, setFilterLabels, setShowFilters },
  )

  const toasts = useBoardToasts(tasks)

  // ── Filtering (needed before actions that reference `filtered`) ──
  const sorted = useMemo(() =>
    [...tasks].sort((a, b) => {
      const posA = a.position ?? 999999
      const posB = b.position ?? 999999
      return posA - posB || a.priority - b.priority || Number(b.createdAt - a.createdAt)
    }),
    [tasks]
  )
  const repoFiltered = useMemo(() =>
    repoFilter ? sorted.filter(t => t.repo === repoFilter) : sorted,
    [sorted, repoFilter]
  )
  const searchFiltered = useMemo(() =>
    searchQuery
      ? repoFiltered.filter(t =>
          t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.requiredSkills?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.repo?.toLowerCase().includes(searchQuery.toLowerCase()) ||
          t.id.toLowerCase().includes(searchQuery.toLowerCase())
        )
      : repoFiltered,
    [repoFiltered, searchQuery]
  )
  const filtered = useMemo(() =>
    searchFiltered.filter(t => {
      if (filterPriorities.size > 0 && !filterPriorities.has(t.priority)) return false
      if (filterAssignees.size > 0) {
        const taskAssignee = t.assignedTo || 'unassigned'
        if (!filterAssignees.has(taskAssignee)) return false
      }
      if (filterLabels.size > 0) {
        const taskLabels = taskLabelMap.get(t.id) || []
        const taskLabelIds = new Set(taskLabels.map(l => l.id))
        let hasMatch = false
        for (const lid of filterLabels) {
          if (taskLabelIds.has(lid)) { hasMatch = true; break }
        }
        if (!hasMatch) return false
      }
      return true
    }),
    [searchFiltered, filterPriorities, filterAssignees, filterLabels, taskLabelMap]
  )

  const {
    handleClaim, handleUnclaim, handleComplete, handleBlock,
    handleDelete, handleArchive, handleArchiveAll,
    handleSetDependency, handleSetSkills, handleQuickAdd,
    handleExport, dropTaskOnColumn,
  } = useTaskActions(tasks, filtered)

  // Persist collapsed columns + column order
  useEffect(() => {
    localStorage.setItem('kanban_collapsed_columns', JSON.stringify([...collapsedColumns]))
  }, [collapsedColumns])
  useEffect(() => {
    localStorage.setItem('kanban_column_order', JSON.stringify(columnOrder))
  }, [columnOrder])

  // Extract unique repos sorted by frequency
  const repos = [...new Set(tasks.map(t => t.repo).filter(Boolean))]
  repos.sort((a, b) => {
    const ca = tasks.filter(t => t.repo === a).length
    const cb = tasks.filter(t => t.repo === b).length
    return cb - ca
  })

  // ── Drag and drop ────────────────────────────────────────────────
  const handleDragStart = (taskId: string) => setDraggedTaskId(taskId)
  const handleDragEnd = () => {
    setDraggedTaskId(null)
    setDragOverColumn(null)
    setDropOnTaskId(null)
  }

  const handleDropOnColumn = async (targetStatus: TaskStatus) => {
    const taskId = draggedTaskId
    if (!taskId) return
    setDraggedTaskId(null)
    setDragOverColumn(null)
    await dropTaskOnColumn(taskId, targetStatus)
  }

  const handleDropOnTask = async (targetTaskId: string) => {
    const taskId = draggedTaskId
    if (!taskId || taskId === targetTaskId) return

    const task = tasks.find(t => t.id === taskId)
    const target = tasks.find(t => t.id === targetTaskId)
    if (!task || !target || task.status !== target.status) return

    setDraggedTaskId(null)
    setDragOverColumn(null)
    setDropOnTaskId(null)

    // Reorder all tasks in the same column with sequential positions
    const colTasks = filtered
      .filter(t => t.status === task.status)
      .sort((a, b) => (a.position ?? 999999) - (b.position ?? 999999) || a.priority - b.priority)

    const srcIdx = colTasks.findIndex(t => t.id === taskId)
    const dstIdx = colTasks.findIndex(t => t.id === targetTaskId)
    if (srcIdx < 0 || dstIdx < 0) return

    const reordered = colTasks.filter(t => t.id !== taskId)
    reordered.splice(dstIdx, 0, task)

    const items = reordered.map((t, i) => ({ task_id: t.id, position: i * 100 }))
    try {
      await api.tasks.bulkReorder(items)
    } catch (e: unknown) {
      console.error('Reorder failed:', e)
    }
  }

  // ── Selection / batch ────────────────────────────────────────────
  const toggleSelect = (taskId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) next.delete(taskId)
      else next.add(taskId)
      return next
    })
  }

  const selectAll = () => {
    if (selectedIds.size === filtered.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filtered.map(t => t.id)))
    }
  }

  const clearSelection = () => {
    setSelectedIds(new Set())
    setSelectMode(false)
  }

  const handleBatch = async (action: BatchAction) => {
    if (selectedIds.size === 0) return
    const label = action === 'delete' ? 'Delete' : action === 'block' ? 'Block' : action === 'unclaim' ? 'Release' : action === 'archive' ? 'Archive' : action.charAt(0).toUpperCase() + action.slice(1)
    if (!confirm(`${label} ${selectedIds.size} selected task(s)?`)) return
    setBatchProcessing(true)
    if (action === 'archive') {
      try {
        const res = await api.tasks.bulkArchive([...selectedIds])
        alert(`Archived ${res.archived}/${selectedIds.size} tasks${res.failed.length ? ` — ${res.failed.length} failed` : ''}`)
      } catch (e: unknown) {
        alert(`Archive failed: ${e instanceof Error ? e.message : String(e)}`)
      }
      setBatchProcessing(false)
      setSelectedIds(new Set())
      return
    }
    let done = 0
    const total = selectedIds.size
    for (const id of selectedIds) {
      try {
        if (action === 'claim') await api.tasks.claim(id, 'web-user')
        else if (action === 'complete') await api.tasks.complete(id)
        else if (action === 'block') await api.tasks.block(id, 'Batch blocked')
        else if (action === 'unclaim') await api.tasks.unclaim(id)
        else if (action === 'delete') await api.tasks.delete(id)
        done++
      } catch { /* skip failures */ }
    }
    setBatchProcessing(false)
    setSelectedIds(new Set())
    alert(`${label}d ${done}/${total} tasks`)
  }

  const handleBatchLabels = async (assign: boolean) => {
    if (selectedIds.size === 0 || selectedLabelIds.size === 0) return
    setBatchProcessing(true)
    try {
      if (assign) {
        await api.tasks.batch.labels([...selectedIds], [...selectedLabelIds])
      } else {
        await api.tasks.batch.unlabels([...selectedIds], [...selectedLabelIds])
      }
      setShowLabelPicker(false)
      setSelectedLabelIds(new Set())
    } catch (e: unknown) {
      alert(`Failed: ${e instanceof Error ? e.message : String(e)}`)
    }
    setBatchProcessing(false)
  }

  // ── Column collapse / reorder ────────────────────────────────────
  const toggleCollapse = (status: string) => {
    setCollapsedColumns(prev => {
      const next = new Set(prev)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  const handleColumnDragStart = (idx: number) => setDraggedColumnIdx(idx)
  const handleColumnDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    if (draggedColumnIdx === null || draggedColumnIdx === idx) return
    setColumnOrder(prev => {
      const next = [...prev]
      const [removed] = next.splice(draggedColumnIdx, 1)
      next.splice(idx, 0, removed)
      return next
    })
    setDraggedColumnIdx(idx)
  }
  const handleColumnDragEnd = () => setDraggedColumnIdx(null)

  // ── Polling effects ──────────────────────────────────────────────
  // Load suggestions and agents periodically — pause when tab hidden
  useEffect(() => {
    const load = async () => {
      if (document.hidden) return
      try {
        const [s, a] = await Promise.all([
          api.suggest.list({ limit: 3 }),
          api.agents.list(),
        ])
        setSuggestions(s)
        setAgents(a)
      } catch { /* silently ignore polling errors */ }
    }
    load()
    const interval = setInterval(load, 30000)
    const onVis = () => { if (document.hidden) clearInterval(interval) }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  // Load labels once (they rarely change)
  useEffect(() => {
    api.labels.list().then(setAllLabels).catch(() => { /* ignore */ })
  }, [])

  // Load issue links for board badges — 30s polling, skip when tab hidden
  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      if (document.hidden) return
      try {
        const links = await api.issues.list()
        const map: Record<string, IssueLink> = {}
        for (const link of links) {
          map[link.kanban_task_id] = link
        }
        setIssueLinks(map)
      } catch { /* silently ignore polling errors */ }
    }
    load()
    const interval = setInterval(load, 30000)
    return () => { clearInterval(interval); controller.abort() }
  }, [])

  // ── Keyboard shortcuts ───────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
        if (e.key === 'Escape') {
          (e.target as HTMLElement)?.blur()
        }
        return
      }

      switch (e.key) {
        case 'n':
          e.preventDefault()
          setShowCreate(true)
          break
        case 's':
        case '/':
          e.preventDefault()
          searchRef.current?.focus()
          break
        case 'c':
          e.preventDefault()
          if (viewMode === 'board' && !compactMode) {
            setCompactMode(true)
          } else if (viewMode === 'board' && compactMode) {
            setViewMode('list')
          } else {
            setViewMode('board')
            setCompactMode(false)
          }
          break
        case 'f':
          e.preventDefault()
          setShowFilters(prev => !prev)
          break
        case 'b':
          e.preventDefault()
          setSelectMode(prev => !prev)
          break
        case 'g':
          e.preventDefault()
          setShowGraph(prev => !prev)
          break
        case 'e':
          e.preventDefault()
          handleExport('csv', repoFilter)
          break
        case '1':
          setMobileStatusTab('available')
          break
        case '2':
          setMobileStatusTab('in_progress')
          break
        case '3':
          setMobileStatusTab('blocked')
          break
        case '4':
          setMobileStatusTab('done')
          break
        case '?':
          e.preventDefault()
          setShowShortcuts(true)
          break
        case 'Escape':
          if (showPanel !== 'none') {
            setShowPanel('none')
          } else if (showFilters) {
            setShowFilters(false)
          } else if (showCreate) {
            setShowCreate(false)
          } else if (detailTaskId) {
            setDetailTaskId(null)
          } else if (showGraph) {
            setShowGraph(false)
          } else if (selectMode) {
            setSelectMode(false)
          } else if (showShortcuts) {
            setShowShortcuts(false)
          }
          break
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  const columnProps = {
    compactMode, selectMode, selectedIds, taskLabelMap, issueLinks,
    draggedTaskId, dragOverColumn, dropOnTaskId,
    onToggleSelect: toggleSelect,
    onClaim: handleClaim, onComplete: handleComplete, onBlock: handleBlock,
    onUnclaim: handleUnclaim, onDelete: handleDelete, onArchive: handleArchive,
    onClick: (id: string) => setDetailTaskId(id),
    onDragStart: handleDragStart, onDragEnd: handleDragEnd,
    onDropOnColumn: handleDropOnColumn, onDropOnTask: handleDropOnTask,
    onSetDependency: handleSetDependency, onSetSkills: handleSetSkills,
    onQuickAdd: handleQuickAdd,
    setDragOverColumn, setDropOnTaskId,
  }

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6">
      <BoardToolbar
        taskCount={tasks.length}
        connected={connected}
        repos={repos}
        repoFilter={repoFilter}
        setRepoFilter={setRepoFilter}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        searchRef={searchRef}
        showPanel={showPanel}
        setShowPanel={setShowPanel}
        showFilters={showFilters}
        setShowFilters={setShowFilters}
        hasActiveFilters={filterPriorities.size > 0 || filterAssignees.size > 0 || filterLabels.size > 0}
        onSaveView={() => setShowSaveDialog(true)}
        selectMode={selectMode}
        setSelectMode={setSelectMode}
        viewMode={viewMode}
        setViewMode={setViewMode}
        compactMode={compactMode}
        setCompactMode={setCompactMode}
        onShowGraph={() => setShowGraph(true)}
        onSeed={() => api.tasks.seed()}
        onExport={(format) => handleExport(format, repoFilter)}
        onShowCreate={() => setShowCreate(true)}
      />

      <SavedViewsPills savedViews={savedViews} onLoad={loadSavedView} onDelete={deleteSavedView} />

      {showSaveDialog && (
        <SaveViewDialog
          name={saveViewName}
          setName={setSaveViewName}
          onSave={saveCurrentView}
          onClose={() => setShowSaveDialog(false)}
        />
      )}

      {showFilters && (
        <AdvancedFilters
          tasks={tasks}
          allLabels={allLabels}
          filterPriorities={filterPriorities}
          setFilterPriorities={setFilterPriorities}
          filterAssignees={filterAssignees}
          setFilterAssignees={setFilterAssignees}
          filterLabels={filterLabels}
          setFilterLabels={setFilterLabels}
        />
      )}

      {/* Live Toast Notifications */}
      {toasts.length > 0 && (
        <div className="fixed top-4 right-4 z-50 space-y-2 max-w-sm pointer-events-none">
          {toasts.map(t => (
            <div key={t.id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] shadow-lg text-sm pointer-events-auto transition-all"
            >
              <span className="text-lg">{t.emoji}</span>
              <span className="truncate text-[var(--color-foreground)]">{t.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* Loading state — skeleton matching current view mode */}
      {loading && (
        viewMode === 'list' ? <ListViewSkeleton /> : <KanbanBoardSkeleton />
      )}

      {/* Empty state — only show if NOT loading and no tasks match */}
      {!loading && !filtered.length && (
        <div className="flex items-center gap-2 text-sm p-3 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {searchQuery
            ? `No tasks match "${searchQuery}"`
            : 'No tasks found. Seed some sample data or create a new task.'}
        </div>
      )}

      {showPanel === 'suggestions' && (
        <SuggestionsPanel suggestions={suggestions} onClaim={(id) => handleClaim(id, 'web-user')} />
      )}

      {showPanel === 'agents' && <AgentsPanel agents={agents} />}

      {/* Mobile status tabs */}
      <div className="flex gap-1 overflow-x-auto sm:hidden">
        {STATUS_COLUMNS.map((status) => {
          const count = filtered.filter(t => t.status === status).length
          return (
            <button
              key={status}
              onClick={() => setMobileStatusTab(status)}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                mobileStatusTab === status
                  ? 'bg-white/10 text-[var(--color-foreground)]'
                  : 'bg-[var(--color-card)] text-[var(--color-muted)]'
              }`}
            >
              {STATUS_LABELS[status]}
              <span className="px-1 rounded bg-white/5 text-[var(--color-muted)]">{count}</span>
            </button>
          )
        })}
      </div>

      {/* Create Task Dialog */}
      {showCreate && (
        <CreateTaskDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => setShowCreate(false)}
        />
      )}

      {/* Task Detail Dialog */}
      {detailTaskId && (
        <TaskDetailDialog
          taskId={detailTaskId}
          tasks={tasks}
          allLabels={allLabels}
          taskLabelMap={taskLabelMap}
          onClose={() => setDetailTaskId(null)}
          onClaim={(id) => { handleClaim(id, 'web-user'); setDetailTaskId(null); }}
          onUnclaim={(id) => { handleUnclaim(id); setDetailTaskId(null); }}
          onComplete={(id) => { handleComplete(id); setDetailTaskId(null); }}
          onBlock={(id) => { handleBlock(id); setDetailTaskId(null); }}
          onDelete={(id) => { handleDelete(id); setDetailTaskId(null); }}
          onArchive={(id) => { handleArchive(id); setDetailTaskId(null); }}
          onSetDependency={(id) => { handleSetDependency(id); }}
          onSetSkills={(id) => { handleSetSkills(id); }}
        />
      )}

      {/* Kanban Columns — each column is its own component for stable hooks */}
      {viewMode === 'board' && (
        <div className="flex gap-4 h-full overflow-x-auto" style={{ maxHeight: 'calc(100vh - 140px)' }}>
          {columnOrder.map((status, idx) => {
            const colTasks = filtered.filter((t) => t.status === status)
            const isCollapsed = collapsedColumns.has(status)
            return (
              <div
                key={status}
                draggable
                onDragStart={() => handleColumnDragStart(idx)}
                onDragOver={(e) => handleColumnDragOver(e, idx)}
                onDragEnd={handleColumnDragEnd}
                className={`${isCollapsed ? 'flex-[0_0_60px] min-w-[60px] max-w-[60px]' : 'flex-[1_1_0] min-w-0'} ${draggedColumnIdx === idx ? 'opacity-50' : ''}`}
              >
                <KanbanColumn
                  key={status}
                  status={status as TaskStatus}
                  tasks={colTasks}
                  collapsed={isCollapsed}
                  onToggleCollapse={toggleCollapse}
                  onArchiveAll={handleArchiveAll}
                  {...columnProps}
                />
              </div>
            )
          })}
        </div>
      )}

      {/* List View mode */}
      {viewMode === 'list' && !loading && (() => {
        try {
          return (
            <ListView
              tasks={filtered}
              loading={loading}
              selectedIds={selectedIds}
              selectMode={selectMode}
              taskLabelMap={taskLabelMap}
              issueLinks={issueLinks}
              onToggleSelect={toggleSelect}
              onClaim={(id) => handleClaim(id, 'web-user')}
              onComplete={handleComplete}
              onBlock={handleBlock}
              onUnclaim={handleUnclaim}
              onDelete={handleDelete}
              onClick={(id) => setDetailTaskId(id)}
            />
          )
        } catch (e: unknown) {
          console.error('ListView crash:', e)
          return <div className="p-4 text-red-400 text-sm">List view error: {e instanceof Error ? e.message : String(e)}</div>
        }
      })()}

      {/* Mobile: single column for selected status using KanbanColumn (proper component = stable hooks) */}
      <div className="sm:hidden">
        <KanbanColumn
          status={mobileStatusTab}
          tasks={filtered.filter(t => t.status === mobileStatusTab)}
          collapsed={false}
          onToggleCollapse={() => {}}
          {...columnProps}
        />
      </div>

      {/* Dependency Graph Overlay */}
      {showGraph && (
        <DependencyGraph
          tasks={filtered}
          onSelectTask={(id) => { setDetailTaskId(id); setShowGraph(false) }}
          onClose={() => setShowGraph(false)}
        />
      )}

      {showShortcuts && <ShortcutsDialog onClose={() => setShowShortcuts(false)} />}

      {(selectMode || selectedIds.size > 0) && (
        <BulkActionBar
          selectedIds={selectedIds}
          filteredLength={filtered.length}
          batchProcessing={batchProcessing}
          allLabels={allLabels}
          showLabelPicker={showLabelPicker}
          setShowLabelPicker={setShowLabelPicker}
          selectedLabelIds={selectedLabelIds}
          setSelectedLabelIds={setSelectedLabelIds}
          onSelectAll={selectAll}
          onClearSelection={clearSelection}
          onBatch={handleBatch}
          onBatchLabels={handleBatchLabels}
        />
      )}
    </div>
  )
}
