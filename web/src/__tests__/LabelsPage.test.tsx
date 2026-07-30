import { describe, it, expect, vi, afterEach } from 'vitest'
import type React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mockList = vi.hoisted(() => vi.fn())
const mockCreate = vi.hoisted(() => vi.fn())
const mockUpdate = vi.hoisted(() => vi.fn())
const mockDelete = vi.hoisted(() => vi.fn())
const mockAddToast = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    labels: {
      list: mockList,
      create: mockCreate,
      update: mockUpdate,
      delete: mockDelete,
    },
  },
}))

vi.mock('../hooks/useToast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

// Mock ConfirmDialog — useConfirm resolves to true by default
const mockConfirm = vi.hoisted(() => vi.fn().mockResolvedValue(true))
vi.mock('../components/ConfirmDialog', () => ({
  useConfirm: () => ({ confirm: mockConfirm }),
  ConfirmProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../components/Skeleton', () => ({
  CardGridSkeleton: () => <div data-testid="card-grid-skeleton">Loading...</div>,
}))

import LabelsPage from '../pages/LabelsPage'
import type { KanbanLabel } from '../api'

const makeLabel = (overrides: Partial<KanbanLabel> = {}): KanbanLabel => ({
  id: 'label-1',
  name: 'bug',
  color: '#ef4444',
  description: 'Bug fixes',
  created_at: 1700000000000,
  ...overrides,
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('LabelsPage', () => {
  it('renders loading skeleton initially', () => {
    mockList.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    expect(screen.getByTestId('card-grid-skeleton')).toBeDefined()
  })

  it('renders label list after data loads', async () => {
    mockList.mockResolvedValue([makeLabel(), makeLabel({ id: 'label-2', name: 'feature', color: '#10b981' })])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('bug')).toBeDefined()
      expect(screen.getByText('feature')).toBeDefined()
      expect(screen.getByText('#ef4444')).toBeDefined()
      expect(screen.getByText('#10b981')).toBeDefined()
    })
  })

  it('shows empty state when no labels', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText(/No labels yet/i)).toBeDefined()
    })
  })

  it('shows error state when API fails', async () => {
    mockList.mockRejectedValue(new Error('Network error'))
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined()
      expect(screen.getByText(/Network error/)).toBeDefined()
    })
  })

  it('opens create dialog on New Label click', async () => {
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /new label/i }))
    expect(screen.getByRole('dialog')).toBeDefined()
    expect(screen.getByRole('heading', { name: /new label/i })).toBeDefined()
  })

  it('creates label via form submit', async () => {
    mockList.mockResolvedValue([])
    mockCreate.mockResolvedValue({ id: 'new-1', name: 'docs', color: '#0ea5e9', description: '', created_at: 1 })
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No labels yet/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /new label/i }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined())
    const nameInput = screen.getByPlaceholderText('Label name')
    fireEvent.change(nameInput, { target: { value: 'docs' } })
    const descInput = screen.getByPlaceholderText('Description (optional)')
    fireEvent.change(descInput, { target: { value: 'Documentation' } })
    fireEvent.click(screen.getByText('Create'))
    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith({ name: 'docs', color: '#0ea5e9', description: 'Documentation' })
    })
  })

  it('create form submit is disabled when name is empty', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No labels yet/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /new label/i }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined())
    const submitBtn = screen.getByText('Create')
    expect(submitBtn.closest('button')).toBeDisabled()
  })

  it('cancels create dialog', async () => {
    mockList.mockResolvedValue([])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No labels yet/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /new label/i }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined())
    fireEvent.click(screen.getByText('Cancel'))
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
  })

  it('displays description on label cards', async () => {
    mockList.mockResolvedValue([makeLabel({ description: 'Urgent fixes for production' })])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Urgent fixes for production')).toBeDefined()
    })
  })

  it('renders Edit and Delete buttons on label cards', async () => {
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('bug')).toBeDefined()
      expect(screen.getByText('Edit')).toBeDefined()
      expect(screen.getByText('Delete')).toBeDefined()
    })
  })

  it('opens edit form on Edit click', async () => {
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByText('Edit'))
    await waitFor(() => {
      expect(screen.getByDisplayValue('bug')).toBeDefined()
      expect(screen.getByDisplayValue('Bug fixes')).toBeDefined()
      expect(screen.getByText('Save')).toBeDefined()
    })
  })

  it('cancels edit form', async () => {
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByText('Edit'))
    await waitFor(() => expect(screen.getByText('Save')).toBeDefined())
    fireEvent.click(screen.getByText('Cancel'))
    await waitFor(() => {
      expect(screen.queryByDisplayValue('Bug fixes')).toBeNull()
    })
  })

  it('saves edit', async () => {
    mockList.mockResolvedValue([makeLabel()])
    mockUpdate.mockResolvedValue({ id: 'label-1', name: 'bug', color: '#ef4444', description: 'Updated desc', created_at: 1 })
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByText('Edit'))
    await waitFor(() => expect(screen.getByText('Save')).toBeDefined())
    const descInput = screen.getByDisplayValue('Bug fixes')
    fireEvent.change(descInput, { target: { value: 'Updated desc' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledWith('label-1', expect.objectContaining({ description: 'Updated desc' }))
    })
  })

  it('deletes label on Delete click with confirmation', async () => {
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByText('Delete'))
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('label-1')
    })
  })

  it('does not delete label when confirmation cancelled', async () => {
    mockConfirm.mockResolvedValueOnce(false)
    mockList.mockResolvedValue([makeLabel()])
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('bug')).toBeDefined())
    fireEvent.click(screen.getByText('Delete'))
    await new Promise(r => setTimeout(r, 50))
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('handles create failure with toast', async () => {
    mockList.mockResolvedValue([])
    mockCreate.mockRejectedValue(new Error('Create failed'))
    render(<MemoryRouter><LabelsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No labels yet/i)).toBeDefined())
    fireEvent.click(screen.getByRole('button', { name: /new label/i }))
    await waitFor(() => expect(screen.getByRole('dialog')).toBeDefined())
    const nameInput = screen.getByPlaceholderText('Label name')
    fireEvent.change(nameInput, { target: { value: 'fail-label' } })
    fireEvent.click(screen.getByText('Create'))
    await waitFor(() => {
      expect(mockAddToast).toHaveBeenCalledWith('❌', expect.stringContaining('Create failed'))
    })
  })
})
