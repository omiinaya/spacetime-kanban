import { useState, useEffect } from 'react'
import { STATUS_COLUMNS } from '../components/constants'
import type { TaskStatus } from './useRealtimeTasks'

interface UseColumnReorderReturn {
  collapsedColumns: Set<string>
  toggleCollapse: (status: string) => void
  columnOrder: string[]
  draggedColumnIdx: number | null
  handleColumnDragStart: (idx: number) => void
  handleColumnDragOver: (e: React.DragEvent, idx: number) => void
  handleColumnDragEnd: () => void
}

export function useColumnReorder(): UseColumnReorderReturn {
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

  // Persist collapsed columns + column order
  useEffect(() => {
    localStorage.setItem('kanban_collapsed_columns', JSON.stringify([...collapsedColumns]))
  }, [collapsedColumns])
  useEffect(() => {
    localStorage.setItem('kanban_column_order', JSON.stringify(columnOrder))
  }, [columnOrder])

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

  return {
    collapsedColumns,
    toggleCollapse,
    columnOrder,
    draggedColumnIdx,
    handleColumnDragStart,
    handleColumnDragOver,
    handleColumnDragEnd,
  }
}
