import { useEffect, useRef, useState } from 'react'
import { DbConnection } from '../stdb'
import type { Task, TaskLog } from '../stdb/types'
import { api } from '../api'

export type { Task, TaskLog }
export type TaskStatus = 'available' | 'in_progress' | 'done' | 'blocked'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 15000, 30000]  // exponential backoff
const POLL_INTERVAL = 30000  // 30s REST polling — only active when STDB is disconnected

/** Shallow compare task arrays by ID + status + assignedTo — skip renders when nothing changed */
function tasksEqual(a: Task[], b: Task[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (a[i].id !== b[i].id) return false
    // Fast path: skip deep comparison if IDs match
  }
  // Full content check only if IDs match length
  const aMap = new Map(a.map(t => [t.id, t]))
  const bMap = new Map(b.map(t => [t.id, t]))
  for (const [id, ta] of aMap) {
    const tb = bMap.get(id)
    if (!tb) return false
    if (ta.status !== tb.status || ta.assignedTo !== tb.assignedTo || ta.priority !== tb.priority) return false
  }
  return true
}

/**
 * React hook that subscribes to SpacetimeDB tasks in real-time.
 *
 * Uses STDB's built-in WebSocket subscription for instant updates.
 * Auto-reconnects on disconnect with exponential backoff.
 * REST polling only fires when STDB WebSocket is disconnected.
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
  const tasksRef = useRef<Task[]>([])  // keep a ref for diffing

  function setTasksIfChanged(newTasks: Task[]) {
    if (!tasksEqual(tasksRef.current, newTasks)) {
      tasksRef.current = newTasks
      setTasks(newTasks)
    }
  }

  // REST API fallback poller — only active when STDB is disconnected
  const syncFromApi = useRef(async () => {
    try {
      const data = await api.tasks.list()
      if (Array.isArray(data)) {
        // API returns snake_case, STDB uses camelCase — map fields
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- API returns number timestamps, Task uses bigint; direct cast fails
        const mapped = (data as unknown as Array<Record<string, unknown>>).map(d => ({
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
          dueBy: d.due_by ?? undefined,
          sprint: d.sprint ?? undefined,
          archived: d.archived ?? false,
          estimatedHours: d.estimated_hours ?? undefined,
          spentHours: d.spent_hours ?? undefined,
        })) as Task[]
        setTasksIfChanged(mapped)
        if (mapped.length > 0) setLoading(false)  // Data with content arrived
      }
    } catch {
      // API might also fail — that's fine, we retry next interval
    }
  })

  useEffect(() => {
    cancelledRef.current = false
    const cancelled = () => cancelledRef.current

    function syncFromCache(conn: DbConnection) {
      try {
        const all = (Array.from(conn.db.tasks.iter()) as Task[])
          .filter(t => !t.archived)
        setTasksIfChanged(all)
        if (all.length > 0) setLoading(false)  // Data with content arrived from STDB
      } catch (e: unknown) {
        console.warn('Failed to sync from STDB cache:', e instanceof Error ? e.message : String(e))
      }
    }

    // Fire an immediate REST fetch — bootstrap data while STDB connects
    syncFromApi.current()

    // Loading timeout: force loading=false after 15s even if no data
    const loadingTimeout = setTimeout(() => {
      if (!cancelled()) setLoading(false)
    }, 15000)

    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function scheduleReconnect() {
      if (cancelled()) return
      const attempt = reconnectRef.current
      const delay = RECONNECT_DELAYS[Math.min(attempt, RECONNECT_DELAYS.length - 1)]
      console.warn(`STDB reconnect in ${delay}ms (attempt ${attempt + 1})`)
      reconnectTimer = setTimeout(() => {
        if (cancelled()) return
        reconnectRef.current++
        connect()
      }, delay)
    }

    function startPolling() {
      stopPolling()
      pollRef.current = setInterval(() => {
        syncFromApi.current()
      }, POLL_INTERVAL)
    }

    function stopPolling() {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }

    function connect() {
      if (cancelled()) return
      try {
        const conn = DbConnection.builder()
          .withUri(`ws://${window.location.hostname}:3001`)
          .withDatabaseName('kanban')
          .onConnect(() => {
            if (cancelled()) return
            setConnected(true)
            setError(null)
            reconnectRef.current = 0  // reset backoff on successful connect
            stopPolling()  // STDB is live — no need for REST polling
            syncFromCache(conn)
          })
          .onConnectError((_ctx: unknown, err: Error) => {
            if (cancelled()) return
            console.warn('STDB WebSocket connection failed:', err.message)
            setConnected(false)
            setError(`STDB disconnected — polling REST API`)
            startPolling()  // Start REST polling since STDB is down
            scheduleReconnect()
          })
          .onDisconnect((_ctx: unknown, err?: Error) => {
            if (cancelled()) return
            console.warn('STDB WebSocket disconnected:', err?.message)
            setConnected(false)
            setError(`STDB disconnected — polling REST API`)
            startPolling()  // Start REST polling since STDB is down
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
      } catch (e: unknown) {
        if (!cancelled()) {
          console.error('STDB connection error:', e)
          setConnected(false)
          setError(`STDB connection failed — polling REST API`)
          startPolling()
          scheduleReconnect()
        }
      }
    }

    connect()

    return () => {
      cancelledRef.current = true
      clearTimeout(loadingTimeout)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      stopPolling()
    }
  }, [])

  return { tasks, connected, loading, error }
}
