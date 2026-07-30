import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockList = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    issues: {
      list: mockList,
    },
  },
}))

vi.mock('../components/Skeleton', () => ({
  ListViewSkeleton: () => <div data-testid="list-view-skeleton">Loading...</div>,
}))

import IssuesPage from '../pages/IssuesPage'
import type { IssueLink } from '../api'

const makeLink = (overrides: Partial<IssueLink> = {}): IssueLink => ({
  kanban_task_id: 'task_abc123',
  issue_number: 42,
  repo: 'owner/repo',
  issue_url: 'https://api.github.com/repos/owner/repo/issues/42',
  html_url: 'https://github.com/owner/repo/issues/42',
  status: 'open',
  linked_at: 1700000000000,
  ...overrides,
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('IssuesPage', () => {
  it('renders loading skeleton initially', () => {
    mockList.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    expect(screen.getByTestId('list-view-skeleton')).toBeDefined()
  })

  it('renders issue links after data loads', async () => {
    mockList.mockResolvedValue([makeLink(), makeLink({ issue_number: 99, kanban_task_id: 'task_xyz', repo: 'owner/repo' })])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('owner/repo#42')).toBeDefined()
      expect(screen.getByText('owner/repo#99')).toBeDefined()
      expect(screen.getByText(/2 linked/)).toBeDefined()
    })
  })

  it('shows error state when API fails', async () => {
    mockList.mockRejectedValue(new Error('Network error'))
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
      expect(screen.getByText(/Failed to load issue links/)).toBeDefined()
      expect(screen.getByText(/Network error/)).toBeDefined()
    })
  })

  it('shows empty state when no links', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText(/No GitHub issue links configured/i)).toBeDefined()
    })
  })

  it('shows empty state when filter has no matches', async () => {
    mockList.mockResolvedValue([makeLink()])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('owner/repo#42')).toBeDefined())
    const searchInput = screen.getByPlaceholderText('Filter links...')
    fireEvent.change(searchInput, { target: { value: 'nonexistent' } })
    await waitFor(() => {
      expect(screen.getByText(/No links match your filter/i)).toBeDefined()
    })
  })

  it('displays repo, task id, and status for each link', async () => {
    mockList.mockResolvedValue([makeLink()])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('owner/repo#42')).toBeDefined()
      expect(screen.getByText(/task_abc/)).toBeDefined()
      expect(screen.getByText('open')).toBeDefined()
    })
  })

  it('renders external GitHub link', async () => {
    mockList.mockResolvedValue([makeLink({ html_url: 'https://github.com/owner/repo/issues/42' })])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      const link = screen.getByLabelText('Open in new tab')
      expect(link).toBeDefined()
      expect(link.closest('a')?.getAttribute('href')).toBe('https://github.com/owner/repo/issues/42')
    })
  })

  it('filters links by repo name', async () => {
    mockList.mockResolvedValue([
      makeLink({ kanban_task_id: 'task_a', repo: 'frontend/app', issue_number: 100 }),
      makeLink({ kanban_task_id: 'task_b', repo: 'backend/api', issue_number: 200 }),
    ])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('frontend/app#100')).toBeDefined())
    const searchInput = screen.getByPlaceholderText('Filter links...')
    fireEvent.change(searchInput, { target: { value: 'backend' } })
    await waitFor(() => {
      expect(screen.queryByText('frontend/app#100')).toBeNull()
      expect(screen.getByText('backend/api#200')).toBeDefined()
    })
  })

  it('filters links by issue number', async () => {
    mockList.mockResolvedValue([
      makeLink({ kanban_task_id: 'task_a', issue_number: 100 }),
      makeLink({ kanban_task_id: 'task_b', issue_number: 200 }),
    ])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('owner/repo#100')).toBeDefined())
    const searchInput = screen.getByPlaceholderText('Filter links...')
    fireEvent.change(searchInput, { target: { value: '200' } })
    await waitFor(() => {
      expect(screen.queryByText('owner/repo#100')).toBeNull()
      expect(screen.getByText('owner/repo#200')).toBeDefined()
    })
  })

  it('has a refresh button', async () => {
    mockList.mockResolvedValue([makeLink()])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('owner/repo#42')).toBeDefined())
    const refreshBtn = screen.getByTitle('Refresh')
    expect(refreshBtn).toBeDefined()
  })

  it('handles non-array API response gracefully', async () => {
    mockList.mockResolvedValue(null as unknown as IssueLink[])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText(/No GitHub issue links configured/i)).toBeDefined()
    })
  })

  it('shows status badge with correct styling for open vs closed', async () => {
    mockList.mockResolvedValue([makeLink({ status: 'open' }), makeLink({ kanban_task_id: 'task_2', status: 'closed' })])
    render(<MemoryRouter><IssuesPage /></MemoryRouter>)
    await waitFor(() => {
      const openBadges = screen.getAllByText('open')
      expect(openBadges.length).toBeGreaterThan(0)
      const closedBadges = screen.getAllByText('closed')
      expect(closedBadges.length).toBeGreaterThan(0)
    })
  })
})
