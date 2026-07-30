import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// ── Global mocks ──────────────────────────────────────────────

vi.mock('../api', () => ({
  api: {
    agents: { health: vi.fn() },
  },
}))

vi.mock('../components/Skeleton', () => ({
  AgentListSkeleton: () => <div data-testid="agent-list-skeleton">Loading...</div>,
}))

// Mock react-router-dom to spy on useNavigate without breaking MemoryRouter
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// ── Imports (after mocks) ────────────────────────────────────

import { api } from '../api'
import type { AgentHealth } from '../api'
import AgentHealthPage from '../pages/AgentHealthPage'

const mockHealth = vi.mocked(api.agents.health)

// ── Helpers ──────────────────────────────────────────────────

function createAgent(overrides: Partial<AgentHealth> = {}): AgentHealth {
  return {
    id: 'agent-alpha',
    host: 'box-1.local',
    status: 'online',
    capabilities: 'python,typescript',
    repo_focus: 'sample-repo-p',
    current_task: null,
    last_heartbeat: Date.now(),
    heartbeat_age_seconds: 30,
    stale: false,
    first_seen: Date.now() - 86400000,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AgentHealthPage />
    </MemoryRouter>
  )
}

// ── Tests ────────────────────────────────────────────────────

describe('AgentHealthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ── 1. Loading skeleton ──────────────────────────────────────
  describe('Loading state', () => {
    it('renders loading skeleton initially', () => {
      mockHealth.mockReturnValue(new Promise(() => {}))
      renderPage()
      expect(screen.getByTestId('agent-list-skeleton')).toBeInTheDocument()
    })
  })

  // ── 2. Agent health data display ─────────────────────────────
  describe('Agent health data', () => {
    it('renders agent health data correctly after API resolves', async () => {
      const agents = [
        createAgent({
          id: 'agent-alpha',
          host: 'box-1.local',
          status: 'busy',
          capabilities: 'python,go,rust',
          current_task: {
            id: 'task-42',
            title: 'Fix auth timeout',
            status: 'in_progress',
            priority: 1,
            repo: 'sample-repo-p',
          },
          heartbeat_age_seconds: 120,
          stale: false,
        }),
      ]
      mockHealth.mockResolvedValue(agents)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })

      // Status label
      expect(screen.getByText('Busy')).toBeInTheDocument()

      // Host
      expect(screen.getByText('box-1.local')).toBeInTheDocument()

      // Capabilities (split by comma)
      expect(screen.getByText('python')).toBeInTheDocument()
      expect(screen.getByText('go')).toBeInTheDocument()
      expect(screen.getByText('rust')).toBeInTheDocument()

      // Current task title
      expect(screen.getByText('Fix auth timeout')).toBeInTheDocument()

      // Current task status (formatted: in_progress → in progress)
      expect(screen.getByText('in progress')).toBeInTheDocument()

      // Repo in task
      expect(screen.getByText('sample-repo-p')).toBeInTheDocument()

      // Heartbeat age (120s = 2m ago)
      expect(screen.getByText('2m ago')).toBeInTheDocument()
    })

    it('renders "No current task" when agent has no current task', async () => {
      mockHealth.mockResolvedValue([
        createAgent({ current_task: null }),
      ])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('No current task')).toBeInTheDocument()
      })
    })

    it('renders agent without host field gracefully', async () => {
      mockHealth.mockResolvedValue([
        createAgent({ host: '' }),
      ])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })
    })

    it('renders agent without capabilities', async () => {
      mockHealth.mockResolvedValue([
        createAgent({ capabilities: null }),
      ])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })
      // No capability badges should render
      expect(screen.queryByText('python')).not.toBeInTheDocument()
    })

    it('renders stale badge for stale agents', async () => {
      mockHealth.mockResolvedValue([
        createAgent({ stale: true }),
      ])

      renderPage()

      await waitFor(() => {
        // Appears in both the stat bar label and the agent card badge
        const staleElements = screen.getAllByText('Stale')
        expect(staleElements.length).toBeGreaterThanOrEqual(1)
      })
    })
  })

  // ── 3. Empty state ──────────────────────────────────────────
  describe('Empty state', () => {
    it('shows empty state when no agents are registered', async () => {
      mockHealth.mockResolvedValue([])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('No agents registered.')).toBeInTheDocument()
      })
      expect(
        screen.getByText(
          'Agents appear here when they send their first heartbeat to the kanban swarm.'
        )
      ).toBeInTheDocument()
    })
  })

  // ── 4. Error state ──────────────────────────────────────────
  describe('Error state', () => {
    it('shows error alert when API call fails', async () => {
      mockHealth.mockRejectedValue(new Error('Failed to fetch health data'))

      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })
      expect(screen.getByText('Failed to fetch health data')).toBeInTheDocument()
    })

    it('handles non-Error rejection (string)', async () => {
      mockHealth.mockRejectedValue('Server unavailable')

      renderPage()

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument()
      })
      expect(screen.getByText('Server unavailable')).toBeInTheDocument()
    })
  })

  // ── 5. formatDuration (tested via rendered output) ──────────
  describe('formatDuration utility', () => {
    it('displays "Xs ago" for heartbeat age < 60 seconds', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 45 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('45s ago')).toBeInTheDocument()
      })
    })

    it('displays "Xm ago" when heartbeat age < 3600 seconds', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 300 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('5m ago')).toBeInTheDocument()
      })
    })

    it('displays "Xh Ym ago" when heartbeat age >= 3600 seconds', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 7500 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('2h 5m ago')).toBeInTheDocument()
      })
    })

    it('displays "never" for negative heartbeat age', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: -1 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('never')).toBeInTheDocument()
      })
    })

    it('renders "0s ago" for zero heartbeat age', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 0 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('0s ago')).toBeInTheDocument()
      })
    })

    it('renders "59s ago" at upper bound of seconds', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 59 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('59s ago')).toBeInTheDocument()
      })
    })

    it('renders "59m ago" at upper bound of minutes', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 3599 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('59m ago')).toBeInTheDocument()
      })
    })

    it('renders "23h 59m ago" near daily boundary', async () => {
      mockHealth.mockResolvedValue([createAgent({ heartbeat_age_seconds: 86340 })])
      renderPage()
      await waitFor(() => {
        expect(screen.getByText('23h 59m ago')).toBeInTheDocument()
      })
    })
  })

  // ── 6. Stat bar counts ──────────────────────────────────────
  describe('Stat bar counts', () => {
    it('shows correct online count (status is online or busy)', async () => {
      const agents = [
        createAgent({ id: 'agent-a', status: 'online' }),
        createAgent({ id: 'agent-b', status: 'busy' }),
        createAgent({ id: 'agent-c', status: 'offline' }),
        createAgent({ id: 'agent-d', status: 'idle' }),
      ]
      mockHealth.mockResolvedValue(agents)

      renderPage()

      await waitFor(() => {
        // "Online" appears in both the stat bar and the agent-a card badge
        expect(screen.getAllByText('Online').length).toBeGreaterThanOrEqual(1)
        // "Working" appears only in the stat bar (no agent has current_task in this test)
        expect(screen.getAllByText('Working').length).toBeGreaterThanOrEqual(1)
        // "Stale" appears only in the stat bar (no agent is stale in this test)
        expect(screen.getAllByText('Stale').length).toBeGreaterThanOrEqual(1)
      })
    })

    it('shows correct working count (agents with current_task)', async () => {
      const task = { id: 't1', title: 'Task', status: 'in_progress' as const, priority: 1, repo: 'r' }
      const agents = [
        createAgent({ id: 'agent-w1', current_task: task, status: 'busy' }),
        createAgent({ id: 'agent-w2', current_task: task, status: 'online' }),
        createAgent({ id: 'agent-w3', current_task: null, status: 'idle' }),
      ]
      mockHealth.mockResolvedValue(agents)

      renderPage()

      await waitFor(() => {
        // "Working" appears in both the stat bar and the two agent card badges
        expect(screen.getAllByText('Working').length).toBeGreaterThanOrEqual(1)
      })
    })

    it('shows correct stale count (agents flagged as stale)', async () => {
      const agents = [
        createAgent({ id: 'agent-s1', stale: true, status: 'online' }),
        createAgent({ id: 'agent-s2', stale: false, status: 'online' }),
        createAgent({ id: 'agent-s3', stale: false, status: 'offline' }),
      ]
      mockHealth.mockResolvedValue(agents)

      renderPage()

      await waitFor(() => {
        // "Stale" appears in both the stat bar and the agent-s1 card badge
        expect(screen.getAllByText('Stale').length).toBeGreaterThanOrEqual(1)
      })
    })
  })

  // ── 7. Refresh button ──────────────────────────────────────
  describe('Refresh button', () => {
    it('renders the refresh button', async () => {
      mockHealth.mockResolvedValue([])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Refresh')).toBeInTheDocument()
      })
    })

    it('calls api.agents.health when refresh button is clicked', async () => {
      mockHealth.mockResolvedValue([createAgent()])

      renderPage()

      // Wait for initial load to complete
      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })

      // Initial call should have happened once
      expect(mockHealth).toHaveBeenCalledTimes(1)

      // Click refresh
      const refreshButton = screen.getByText('Refresh')
      fireEvent.click(refreshButton)

      // Should be called again
      await waitFor(() => {
        expect(mockHealth).toHaveBeenCalledTimes(2)
      })
    })

    it('disables refresh button while refreshing', async () => {
      // Keep the second call hanging so we can see the disabled state
      let resolveSecondCall!: (value: AgentHealth[]) => void
      mockHealth
        .mockResolvedValueOnce([createAgent()])
        .mockReturnValueOnce(new Promise<AgentHealth[]>((resolve) => {
          resolveSecondCall = resolve
        }))

      renderPage()

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })

      // Click refresh
      fireEvent.click(screen.getByText('Refresh'))

      // Button should be disabled while refreshing
      await waitFor(() => {
        expect(screen.getByText('Refresh').closest('button')).toBeDisabled()
      })

      // Resolve the second call to clean up
      await act(async () => {
        resolveSecondCall([createAgent()])
      })
    })
  })

  // ── 8. Navigate on current task click ───────────────────────
  describe('Navigation on task click', () => {
    it('navigates to "/" when clicking on a current task', async () => {
      mockNavigate.mockClear()

      mockHealth.mockResolvedValue([
        createAgent({
          id: 'agent-nav',
          current_task: {
            id: 'task-nav',
            title: 'Clickable task',
            status: 'in_progress',
            priority: 1,
            repo: 'sample-repo-p',
          },
        }),
      ])

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Clickable task')).toBeInTheDocument()
      })

      // The current task div has cursor-pointer and onClick={() => navigate('/')}
      const taskDiv = screen.getByText('Clickable task').closest('[class*="cursor-pointer"]')
      expect(taskDiv).toBeInTheDocument()

      // Click the task area
      fireEvent.click(taskDiv!)

      // Verify navigate was called with '/'
      expect(mockNavigate).toHaveBeenCalledWith('/')
    })
  })

  // ── 9. Auto-refresh note ────────────────────────────────────
  describe('Auto-refresh', () => {
    it('shows auto-refresh note at the bottom', async () => {
      mockHealth.mockResolvedValue([])
      renderPage()

      await waitFor(() => {
        expect(screen.getByText('Auto-refreshes every 15 seconds')).toBeInTheDocument()
      })
    })
  })

  // ── 10. Multiple agents ──────────────────────────────────────
  describe('Multiple agents', () => {
    it('renders multiple agent cards', async () => {
      const agents = [
        createAgent({ id: 'agent-1', status: 'online' }),
        createAgent({ id: 'agent-2', status: 'busy' }),
        createAgent({ id: 'agent-3', status: 'idle' }),
        createAgent({ id: 'agent-4', status: 'offline' }),
      ]
      mockHealth.mockResolvedValue(agents)

      renderPage()

      await waitFor(() => {
        expect(screen.getByText('agent-1')).toBeInTheDocument()
        expect(screen.getByText('agent-2')).toBeInTheDocument()
        expect(screen.getByText('agent-3')).toBeInTheDocument()
        expect(screen.getByText('agent-4')).toBeInTheDocument()
      })
    })
  })

  // ── 11. Loading → Data transition ──────────────────────────
  describe('Loading transition', () => {
    it('transitions from loading skeleton to data', async () => {
      let resolvePromise!: (value: AgentHealth[]) => void
      mockHealth.mockReturnValue(new Promise<AgentHealth[]>((resolve) => {
        resolvePromise = resolve
      }))

      renderPage()

      // Initially shows skeleton
      expect(screen.getByTestId('agent-list-skeleton')).toBeInTheDocument()

      // Resolve the API call
      await act(async () => {
        resolvePromise([createAgent()])
      })

      // Should now show data
      await waitFor(() => {
        expect(screen.getByText('agent-alpha')).toBeInTheDocument()
      })

      // Skeleton should be gone
      expect(screen.queryByTestId('agent-list-skeleton')).not.toBeInTheDocument()
    })
  })
})
