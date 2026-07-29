export function CardSkeleton() {
  return (
    <div className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2 animate-pulse" aria-busy="true">
      <div className="flex items-start justify-between gap-2">
        <div className="h-4 w-16 rounded bg-white/10" />
        <div className="h-4 w-20 rounded bg-white/10" />
      </div>
      <div className="h-5 w-3/4 rounded bg-white/10" />
      <div className="h-4 w-full rounded bg-white/5" />
      <div className="flex items-center gap-2">
        <div className="h-4 w-16 rounded bg-white/10" />
        <div className="h-4 w-24 rounded bg-white/10" />
      </div>
      <div className="flex items-center gap-1 pt-1 border-t border-[var(--color-border)]">
        <div className="h-6 w-16 rounded bg-white/10" />
        <div className="h-6 w-12 rounded bg-white/10" />
      </div>
    </div>
  )
}

export function CompactCardSkeleton() {
  return (
    <div className="bg-[var(--color-card)] rounded border-l-4 border-l-slate-400 border border-[var(--color-border)] py-1.5 px-2 animate-pulse flex items-center gap-2" aria-busy="true">
      <div className="h-4 w-3/4 rounded bg-white/10" />
      <div className="h-3 w-12 rounded bg-white/10" />
    </div>
  )
}

export function TableRowSkeleton() {
  return (
    <tr className="animate-pulse border-b border-[var(--color-border)]" aria-busy="true">
      <td className="py-2.5 px-3"><div className="h-4 w-6 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-14 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-3/4 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-20 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-16 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-12 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-10 rounded bg-white/10" /></td>
      <td className="py-2.5 px-3"><div className="h-4 w-10 rounded bg-white/10" /></td>
    </tr>
  )
}

export function ColumnSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-3 animate-pulse" aria-busy="true">
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 rounded bg-white/10" />
        <div className="h-5 w-8 rounded-full bg-white/10" />
      </div>
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  )
}

export function ListViewSkeleton() {
  return (
    <div className="space-y-4 animate-pulse" aria-busy="true">
      {/* Toolbar skeleton */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-48 rounded bg-white/10" />
          <div className="h-8 w-32 rounded bg-white/10" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-8 w-24 rounded bg-white/10" />
          <div className="h-8 w-32 rounded bg-white/10" />
        </div>
      </div>
      {/* Table header skeleton */}
      <div className="rounded-lg border border-[var(--color-border)] overflow-hidden">
        <div className="bg-white/[0.03] border-b border-[var(--color-border)] px-3 py-2 flex items-center gap-4">
          <div className="h-4 w-6 rounded bg-white/10" />
          <div className="h-4 w-16 rounded bg-white/10" />
          <div className="h-4 w-3/12 rounded bg-white/10" />
          <div className="h-4 w-2/12 rounded bg-white/10 ml-auto" />
          <div className="h-4 w-2/12 rounded bg-white/10" />
          <div className="h-4 w-2/12 rounded bg-white/10" />
          <div className="h-4 w-16 rounded bg-white/10" />
        </div>
        <table className="w-full table-auto">
          <tbody>
            {Array.from({ length: 8 }).map((_, i) => (
              <TableRowSkeleton key={i} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function KanbanBoardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="flex items-center justify-between gap-3">
        <div className="h-6 w-40 rounded bg-white/10 animate-pulse" />
        <div className="flex items-center gap-2">
          <div className="h-8 w-24 rounded bg-white/10 animate-pulse" />
          <div className="h-8 w-20 rounded bg-white/10 animate-pulse" />
          <div className="h-8 w-16 rounded bg-white/10 animate-pulse" />
        </div>
      </div>
      <div className="hidden sm:grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <ColumnSkeleton key={i} count={i < 2 ? 5 : 3} />
        ))}
      </div>
    </div>
  )
}

/** Generic full-page skeleton — header + body bars. */
export function PageSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6 animate-pulse" aria-busy="true">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="h-6 w-44 rounded bg-white/10" />
        <div className="h-8 w-28 rounded bg-white/10" />
      </div>
      {/* Body bars */}
      <div className="space-y-4">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="h-4 w-3/4 rounded bg-white/10" />
            <div className="h-3 w-full rounded bg-white/5" />
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton for analytics page — stat cards + chart areas. */
export function AnalyticsSkeleton() {
  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6 animate-pulse" aria-busy="true">
      <div className="flex items-center justify-between">
        <div className="h-6 w-32 rounded bg-white/10" />
        <div className="h-7 w-16 rounded bg-white/10" />
      </div>
      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-2">
            <div className="h-3 w-20 rounded bg-white/10" />
            <div className="h-6 w-12 rounded bg-white/10" />
            <div className="h-2 w-24 rounded bg-white/5" />
          </div>
        ))}
      </div>
      {/* Two-column charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
            <div className="h-3 w-36 rounded bg-white/10" />
            {Array.from({ length: 4 }).map((_, j) => (
              <div key={j} className="h-4 w-full rounded bg-white/5" />
            ))}
          </div>
        ))}
      </div>
      {/* Chart placeholder */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-3">
        <div className="h-3 w-40 rounded bg-white/10" />
        <div className="h-24 flex items-end gap-1">
          {Array.from({ length: 14 }).map((_, i) => (
            <div key={i} className="flex-1 rounded-t bg-white/10" style={{ height: `${20 + Math.random() * 60}%` }} />
          ))}
        </div>
      </div>
    </div>
  )
}

/** Skeleton for card-grid pages (labels, projects). */
export function CardGridSkeleton({ cards = 6 }: { cards?: number }) {
  return (
    <div className="p-4 md:p-6 lg:p-8 space-y-6 animate-pulse" aria-busy="true">
      <div className="flex items-center justify-between">
        <div className="h-6 w-36 rounded bg-white/10" />
        <div className="h-8 w-28 rounded bg-white/10" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: cards }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-white/10" />
              <div className="h-4 w-28 rounded bg-white/10 flex-1" />
            </div>
            <div className="h-3 w-full rounded bg-white/5" />
            <div className="flex items-center gap-2 pt-2 border-t border-[var(--color-border)]">
              <div className="h-5 w-12 rounded bg-white/10" />
              <div className="h-5 w-12 rounded bg-white/10 ml-auto" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton for agent health page. */
export function AgentListSkeleton() {
  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 space-y-6 animate-pulse" aria-busy="true">
      <div className="flex items-center justify-between">
        <div className="h-6 w-32 rounded bg-white/10" />
        <div className="h-7 w-20 rounded bg-white/10" />
      </div>
      {/* Stat bar */}
      <div className="grid grid-cols-3 gap-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 space-y-1">
            <div className="h-5 w-8 mx-auto rounded bg-white/10" />
            <div className="h-2 w-12 mx-auto rounded bg-white/5" />
          </div>
        ))}
      </div>
      {/* Agent cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4 space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-white/10" />
              <div className="h-4 w-28 rounded bg-white/10" />
            </div>
            <div className="h-3 w-24 rounded bg-white/5" />
            <div className="flex flex-wrap gap-1">
              {Array.from({ length: 3 }).map((_, j) => (
                <div key={j} className="h-4 w-12 rounded bg-white/5" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton for calendar page — month grid. */
export function CalendarSkeleton() {
  return (
    <div className="p-3 sm:p-4 md:p-6 lg:p-8 animate-pulse" aria-busy="true">
      <div className="flex items-center justify-between mb-6">
        <div className="h-6 w-28 rounded bg-white/10" />
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded bg-white/10" />
          <div className="h-4 w-32 rounded bg-white/10" />
          <div className="h-7 w-7 rounded bg-white/10" />
        </div>
      </div>
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] overflow-hidden">
        <div className="grid grid-cols-7 border-b border-[var(--color-border)]">
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="h-4 my-2 mx-auto w-8 rounded bg-white/10" />
          ))}
        </div>
        <div className="grid grid-cols-7">
          {Array.from({ length: 35 }).map((_, i) => (
            <div key={i} className="min-h-[80px] border-b border-r border-[var(--color-border)] p-1">
              <div className="h-4 w-4 rounded-full bg-white/10 mb-1" />
              {i % 3 === 0 && <div className="h-3 w-full rounded bg-white/5 mb-0.5" />}
              {i % 5 === 0 && <div className="h-3 w-3/4 rounded bg-white/5" />}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
