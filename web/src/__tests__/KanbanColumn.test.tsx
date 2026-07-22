import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import KanbanColumn from '../components/KanbanColumn'
import type { Task, TaskStatus } from '../hooks/useRealtimeTasks'
import type { KanbanLabel, IssueLink } from '../api'

// Mock IntersectionObserver — jsdom doesn't have it
vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})))

// Mock useLazyLoad — returns controlled values
vi.mock('../hooks/useLazyLoad', () => ({
  useLazyLoad: vi.fn(() => ({
    sentinelRef: vi.fn(),
    count: 50,
    hasMore: false,
    reset: vi.fn(),
  })),
}))

// Mock TaskCard — we just want to verify KanbanColumn renders it, not test TaskCard internals
vi.mock('../components/board/TaskCard', () => ({
  default: ({ task, compact }: { task: Task; compact: boolean }) => (
    <div data-testid={`task-card-${task.id}`} data-compact={compact}>
      {task.title}
    </div>
  ),
}))

function createTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    title: 'Test Task',
    description: 'A test task',
    priority: 2,
    status: 'available',
    assignedTo: undefined,
    repo: 'test-repo',
    branch: undefined,
    roadmapItem: '',
    createdBy: 'test',
    createdAt: BigInt(Date.now()),
    updatedAt: BigInt(Date.now()),
    dependsOn: undefined,
    requiredSkills: undefined,
    score: 0,
    position: undefined,
    failCount: 0,
    maxAttempts: 3,
    failReason: undefined,
    subtaskOf: undefined,
    subtasks: undefined,
    dueBy: undefined,
    sprint: undefined,
    archived: false,
    estimatedHours: undefined,
    spentHours: undefined,
    ...overrides,
  }
}

const defaultProps = {
  status: 'available' as TaskStatus,
  tasks: [] as Task[],
  compactMode: false,
  selectMode: false,
  selectedIds: new Set<string>(),
  taskLabelMap: new Map<string, KanbanLabel[]>(),
  issueLinks: {} as Record<string, IssueLink>,
  draggedTaskId: null,
  dragOverColumn: null,
  dropOnTaskId: null,
  collapsed: false,
  onToggleCollapse: vi.fn(),
  onToggleSelect: vi.fn(),
  onClaim: vi.fn(),
  onComplete: vi.fn(),
  onBlock: vi.fn(),
  onUnclaim: vi.fn(),
  onDelete: vi.fn(),
  onArchive: vi.fn(),
  onArchiveAll: vi.fn(),
  onClick: vi.fn(),
  onDragStart: vi.fn(),
  onDragEnd: vi.fn(),
  onDropOnColumn: vi.fn(),
  onDropOnTask: vi.fn(),
  onSetDependency: vi.fn(),
  onSetSkills: vi.fn(),
  onQuickAdd: vi.fn(),
  setDragOverColumn: vi.fn(),
  setDropOnTaskId: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('KanbanColumn', () => {
  // ---------- Empty column ----------
  it('renders empty column with "Empty" text', () => {
    render(<KanbanColumn {...defaultProps} tasks={[]} />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
  })

  it('renders column header with status label', () => {
    render(<KanbanColumn {...defaultProps} status="in_progress" tasks={[]} />)
    expect(screen.getByText('In Progress')).toBeInTheDocument()
  })

  it('shows task count in column header', () => {
    const tasks = [createTask({ id: 't1' }), createTask({ id: 't2' })]
    render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    // Expanded column shows "shownCount/totalCount" in the badge
    // With our mocked useLazyLoad (count=50) and 2 tasks: "2/2"
    expect(screen.getByText('2/2')).toBeInTheDocument()
  })

  // ---------- Renders with tasks ----------
  it('renders task cards for each task', () => {
    const tasks = [
      createTask({ id: 't1', title: 'First Task' }),
      createTask({ id: 't2', title: 'Second Task' }),
    ]
    render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    expect(screen.getByTestId('task-card-t1')).toBeInTheDocument()
    expect(screen.getByTestId('task-card-t2')).toBeInTheDocument()
    expect(screen.getByText('First Task')).toBeInTheDocument()
    expect(screen.getByText('Second Task')).toBeInTheDocument()
  })

  it('passes compact mode to TaskCard', () => {
    const tasks = [createTask({ id: 't1' })]
    const { rerender } = render(<KanbanColumn {...defaultProps} tasks={tasks} compactMode={false} />)
    expect(screen.getByTestId('task-card-t1').dataset.compact).toBe('false')

    rerender(<KanbanColumn {...defaultProps} tasks={tasks} compactMode={true} />)
    expect(screen.getByTestId('task-card-t1').dataset.compact).toBe('true')
  })

  // ---------- WIP limits ----------
  it('shows WIP limit count (tasks/limit) when limit is finite', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 10 }))
    const tasks = Array.from({ length: 3 }, (_, i) => createTask({ id: `t${i}` }))
    render(<KanbanColumn {...defaultProps} status="available" tasks={tasks} />)
    // Header should show "(3/10)" as part of the heading
    expect(screen.getByText(/3\/10/)).toBeInTheDocument()
  })

  it('does NOT show WIP limit count for Infinity limit (done column)', () => {
    // 'done' defaults to Infinity — no "(count/Infinity)" shown
    const tasks = Array.from({ length: 5 }, (_, i) => createTask({ id: `t${i}`, status: 'done' }))
    render(<KanbanColumn {...defaultProps} status="done" tasks={tasks} />)
    // The header should just show "Done" without "(x/Infinity)"
    const header = screen.getByText('Done')
    expect(header).toBeInTheDocument()
    expect(header.textContent).not.toContain('Infinity')
  })

  it('applies warning style (amber) when WIP >80% and <100%', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 10 }))
    // 9 out of 10 = 90% — warning (amber) zone
    const tasks = Array.from({ length: 9 }, (_, i) => createTask({ id: `t${i}` }))
    const { container } = render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    const badge = container.querySelector('.bg-amber-500\\/20')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveTextContent('9/9')
  })

  it('applies critical style (red) when WIP >=100%', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 10 }))
    // 10 out of 10 = 100% — critical zone
    const tasks = Array.from({ length: 10 }, (_, i) => createTask({ id: `t${i}` }))
    const { container } = render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    const badge = container.querySelector('.bg-red-500\\/20')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveTextContent('10/10')
  })

  it('applies critical style when over WIP limit', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 5 }))
    const tasks = Array.from({ length: 7 }, (_, i) => createTask({ id: `t${i}` }))
    const { container } = render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    const badge = container.querySelector('.bg-red-500\\/20')
    expect(badge).toBeInTheDocument()
  })

  // ---------- Quick-add button ----------
  it('shows quick-add button (Plus icon) when not at WIP limit', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 10 }))
    const tasks = [createTask()]
    render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    // Plus icon component renders as an SVG — just check the button exists and isn't disabled
    const plusButton = screen.getByTitle('Add task to Available')
    expect(plusButton).toBeInTheDocument()
    expect(plusButton).not.toBeDisabled()
  })

  it('disables quick-add button when at WIP limit', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 1 }))
    const tasks = [createTask({ id: 't1' })]
    render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    const plusButton = screen.getByTitle('WIP limit reached (1/1)')
    expect(plusButton).toBeInTheDocument()
    expect(plusButton).toBeDisabled()
  })

  it('hides quick-add input initially, shows on plus click', () => {
    render(<KanbanColumn {...defaultProps} tasks={[]} />)
    expect(screen.queryByPlaceholderText('Task title...')).not.toBeInTheDocument()

    // Click the plus button to open quick-add
    const plusButton = screen.getByTitle('Add task to Available')
    fireEvent.click(plusButton)
    expect(screen.getByPlaceholderText('Task title...')).toBeInTheDocument()
  })

  it('prevents quick-add from opening when at WIP limit', () => {
    localStorage.setItem('kanban-wip-limits', JSON.stringify({ available: 1 }))
    const tasks = [createTask({ id: 't1' })]
    render(<KanbanColumn {...defaultProps} tasks={tasks} />)
    const plusButton = screen.getByTitle('WIP limit reached (1/1)')
    fireEvent.click(plusButton)
    expect(screen.queryByPlaceholderText('Task title...')).not.toBeInTheDocument()
  })

  it('calls onQuickAdd when quick-add form is submitted', () => {
    const onQuickAdd = vi.fn()
    render(<KanbanColumn {...defaultProps} tasks={[]} onQuickAdd={onQuickAdd} />)

    // Open quick-add
    fireEvent.click(screen.getByTitle('Add task to Available'))
    const input = screen.getByPlaceholderText('Task title...')
    fireEvent.change(input, { target: { value: 'New Task Title' } })
    fireEvent.click(screen.getByText('Add'))

    expect(onQuickAdd).toHaveBeenCalledWith('available', 'New Task Title')
  })

  it('does not call onQuickAdd with empty title', () => {
    const onQuickAdd = vi.fn()
    render(<KanbanColumn {...defaultProps} tasks={[]} onQuickAdd={onQuickAdd} />)

    fireEvent.click(screen.getByTitle('Add task to Available'))
    // Add button is disabled when input is empty
    const addButton = screen.getByText('Add')
    expect(addButton).toBeDisabled()
    fireEvent.click(addButton)
    expect(onQuickAdd).not.toHaveBeenCalled()
  })

  // ---------- Collapsed column ----------
  it('renders collapsed column differently', () => {
    const { container } = render(<KanbanColumn {...defaultProps} tasks={[]} collapsed={true} />)
    // Collapsed mode shows vertical text and a count badge, not "Empty"
    expect(screen.queryByText('Empty')).not.toBeInTheDocument()
    // Collapsed shows the status label (vertical)
    expect(screen.getByText('Available')).toBeInTheDocument()
    // Collapsed count badge
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('calls onToggleCollapse when collapse button is clicked', () => {
    const onToggleCollapse = vi.fn()
    render(<KanbanColumn {...defaultProps} onToggleCollapse={onToggleCollapse} />)
    // The ▼ collapse button
    const collapseBtn = screen.getByTitle('Collapse')
    fireEvent.click(collapseBtn)
    expect(onToggleCollapse).toHaveBeenCalledWith('available')
  })
})
