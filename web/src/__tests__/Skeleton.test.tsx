import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  CardSkeleton,
  CompactCardSkeleton,
  TableRowSkeleton,
  ColumnSkeleton,
  KanbanBoardSkeleton,
  ListViewSkeleton,
} from '../components/Skeleton'

describe('Skeleton components', () => {
  it('renders CardSkeleton', () => {
    const { container } = render(<CardSkeleton />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('renders CompactCardSkeleton', () => {
    const { container } = render(<CompactCardSkeleton />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('renders TableRowSkeleton', () => {
    const { container } = render(<TableRowSkeleton />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('renders ColumnSkeleton with default count', () => {
    const { container } = render(<ColumnSkeleton />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders KanbanBoardSkeleton', () => {
    const { container } = render(<KanbanBoardSkeleton />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })

  it('renders ListViewSkeleton', () => {
    const { container } = render(<ListViewSkeleton />)
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThan(0)
  })
})
