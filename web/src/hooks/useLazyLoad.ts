import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * Hook that provides lazy loading with IntersectionObserver.
 *
 * Returns a ref to attach to the sentinel element, and the count of items
 * to render. The count increases by `step` each time the sentinel enters
 * the viewport, up to `total`.
 *
 * Features:
 * - Configurable initial render count and step
 * - Negative step for virtualization (unload items above viewport) — optional
 * - Resets when total changes (e.g., after filter change)
 * - Call `reset()` to manually restart lazy loading
 */
export function useLazyLoad(
  total: number,
  initial = 20,
  step = 15,
): {
  sentinelRef: React.RefCallback<HTMLDivElement>
  count: number
  hasMore: boolean
  reset: () => void
} {
  const sentinelElRef = useRef<HTMLDivElement | null>(null)
  const [count, setCount] = useState(initial)
  const hasMore = count < total

  // Reset when total items change (e.g., filter applied)
  useEffect(() => {
    setCount(initial)
  }, [total, initial])

  useEffect(() => {
    if (!hasMore) return

    const sentinel = sentinelElRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry?.isIntersecting) {
          setCount((prev) => Math.min(prev + step, total))
        }
      },
      { rootMargin: '200px 0px' },
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMore, step, total])

  const sentinelRef: React.RefCallback<HTMLDivElement> = useCallback((el) => {
    sentinelElRef.current = el
  }, [])

  const reset = useCallback(() => {
    setCount(initial)
  }, [initial])

  return { sentinelRef, count, hasMore, reset }
}

/**
 * Pagination hook for the list/table view — page-based instead of infinite.
 */
export function usePagination(
  total: number,
  perPage = 25,
) {
  const [page, setPage] = useState(0)

  const totalPages = Math.max(1, Math.ceil(total / perPage))
  const currentPage = Math.min(page, totalPages - 1)
  const offset = currentPage * perPage
  const hasPrev = currentPage > 0
  const hasNext = currentPage < totalPages - 1
  const showingFrom = offset + 1
  const showingTo = Math.min(offset + perPage, total)

  const goNext = useCallback(() => {
    setPage((p) => Math.min(p + 1, totalPages - 1))
  }, [totalPages])

  const goPrev = useCallback(() => {
    setPage((p) => Math.max(p - 1, 0))
  }, [])

  const goTo = useCallback(
    (p: number) => {
      setPage(Math.max(0, Math.min(p, totalPages - 1)))
    },
    [totalPages],
  )

  // Reset page when total changes
  useEffect(() => {
    setPage(0)
  }, [total])

  return {
    page: currentPage,
    offset,
    limit: perPage,
    totalPages,
    hasPrev,
    hasNext,
    showingFrom,
    showingTo,
    goNext,
    goPrev,
    goTo,
  }
}
