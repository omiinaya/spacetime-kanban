import { useEffect, useState, useRef } from 'react'
import { DbConnection } from '../stdb'
import type { Task, TaskLog } from '../stdb/types'
import { api } from '../api'

export type { Task, TaskLog }
export type TaskStatus = 'available' | 'in_progress' | 'done' | 'blocked'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000, 30000]  // exponential backoff
const POLL_INTERVAL = 10000  // 10s — always polling as safety net

/**
 * React hook that subscribes to SpacetimeDB tasks in real-time.
 *
 * Uses STDB's built-in WebSocket subscription for instant updates.
 * Auto-reconnects on disconnect with exponential backoff.
 * Falls back to REST API polling when WebSocket is down.
 */
export function useRealtimeTasks() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)  // true until first data arrives
  const [error, setError] = useState<string | null>(null)
  const connRef = useRef<DbConnection | null>(null)
  const reconnectRef = useRef(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const cancelledRef = useRef(false)

  // REST API fallback poller — always running as safety net
  const syncFromApi = useRef(async () => {
    try {
      const data = await api.tasks.list()
      if (Array.isArray(data)) {
        // API returns snake_case, STDB uses camelCase — map fields
        const mapped = (data as unknown as any[]).map(d => ({
          id: d.id,
          title: d.title,
          description: d.description,
          priority: d.priority,
          status: d.status,
          assignedTo: d.assigned_to ?? undefined,
          repo: d.repo,
          branch: d.branch ?? undefined,
          roadmapItem: d.roadmap_item ?? '',
          createdBy: d.created_by ?? '',
          createdAt: d.created_at ?? Date.now(),
          updatedAt: d.updated_at ?? Date.now(),
          dependsOn: d.depends_on ?? undefined,
          requiredSkills: d.required_skills ?? undefined,
          score: d.score ?? 0,
          position: d.position ?? undefined,
          failCount: d.fail_count ?? 0,
          maxAttempts: d.max_attempts ?? 3,
          failReason: d.fail_reason ?? undefined,
          subtaskOf: d.subtask_of ?? undefined,
          subtasks: d.subtasks ?? undefined,
        })) as Task[]
        setTasks(mapped)
        setLoading(false)  // Data arrived, done loading
      }
    } catch (e: any) {
      // API might also fail — that's fine, we retry next interval
    }
  })

  function syncFromCache(conn: DbConnection) {
    try {
      const all = Array.from(conn.db.tasks.iter()) as Task[]
      setTasks(all)
      setLoading(false)  // Data arrived from STDB
    } catch (e: any) {
      console.warn('Failed to sync from STDB cache:', e.message)
    }
  }

  useEffect(() => {
    cancelledRef.current = false
    const cancelled = () => cancelledRef.current

    // Start REST API polling immediately — always on as safety net
    pollRef.current = setInterval(() => {
      syncFromApi.current()
    }, POLL_INTERVAL)

    // 🚀 Fire an immediate REST fetch — don't wait 10s for first poll
    syncFromApi.current()

    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function scheduleReconnect() {
      if (cancelled()) return
      const attempt = reconnectRef.current
      const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)]
      console.log(`STDB reconnect in ${delay}ms (attempt ${attempt + 1})`)
      reconnectTimer = setTimeout(() => {
        if (cancelled()) return
        reconnectRef.current++
        connect()
      }, delay)
    }

    function connect() {
      if (cancelled()) return
      try {
        const conn = DbConnection.builder()
          .withUri(`ws://${window.location.hostname}:3001`)
          .withDatabaseName('spacetimedb-kanban')
          .onConnect(() => {
            if (cancelled()) return
            setConnected(true)
            setError(null)
            reconnectRef.current = 0  // reset backoff on successful connect
            syncFromCache(conn)
          })
          .onConnectError((_ctx: any, err: Error) => {
            if (cancelled()) return
            console.warn('STDB WebSocket connection failed:', err.message)
            setConnected(false)
            setError(`STDB disconnected — polling REST API`)
            scheduleReconnect()
          })
          .onDisconnect((_ctx: any, err?: Error) => {
            if (cancelled()) return
            console.warn('STDB WebSocket disconnected:', err?.message)
            setConnected(false)
            setError(`STDB disconnected — polling REST API`)
            scheduleReconnect()
          })
          .build()

        connRef.current = conn

        // Subscribe to all tasks — STDB pushes changes instantly
        conn.subscriptionBuilder()
          .onApplied(() => {
            if (!cancelled()) syncFromCache(conn)
          })
          .subscribe('SELECT * FROM tasks')

        // Register for live row-level updates
        conn.db.tasks.onInsert(() => {
          if (!cancelled()) syncFromCache(conn)
        })
        conn.db.tasks.onUpdate(() => {
          if (!cancelled()) syncFromCache(conn)
        })
        conn.db.tasks.onDelete(() => {
          if (!cancelled()) syncFromCache(conn)
        })
      } catch (e: any) {
        if (!cancelled()) {
          console.error('STDB connection error:', e)
          setConnected(false)
          setError(`STDB connection failed — polling REST API`)
          scheduleReconnect()
        }
      }
    }

    connect()

    return () => {
      cancelledRef.current = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (pollRef.current) clearInterval(pollRef.current)
      // Don't reset reconnectRef — we want a fresh backoff next mount
    }
  }, [])

  return { tasks, connected, loading, error }
}
