import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockList = vi.hoisted(() => vi.fn())
const mockCreate = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    migrations: {
      list: mockList,
      create: mockCreate,
    },
  },
}))

vi.mock('../components/Skeleton', () => ({
  ListViewSkeleton: () => <div data-testid="list-view-skeleton">Loading...</div>,
}))

import SchemaMigrationsPage from '../pages/SchemaMigrationsPage'
import type { SchemaMigration } from '../api'

const makeMigration = (overrides: Partial<SchemaMigration> = {}): SchemaMigration => ({
  version: 'v2.1.0',
  description: 'Add user preferences table',
  applied_at: 1700000000000,
  applied_by: 'hermes',
  checksum: 'sha256:abc123',
  ...overrides,
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('SchemaMigrationsPage', () => {
  it('renders loading skeleton initially', () => {
    mockList.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    expect(screen.getByTestId('list-view-skeleton')).toBeDefined()
  })

  it('renders migration list after data loads', async () => {
    mockList.mockResolvedValue([makeMigration(), makeMigration({ version: 'v2.2.0', description: 'Add indexes' })])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('v2.1.0')).toBeDefined()
      expect(screen.getByText('v2.2.0')).toBeDefined()
      expect(screen.getByText('Add user preferences table')).toBeDefined()
      expect(screen.getByText('Add indexes')).toBeDefined()
    })
  })

  it('shows empty state when no migrations', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText(/No schema migrations recorded/i)).toBeDefined()
    })
  })

  it('shows error state when API fails', async () => {
    mockList.mockRejectedValue(new Error('Failed to fetch'))
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
      expect(screen.getByText(/Failed to fetch/)).toBeDefined()
    })
  })

  it('shows Record button toggles form', async () => {
    mockList.mockResolvedValue([makeMigration()])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('v2.1.0')).toBeDefined())
    const recordBtn = screen.getByRole('button', { name: /^record$/i })
    fireEvent.click(recordBtn)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /record new migration/i })).toBeDefined()
    })
    // Click Cancel to hide - use the first cancel button (the form cancel, not the toggle)
    const cancelBtns = screen.getAllByText('Cancel')
    fireEvent.click(cancelBtns[0])
    await waitFor(() => {
      expect(screen.queryByText(/Record New Migration/i)).toBeNull()
    })
  })

  it('records a migration via form submit', async () => {
    mockList.mockResolvedValue([])
    mockCreate.mockResolvedValue({ status: 'ok' })
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No schema migrations recorded/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /^record$/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /record new migration/i })).toBeDefined())

    const versionInput = screen.getByPlaceholderText('v2.1.0')
    const descInput = screen.getByPlaceholderText('What this migration does')
    fireEvent.change(versionInput, { target: { value: 'v2.5.0' } })
    fireEvent.change(descInput, { target: { value: 'Add audit log table' } })

    fireEvent.click(screen.getByRole('button', { name: /record migration$/i }))

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({
        version: 'v2.5.0',
        description: 'Add audit log table',
        applied_by: undefined,
        checksum: undefined,
      })
    })
  })

  it('disables record button when version is empty', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No schema migrations recorded/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /^record$/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /record new migration/i })).toBeDefined())
    expect(screen.getByRole('button', { name: /record migration$/i }).closest('button')).toBeDisabled()
  })

  it('shows success message after recording', async () => {
    mockList.mockResolvedValue([])
    mockCreate.mockResolvedValue({ status: 'ok' })
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No schema migrations recorded/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /^record$/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /record new migration/i })).toBeDefined())
    fireEvent.change(screen.getByPlaceholderText('v2.1.0'), { target: { value: 'v3.0.0' } })
    fireEvent.click(screen.getByRole('button', { name: /record migration$/i }))
    await waitFor(() => {
      expect(screen.getByText(/Migration recorded successfully/i)).toBeDefined()
    })
  })

  it('shows error message when recording fails', async () => {
    mockList.mockResolvedValue([])
    mockCreate.mockRejectedValue(new Error('Duplicate version'))
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No schema migrations recorded/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /^record$/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /record new migration/i })).toBeDefined())
    fireEvent.change(screen.getByPlaceholderText('v2.1.0'), { target: { value: 'v3.0.0' } })
    fireEvent.click(screen.getByRole('button', { name: /record migration$/i }))
    await waitFor(() => {
      expect(screen.getByText('Duplicate version')).toBeDefined()
    })
  })

  it('shows checksum in table', async () => {
    mockList.mockResolvedValue([makeMigration({ checksum: 'sha256:xyz789' })])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('sha256:xyz789')).toBeDefined()
    })
  })

  it('shows dash for empty checksum', async () => {
    mockList.mockResolvedValue([makeMigration({ checksum: null })])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      const dashes = screen.getAllByText('—')
      expect(dashes.length).toBeGreaterThan(0)
    })
  })

  it('shows dash for missing description', async () => {
    mockList.mockResolvedValue([makeMigration({ description: '' })])
    render(<MemoryRouter><SchemaMigrationsPage /></MemoryRouter>)
    await waitFor(() => {
      const dashes = screen.getAllByText('—')
      expect(dashes.length).toBeGreaterThan(0)
    })
  })
})
