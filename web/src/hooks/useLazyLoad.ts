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
 * - Resets when total decreases (filter applied) but NOT when total grows (WS update)
 * - Tracks sentinel element lifecycle — re-observes if sentinel is unmounted/remounted
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
  const [count, setCount] = useState(initial)
  const prevTotalRef = useRef(total)
  const sentinelElRef = useRef<HTMLDivElement | null>(null)
  const observerRef = useRef<IntersectionObserver | null>(null)
  const hasMore = count < total

  // Store latest deps in refs so the observer callback always has fresh values
  const stepRef = useRef(step)
  stepRef.current = step
  const totalRef = useRef(total)
  totalRef.current = total

  // Reset when total decreases (user applied stricter filter).
  // Do NOT reset when total grows (new tasks via WS) — preserves scroll position.
  useEffect(() => {
    if (total < prevTotalRef.current) {
      setCount(initial)
    }
    prevTotalRef.current = total
  }, [total, initial])

  // Connect/disconnect the IntersectionObserver.
  // Runs whenever hasMore changes, OR the sentinel element (via the ref callback calling this).
  const connectObserver = useCallback(() => {
    // Clean up previous observer
    if (observerRef.current) {
      observerRef.current.disconnect()
      observerRef.current = null
    }

    if (!hasMore) return

    const sentinel = sentinelElRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (entry?.isIntersecting) {
          setCount((prev) => Math.min(prev + stepRef.current, totalRef.current))
        }
      },
      { rootMargin: '200px 0px' },
    )

    observer.observe(sentinel)
    observerRef.current = observer
  }, [hasMore])

  // Callback ref — called by React when the sentinel mounts/unmounts
  const sentinelRef: React.RefCallback<HTMLDivElement> = useCallback((el) => {
    sentinelElRef.current = el
    // Trigger observer setup with the fresh element reference
    connectObserver()
  }, [connectObserver])

  // Re-connect observer when hasMore changes (e.g., all loaded, then new items arrive)
  useEffect(() => {
    connectObserver()
    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
        observerRef.current = null
      }
    }
  }, [connectObserver])

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
