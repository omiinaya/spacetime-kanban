import { useEffect, type RefObject } from 'react'
import type { TaskStatus } from './useRealtimeTasks'

interface UseBoardShortcutsOptions {
  searchRef: RefObject<HTMLInputElement | null>
  viewMode: 'board' | 'list'
  setViewMode: (v: 'board' | 'list') => void
  compactMode: boolean
  setCompactMode: (v: boolean) => void
  setShowCreate: (v: boolean) => void
  setShowFilters: (v: boolean | ((prev: boolean) => boolean)) => void
  setSelectMode: (v: boolean | ((prev: boolean) => boolean)) => void
  setShowGraph: (v: boolean | ((prev: boolean) => boolean)) => void
  setShowShortcuts: (v: boolean) => void
  setMobileStatusTab: (v: TaskStatus) => void
  handleExport: (format: 'csv' | 'json', repoFilter: string) => void
  repoFilter: string
  showPanel: 'none' | 'suggestions' | 'agents'
  setShowPanel: (v: 'none' | 'suggestions' | 'agents') => void
  showFilters: boolean
  showCreate: boolean
  detailTaskId: string | null
  setDetailTaskId: (v: string | null) => void
  showGraph: boolean
  selectMode: boolean
  showShortcuts: boolean
}

export function useBoardShortcuts(options: UseBoardShortcutsOptions) {
  const {
    searchRef,
    viewMode,
    setViewMode,
    compactMode,
    setCompactMode,
    setShowCreate,
    setShowFilters,
    setSelectMode,
    setShowGraph,
    setShowShortcuts,
    setMobileStatusTab,
    handleExport,
    repoFilter,
    showPanel,
    setShowPanel,
    showFilters,
    showCreate,
    detailTaskId,
    setDetailTaskId,
    showGraph,
    selectMode,
    showShortcuts,
  } = options

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
          setShowFilters((prev: boolean) => !prev)
          break
        case 'b':
          e.preventDefault()
          setSelectMode((prev: boolean) => !prev)
          break
        case 'g':
          e.preventDefault()
          setShowGraph((prev: boolean) => !prev)
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
  }, [
    viewMode, compactMode, repoFilter, handleExport, searchRef,
    showPanel, showFilters, showCreate, detailTaskId, showGraph,
    selectMode, showShortcuts,
    setShowCreate, setShowFilters, setSelectMode, setShowGraph,
    setShowShortcuts, setMobileStatusTab, setShowPanel, setViewMode,
    setCompactMode, setDetailTaskId,
  ])
}
