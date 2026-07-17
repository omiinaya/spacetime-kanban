import { useState, useEffect } from 'react'

export interface SavedFilterView {
  id: string
  name: string
  searchQuery: string
  repoFilter: string
  filterPriorities: number[]
  filterAssignees: string[]
  filterLabels: string[]
}

interface ViewState {
  searchQuery: string
  repoFilter: string
  filterPriorities: Set<number>
  filterAssignees: Set<string>
  filterLabels: Set<string>
}

interface ViewSetters {
  setSearchQuery: (v: string) => void
  setRepoFilter: (v: string) => void
  setFilterPriorities: (v: Set<number>) => void
  setFilterAssignees: (v: Set<string>) => void
  setFilterLabels: (v: Set<string>) => void
  setShowFilters: (v: boolean) => void
}

export function useSavedViews(current: ViewState, setters: ViewSetters) {
  const [savedViews, setSavedViews] = useState<SavedFilterView[]>(() => {
    try { return JSON.parse(localStorage.getItem('kanban_saved_views') || '[]') }
    catch { return [] }
  })
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [saveViewName, setSaveViewName] = useState('')

  useEffect(() => {
    localStorage.setItem('kanban_saved_views', JSON.stringify(savedViews))
  }, [savedViews])

  const saveCurrentView = () => {
    const name = saveViewName.trim()
    if (!name) return
    const newView: SavedFilterView = {
      id: `view_${Date.now()}`,
      name,
      searchQuery: current.searchQuery,
      repoFilter: current.repoFilter,
      filterPriorities: [...current.filterPriorities],
      filterAssignees: [...current.filterAssignees],
      filterLabels: [...current.filterLabels],
    }
    setSavedViews(prev => [...prev, newView])
    setSaveViewName('')
    setShowSaveDialog(false)
  }

  const loadSavedView = (view: SavedFilterView) => {
    setters.setSearchQuery(view.searchQuery)
    setters.setRepoFilter(view.repoFilter)
    setters.setFilterPriorities(new Set(view.filterPriorities))
    setters.setFilterAssignees(new Set(view.filterAssignees))
    setters.setFilterLabels(new Set(view.filterLabels))
    setters.setShowFilters(true)
  }

  const deleteSavedView = (id: string) => {
    setSavedViews(prev => prev.filter(v => v.id !== id))
  }

  return {
    savedViews, showSaveDialog, setShowSaveDialog,
    saveViewName, setSaveViewName,
    saveCurrentView, loadSavedView, deleteSavedView,
  }
}
