import { useState, useEffect, useRef, useMemo } from 'react'
import { Plus, Loader2, AlertCircle, Trash2, Play, CheckCircle2,
  Ban, RotateCcw, ChevronDown, ChevronUp, Wifi, WifiOff, Link, Lightbulb,
  Users, Cpu, Info, History, GitBranch, ExternalLink, X, Search, Github, Download,
  CheckSquare, Square, LayoutGrid, List, SlidersHorizontal, Tag, Keyboard, Save, Bookmark,
  MessageSquare, Send
} from 'lucide-react'

interface SavedFilterView {
  id: string
  name: string
  searchQuery: string
  repoFilter: string
  filterPriorities: number[]
  filterAssignees: string[]
  filterLabels: string[]
}

import { api, type SuggestResult, type Agent, type Task as ApiTask, type KanbanLabel, type IssueLink, type TaskComment, type ChecklistItem } from '../api'
import { useRealtimeTasks, type TaskStatus, type Task } from '../hooks/useRealtimeTasks'
import KanbanColumn from '../components/KanbanColumn'
import { KanbanBoardSkeleton, ListViewSkeleton } from '../components/Skeleton'
import ListView from '../components/ListView'
import DependencyGraph from './DependencyGraph'
import { PRIORITY_LABELS, PRIORITY_COLORS, STATUS_COLUMNS, STATUS_LABELS, type TaskTemplate, BUILT_IN_TEMPLATES } from '../components/constants'
import { CreateTaskDialog } from '../components/CreateTaskDialog'
import { TaskDetailDialog } from '../components/TaskDetailDialog'

export default function BoardPage() {
  const { tasks, connected, error: stdbError, loading } = useRealtimeTasks()
  const [showCreate, setShowCreate] = useState(false)
  const [claiming, setClaiming] = useState<string | null>(null)
  const [repoFilter, setRepoFilter] = useState<string>('')
  const [mobileStatusTab, setMobileStatusTab] = useState<TaskStatus>('available')
  const [suggestions, setSuggestions] = useState<SuggestResult[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [showPanel, setShowPanel] = useState<'none' | 'suggestions' | 'agents'>('none')
  const [detailTaskId, setDetailTaskId] = useState<string | null>(null)
  const [showGraph, setShowGraph] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [toasts, setToasts] = useState<{ id: number; emoji: string; text: string }[]>([])
  const prevTasksRef = useRef<Task[]>([])
  const toastIdCounter = useRef(0)
  const [draggedTaskId, setDraggedTaskId] = useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null)
  const [dropOnTaskId, setDropOnTaskId] = useState<string | null>(null)
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchProcessing, setBatchProcessing] = useState(false)
  const [showLabelPicker, setShowLabelPicker] = useState(false)
  const [selectedLabelIds, setSelectedLabelIds] = useState<Set<string>>(new Set())
  // quick-add state moved to KanbanColumn component
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
          stored.every((s: string) => STATUS_COLUMNS.includes(s as any)))
        return stored
    } catch {}
    return [...STATUS_COLUMNS]
  })

  // Column drag-reorder state
  const [draggedColumnIdx, setDraggedColumnIdx] = useState<number | null>(null)
  const [viewMode, setViewMode] = useState<'board' | 'list'>('list')
  const [showFilters, setShowFilters] = useState(false)
  const [filterPriorities, setFilterPriorities] = useState<Set<number>>(new Set())
  const [filterAssignees, setFilterAssignees] = useState<Set<string>>(new Set())
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set())
  const [sprintFilter, setSprintFilter] = useState<string>('')
  const [allLabels, setAllLabels] = useState<KanbanLabel[]>([])
  const [taskLabelMap, setTaskLabelMap] = useState<Map<string, KanbanLabel[]>>(new Map())
  const [issueLinks, setIssueLinks] = useState<Record<string, IssueLink>>({})
  const [showShortcuts, setShowShortcuts] = useState(false)
  const searchRef = useRef<HTMLInputElement>(null)
  const [savedViews, setSavedViews] = useState<SavedFilterView[]>(() => {
    try { return JSON.parse(localStorage.getItem('kanban_saved_views') || '[]') }
    catch { return [] }
  })
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveViewName, setSaveViewName] = useState('')

  // Persist saved views to localStorage
  useEffect(() => {
    localStorage.setItem('kanban_saved_views', JSON.stringify(savedViews))
  }, [savedViews])

  // Persist collapsed columns to localStorage
  useEffect(() => {
    localStorage.setItem('kanban_collapsed_columns', JSON.stringify([...collapsedColumns]))
  }, [collapsedColumns])

  // Persist column order to localStorage
  useEffect(() => {
    localStorage.setItem('kanban_column_order', JSON.stringify(columnOrder))
  }, [columnOrder])

  const saveCurrentView = () => {
    const name = saveViewName.trim()
    if (!name) return
    const newView: SavedFilterView = {
      id: `view_${Date.now()}`,
      name,
      searchQuery,
      repoFilter,
      filterPriorities: [...filterPriorities],
      filterAssignees: [...filterAssignees],
      filterLabels: [...filterLabels],
    }
    setSavedViews(prev => [...prev, newView])
    setSaveViewName('')
    setShowSaveDialog(false)
  }

  const loadSavedView = (view: SavedFilterView) => {
    setSearchQuery(view.searchQuery)
    setRepoFilter(view.repoFilter)
    setFilterPriorities(new Set(view.filterPriorities))
    setFilterAssignees(new Set(view.filterAssignees))
    setFilterLabels(new Set(view.filterLabels))
    setShowFilters(true)
  }

  const deleteSavedView = (id: string) => {
    setSavedViews(prev => prev.filter(v => v.id !== id))
  }

  // Build a lookup map: taskId -> task title
  const taskTitleMap = new Map(tasks.map(t => [t.id, t.title]))

  // Extract unique repos sorted by frequency
  const repos = [...new Set(tasks.map(t => t.repo).filter(Boolean))]
  repos.sort((a, b) => {
    const ca = tasks.filter(t => t.repo === a).length
    const cb = tasks.filter(t => t.repo === b).length
    return cb - ca
  })

  const handleClaim = async (taskId: string, agentId: string) => {
    setClaiming(taskId)
    try {
      await api.tasks.claim(taskId, agentId)
      // STDB subscription will push the update — no manual refresh needed
    } catch (e: any) {
      alert(`Claim failed: ${e.message}`)
    } finally {
      setClaiming(null)
    }
  }

  const handleUnclaim = async (taskId: string) => {
    try {
      await api.tasks.unclaim(taskId)
    } catch (e: any) {
      alert(`Unclaim failed: ${e.message}`)
    }
  }

  const handleComplete = async (taskId: string) => {
    try {
      await api.tasks.complete(taskId, 'Done via web UI')
    } catch (e: any) {
      alert(`Complete failed: ${e.message}`)
    }
  }

  const handleBlock = async (taskId: string) => {
    const reason = prompt('Block reason:')
    if (reason === null) return
    try {
      await api.tasks.block(taskId, reason || 'Blocked')
    } catch (e: any) {
      alert(`Block failed: ${e.message}`)
    }
  }

  const handleDragStart = (taskId: string) => {
    setDraggedTaskId(taskId)
  }

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

    const task = tasks.find(t => t.id === taskId)
    if (!task || task.status === targetStatus) return

    try {
      switch (targetStatus) {
        case 'available':
          if (task.status === 'in_progress' || task.status === 'blocked') {
            await api.tasks.unclaim(taskId)
          }
          break
        case 'in_progress':
          if (task.status === 'available') {
            await api.tasks.claim(taskId, 'web-user')
          }
          break
        case 'blocked':
          if (task.status !== 'blocked') {
            await api.tasks.block(taskId, 'Moved to blocked')
          }
          break
        case 'done':
          if (task.status === 'in_progress') {
            await api.tasks.complete(taskId)
          } else if (task.status === 'available') {
            await api.tasks.claim(taskId, 'web-user')
            await api.tasks.complete(taskId)
          }
          break
      }
    } catch (e: any) {
      alert(`Drop failed: ${e.message}`)
    }
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

    // Rebuild the array with the dragged card at the target position
    const reordered = colTasks.filter(t => t.id !== taskId)
    reordered.splice(dstIdx, 0, task)

    const items = reordered.map((t, i) => ({ task_id: t.id, position: i * 100 }))
    try {
      await api.tasks.bulkReorder(items)
    } catch (e: any) {
      console.error('Reorder failed:', e)
    }
  }

  const handleExport = (format: 'csv' | 'json') => {
    const url = api.tasks.export(format, repoFilter || undefined)
    window.open(url, '_blank')
  }

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

  const handleBatch = async (action: 'claim' | 'complete' | 'block' | 'unclaim' | 'delete') => {
    if (selectedIds.size === 0) return
    const label = action === 'delete' ? 'Delete' : action === 'block' ? 'Block' : action === 'unclaim' ? 'Release' : action.charAt(0).toUpperCase() + action.slice(1)
    if (!confirm(`${label} ${selectedIds.size} selected task(s)?`)) return
    setBatchProcessing(true)
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
    } catch (e: any) {
      alert(`Failed: ${e.message}`)
    }
    setBatchProcessing(false)
  }

  const handleQuickAdd = async (status: string, title: string) => {
    const trimmed = title.trim()
    if (!trimmed) return
    try {
      if (status === 'in_progress') {
        const result = await api.tasks.create({ title: trimmed })
        if (result.id) {
          await api.tasks.claim(result.id, 'web-user')
        }
      } else {
        await api.tasks.create({ title: trimmed, status })
      }
    } catch (e: any) {
      alert(`Create failed: ${e.message}`)
    }
  }

  const handleDelete = async (taskId: string) => {
    if (!confirm('Delete this task?')) return
    try {
      await api.tasks.delete(taskId)
    } catch (e: any) {
      alert(`Delete failed: ${e.message}`)
    }
  }

  const handleSetDependency = async (taskId: string) => {
    const depId = prompt('Enter the ID of the task this task depends on (leave empty to clear):')
    if (depId === null) return
    try {
      await api.tasks.setDependency(taskId, depId.trim())
    } catch (e: any) {
      alert(`Set dependency failed: ${e.message}`)
    }
  }

  const handleSetSkills = async (taskId: string) => {
    const skills = prompt('Enter required skills (comma-separated, e.g. rust,typescript,react):')
    if (skills === null) return
    try {
      await api.tasks.setSkills(taskId, skills.trim())
    } catch (e: any) {
      alert(`Set skills failed: ${e.message}`)
    }
  }

  // Toggle column collapse/expand
  const toggleCollapse = (status: string) => {
    setCollapsedColumns(prev => {
      const next = new Set(prev)
      if (next.has(status)) next.delete(status)
      else next.add(status)
      return next
    })
  }

  // Column drag reorder handlers
  const handleColumnDragStart = (idx: number) => {
    setDraggedColumnIdx(idx)
  }

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

  const handleColumnDragEnd = () => {
    setDraggedColumnIdx(null)
  }

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
      } catch {}
    }
    load()
    const interval = setInterval(load, 30000)
    const onVis = () => { if (document.hidden) clearInterval(interval) }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  // Load labels once (they rarely change)
  useEffect(() => {
    api.labels.list().then(setAllLabels).catch(() => {})
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
      } catch {}
    }
    load()
    const interval = setInterval(load, 30000)
    return () => { clearInterval(interval); controller.abort() }
  }, [])

  // Toast notifications for live task changes — single toast max, collapse burst
  useEffect(() => {
    const prev = prevTasksRef.current
    const prevMap = new Map(prev.map(t => [t.id, t]))

    let claimed = 0, created = 0, completed = 0, blocked = 0, released = 0
    for (const t of tasks) {
      const old = prevMap.get(t.id)
      if (!old) {
        created++
      } else if (old.status !== t.status || old.assignedTo !== t.assignedTo) {
        if (t.status === 'in_progress' && old.status === 'available') claimed++
        else if (t.status === 'done') completed++
        else if (t.status === 'blocked') blocked++
        else if (t.status === 'available' && old.status !== 'available') released++
      }
    }

    const total = claimed + created + completed + blocked + released
    if (total > 0) {
      const parts: string[] = []
      if (claimed) parts.push(`${claimed} claimed`)
      if (created) parts.push(`${created} created`)
      if (completed) parts.push(`${completed} done`)
      if (blocked) parts.push(`${blocked} blocked`)
      if (released) parts.push(`${released} released`)
      const text = parts.join(', ')
      const emoji = completed > 0 ? '✅' : claimed > created ? '👤' : '🆕'
      setToasts([{ id: ++toastIdCounter.current, emoji, text }])
    }

    prevTasksRef.current = tasks
  }, [tasks])

  // Auto-dismiss toasts after 3.5s
  useEffect(() => {
    if (toasts.length === 0) return
    const timer = setTimeout(() => setToasts([]), 3500)
    return () => clearTimeout(timer)
  }, [toasts])


  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger shortcuts when typing in inputs
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
          // Cycle: board(detailed) → board(compact) → list → board(detailed)
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
          // Focus export button area — we'll just open the first export
          handleExport('csv')
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

  const renderDependencyBadge = (depId: string | null | undefined) => {
    if (!depId) return null
    const depTitle = taskTitleMap.get(depId)
    return (
      <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400/80 font-medium truncate max-w-[180px]" title={depId}>
        ⬆ {depTitle || depId}
      </span>
    )
  }

  // Sort: position asc (nulls last), then priority asc, then createdAt desc
  const sorted = useMemo(() =>
    [...tasks].sort((a, b) => {
      const posA = a.position ?? 999999
      const posB = b.position ?? 999999
      return posA - posB || a.priority - b.priority || Number(b.createdAt - a.createdAt)
    }),
    [tasks]
  )
  // Filter: repo
  const repoFiltered = useMemo(() =>
    repoFilter ? sorted.filter(t => t.repo === repoFilter) : sorted,
    [sorted, repoFilter]
  )
  // Filter: search text
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
  // Filter: priority + assignee + labels
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

  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold flex items-center gap-2">
            Board
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-white/5 text-[var(--color-muted)] font-normal">{tasks.length}</span>
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
              showFilters || filterPriorities.size > 0 || filterAssignees.size > 0 || filterLabels.size > 0
                ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]'
                : 'bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10'
            }`}
          ><SlidersHorizontal className="w-3 h-3" /> Filters</button>
          <button onClick={() => setShowSaveDialog(true)}
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
            ><LayoutGrid className="w-3 h-3" /></button>
            <button onClick={() => { setViewMode('board'); setCompactMode(true) }}
              className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${
                viewMode === 'board' && compactMode
                  ? 'bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm'
                  : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
              }`}
              title="Card view (compact)"
            ><List className="w-3 h-3" /></button>
            <button onClick={() => setViewMode('list')}
              className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-[var(--color-card)] text-[var(--color-foreground)] shadow-sm'
                  : 'text-[var(--color-muted)] hover:text-[var(--color-foreground)]'
              }`}
              title="Table / list view"
            ><span className="text-[11px] font-mono font-bold">≡</span></button>
          </div>
          <button onClick={() => setShowGraph(true)}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-violet-500/15 text-violet-400 hover:bg-violet-500/30 transition-colors"
          ><span className="text-sm">🗺️</span> Graph</button>
          <button onClick={() => api.tasks.seed()}
            className="text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors hidden sm:inline-block"
          >Seed</button>
          <div className="relative group hidden sm:inline-block">
            <button className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors">
              <Download className="w-3 h-3" /> Export
            </button>
            <div className="absolute right-0 top-full mt-1 w-24 bg-[var(--color-card)] border border-[var(--color-border)] rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
              <button onClick={() => handleExport('csv')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-t-lg">CSV</button>
              <button onClick={() => handleExport('json')} className="w-full text-left text-xs px-3 py-2 hover:bg-white/5 transition-colors rounded-b-lg">JSON</button>
            </div>
          </div>
          <button onClick={() => setShowCreate(true)}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
          ><Plus className="w-4 h-4" /> New</button>
        </div>
      </div>

      {/* Saved Views Pills */}
      {savedViews.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Bookmark className="w-3 h-3 text-[var(--color-muted)]" />
          {savedViews.map(view => (
            <div key={view.id} className="group relative">
              <button
                onClick={() => loadSavedView(view)}
                className="text-xs px-2 py-1 rounded-full bg-[var(--color-card)] border border-[var(--color-border)] text-[var(--color-muted-foreground)] hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] transition-colors"
              >{view.name}</button>
              <button
                onClick={() => deleteSavedView(view.id)}
                className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-red-500/80 text-white opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                title="Delete view"
              ><X className="w-2 h-2" /></button>
            </div>
          ))}
        </div>
      )}

      {/* Save View Dialog */}
      {showSaveDialog && (
        <div className="relative">
          <div className="fixed inset-0 z-40" onClick={() => setShowSaveDialog(false)} />
          <div className="absolute left-0 z-50 mt-1 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 shadow-xl space-y-2">
            <p className="text-xs font-medium text-[var(--color-muted)]">Save current filters as</p>
            <input
              value={saveViewName}
              onChange={e => setSaveViewName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') saveCurrentView(); if (e.key === 'Escape') setShowSaveDialog(false) }}
              placeholder="View name..."
              autoFocus
              className="w-full px-2 py-1.5 text-xs rounded border border-[var(--color-border)] bg-[var(--color-background)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
            />
            <div className="flex items-center gap-2">
              <button onClick={saveCurrentView} disabled={!saveViewName.trim()}
                className="flex-1 text-xs px-2 py-1.5 rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
              >Save</button>
              <button onClick={() => setShowSaveDialog(false)}
                className="flex-1 text-xs px-2 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors"
              >Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Advanced Filters Bar */}
      {showFilters && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            {/* Priority filter */}
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Priority</p>
              <div className="flex flex-wrap gap-1.5">
                {[0, 1, 2, 3].map(p => {
                  const active = filterPriorities.has(p)
                  return (
                    <button key={p}
                      onClick={() => setFilterPriorities(prev => {
                        const next = new Set(prev)
                        next.has(p) ? next.delete(p) : next.add(p)
                        return next
                      })}
                      className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                        active
                          ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-white'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                      }`}
                    >
                      {active ? '✓ ' : ''}{PRIORITY_LABELS[p] || p}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Assignee filter */}
            <div className="space-y-1">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Assignee</p>
              <div className="flex flex-wrap gap-1.5">
                {['unassigned', ...new Set(tasks.map(t => t.assignedTo).filter(Boolean) as string[]) ].map(a => {
                  const active = filterAssignees.has(a)
                  return (
                    <button key={a}
                      onClick={() => setFilterAssignees(prev => {
                        const next = new Set(prev)
                        next.has(a) ? next.delete(a) : next.add(a)
                        return next
                      })}
                      className={`text-xs px-2 py-1 rounded-md border transition-colors ${
                        active
                          ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-white'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                      }`}
                    >
                      {active ? '✓ ' : ''}{a === 'unassigned' ? 'Unassigned' : a}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Label filter */}
            {allLabels.length > 0 && (
              <div className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Labels</p>
                <div className="flex flex-wrap gap-1.5">
                  {allLabels.map(lbl => {
                    const active = filterLabels.has(lbl.id)
                    return (
                      <button key={lbl.id}
                        onClick={() => setFilterLabels(prev => {
                          const next = new Set(prev)
                          next.has(lbl.id) ? next.delete(lbl.id) : next.add(lbl.id)
                          return next
                        })}
                        className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border transition-colors ${
                          active
                            ? 'border-white/50 text-white'
                            : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                        }`}
                        style={active ? { backgroundColor: lbl.color + '30', borderColor: lbl.color + '60' } : {}}
                      >
                        <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: lbl.color }} />
                        {active ? '✓ ' : ''}{lbl.name}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Clear filters */}
          {(filterPriorities.size > 0 || filterAssignees.size > 0 || filterLabels.size > 0) && (
            <div className="flex items-center justify-between pt-1 border-t border-[var(--color-border)]">
              <span className="text-xs text-[var(--color-muted)]">Active filters</span>
              <button
                onClick={() => { setFilterPriorities(new Set()); setFilterAssignees(new Set()); setFilterLabels(new Set()) }}
                className="text-xs px-2 py-1 rounded bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
              >Clear all filters</button>
            </div>
          )}
        </div>
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

      {/* Smart Suggestions Panel */}
      {showPanel === 'suggestions' && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Lightbulb className="w-3 h-3 text-amber-400" /> Smart Suggestions
            </h3>
            <span className="text-[10px] text-[var(--color-muted)]">Refreshes every 30s</span>
          </div>
          {suggestions.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No suggestions available. All tasks may be claimed or blocked.</p>
          ) : (
            <div className="space-y-1.5">
              {suggestions.map((s, i) => (
                <div key={i} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] hover:bg-white/[0.06] transition-colors cursor-pointer" onClick={() => handleClaim(s.task.id, 'web-user')}>
                  <span className="text-lg mt-0.5">{['🥇', '🥈', '🥉'][i] || '📋'}</span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium truncate">{s.task.title}</span>
                      <span className="text-xs px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted-foreground)] font-mono">{s.score}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[11px] text-[var(--color-muted)] mt-0.5">
                      <span className={`px-1 py-0.25 rounded text-[10px] ${PRIORITY_COLORS[s.task.priority] || ''}`}>
                        {PRIORITY_LABELS[s.task.priority] || s.task.priority}
                      </span>
                      <span>{s.reason}</span>
                      {s.task.required_skills && <span className="text-cyan-400">Skills: {s.task.required_skills}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Agent Panel */}
      {showPanel === 'agents' && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] flex items-center gap-1">
              <Users className="w-3 h-3 text-cyan-400" /> Swarm Agents
            </h3>
            <span className="text-[10px] text-[var(--color-muted)]">{agents.length} agent(s)</span>
          </div>
          {agents.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)]">No agents registered. Run <code className="px-1 py-0.5 rounded bg-white/10">kanban register --capabilities=...</code> to join the swarm.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {agents.map((a) => {
                const isOnline = a.status === 'online' || a.status === 'busy'
                const agentAge = Math.floor((Date.now() - a.last_heartbeat) / 1000)
                const isStale = agentAge > 60
                return (
                  <div key={a.id} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] border border-[var(--color-border)]">
                    <div className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${isStale ? 'bg-red-500' : isOnline ? 'bg-emerald-400' : 'bg-slate-500'}`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium truncate">{a.id}</span>
                        {a.repo_focus && <span className="text-[10px] px-1 py-0.5 rounded bg-white/10 text-[var(--color-muted)]">{a.repo_focus}</span>}
                      </div>
                      {a.capabilities && (
                        <div className="flex flex-wrap gap-1 mt-0.5">
                          {a.capabilities.split(',').map((c, j) => (
                            <span key={j} className="text-[10px] px-1 py-0.25 rounded bg-cyan-500/10 text-cyan-400/80">{c.trim()}</span>
                          ))}
                        </div>
                      )}
                      <div className="text-[10px] text-[var(--color-muted)] mt-0.5">
                        {a.host} · {isStale ? 'stale' : a.status} · {Math.floor(agentAge / 60)}m ago
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

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
          taskTitleMap={taskTitleMap}
          allLabels={allLabels}
          taskLabelMap={taskLabelMap}
          onClose={() => setDetailTaskId(null)}
          onClaim={(id) => { handleClaim(id, 'web-user'); setDetailTaskId(null); }}
          onUnclaim={(id) => { handleUnclaim(id); setDetailTaskId(null); }}
          onComplete={(id) => { handleComplete(id); setDetailTaskId(null); }}
          onBlock={(id) => { handleBlock(id); setDetailTaskId(null); }}
          onDelete={(id) => { handleDelete(id); setDetailTaskId(null); }}
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
                  status={status}
                  tasks={colTasks}
                  compactMode={compactMode}
                  selectMode={selectMode}
                  selectedIds={selectedIds}
                  taskLabelMap={taskLabelMap}
                  issueLinks={issueLinks}
                  draggedTaskId={draggedTaskId}
                  dragOverColumn={dragOverColumn}
                  dropOnTaskId={dropOnTaskId}
                  collapsed={isCollapsed}
                  onToggleCollapse={toggleCollapse}
                  onToggleSelect={toggleSelect}
                  onClaim={handleClaim}
                  onComplete={handleComplete}
                  onBlock={handleBlock}
                  onUnclaim={handleUnclaim}
                  onDelete={handleDelete}
                  onClick={(id) => setDetailTaskId(id)}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                  onDropOnColumn={handleDropOnColumn}
                  onDropOnTask={handleDropOnTask}
                  onSetDependency={handleSetDependency}
                  onSetSkills={handleSetSkills}
                  onQuickAdd={handleQuickAdd}
                  setDragOverColumn={setDragOverColumn}
                  setDropOnTaskId={setDropOnTaskId}
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
              allLabels={allLabels}
              onToggleSelect={toggleSelect}
              onClaim={(id) => handleClaim(id, 'web-user')}
              onComplete={handleComplete}
              onBlock={handleBlock}
              onUnclaim={handleUnclaim}
              onDelete={handleDelete}
              onClick={(id) => setDetailTaskId(id)}
            />
          )
        } catch (e: any) {
          console.error('ListView crash:', e)
          return <div className="p-4 text-red-400 text-sm">List view error: {e.message}</div>
        }
      })()}

      {/* Mobile: single column for selected status using KanbanColumn (proper component = stable hooks) */}
      <div className="sm:hidden">
        <KanbanColumn
          status={mobileStatusTab}
          tasks={filtered.filter(t => t.status === mobileStatusTab)}
          compactMode={compactMode}
          selectMode={selectMode}
          selectedIds={selectedIds}
          taskLabelMap={taskLabelMap}
          issueLinks={issueLinks}
          draggedTaskId={draggedTaskId}
          dragOverColumn={dragOverColumn}
          dropOnTaskId={dropOnTaskId}
          onToggleSelect={toggleSelect}
          onClaim={handleClaim}
          onComplete={handleComplete}
          onBlock={handleBlock}
          onUnclaim={handleUnclaim}
          onDelete={handleDelete}
          onClick={(id) => setDetailTaskId(id)}
          onDragStart={handleDragStart}
          onDragEnd={handleDragEnd}
          onDropOnColumn={handleDropOnColumn}
          onDropOnTask={handleDropOnTask}
          onSetDependency={handleSetDependency}
          onSetSkills={handleSetSkills}
          onQuickAdd={handleQuickAdd}
          setDragOverColumn={setDragOverColumn}
          setDropOnTaskId={setDropOnTaskId}
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

      {/* Keyboard Shortcuts Help */}
      {showShortcuts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowShortcuts(false)}>
          <div className="w-full max-w-md bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 space-y-4" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold flex items-center gap-2"><Keyboard className="w-4 h-4" /> Keyboard Shortcuts</h3>
              <button onClick={() => setShowShortcuts(false)} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
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
      )}

      {/* Bulk Action Bar */}
      {(selectMode || selectedIds.size > 0) && (
        <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-[var(--color-border)] bg-[var(--color-card)]/95 backdrop-blur-sm px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button onClick={selectAll} className="text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors">
              {selectedIds.size === filtered.length ? 'Deselect all' : 'Select all'}
            </button>
            <span className="text-xs text-[var(--color-muted)]">
              {selectedIds.size} of {filtered.length} selected
            </span>
            <button onClick={clearSelection} className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-white/5 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors">
              <X className="w-3 h-3" /> Clear
            </button>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => handleBatch('claim')}
              disabled={batchProcessing}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors disabled:opacity-40"
            ><Play className="w-3 h-3" /> Claim</button>
            <button onClick={() => handleBatch('complete')}
              disabled={batchProcessing}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-40"
            ><CheckCircle2 className="w-3 h-3" /> Complete</button>
            <button onClick={() => handleBatch('block')}
              disabled={batchProcessing}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors disabled:opacity-40"
            ><Ban className="w-3 h-3" /> Block</button>
            <button onClick={() => handleBatch('unclaim')}
              disabled={batchProcessing}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors disabled:opacity-40"
            ><RotateCcw className="w-3 h-3" /> Release</button>
            <button onClick={() => handleBatch('delete')}
              disabled={batchProcessing}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-40"
            ><Trash2 className="w-3 h-3" /> Delete</button>
            {/* Labels button */}
            <div className="relative">
              <button
                onClick={() => { setShowLabelPicker(!showLabelPicker); if (!showLabelPicker) setSelectedLabelIds(new Set()) }}
                disabled={batchProcessing}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-violet-500/20 text-violet-400 hover:bg-violet-500/30 transition-colors disabled:opacity-40"
              ><Tag className="w-3 h-3" /> Labels</button>
              {showLabelPicker && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowLabelPicker(false)} />
                  <div className="absolute bottom-full right-0 mb-2 z-50 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 shadow-xl space-y-2">
                    <p className="text-xs font-medium text-[var(--color-muted)]">Assign labels to {selectedIds.size} task(s)</p>
                    {allLabels.length === 0 ? (
                      <p className="text-xs text-[var(--color-muted)]">No labels exist.</p>
                    ) : (
                      <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                        {allLabels.map(lbl => (
                          <button
                            key={lbl.id}
                            onClick={() => {
                              const next = new Set(selectedLabelIds)
                              if (next.has(lbl.id)) next.delete(lbl.id)
                              else next.add(lbl.id)
                              setSelectedLabelIds(next)
                            }}
                            className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                              selectedLabelIds.has(lbl.id)
                                ? 'border-transparent text-white font-medium'
                                : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                            }`}
                            style={selectedLabelIds.has(lbl.id) ? { backgroundColor: lbl.color } : {}}
                          >{lbl.name}</button>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2 pt-1 border-t border-[var(--color-border)]">
                      <button
                        onClick={() => handleBatchLabels(true)}
                        disabled={selectedLabelIds.size === 0 || batchProcessing}
                        className="flex-1 text-xs px-2 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors disabled:opacity-40"
                      >Assign</button>
                      <button
                        onClick={() => handleBatchLabels(false)}
                        disabled={selectedLabelIds.size === 0 || batchProcessing}
                        className="flex-1 text-xs px-2 py-1.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-40"
                      >Remove</button>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

