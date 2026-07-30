import { useState, useEffect, useRef, useMemo } from 'react'
import { AlertCircle } from 'lucide-react'

import { api, type SuggestResult, type Agent, type KanbanLabel, type IssueLink } from '../api'
import { useRealtimeTasks, type TaskStatus } from '../hooks/useRealtimeTasks'
import KanbanColumn from '../components/KanbanColumn'
import { KanbanBoardSkeleton, ListViewSkeleton } from '../components/Skeleton'
import ListView from '../components/ListView'
import { ErrorBoundary } from '../components/ErrorBoundary'
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
import { useToast } from '../hooks/useToast'
import { useConfirm } from '../components/ConfirmDialog'
import { useBoardShortcuts } from '../hooks/useBoardShortcuts'
import { useColumnReorder } from '../hooks/useColumnReorder'

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

  // ── Column collapse/reorder (extracted hook) ──────────────────────
  const {
    collapsedColumns, toggleCollapse,
    columnOrder, draggedColumnIdx,
    handleColumnDragStart, handleColumnDragOver, handleColumnDragEnd,
  } = useColumnReorder()
  const [viewMode, setViewMode] = useState<'board' | 'list'>('list')
  const [showFilters, setShowFilters] = useState(false)
  const [filterPriorities, setFilterPriorities] = useState<Set<number>>(new Set())
  const [filterAssignees, setFilterAssignees] = useState<Set<string>>(new Set())
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set())
  const [allLabels, setAllLabels] = useState<KanbanLabel[]>([])
  const [taskLabelMap, setTaskLabelMap] = useState<Map<string, KanbanLabel[]>>(new Map())
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
  const { addToast } = useToast()
  const { confirm } = useConfirm()

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
      addToast('❌', `Reorder failed: ${e instanceof Error ? e.message : String(e)}`)
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
    const ok = await confirm({ title: `${label} Tasks`, message: `${label} ${selectedIds.size} selected task(s)?`, confirmLabel: label, variant: action === 'delete' ? 'danger' : 'warning' })
    if (!ok) return
    setBatchProcessing(true)
    if (action === 'archive') {
      try {
        const res = await api.tasks.bulkArchive([...selectedIds])
        addToast('✅', `Archived ${res.archived}/${selectedIds.size} tasks${res.failed.length ? ` — ${res.failed.length} failed` : ''}`)
      } catch (e: unknown) {
        addToast('❌', `Archive failed: ${e instanceof Error ? e.message : String(e)}`)
      }
      setBatchProcessing(false)
      setSelectedIds(new Set())
      return
    }
    // Use single bulk endpoint instead of N sequential calls
    try {
      const payload: Record<string, string> = {}
      if (action === 'claim') payload.agent_id = 'web-user'
      else if (action === 'block') payload.reason = 'Batch blocked'
      else if (action === 'complete') payload.result_notes = 'Batch completed'
      const res = await api.tasks.bulk(action, [...selectedIds], payload)
      const done = res.results.filter(r => r.status !== 'error').length
      const failed = res.results.filter(r => r.status === 'error')
      if (failed.length > 0) {
        addToast('⚠️', `${label}d ${done}/${selectedIds.size} tasks — ${failed.length} failed (${failed[0].error || 'unknown error'})`)
      } else {
        addToast('✅', `${label}d ${done}/${selectedIds.size} tasks`)
      }
    } catch (e: unknown) {
      addToast('❌', `Batch ${action} failed: ${e instanceof Error ? e.message : String(e)}`)
    }
    setBatchProcessing(false)
    setSelectedIds(new Set())
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
      addToast('❌', `Failed: ${e instanceof Error ? e.message : String(e)}`)
    }
    setBatchProcessing(false)
  }

  // ── Column collapse / reorder (handled by useColumnReorder hook) ──

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

  // Load task-label assignments for filtering and badge display
  useEffect(() => {
    api.labels.assignments().then((data) => {
      const map = new Map<string, KanbanLabel[]>()
      for (const [taskId, labels] of Object.entries(data)) {
        map.set(taskId, labels)
      }
      setTaskLabelMap(map)
    }).catch(() => { /* ignore */ })
  }, [])

  // Load issue links for board badges — 30s polling, skip when tab hidden
  useEffect(() => {
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
    return () => { clearInterval(interval) }
  }, [])

  // ── Keyboard shortcuts (extracted hook) ──────────────────────────
  useBoardShortcuts({
    searchRef,
    viewMode, setViewMode, compactMode, setCompactMode,
    setShowCreate, setShowFilters, setSelectMode, setShowGraph,
    setShowShortcuts, setMobileStatusTab,
    handleExport, repoFilter,
    showPanel, setShowPanel,
    showFilters, showCreate, detailTaskId, setDetailTaskId,
    showGraph, selectMode, showShortcuts,
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
        <ErrorBoundary>
          <DependencyGraph
            tasks={filtered}
            onSelectTask={(id) => { setDetailTaskId(id); setShowGraph(false) }}
            onClose={() => setShowGraph(false)}
          />
        </ErrorBoundary>
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
