import { useEffect, useState, useRef } from 'react'
import { DbConnection } from '../stdb'
import type { Task, TaskLog } from '../stdb/types'
import { api } from '../api'

export type { Task, TaskLog }
export type TaskStatus = 'available' | 'in_progress' | 'done' | 'blocked'

/**
 * React hook that subscribes to the SpacetimeDB tasks table in real-time.
 *
 * Uses STDB's built-in WebSocket subscription: when any reducer modifies
 * the tasks table (claim, complete, etc.), the client cache updates
 * instantly and React re-renders. No polling.
 */
export function useRealtimeTasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const connRef = useRef<DbConnection | null>(null)

  useEffect(() => {
    let cancelled = false

    function connect() {
      try {
        const conn = DbConnection.builder()
          .withUri(`ws://${window.location.hostname}:3001`)
          .withDatabaseName('spacetimedb-kanban')
          .onConnect(() => {
            if (cancelled) return
            setConnected(true)
            setError(null)
          })
          .onConnectError((_ctx: any, err: Error) => {
            if (cancelled) return
            console.warn('STDB WebSocket connection failed:', err.message)
            setConnected(false)
            setError(`STDB connection failed: ${err.message}`)
          })
          .onDisconnect((_ctx: any, err?: Error) => {
            if (cancelled) return
            console.warn('STDB WebSocket disconnected:', err?.message)
            setConnected(false)
          })
          .build()

        connRef.current = conn

        // Subscribe to all tasks — STDB pushes changes instantly
        conn.subscriptionBuilder()
          .onApplied(() => {
            if (!cancelled) syncFromCache(conn)
          })
          .subscribe('SELECT * FROM tasks')

        // Register for live row-level updates
        conn.db.tasks.onInsert(() => {
          if (!cancelled) syncFromCache(conn)
        })
        conn.db.tasks.onUpdate(() => {
          if (!cancelled) syncFromCache(conn)
        })
        conn.db.tasks.onDelete(() => {
          if (!cancelled) syncFromCache(conn)
        })
      } catch (e: any) {
        if (!cancelled) {
          console.error('STDB connection error:', e)
          setConnected(false)
          setError(`STDB connection failed: ${e.message}`)
        }
      }
    }

    function syncFromCache(conn: DbConnection) {
      try {
        const all = Array.from(conn.db.tasks.iter()) as Task[]
        setTasks(all)
      } catch (e: any) {
        console.warn('Failed to sync from STDB cache:', e.message)
      }
    }

    connect()

    return () => {
      cancelled = true
    }
  }, [])

  return { tasks, connected, error }
}
