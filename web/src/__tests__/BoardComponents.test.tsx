import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import TaskCard from '../components/board/TaskCard'
import ListView from '../components/ListView'
import type { Task, TaskStatus } from '../hooks/useRealtimeTasks'
import type { KanbanLabel, IssueLink } from '../api'

// Mock IntersectionObserver (needed by ListView via useLazyLoad)
vi.stubGlobal('IntersectionObserver', vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
})))

// Mock useLazyLoad for ListView
vi.mock('../hooks/useLazyLoad', () => ({
  useLazyLoad: vi.fn(() => ({
    sentinelRef: vi.fn(),
    count: 50,
    hasMore: false,
    reset: vi.fn(),
  })),
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

beforeEach(() => {
  vi.clearAllMocks()
})

// ──────────────────────────────────────────────
// TaskCard Tests
// ──────────────────────────────────────────────

describe('TaskCard', () => {
  const baseProps = {
    compact: false,
    selectMode: false,
    selected: false,
    labels: [] as KanbanLabel[],
    issueLink: undefined as IssueLink | undefined,
    draggedTaskId: null,
    dropOnTaskId: null,
    onToggleSelect: vi.fn(),
    onClaim: vi.fn(),
    onComplete: vi.fn(),
    onBlock: vi.fn(),
    onUnclaim: vi.fn(),
    onDelete: vi.fn(),
    onArchive: vi.fn(),
    onClick: vi.fn(),
    onDragStart: vi.fn(),
    onDragEnd: vi.fn(),
    onDropOnTask: vi.fn(),
    onSetDependency: vi.fn(),
    onSetSkills: vi.fn(),
    setDropOnTaskId: vi.fn(),
  }

  // ---------- Basic rendering ----------
  it('renders task title', () => {
    const task = createTask({ title: 'My Awesome Task' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('My Awesome Task')).toBeInTheDocument()
  })

  it('renders repo badge when present', () => {
    const task = createTask({ repo: 'my-org/my-repo' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('my-org/my-repo')).toBeInTheDocument()
  })

  it('does not render repo badge when repo is empty', () => {
    const task = createTask({ repo: '' })
    const { container } = render(<TaskCard {...baseProps} task={task} />)
    // In detailed mode, repo renders in a div with flex-wrap — verify no repo text appears
    // The component checks `task.repo &&` so empty string means no badge
    const repoElements = container.querySelectorAll('.bg-white\\/8')
    // There might be bg-white/8 for other elements, but none should contain repo text
    const badgeRepos = Array.from(container.querySelectorAll('span')).filter(
      el => el.textContent === 'test-repo'
    )
    expect(badgeRepos).toHaveLength(0)
  })

  it('renders priority badge with label', () => {
    const task = createTask({ priority: 0 })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('Urgent')).toBeInTheDocument()
  })

  it('renders correct priority label for each level', () => {
    const { rerender } = render(<TaskCard {...baseProps} task={createTask({ priority: 0 })} />)
    expect(screen.getByText('Urgent')).toBeInTheDocument()

    rerender(<TaskCard {...baseProps} task={createTask({ priority: 1 })} />)
    expect(screen.getByText('High')).toBeInTheDocument()

    rerender(<TaskCard {...baseProps} task={createTask({ priority: 2 })} />)
    expect(screen.getByText('Medium')).toBeInTheDocument()

    rerender(<TaskCard {...baseProps} task={createTask({ priority: 3 })} />)
    expect(screen.getByText('Low')).toBeInTheDocument()
  })

  // ---------- Status-dependent rendering ----------
  it('shows "Claim" button for available task', () => {
    const task = createTask({ status: 'available' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('Claim')).toBeInTheDocument()
  })

  it('shows "Done" and "Block" buttons for in_progress task', () => {
    const task = createTask({ status: 'in_progress' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Block')).toBeInTheDocument()
  })

  it('shows "Release" button for blocked task', () => {
    const task = createTask({ status: 'blocked' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('Release')).toBeInTheDocument()
  })

  it('shows "Archive" and "Delete" buttons for done task (detailed mode)', () => {
    const task = createTask({ status: 'done' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('Archive')).toBeInTheDocument()
    expect(screen.getByText('Delete')).toBeInTheDocument()
  })

  it('shows "Arc" and "Del" buttons for done task (compact mode)', () => {
    const task = createTask({ status: 'done' })
    render(<TaskCard {...baseProps} task={task} compact={true} />)
    expect(screen.getByText('Arc')).toBeInTheDocument()
    expect(screen.getByText('Del')).toBeInTheDocument()
  })

  it('does not render Archive button when onArchive is undefined', () => {
    const task = createTask({ status: 'done' })
    render(<TaskCard {...baseProps} task={task} onArchive={undefined} />)
    expect(screen.queryByText('Archive')).not.toBeInTheDocument()
    expect(screen.getByText('Delete')).toBeInTheDocument()
  })

  // ---------- Assignee ----------
  it('renders assigned user handle', () => {
    const task = createTask({ assignedTo: 'alice' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('alice')).toBeInTheDocument()
  })

  // ---------- Description ----------
  it('renders description when present', () => {
    const task = createTask({ description: 'This is a detailed description' })
    render(<TaskCard {...baseProps} task={task} />)
    expect(screen.getByText('This is a detailed description')).toBeInTheDocument()
  })

  it('does not render description when empty', () => {
    const task = createTask({ description: '' })
    const { container } = render(<TaskCard {...baseProps} task={task} />)
    expect(container.querySelector('.line-clamp-2')).not.toBeInTheDocument()
  })

  // ---------- Interaction callbacks ----------
  it('calls onClick when card is clicked', () => {
    const onClick = vi.fn()
    const task = createTask({ id: 'task-42' })
    render(<TaskCard {...baseProps} task={task} onClick={onClick} />)
    fireEvent.click(screen.getByText('Test Task'))
    expect(onClick).toHaveBeenCalledWith('task-42')
  })

  it('calls onClaim when claim button is clicked', () => {
    const onClaim = vi.fn()
    const task = createTask({ id: 'task-claim-me', status: 'available' })
    render(<TaskCard {...baseProps} task={task} onClaim={onClaim} />)
    fireEvent.click(screen.getByText('Claim'))
    expect(onClaim).toHaveBeenCalledWith('task-claim-me', 'web-user')
  })

  it('calls onComplete when done button is clicked', () => {
    const onComplete = vi.fn()
    const task = createTask({ id: 'task-complete', status: 'in_progress' })
    render(<TaskCard {...baseProps} task={task} onComplete={onComplete} />)
    fireEvent.click(screen.getByText('Done'))
    expect(onComplete).toHaveBeenCalledWith('task-complete')
  })

  // ---------- Compact mode ----------
  it('renders compact mode with Claim button for available task', () => {
    const task = createTask({ status: 'available', title: 'Compact Task' })
    render(<TaskCard {...baseProps} task={task} compact={true} />)
    expect(screen.getByText('Compact Task')).toBeInTheDocument()
    expect(screen.getByText('Claim')).toBeInTheDocument()
  })

  it('renders repo in compact mode', () => {
    const task = createTask({ repo: 'my-repo', title: 'Compact Repo Task' })
    render(<TaskCard {...baseProps} task={task} compact={true} />)
    expect(screen.getByText('my-repo')).toBeInTheDocument()
    expect(screen.getByText('Compact Repo Task')).toBeInTheDocument()
  })

  // ---------- Labels ----------
  it('renders label indicators', () => {
    const labels: KanbanLabel[] = [
      { id: 'lbl-1', name: 'bug', color: '#ff0000', description: '', created_at: 0 },
      { id: 'lbl-2', name: 'feature', color: '#00ff00', description: '', created_at: 0 },
    ]
    const task = createTask()
    const { container } = render(<TaskCard {...baseProps} task={task} labels={labels} />)
    // Labels render as colored dots in compact mode, or as tag badges in detailed mode
    // In detailed mode, label names should appear
    expect(screen.getByText('bug')).toBeInTheDocument()
    expect(screen.getByText('feature')).toBeInTheDocument()
  })

  // ---------- Dependency badge ----------
  it('shows dependency badge when task has dependsOn', () => {
    const task = createTask({ dependsOn: 'task-prereq' })
    render(<TaskCard {...baseProps} task={task} />)
    // Dep badge renders as "⬆" with title
    expect(screen.getByTitle('Depends on: task-prereq')).toBeInTheDocument()
  })

  it('does not show dependency badge when no dependsOn', () => {
    const task = createTask({ dependsOn: undefined })
    const { container } = render(<TaskCard {...baseProps} task={task} />)
    expect(screen.queryByTitle(/Depends on:/)).not.toBeInTheDocument()
  })
})

// ──────────────────────────────────────────────
// ListView Tests
// ──────────────────────────────────────────────

describe('ListView', () => {
  const baseProps = {
    tasks: [] as Task[],
    loading: false,
    selectedIds: new Set<string>(),
    selectMode: false,
    taskLabelMap: new Map<string, KanbanLabel[]>(),
    issueLinks: {} as Record<string, IssueLink>,
    onToggleSelect: vi.fn(),
    onClaim: vi.fn(),
    onComplete: vi.fn(),
    onBlock: vi.fn(),
    onUnclaim: vi.fn(),
    onDelete: vi.fn(),
    onClick: vi.fn(),
  }

  it('renders "No tasks match" message when empty', () => {
    render(<ListView {...baseProps} tasks={[]} />)
    expect(screen.getByText('No tasks match the current filters')).toBeInTheDocument()
  })

  it('renders table with task items', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Task Alpha', status: 'available' }),
      createTask({ id: 't2', title: 'Task Beta', status: 'in_progress' }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    expect(screen.getByText('Task Alpha')).toBeInTheDocument()
    expect(screen.getByText('Task Beta')).toBeInTheDocument()
  })

  it('renders status badges with correct text', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Ready', status: 'available' }),
      createTask({ id: 't2', title: 'Working', status: 'in_progress' }),
      createTask({ id: 't3', title: 'Stuck', status: 'blocked' }),
      createTask({ id: 't4', title: 'Finished', status: 'done' }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    expect(screen.getByText('available')).toBeInTheDocument()
    expect(screen.getByText('in progress')).toBeInTheDocument()
    expect(screen.getByText('blocked')).toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
  })

  it('renders repo names in the project column', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Repo Task', repo: 'org/project-a' }),
      createTask({ id: 't2', title: 'No Repo', repo: '' }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    expect(screen.getByText('org/project-a')).toBeInTheDocument()
    // Empty repo should show "—"
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('renders priority labels', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Urgent Task', priority: 0 }),
      createTask({ id: 't2', title: 'Low Priority', priority: 3 }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    // Priority labels are rendered inside a span with rounded font-medium class
    const prioritySpans = screen.getAllByText('Urgent')
    expect(prioritySpans.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Low')).toBeInTheDocument()
  })

  it('renders assignee handles', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Assigned', assignedTo: 'bob' }),
      createTask({ id: 't2', title: 'Unassigned', assignedTo: undefined }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    expect(screen.getByText('@bob')).toBeInTheDocument()
  })

  it('calls onClick when a table row is clicked', () => {
    const onClick = vi.fn()
    const tasks = [createTask({ id: 't-click', title: 'Clickable' })]
    render(<ListView {...baseProps} tasks={tasks} onClick={onClick} />)
    fireEvent.click(screen.getByText('Clickable'))
    expect(onClick).toHaveBeenCalledWith('t-click')
  })

  it('calls onClaim from action buttons in table', () => {
    const onClaim = vi.fn()
    const tasks = [createTask({ id: 't-claim', title: 'Claim Me', status: 'available' })]
    render(<ListView {...baseProps} tasks={tasks} onClaim={onClaim} />)
    // Claim button in ListView has title "Claim"
    const claimBtn = screen.getByTitle('Claim')
    fireEvent.click(claimBtn)
    expect(onClaim).toHaveBeenCalledWith('t-claim')
  })

  it('renders action buttons per task status', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Avail', status: 'available' }),
      createTask({ id: 't2', title: 'InProg', status: 'in_progress' }),
      createTask({ id: 't3', title: 'Blocked', status: 'blocked' }),
      createTask({ id: 't4', title: 'Done', status: 'done' }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    // The action buttons render as icons with title attributes (Play, CheckCircle2, Ban, RotateCcw, Trash2)
    expect(screen.getByTitle('Claim')).toBeInTheDocument()
    expect(screen.getByTitle('Complete')).toBeInTheDocument()
    expect(screen.getByTitle('Block')).toBeInTheDocument()
    expect(screen.getByTitle('Release')).toBeInTheDocument()
    expect(screen.getByTitle('Delete')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading with no tasks', () => {
    const { container } = render(<ListView {...baseProps} tasks={[]} loading={true} />)
    // Skeleton rows have animate-pulse class
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
    // Should not show the empty message during loading
    expect(screen.queryByText('No tasks match the current filters')).not.toBeInTheDocument()
  })

  it('shows task count with "Showing X of Y tasks"', () => {
    const tasks = Array.from({ length: 5 }, (_, i) => createTask({ id: `t${i}`, title: `Task ${i}` }))
    render(<ListView {...baseProps} tasks={tasks} />)
    expect(screen.getByText('Showing 5 of 5 tasks')).toBeInTheDocument()
  })

  it('sorts by priority ascending by default', () => {
    const tasks = [
      createTask({ id: 't1', title: 'Task Low', priority: 3 }),
      createTask({ id: 't2', title: 'Task Urgent', priority: 0 }),
      createTask({ id: 't3', title: 'Task High', priority: 1 }),
    ]
    render(<ListView {...baseProps} tasks={tasks} />)
    // The rendering order should follow sorted order (ascending priority)
    const rows = screen.getAllByRole('row')
    // Row 0 is the header row. Row 1 should be Urgent, Row 2 High, Row 3 Low
    expect(rows[1]).toHaveTextContent('Urgent')
    expect(rows[2]).toHaveTextContent('High')
    expect(rows[3]).toHaveTextContent('Low')
  })
})
