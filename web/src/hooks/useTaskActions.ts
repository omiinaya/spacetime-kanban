import { api } from '../api'
import type { Task, TaskStatus } from './useRealtimeTasks'
import { STATUS_LABELS } from '../components/constants'
import { useToast } from './useToast'
import { useConfirm } from '../components/ConfirmDialog'

/** All task-mutating actions for the board (claim/complete/block/archive/etc).
 *  Drag-and-drop state handlers stay in BoardPage — this hook is API calls only. */
export function useTaskActions(tasks: Task[], filtered: Task[]) {
  const { addToast } = useToast()
  const { confirm } = useConfirm()

  const handleClaim = async (taskId: string, agentId: string) => {
    try {
      await api.tasks.claim(taskId, agentId)
      // STDB subscription will push the update — no manual refresh needed
    } catch (e: unknown) {
      addToast('❌', `Claim failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleUnclaim = async (taskId: string) => {
    try {
      await api.tasks.unclaim(taskId)
    } catch (e: unknown) {
      addToast('❌', `Unclaim failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleComplete = async (taskId: string) => {
    try {
      await api.tasks.complete(taskId, 'Done via web UI')
    } catch (e: unknown) {
      addToast('❌', `Complete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleBlock = async (taskId: string) => {
    const ok = await confirm({ title: 'Block Task', message: 'Enter the reason for blocking this task:', confirmLabel: 'Block', variant: 'warning' })
    if (!ok) return
    try {
      await api.tasks.block(taskId, 'Blocked')
    } catch (e: unknown) {
      addToast('❌', `Block failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleDelete = async (taskId: string) => {
    const ok = await confirm({ title: 'Delete Task', message: 'Delete this task? This cannot be undone.', confirmLabel: 'Delete', variant: 'danger' })
    if (!ok) return
    try {
      await api.tasks.delete(taskId)
    } catch (e: unknown) {
      addToast('❌', `Delete failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleArchive = async (taskId: string) => {
    try {
      await api.tasks.archive(taskId)
    } catch (e: unknown) {
      addToast('❌', `Archive failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleArchiveAll = async (status: string) => {
    const ids = filtered.filter(t => t.status === status).map(t => t.id)
    if (ids.length === 0) return
    const label = STATUS_LABELS[status as TaskStatus] || status
    const ok = await confirm({ title: 'Archive All', message: `Archive all ${ids.length} ${label} task(s)?\n\nThey will disappear from the board (recoverable via API).`, confirmLabel: 'Archive', variant: 'warning' })
    if (!ok) return
    try {
      const res = await api.tasks.bulkArchive(ids)
      addToast('✅', `Archived ${res.archived}/${ids.length} tasks${res.failed.length ? ` — ${res.failed.length} failed` : ''}`)
    } catch (e: unknown) {
      addToast('❌', `Archive failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleSetDependency = async (taskId: string) => {
    const ok = await confirm({ title: 'Set Dependency', message: 'Enter the ID of the task this task depends on (leave empty to clear):', confirmLabel: 'Set', variant: 'info' })
    if (!ok) return
    try {
      await api.tasks.setDependency(taskId, '')
    } catch (e: unknown) {
      addToast('❌', `Set dependency failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleSetSkills = async (taskId: string) => {
    const ok = await confirm({ title: 'Set Skills', message: 'Enter required skills (comma-separated, e.g. rust,typescript,react):', confirmLabel: 'Set', variant: 'info' })
    if (!ok) return
    try {
      await api.tasks.setSkills(taskId, '')
    } catch (e: unknown) {
      addToast('❌', `Set skills failed: ${e instanceof Error ? e.message : String(e)}`)
    }
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
    } catch (e: unknown) {
      addToast('❌', `Create failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  const handleExport = (format: 'csv' | 'json', repoFilter: string) => {
    const url = api.tasks.export(format, repoFilter || undefined)
    window.open(url, '_blank')
  }

  // Drag-and-drop column transitions (API half — state half stays in BoardPage)
  const dropTaskOnColumn = async (taskId: string, targetStatus: TaskStatus) => {
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
    } catch (e: unknown) {
      addToast('❌', `Drop failed: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return {
    handleClaim, handleUnclaim, handleComplete, handleBlock,
    handleDelete, handleArchive, handleArchiveAll,
    handleSetDependency, handleSetSkills, handleQuickAdd,
    handleExport, dropTaskOnColumn,
  }
}
