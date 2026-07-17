import { useEffect, useRef, useState } from 'react'
import type { Task } from './useRealtimeTasks'

interface Toast {
  id: number
  emoji: string
  text: string
}

/** Live toast notifications for task state changes (single toast, burst-collapsed). */
export function useBoardToasts(tasks: Task[]) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const prevTasksRef = useRef<Task[]>([])
  const toastIdCounter = useRef(0)

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

  // Auto-dismiss after 3.5s
  useEffect(() => {
    if (toasts.length === 0) return
    const timer = setTimeout(() => setToasts([]), 3500)
    return () => clearTimeout(timer)
  }, [toasts])

  return toasts
}
