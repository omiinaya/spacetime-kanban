import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePagination } from '../hooks/useLazyLoad'

describe('usePagination', () => {
  it('returns correct initial values', () => {
    const { result } = renderHook(() => usePagination(50, 10))
    expect(result.current.page).toBe(0)
    expect(result.current.offset).toBe(0)
    expect(result.current.limit).toBe(10)
    expect(result.current.totalPages).toBe(5)
    expect(result.current.hasPrev).toBe(false)
    expect(result.current.hasNext).toBe(true)
    expect(result.current.showingFrom).toBe(1)
    expect(result.current.showingTo).toBe(10)
  })

  it('goes to next page', () => {
    const { result } = renderHook(() => usePagination(50, 10))
    act(() => result.current.goNext())
    expect(result.current.page).toBe(1)
    expect(result.current.offset).toBe(10)
    expect(result.current.hasPrev).toBe(true)
    expect(result.current.hasNext).toBe(true)
  })

  it('stops at last page', () => {
    const { result } = renderHook(() => usePagination(13, 5))
    // Last page is page 2 (0-indexed)
    act(() => result.current.goNext())
    act(() => result.current.goNext())
    expect(result.current.page).toBe(2)
    expect(result.current.hasNext).toBe(false)
  })

  it('goes to previous page', () => {
    const { result } = renderHook(() => usePagination(50, 10))
    act(() => result.current.goNext())
    act(() => result.current.goPrev())
    expect(result.current.page).toBe(0)
  })

  it('goes to specific page', () => {
    const { result } = renderHook(() => usePagination(100, 10))
    act(() => result.current.goTo(3))
    expect(result.current.page).toBe(3)
    expect(result.current.offset).toBe(30)
  })

  it('handles empty total', () => {
    const { result } = renderHook(() => usePagination(0, 10))
    expect(result.current.totalPages).toBe(1)
    expect(result.current.offset).toBe(0)
  })

  it('handles total less than perPage', () => {
    const { result } = renderHook(() => usePagination(3, 10))
    expect(result.current.totalPages).toBe(1)
    expect(result.current.showingTo).toBe(3)
    expect(result.current.hasNext).toBe(false)
  })
})
