import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import LogsPage from '../pages/LogsPage'
import type { LogEntry, LogStats } from '../api'

// ──────────────────────────────────────────────
// Mocks
// ──────────────────────────────────────────────

const { mockLogsList, mockLogsStats } = vi.hoisted(() => ({
  mockLogsList: vi.fn(),
  mockLogsStats: vi.fn(),
}))

vi.mock('../api', () => ({
  api: {
    logs: {
      list: mockLogsList,
      stats: mockLogsStats,
    },
  },
}))

vi.mock('../components/Skeleton', () => ({
  ListViewSkeleton: () => <div data-testid="list-view-skeleton">List View Skeleton</div>,
}))

// ──────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────

function createLogEntry(overrides: Partial<LogEntry> = {}): LogEntry {
  return {
    id: 'log-1',
    task_id: 'task_1748397912_abc12345',
    action: 'created',
    agent_id: 'agent-alpha',
    notes: 'Task was created for testing',
    timestamp: Date.now() - 60_000,
    ...overrides,
  }
}

function createStats(overrides: Partial<LogStats> = {}): LogStats {
  return {
    total_events: 142,
    today_events: 31,
    active_agents_today: 4,
    action_breakdown: {
      created: 50,
      claimed: 42,
      completed: 30,
      blocked: 12,
      agent_registered: 8,
    },
    top_agents: { 'agent-alpha': 60, 'agent-beta': 45, 'agent-gamma': 37 },
    ...overrides,
  }
}

function generateLogs(count: number): LogEntry[] {
  return Array.from({ length: count }, (_, i) =>
    createLogEntry({
      id: `log-${i + 1}`,
      task_id: `task_${i}_abc${i}def`,
      action: (['created', 'claimed', 'completed', 'blocked'] as const)[i % 4],
      agent_id: i % 2 === 0 ? 'agent-alpha' : 'agent-beta',
      notes: i % 3 === 0 ? `Log entry number ${i + 1}` : null,
      timestamp: Date.now() - i * 30_000,
    }),
  )
}

// ──────────────────────────────────────────────
// Setup / Teardown
// ──────────────────────────────────────────────
beforeEach(() => {
  vi.clearAllMocks()
  mockLogsList.mockResolvedValue([createLogEntry()])
  mockLogsStats.mockResolvedValue(createStats())
})

afterEach(() => {
  vi.useRealTimers()
})

// ──────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────

describe('LogsPage', () => {
  // ─── 1. Loading skeleton ──────────────────────────────
  it('renders loading skeleton initially', () => {
    // Keep the promise pending so loading state persists
    mockLogsList.mockImplementation(() => new Promise<never>(() => {}))
    mockLogsStats.mockImplementation(() => new Promise<never>(() => {}))

    render(<LogsPage />)

    expect(screen.getByTestId('list-view-skeleton')).toBeInTheDocument()
  })

  // ─── 2. Renders log entries after data loads ─────────
  it('renders log entries after data loads', async () => {
    const logs = [
      createLogEntry({ id: 'log-1', action: 'claimed', notes: 'Claimed task' }),
      createLogEntry({ id: 'log-2', action: 'completed', notes: 'Completed task' }),
    ]
    mockLogsList.mockResolvedValue(logs)
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    // Verify entries rendered via their notes (unique text)
    await waitFor(() => {
      expect(screen.getByText('Claimed task')).toBeInTheDocument()
    })
    expect(screen.getByText('Completed task')).toBeInTheDocument()
  })

  // ─── 3. Stats bar renders ────────────────────────────
  it('renders stats bar with total_events, today_events, active_agents_today', async () => {
    mockLogsStats.mockResolvedValue(
      createStats({ total_events: 250, today_events: 41, active_agents_today: 7 }),
    )

    render(<LogsPage />)

    // Wait for stats to render by looking for the total_events value
    await waitFor(() => {
      expect(screen.getByText('250')).toBeInTheDocument()
    })
    expect(screen.getByText('41')).toBeInTheDocument()
    expect(screen.getByText('7')).toBeInTheDocument()
  })

  // ─── 4. Empty state when no logs ─────────────────────
  it('shows empty state when there are no logs', async () => {
    mockLogsList.mockResolvedValue([])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    await waitFor(() => {
      expect(screen.getByText(/No activity yet/i)).toBeInTheDocument()
    })
  })

  // ─── 5. Error state when API fails ───────────────────
  it('shows error message when API call fails', async () => {
    mockLogsList.mockRejectedValue(new Error('Server unavailable'))

    render(<LogsPage />)

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByText('Server unavailable')).toBeInTheDocument()
  })

  // ─── 6. Filter by action ─────────────────────────────
  it('filters logs when an action is selected from the dropdown', async () => {
    mockLogsList.mockResolvedValue([createLogEntry()])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    // Wait for initial load
    await waitFor(() => {
      expect(mockLogsList).toHaveBeenCalledTimes(1)
    })

    // Open action dropdown
    const actionsButton = screen.getByRole('button', { name: /actions/i })
    fireEvent.click(actionsButton)

    // Click "created" action from the dropdown
    const createdOption = screen.getByRole('button', { name: /^created$/i })
    fireEvent.click(createdOption)

    // After selecting an action, load() re-fires with the filter param
    await waitFor(() => {
      const calls = mockLogsList.mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(2)
      const lastCall = calls[calls.length - 1]
      expect(lastCall[0]).toHaveProperty('action')
      expect(lastCall[0].action).toContain('created')
    })
  })

  // ─── 7. Search input works ───────────────────────────
  it('filters logs when search query is typed', async () => {
    mockLogsList.mockResolvedValue([createLogEntry()])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    // Wait for initial load
    await waitFor(() => {
      expect(mockLogsList).toHaveBeenCalledTimes(1)
    })

    // Type in search field
    const searchInput = screen.getByPlaceholderText('Search logs...')
    fireEvent.change(searchInput, { target: { value: 'test query' } })

    await waitFor(() => {
      const calls = mockLogsList.mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(2)
      const lastCall = calls[calls.length - 1]
      expect(lastCall[0]).toHaveProperty('search', 'test query')
    })
  })

  // ─── 8. Date range buttons ───────────────────────────
  it('applies date range filter when 7d button is clicked', async () => {
    mockLogsList.mockResolvedValue([createLogEntry()])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    await waitFor(() => {
      expect(mockLogsList).toHaveBeenCalledTimes(1)
    })

    // Click "7d" button
    const sevenDayBtn = screen.getByRole('button', { name: '7d' })
    fireEvent.click(sevenDayBtn)

    await waitFor(() => {
      const calls = mockLogsList.mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(2)
      const lastCall = calls[calls.length - 1]
      expect(lastCall[0]).toHaveProperty('since')
      expect(typeof lastCall[0].since).toBe('number')
    })
  })

  it('resets date range to all when All button is clicked', async () => {
    mockLogsList.mockResolvedValue([createLogEntry()])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    await waitFor(() => {
      expect(mockLogsList).toHaveBeenCalledTimes(1)
    })

    // First select a date range
    const sevenDayBtn = screen.getByRole('button', { name: '7d' })
    fireEvent.click(sevenDayBtn)

    await waitFor(() => {
      const calls = mockLogsList.mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(2)
    })

    // Then click "All" to reset
    const allBtn = screen.getByRole('button', { name: 'All' })
    fireEvent.click(allBtn)

    await waitFor(() => {
      const calls = mockLogsList.mock.calls
      expect(calls.length).toBeGreaterThanOrEqual(3)
      const lastCall = calls[calls.length - 1]
      // Since dateRange = 0, no 'since' param should be present
      expect(lastCall[0]).not.toHaveProperty('since')
    })
  })

  // ─── 9. Clear filters button ─────────────────────────
  it('shows clear filters button when filters are active and clears them on click', async () => {
    mockLogsList.mockResolvedValue([createLogEntry()])
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    // Wait for data to load (initial log entry renders)
    await waitFor(() => {
      expect(screen.getByText('Task was created for testing')).toBeInTheDocument()
    })

    // No clear button initially
    expect(screen.queryByText(/clear/i)).not.toBeInTheDocument()

    // Apply a filter — type in search
    const searchInput = screen.getByPlaceholderText('Search logs...')
    fireEvent.change(searchInput, { target: { value: 'filtered' } })

    // Clear button should appear
    await waitFor(() => {
      expect(screen.getByText(/clear/i)).toBeInTheDocument()
    })

    // Click clear
    const clearBtn = screen.getByText(/clear/i)
    fireEvent.click(clearBtn)

    // Filters should be removed
    await waitFor(() => {
      expect(screen.queryByText(/clear/i)).not.toBeInTheDocument()
    })
    expect(screen.getByPlaceholderText('Search logs...')).toHaveValue('')
  })

  // ─── 10. Load more button ────────────────────────────
  it('shows and triggers load more button when hasMore is true', async () => {
    const fiftyLogs = generateLogs(50)
    mockLogsList.mockResolvedValue(fiftyLogs)
    mockLogsStats.mockResolvedValue(createStats())

    render(<LogsPage />)

    // Wait for load more button to appear
    await waitFor(() => {
      expect(screen.getByText('Load more')).toBeInTheDocument()
    })

    // Before clicking, record call count
    const callsBefore = mockLogsList.mock.calls.length

    // Click load more (the button text, but there may be duplicates; use getAllByText)
    fireEvent.click(screen.getByText('Load more'))

    // Should call list with offset=50
    await waitFor(() => {
      expect(mockLogsList.mock.calls.length).toBeGreaterThan(callsBefore)
    })
    const lastCall = mockLogsList.mock.calls[mockLogsList.mock.calls.length - 1]
    expect(lastCall[0]).toHaveProperty('offset', 50)
  })

  // ─── 11. Event Distribution section ──────────────────
  it('renders Event Distribution section with action breakdown', async () => {
    mockLogsStats.mockResolvedValue(
      createStats({
        total_events: 134,
        action_breakdown: {
          created: 50,
          claimed: 42,
          completed: 30,
          blocked: 12,
        },
      }),
    )

    render(<LogsPage />)

    await waitFor(() => {
      expect(screen.getByText('Event Distribution')).toBeInTheDocument()
    })

    // Check count values — these are unique in the stats cards
    expect(screen.getByText('50')).toBeInTheDocument()
    // Check percentage text appears (50/134 ≈ 37%)
    expect(screen.getByText(/\(37%\)/)).toBeInTheDocument()
    expect(screen.getByText(/\(31%\)/)).toBeInTheDocument()
  })

  // ─── 12. relativeTime helper ─────────────────────────
  describe('relativeTime displays correct relative timestamps', () => {
    it('shows "just now" for events less than 1 minute old', async () => {
      // Only fake Date, not timers — so waitFor still works
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-07-29T12:00:00Z'))

      const logs = [createLogEntry({ id: 'l1', timestamp: Date.now() - 5_000 })]
      mockLogsList.mockResolvedValue(logs)
      mockLogsStats.mockResolvedValue(createStats({ total_events: 1, today_events: 1, active_agents_today: 1 }))

      render(<LogsPage />)

      await waitFor(() => {
        expect(screen.getByText('just now')).toBeInTheDocument()
      })
    })

    it('shows "Xm ago" for events less than 60 minutes old', async () => {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-07-29T12:00:00Z'))

      const logs = [createLogEntry({ id: 'l1', timestamp: Date.now() - 5 * 60_000 })]
      mockLogsList.mockResolvedValue(logs)
      mockLogsStats.mockResolvedValue(createStats({ total_events: 1, today_events: 1, active_agents_today: 1 }))

      render(<LogsPage />)

      await waitFor(() => {
        expect(screen.getByText('5m ago')).toBeInTheDocument()
      })
    })

    it('shows "Xh ago" for events less than 24 hours old', async () => {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-07-29T12:00:00Z'))

      const logs = [createLogEntry({ id: 'l1', timestamp: Date.now() - 3 * 3_600_000 })]
      mockLogsList.mockResolvedValue(logs)
      mockLogsStats.mockResolvedValue(createStats({ total_events: 1, today_events: 1, active_agents_today: 1 }))

      render(<LogsPage />)

      await waitFor(() => {
        expect(screen.getByText('3h ago')).toBeInTheDocument()
      })
    })

    it('shows "Xd ago" for events less than 30 days old', async () => {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-07-29T12:00:00Z'))

      const logs = [createLogEntry({ id: 'l1', timestamp: Date.now() - 5 * 86_400_000 })]
      mockLogsList.mockResolvedValue(logs)
      mockLogsStats.mockResolvedValue(createStats({ total_events: 1, today_events: 1, active_agents_today: 1 }))

      render(<LogsPage />)

      await waitFor(() => {
        expect(screen.getByText('5d ago')).toBeInTheDocument()
      })
    })

    it('falls back to date string for events 30+ days old', async () => {
      vi.useFakeTimers({ toFake: ['Date'] })
      vi.setSystemTime(new Date('2026-07-29T12:00:00Z'))

      const logs = [createLogEntry({ id: 'l1', timestamp: new Date('2026-06-01T12:00:00Z').getTime() })]
      mockLogsList.mockResolvedValue(logs)
      mockLogsStats.mockResolvedValue(createStats({ total_events: 1, today_events: 1, active_agents_today: 1 }))

      render(<LogsPage />)

      await waitFor(() => {
        // toLocaleDateString() for June 1 2026 — locale dependent, so accept both US and Intl formats
        const dateEl = screen.getByText(/6\/1\/2026|1\/6\/2026|2026-06-01|Jun 1, 2026|1 Jun 2026/i)
        expect(dateEl).toBeInTheDocument()
      })
    })
  })

  // ─── 13. Clicking on log entry toggles highlight ─────
  it('toggles highlight class when a log entry is clicked', async () => {
    const logs = [
      createLogEntry({ id: 'log-click-1', action: 'claimed', notes: 'Click me' }),
    ]
    mockLogsList.mockResolvedValue(logs)
    mockLogsStats.mockResolvedValue(createStats())

    const { container } = render(<LogsPage />)

    // Wait for log entry to render
    await waitFor(() => {
      expect(screen.getByText('Click me')).toBeInTheDocument()
    })

    // Find the clickable log entry div — the outermost <div> sibling of the note text.
    // Look for the parent div with onClick handler that has cursor-pointer class.
    // Use a more specific selector: `[class*="flex items-start"]` to avoid the <select> element
    const logEntry = container.querySelector('[class*="items-start"]')
    expect(logEntry).not.toBeNull()

    // Click to highlight
    fireEvent.click(logEntry!)
    expect(logEntry!.className).toContain('ring-1')

    // Click again to un-highlight
    fireEvent.click(logEntry!)
    await waitFor(() => {
      expect(logEntry!.className).not.toContain('ring-1')
    })
  })
})
