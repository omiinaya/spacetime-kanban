import { useState, useCallback, useEffect, useRef } from 'react'
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

import { api, type SuggestResult, type Agent, type Task as ApiTask, type KanbanLabel, type IssueLink, type TaskComment } from '../api'
import { useRealtimeTasks, type TaskStatus, type Task } from '../hooks/useRealtimeTasks'
import DependencyGraph from './DependencyGraph'
import { Link as RouterLink } from 'react-router-dom'

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Urgent',
  1: 'High',
  2: 'Medium',
  3: 'Low',
}

const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-red-500/20 text-red-400',
  1: 'bg-orange-500/20 text-orange-400',
  2: 'bg-blue-500/20 text-blue-400',
  3: 'bg-slate-500/20 text-slate-400',
}

const STATUS_COLUMNS: TaskStatus[] = ['available', 'in_progress', 'blocked', 'done']
const STATUS_LABELS: Record<string, string> = {
  available: 'Available',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  done: 'Done',
}

export default function BoardPage() {
  const { tasks, connected, error: stdbError } = useRealtimeTasks()
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
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [batchProcessing, setBatchProcessing] = useState(false)
  const [showLabelPicker, setShowLabelPicker] = useState(false)
  const [selectedLabelIds, setSelectedLabelIds] = useState<Set<string>>(new Set())
  const [quickAddStatus, setQuickAddStatus] = useState<string | null>(null)
  const [quickAddTitle, setQuickAddTitle] = useState('')
  const quickAddRef = useRef<HTMLInputElement>(null)
  const [compactMode, setCompactMode] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [filterPriorities, setFilterPriorities] = useState<Set<number>>(new Set())
  const [filterAssignees, setFilterAssignees] = useState<Set<string>>(new Set())
  const [filterLabels, setFilterLabels] = useState<Set<string>>(new Set())
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

  const handleQuickAdd = async (status: string) => {
    const title = quickAddTitle.trim()
    if (!title) { setQuickAddStatus(null); return }
    try {
      if (status === 'in_progress') {
        // Create as available, then claim
        const result = await api.tasks.create({ title })
        if (result.id) {
          await api.tasks.claim(result.id, 'web-user')
        }
      } else {
        await api.tasks.create({ title, status })
      }
      setQuickAddStatus(null)
      setQuickAddTitle('')
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

  // Load suggestions and agents periodically
  useEffect(() => {
    const load = async () => {
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
    return () => clearInterval(interval)
  }, [])

  // Load labels and task-label assignments
  useEffect(() => {
    const load = async () => {
      try {
        const lbls = await api.labels.list()
        setAllLabels(lbls)

        // Build label map: for each label, find which tasks use it
        const map = new Map<string, KanbanLabel[]>()
        await Promise.all(lbls.map(async (lbl) => {
          try {
            const labelTasks = await api.tasks.list({ label: lbl.id })
            for (const t of labelTasks) {
              const existing = map.get(t.id) || []
              existing.push(lbl)
              map.set(t.id, existing)
            }
          } catch {}
        }))
        setTaskLabelMap(map)
      } catch {}
    }
    load()
    const interval = setInterval(load, 60000)
    return () => clearInterval(interval)
  }, [])

  // Load issue links for board badges
  useEffect(() => {
    const load = async () => {
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
    return () => clearInterval(interval)
  }, [])

  // Toast notifications for live task changes
  useEffect(() => {
    const prev = prevTasksRef.current
    const prevMap = new Map(prev.map(t => [t.id, t]))

    const added: typeof toasts = []
    for (const t of tasks) {
      const old = prevMap.get(t.id)
      if (!old) {
        // New task created
        added.push({ id: ++toastIdCounter.current, emoji: '🆕', text: `"${t.title}" created` })
      } else if (old.status !== t.status || old.assignedTo !== t.assignedTo) {
        if (t.status === 'in_progress' && old.status === 'available') {
          added.push({ id: ++toastIdCounter.current, emoji: '👤', text: `"${t.title}" claimed by ${t.assignedTo || 'web-user'}` })
        } else if (t.status === 'done') {
          added.push({ id: ++toastIdCounter.current, emoji: '✅', text: `"${t.title}" completed` })
        } else if (t.status === 'blocked') {
          added.push({ id: ++toastIdCounter.current, emoji: '🚧', text: `"${t.title}" blocked` })
        } else if (t.status === 'available' && old.status !== 'available') {
          added.push({ id: ++toastIdCounter.current, emoji: '↩️', text: `"${t.title}" released` })
        }
      }
    }

    if (added.length > 0) {
      setToasts(prev => [...prev, ...added].slice(-5))  // max 5 visible
    }

    prevTasksRef.current = tasks
  }, [tasks])

  // Auto-dismiss toasts after 3.5s
  useEffect(() => {
    if (toasts.length === 0) return
    const timer = setTimeout(() => setToasts([]), 3500)
    return () => clearTimeout(timer)
  }, [toasts])

  // Auto-focus quick-add input
  useEffect(() => {
    if (quickAddStatus && quickAddRef.current) {
      quickAddRef.current.focus()
    }
  }, [quickAddStatus])

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
          setCompactMode(prev => !prev)
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

  const renderTaskCard = (task: Task) => {
    const priorityColor = ({0: 'border-l-red-500', 1: 'border-l-orange-400', 2: 'border-l-blue-400', 3: 'border-l-slate-400'} as Record<number, string>)[task.priority] || 'border-l-slate-400'

    if (compactMode) {
      // Compact card: minimal info, colored left border, title only
      return (
        <div key={task.id}
          draggable
          onDragStart={() => handleDragStart(task.id)}
          onDragEnd={handleDragEnd}
          onClick={() => setDetailTaskId(task.id)}
          className={`bg-[var(--color-card)] rounded border-l-4 border border-[var(--color-border)] py-1.5 px-2 cursor-pointer hover:border-[var(--color-ring)] transition-colors flex items-center gap-2 ${
            priorityColor
          } ${
            draggedTaskId === task.id ? 'opacity-50' : ''
          }`}
        >
          {selectMode && (
            <button
              onClick={(e) => { e.stopPropagation(); toggleSelect(task.id) }}
              className="flex-shrink-0 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            >
              {selectedIds.has(task.id)
                ? <CheckSquare className="w-3.5 h-3.5 text-[var(--color-primary)]" />
                : <Square className="w-3.5 h-3.5" />
              }
            </button>
          )}
          <div className="min-w-0 flex-1 flex items-center gap-2">
            <span className="text-sm font-medium truncate">{task.title}</span>
            {task.assignedTo && (
              <span className="text-[10px] text-[var(--color-muted)] flex-shrink-0">@{task.assignedTo}</span>
            )}
            {task.repo && (
              <span className="text-[10px] px-1 py-0.5 rounded bg-white/8 text-[var(--color-muted)] font-medium flex-shrink-0">{task.repo}</span>
            )}
            {renderDependencyBadge(task.dependsOn)}
            {/* Label dots on compact cards */}
            {(taskLabelMap.get(task.id) || []).map(lbl => (
              <span key={lbl.id} className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: lbl.color }} title={lbl.name} />
            ))}
            {/* Issue badge on compact card */}
            {issueLinks[task.id] && (() => {
              const link = issueLinks[task.id]
              const closed = link.html_url?.includes('closed') || link.status === 'closed'
              return (
                <span className={`text-[10px] px-1 py-0.5 rounded font-medium flex-shrink-0 ${closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                  #{link.issue_number}
                </span>
              )
            })()}
          </div>
          <div className="flex items-center gap-0.5 flex-shrink-0">
            {task.status === 'available' && (
              <button onClick={(e) => { e.stopPropagation(); handleClaim(task.id, 'web-user') }}
                className="text-xs px-1.5 py-0.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors">Claim</button>
            )}
            {task.status === 'in_progress' && (
              <>
                <button onClick={(e) => { e.stopPropagation(); handleComplete(task.id) }}
                  className="text-xs px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors">Done</button>
                <button onClick={(e) => { e.stopPropagation(); handleBlock(task.id) }}
                  className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors">Block</button>
              </>
            )}
            {task.status === 'blocked' && (
              <button onClick={(e) => { e.stopPropagation(); handleUnclaim(task.id) }}
                className="text-xs px-1.5 py-0.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors">Release</button>
            )}
            {task.status === 'done' && (
              <button onClick={(e) => { e.stopPropagation(); handleDelete(task.id) }}
                className="text-xs px-1.5 py-0.5 rounded text-red-400 hover:bg-red-500/20 transition-colors">Del</button>
            )}
          </div>
        </div>
      )
    }

    // Detailed card (default)
    return (
    <div key={task.id}
      draggable
      onDragStart={() => handleDragStart(task.id)}
      onDragEnd={handleDragEnd}
      onClick={() => setDetailTaskId(task.id)}
      className={`bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2 cursor-pointer hover:border-[var(--color-ring)] transition-colors ${
        draggedTaskId === task.id ? 'opacity-50 ring-2 ring-[var(--color-primary)]' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {selectMode && (
            <button
              onClick={(e) => { e.stopPropagation(); toggleSelect(task.id) }}
              className="flex-shrink-0 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            >
              {selectedIds.has(task.id)
                ? <CheckSquare className="w-4 h-4 text-[var(--color-primary)]" />
                : <Square className="w-4 h-4" />
              }
            </button>
          )}
          <span className={`text-xs px-1.5 py-0.5 rounded font-medium whitespace-nowrap ${PRIORITY_COLORS[task.priority] || ''}`}>
            {PRIORITY_LABELS[task.priority] || task.priority}
          </span>
        </div>
        {task.assignedTo && (
          <span className="text-xs text-[var(--color-muted)] truncate max-w-[100px]">
            {task.assignedTo}
          </span>
        )}
      </div>

      <p className="text-sm font-medium leading-snug">{task.title}</p>

      {task.description && (
        <p className="text-xs text-[var(--color-muted-foreground)] line-clamp-2">{task.description}</p>
      )}

      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        {task.repo && (
          <span className="px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)] font-medium">
            {task.repo}
          </span>
        )}
        {task.branch && <span className="text-blue-400 truncate max-w-[120px]">:{task.branch}</span>}
        {task.roadmapItem && <span className="text-purple-400/70 truncate">{task.roadmapItem}</span>}
        {renderDependencyBadge(task.dependsOn)}
        {task.requiredSkills && (
          <span className="px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400/80 font-medium truncate max-w-[140px]" title={`Skills: ${task.requiredSkills}`}>
            <Cpu className="w-3 h-3 inline mr-0.5" />{task.requiredSkills}
          </span>
        )}
        {/* Issue badge on detailed card */}
        {issueLinks[task.id] && (() => {
          const link = issueLinks[task.id]
          const closed = link.html_url?.includes('closed') || link.status === 'closed'
          return (
            <a href={link.html_url} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium hover:opacity-80 transition-opacity ${
                closed ? 'bg-purple-500/20 text-purple-400' : 'bg-emerald-500/20 text-emerald-400'
              }`}
            >
              <Github className="w-2.5 h-2.5" /> {link.repo.split('/').pop()}#{link.issue_number}
            </a>
          )
        })()}
        {/* Label badges */}
        {(taskLabelMap.get(task.id) || []).map(lbl => (
          <span key={lbl.id} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium truncate max-w-[100px]"
            style={{ backgroundColor: lbl.color + '20', color: lbl.color, border: `1px solid ${lbl.color}40` }}>
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: lbl.color }} />
            {lbl.name}
          </span>
        ))}
      </div>

      <div className="flex items-center gap-1 pt-1 border-t border-[var(--color-border)]">
        {task.status === 'available' && (
          <>
            <button onClick={() => handleClaim(task.id, 'web-user')}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
            ><Play className="w-3 h-3" /> Claim</button>
            <button onClick={() => handleSetDependency(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
            ><Link className="w-3 h-3" /> Dep</button>
            <button onClick={() => handleSetSkills(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
            ><Cpu className="w-3 h-3" /> Skills</button>
            <button onClick={() => handleDelete(task.id)}
              className="text-xs px-2 py-1 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
            ><Trash2 className="w-3 h-3" /></button>
          </>
        )}
        {task.status === 'in_progress' && (
          <>
            <button onClick={() => handleComplete(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
            ><CheckCircle2 className="w-3 h-3" /> Done</button>
            <button onClick={() => handleBlock(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
            ><Ban className="w-3 h-3" /> Block</button>
            <button onClick={() => handleUnclaim(task.id)}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors ml-auto"
            ><RotateCcw className="w-3 h-3" /></button>
          </>
        )}
        {task.status === 'blocked' && (
          <button onClick={() => handleUnclaim(task.id)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
          ><RotateCcw className="w-3 h-3" /> Release</button>
        )}
        {task.status === 'done' && (
          <button onClick={() => handleDelete(task.id)}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
          ><Trash2 className="w-3 h-3" /> Delete</button>
        )}
      </div>
    </div>
    )
  }

  // Sort: priority asc, then createdAt desc
  const sorted = [...tasks].sort((a, b) => a.priority - b.priority || Number(b.createdAt - a.createdAt))
  // Filter: repo
  const repoFiltered = repoFilter ? sorted.filter(t => t.repo === repoFilter) : sorted
  // Filter: search text
  const searchFiltered = searchQuery
    ? repoFiltered.filter(t =>
        t.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.description?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.requiredSkills?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.repo?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        t.id.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : repoFiltered
  // Filter: priority + assignee + labels
  const filtered = searchFiltered.filter(t => {
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
  })

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
          <button onClick={() => setCompactMode(!compactMode)}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded bg-white/5 text-[var(--color-muted-foreground)] hover:bg-white/10 transition-colors hidden sm:inline-flex"
            title={compactMode ? 'Detailed view' : 'Compact view'}
          >
            {compactMode ? <LayoutGrid className="w-3 h-3" /> : <List className="w-3 h-3" />}
          </button>
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

      {(stdbError || !filtered.length) && !stdbError && (
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

      {/* Kanban Columns — single for mobile, 2 for tablet, 4 for desktop */}
      <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STATUS_COLUMNS.map((status) => {
          const colTasks = filtered.filter((t) => t.status === status)
          const isOver = dragOverColumn === status && draggedTaskId !== null
          return (
            <div key={status} className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
                  {STATUS_LABELS[status]}
                </h2>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setQuickAddStatus(quickAddStatus === status ? null : status)}
                    className="p-0.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
                    title={`Add task to ${STATUS_LABELS[status]}`}
                  ><Plus className="w-3.5 h-3.5" /></button>
                  <span className="text-xs px-1.5 py-0.5 rounded-full bg-[var(--color-card)] text-[var(--color-muted)]">
                    {colTasks.length}
                  </span>
                </div>
              </div>
              {quickAddStatus === status && (
                <div className="flex items-center gap-1.5">
                  <input
                    ref={quickAddRef}
                    value={quickAddTitle}
                    onChange={e => setQuickAddTitle(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleQuickAdd(status)
                      if (e.key === 'Escape') { setQuickAddStatus(null); setQuickAddTitle('') }
                    }}
                    placeholder="Task title..."
                    className="flex-1 px-2 py-1 text-xs rounded border border-[var(--color-border)] bg-[var(--color-background)] placeholder:text-[var(--color-muted)] focus:outline-none focus:border-[var(--color-primary)]"
                  />
                  <button
                    onClick={() => handleQuickAdd(status)}
                    disabled={!quickAddTitle.trim()}
                    className="px-2 py-1 text-xs rounded bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40"
                  >Add</button>
                </div>
              )}
              <div
                className={`space-y-2 min-h-[120px] rounded-lg transition-colors ${
                  isOver ? 'bg-white/5 ring-2 ring-[var(--color-primary)] border-2 border-dashed border-[var(--color-primary)]' : ''
                }`}
                onDragOver={(e) => { e.preventDefault(); setDragOverColumn(status) }}
                onDragEnter={(e) => { e.preventDefault(); setDragOverColumn(status) }}
                onDragLeave={() => setDragOverColumn(null)}
                onDrop={() => handleDropOnColumn(status)}
              >
                {colTasks.map(renderTaskCard)}
                {colTasks.length === 0 && (
                  <div className={`text-center py-6 text-xs border border-dashed rounded-lg transition-colors ${
                    isOver
                      ? 'text-[var(--color-primary)] border-[var(--color-primary)] bg-white/5'
                      : 'text-[var(--color-muted)] border-[var(--color-border)]'
                  }`}>
                    {isOver ? 'Drop here' : 'Empty'}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Mobile: single column for selected status */}
      <div className="sm:hidden space-y-2">
        {filtered.filter(t => t.status === mobileStatusTab).map(renderTaskCard)}
        {filtered.filter(t => t.status === mobileStatusTab).length === 0 && (
          <div className="text-center py-12 text-sm text-[var(--color-muted)]">
            No {STATUS_LABELS[mobileStatusTab].toLowerCase()} tasks
            {repoFilter ? ` in ${repoFilter}` : ''}
          </div>
        )}
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

interface TaskTemplate {
  name: string
  title: string
  description: string
  priority: number
  repo: string
  roadmap: string
  skills: string
  icon: string
}

const BUILT_IN_TEMPLATES: TaskTemplate[] = [
  { name: 'Bug Fix', title: 'Fix: ', description: [
    '## Steps to Reproduce',
    '1. ',
    '2. ',
    '',
    '## Expected Behavior',
    '',
    '## Actual Behavior',
  ].join('\n'), priority: 0, repo: '', roadmap: '', skills: '', icon: '🐛' },
  { name: 'Feature', title: 'Add ', description: [
    '## Description',
    '',
    '## Acceptance Criteria',
    '- [ ] ',
    '- [ ] ',
    '',
    '## Implementation Notes',
  ].join('\n'), priority: 1, repo: '', roadmap: '', skills: '', icon: '✨' },
  { name: 'Refactor', title: 'Refactor ', description: [
    '## Motivation',
    '',
    '## Changes',
    '',
    '## Risk Assessment',
    '## ',
  ].join('\n'), priority: 2, repo: '', roadmap: '', skills: '', icon: '🔧' },
  { name: 'Chore/Task', title: '', description: '', priority: 2, repo: '', roadmap: '', skills: '', icon: '📋' },
  { name: 'Documentation', title: 'Document ', description: [
    '## What',
    '',
    '## Why',
    '',
    '## Who',
  ].join('\n'), priority: 3, repo: '', roadmap: '', skills: '', icon: '📝' },
  { name: 'Performance', title: 'Optimize ', description: [
    '## Current State',
    '',
    '## Benchmarks',
    '',
    '## Expected Gain',
  ].join('\n'), priority: 0, repo: '', roadmap: '', skills: '', icon: '⚡' },
  { name: 'Security', title: 'Security: ', description: [
    '## Vulnerability',
    '',
    '## Impact',
    '',
    '## Fix',
  ].join('\n'), priority: 0, repo: '', roadmap: '', skills: '', icon: '🔒' },
]

function CreateTaskDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.tasks.create({
        title: title.trim(),
        description,
        priority,
        repo,
        roadmap_item: roadmap,
        required_skills: skills,
      })
      onCreated()
    } catch (e: any) {
      alert(`Create failed: ${e.message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">New Task</h3>
          <button onClick={onClose} className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <ChevronDown className="w-4 h-4" />
          </button>
        </div>

        {/* Template selector */}
        <div className="flex flex-wrap gap-1.5 pb-2 border-b border-[var(--color-border)]">
          {BUILT_IN_TEMPLATES.map(tpl => (
            <button
              key={tpl.name}
              onClick={() => applyTemplate(tpl)}
              className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                selectedTemplate?.name === tpl.name
                  ? 'bg-[var(--color-primary)]/15 border-[var(--color-primary)]/30 text-[var(--color-primary)]'
                  : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)] hover:text-[var(--color-foreground)]'
              }`}
            >{tpl.icon} {tpl.name}</button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Task title"
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            autoFocus
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            rows={3}
            className="w-full px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] resize-none"
          />
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <select
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value))}
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm"
            >
              <option value={0}>Urgent</option>
              <option value={1}>High</option>
              <option value={2}>Medium</option>
              <option value={3}>Low</option>
            </select>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="Repo slug"
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <input
              value={roadmap}
              onChange={(e) => setRoadmap(e.target.value)}
              placeholder="Roadmap item"
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
            <input
              value={skills}
              onChange={(e) => setSkills(e.target.value)}
              placeholder="Skills (e.g. rust,python)"
              className="px-3 py-2 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)]"
            />
          </div>
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
  )
}

function TaskDetailDialog({
  taskId, tasks, taskTitleMap, onClose,
  onClaim, onUnclaim, onComplete, onBlock, onDelete,
  onSetDependency, onSetSkills,
  allLabels = [], taskLabelMap = new Map(),
}: {
  taskId: string
  tasks: Task[]
  taskTitleMap: Map<string, string>
  onClose: () => void
  onClaim: (id: string) => void
  onUnclaim: (id: string) => void
  onComplete: (id: string) => void
  onBlock: (id: string) => void
  onDelete: (id: string) => void
  onSetDependency: (id: string) => void
  onSetSkills: (id: string) => void
  allLabels?: KanbanLabel[]
  taskLabelMap?: Map<string, KanbanLabel[]>
}) {
  const [logs, setLogs] = useState<any[]>([])
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [issueLink, setIssueLink] = useState<{ html_url: string; issue_number: number; repo: string; status?: string } | null>(null)
  const [loadingIssue, setLoadingIssue] = useState(true)
  const [currentLabelIds, setCurrentLabelIds] = useState<Set<string>>(new Set())
  const [labelSaving, setLabelSaving] = useState(false)

  // ── Comments state ─────────────────────────────────────────────────
  const [comments, setComments] = useState<TaskComment[]>([])
  const [loadingComments, setLoadingComments] = useState(true)
  const [newComment, setNewComment] = useState('')
  const [sendingComment, setSendingComment] = useState(false)

  const task = tasks.find(t => t.id === taskId)
  const downstream = tasks.filter(t => t.dependsOn === taskId)
  const upstream = task?.dependsOn ? tasks.find(t => t.id === task.dependsOn) : null
  const blockedByDep = task?.dependsOn && tasks.find(t => t.id === task.dependsOn)?.status !== 'done'

  useEffect(() => {
    let cancelled = false
    setLoadingLogs(true)
    api.logs.list({ task_id: taskId, limit: 20 }).then(l => {
      if (!cancelled) { setLogs(l); setLoadingLogs(false) }
    }).catch(() => { if (!cancelled) setLoadingLogs(false) })
    return () => { cancelled = true }
  }, [taskId])

  useEffect(() => {
    let cancelled = false
    setLoadingIssue(true)
    api.issues.get(taskId).then(link => {
      if (!cancelled) { setIssueLink(link); setLoadingIssue(false) }
    }).catch(() => { if (!cancelled) setLoadingIssue(false) })
    return () => { cancelled = true }
  }, [taskId])

  // Initialize label IDs from taskLabelMap
  useEffect(() => {
    const labels = taskLabelMap.get(taskId) || []
    setCurrentLabelIds(new Set(labels.map(l => l.id)))
  }, [taskId, taskLabelMap])

  // Load comments
  useEffect(() => {
    let cancelled = false
    setLoadingComments(true)
    api.comments.list(taskId).then(c => {
      if (!cancelled) { setComments(c); setLoadingComments(false) }
    }).catch(() => { if (!cancelled) setLoadingComments(false) })
    return () => { cancelled = true }
  }, [taskId])

  const handleAddComment = async () => {
    const text = newComment.trim()
    if (!text) return
    setSendingComment(true)
    try {
      const result = await api.comments.add(taskId, text, 'web-user')
      if (result.id) {
        setComments(prev => [...prev, {
          id: result.id,
          task_id: taskId,
          author: 'web-user',
          body: text,
          created_at: Date.now(),
        }])
        setNewComment('')
      }
    } catch (e: any) {
      alert(`Failed to add comment: ${e.message}`)
    } finally {
      setSendingComment(false)
    }
  }

  const toggleLabel = async (labelId: string) => {
    setLabelSaving(true)
    const next = new Set(currentLabelIds)
    if (next.has(labelId)) {
      next.delete(labelId)
    } else {
      next.add(labelId)
    }
    try {
      await api.labels.setForTask(taskId, { label_ids: [...next] })
      setCurrentLabelIds(next)
    } catch (e: any) {
      alert(`Failed to update labels: ${e.message}`)
    } finally {
      setLabelSaving(false)
    }
  }

  const actionIcons: Record<string, string> = {
    created: '🆕', claimed: '👤', unclaimed: '↩️', completed: '✅',
    blocked: '🚧', dependency_set: '🔗', skills_set: '🛠️',
    agent_registered: '🤖', agent_reconnected: '🔄',
  }

  if (!task) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6" onClick={e => e.stopPropagation()}>
        <p className="text-sm text-[var(--color-muted)]">Task not found. It may have been deleted.</p>
        <button onClick={onClose} className="mt-3 text-sm px-3 py-1.5 rounded bg-[var(--color-primary)] text-white">Close</button>
      </div>
    </div>
  )

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-8 sm:pt-16 pb-8 overflow-y-auto bg-black/50" onClick={onClose}>
      <div className="w-full max-w-2xl bg-[var(--color-card)] rounded-xl border border-[var(--color-border)]" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-4 sm:p-6 border-b border-[var(--color-border)]">
          <div className="min-w-0 space-y-2 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${PRIORITY_COLORS[task.priority] || ''}`}>
                {PRIORITY_LABELS[task.priority] || task.priority}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                task.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' :
                task.status === 'in_progress' ? 'bg-blue-500/20 text-blue-400' :
                task.status === 'blocked' ? 'bg-red-500/20 text-red-400' :
                'bg-slate-500/20 text-slate-400'
              }`}>{STATUS_LABELS[task.status]}</span>
              {task.repo && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-white/8 text-[var(--color-muted)]">{task.repo}</span>
              )}
              {task.score > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 font-mono">Score: {task.score}</span>
              )}
            </div>
            <h2 className="text-base sm:text-lg font-semibold leading-snug">{task.title}</h2>
          </div>
          <button onClick={onClose} className="flex-shrink-0 p-1 rounded hover:bg-white/10 transition-colors">
            <X className="w-4 h-4 text-[var(--color-muted)]" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 sm:p-6 space-y-4">
          {/* Description */}
          {task.description && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-1">Description</p>
              <p className="text-sm text-[var(--color-muted-foreground)]">{task.description}</p>
            </div>
          )}

          {/* Metadata grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">ID</p>
              <p className="text-xs font-mono text-[var(--color-muted-foreground)] truncate" title={task.id}>{task.id.slice(0, 28)}...</p>
            </div>
            {task.assignedTo && (
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Agent</p>
                <p className="text-xs text-[var(--color-foreground)]">{task.assignedTo}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Roadmap</p>
              <p className="text-xs text-[var(--color-muted-foreground)] truncate">{task.roadmapItem || '—'}</p>
            </div>
            {task.branch && (
              <div className="col-span-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Branch</p>
                <p className="text-xs font-mono text-blue-400 truncate"><GitBranch className="w-3 h-3 inline mr-0.5" />{task.branch}</p>
              </div>
            )}
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Created</p>
              <p className="text-xs text-[var(--color-muted-foreground)]">{new Date(Number(task.createdAt)).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Updated</p>
              <p className="text-xs text-[var(--color-muted-foreground)]">{new Date(Number(task.updatedAt)).toLocaleString()}</p>
            </div>
            {task.requiredSkills && (
              <div className="col-span-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-muted)]">Required Skills</p>
                <div className="flex flex-wrap gap-1 mt-0.5">
                  {task.requiredSkills.split(',').map((s: string, i: number) => (
                    <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-400"><Cpu className="w-2.5 h-2.5 inline mr-0.5" />{s.trim()}</span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Labels */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Tag className="w-3 h-3" /> Labels
            </p>
            {allLabels.length === 0 ? (
              <p className="text-xs text-[var(--color-muted)]">No labels defined. <RouterLink to="/labels" className="text-blue-400 hover:text-blue-300 underline underline-offset-2">Create labels</RouterLink> to organize tasks.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {allLabels.map(lbl => {
                  const active = currentLabelIds.has(lbl.id)
                  return (
                    <button key={lbl.id} onClick={() => toggleLabel(lbl.id)}
                      disabled={labelSaving}
                      className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-md border transition-all ${
                        active
                          ? 'border-white/50 text-white font-medium'
                          : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                      } disabled:opacity-50`}
                      style={active ? { backgroundColor: lbl.color + '30', borderColor: lbl.color + '60' } : {}}
                    >
                      <span className="w-2 h-2 rounded-full" style={{ backgroundColor: lbl.color }} />
                      {active ? '✓ ' : ''}{lbl.name}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          {/* GitHub Issue */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Github className="w-3 h-3" /> GitHub Issue
            </p>
            {loadingIssue ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
                <Loader2 className="w-3 h-3 animate-spin" /> Checking...
              </div>
            ) : issueLink ? (
              <div className="flex items-center gap-2 p-2 rounded bg-[var(--color-background)] border border-[var(--color-border)]">
                <Github className="w-4 h-4 text-[var(--color-muted)] shrink-0" />
                <span className="text-sm text-[var(--color-foreground)]">
                  <a href={issueLink.html_url} target="_blank" rel="noopener noreferrer"
                    className="text-blue-400 hover:text-blue-300 underline underline-offset-2">
                    {issueLink.repo}#{issueLink.issue_number}
                  </a>
                </span>
                <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                  issueLink.html_url.includes('closed') || issueLink.status === 'closed'
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-emerald-500/20 text-emerald-400'
                }`}>{issueLink.status}</span>
                <a href={issueLink.html_url} target="_blank" rel="noopener noreferrer"
                  className="text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <p className="text-xs text-[var(--color-muted)]">No GitHub issue linked</p>
                <button onClick={async () => {
                  const repo = task.repo || prompt('GitHub repo (owner/repo):')
                  if (!repo) return
                  const labels = prompt('Labels (optional, comma-separated):') || ''
                  try {
                    const result = await api.issues.create(task.id, repo, labels)
                    setIssueLink({ html_url: result.html_url, issue_number: result.issue_number, repo })
                  } catch (e: any) {
                    alert(`Failed to create issue: ${e.message}`)
                  }
                }}
                  className="text-xs px-2 py-1 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors ml-auto"
                >
                  <Plus className="w-3 h-3 inline mr-0.5" /> Create Issue
                </button>
              </div>
            )}
          </div>

          {/* Dependency Chain */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <Link className="w-3 h-3" /> Dependency Chain
            </p>
            <div className="space-y-1.5">
              {upstream && (
                <div className="flex items-center gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20">
                  <span className="text-xs text-amber-400 font-medium shrink-0">Depends on:</span>
                  <span className="text-sm truncate">{upstream.title}</span>
                  <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                    upstream.status === 'done' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                  }`}>{upstream.status}</span>
                </div>
              )}
              {!upstream && (
                <p className="text-xs text-[var(--color-muted)]">No dependencies — can be claimed freely</p>
              )}
              {downstream.length > 0 && (
                <div className="space-y-1 mt-2">
                  <p className="text-xs text-[var(--color-muted)]">Blocks {downstream.length} task(s):</p>
                  {downstream.slice(0, 5).map(dt => (
                    <div key={dt.id} className="flex items-center gap-2 p-1.5 rounded bg-white/[0.03]">
                      <span className="text-sm truncate">{dt.title}</span>
                      <span className={`text-[10px] px-1 py-0.5 rounded ml-auto ${
                        dt.status === 'blocked' ? 'bg-red-500/20 text-red-400' :
                        dt.status === 'available' ? 'bg-blue-500/20 text-blue-400' :
                        'bg-emerald-500/20 text-emerald-400'
                      }`}>{dt.status}</span>
                    </div>
                  ))}
                  {downstream.length > 5 && (
                    <p className="text-[10px] text-[var(--color-muted)]">...and {downstream.length - 5} more</p>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Activity Log */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <History className="w-3 h-3" /> Activity Log
            </p>
            {loadingLogs ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] py-2">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading...
              </div>
            ) : logs.length === 0 ? (
              <p className="text-xs text-[var(--color-muted)] py-2">No activity recorded.</p>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {logs.map((log: any) => (
                  <div key={log.id} className="flex items-start gap-2 py-1.5 border-b border-[var(--color-border)] last:border-0">
                    <span className="text-sm shrink-0">{actionIcons[log.action] || '📋'}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium capitalize">{log.action.replace(/_/g, ' ')}</span>
                        {log.agent_id && <span className="text-[10px] text-[var(--color-muted)]">by {log.agent_id}</span>}
                      </div>
                      {log.notes && <p className="text-[11px] text-[var(--color-muted-foreground)] truncate">{log.notes}</p>}
                    </div>
                    <span className="text-[10px] text-[var(--color-muted)] shrink-0">{new Date(log.timestamp).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Comments */}
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
              <MessageSquare className="w-3 h-3" /> Comments
            </p>
            {loadingComments ? (
              <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] py-2">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading...
              </div>
            ) : (
              <div className="space-y-2 max-h-60 overflow-y-auto mb-3">
                {comments.length === 0 ? (
                  <p className="text-xs text-[var(--color-muted)] py-1">No comments yet.</p>
                ) : (
                  comments.map(cmt => (
                    <div key={cmt.id} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] border border-[var(--color-border)]">
                      <div className="w-6 h-6 rounded-full bg-[var(--color-primary)]/20 text-[var(--color-primary)] flex items-center justify-center text-[10px] font-semibold shrink-0 mt-0.5">
                        {cmt.author.charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium">{cmt.author}</span>
                          <span className="text-[10px] text-[var(--color-muted)]">
                            {new Date(cmt.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="text-sm text-[var(--color-muted-foreground)] mt-0.5 whitespace-pre-wrap break-words">{cmt.body}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
            <div className="flex items-start gap-2">
              <textarea
                value={newComment}
                onChange={e => setNewComment(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    handleAddComment()
                  }
                }}
                placeholder="Add a comment... (Enter to send, Shift+Enter for newline)"
                rows={2}
                className="flex-1 px-3 py-2 text-xs rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] placeholder:text-[var(--color-muted)]"
              />
              <button
                onClick={handleAddComment}
                disabled={!newComment.trim() || sendingComment}
                className="flex items-center gap-1 text-xs px-3 py-2 rounded-lg bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
              >
                {sendingComment ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Action Footer */}
        <div className="flex items-center gap-2 p-4 sm:p-6 border-t border-[var(--color-border)]">
          {task.status === 'available' && (
            <>
              <button onClick={() => onClaim(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors"
              ><Play className="w-3 h-3" /> Claim</button>
              <button onClick={() => onSetDependency(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/15 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Link className="w-3 h-3" /> Set Dep</button>
              <button onClick={() => onSetSkills(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-cyan-500/15 text-cyan-400 hover:bg-cyan-500/30 transition-colors"
              ><Cpu className="w-3 h-3" /> Set Skills</button>
              <button onClick={() => { if (confirm('Delete this task?')) onDelete(task.id) }}
                className="text-xs px-3 py-1.5 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
              ><Trash2 className="w-3 h-3" /> Delete</button>
            </>
          )}
          {task.status === 'in_progress' && (
            <>
              <button onClick={() => onComplete(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors"
              ><CheckCircle2 className="w-3 h-3" /> Complete</button>
              <button onClick={() => onBlock(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors"
              ><Ban className="w-3 h-3" /> Block</button>
              <button onClick={() => onUnclaim(task.id)}
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors ml-auto"
              ><RotateCcw className="w-3 h-3" /> Release</button>
            </>
          )}
          {task.status === 'blocked' && (
            <button onClick={() => onUnclaim(task.id)}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
            ><RotateCcw className="w-3 h-3" /> Release back to available</button>
          )}
          {task.status === 'done' && (
            <button onClick={() => { if (confirm('Delete this task?')) onDelete(task.id) }}
              className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-red-400 hover:bg-red-500/20 transition-colors ml-auto"
            ><Trash2 className="w-3 h-3" /> Delete</button>
          )}
        </div>
      </div>
    </div>
  )
}
