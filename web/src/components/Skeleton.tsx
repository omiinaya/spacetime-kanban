export function CardSkeleton() {
  return (
    <div className="bg-[var(--color-card)] rounded-lg border border-[var(--color-border)] p-3 space-y-2 animate-pulse">
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
    <div className="bg-[var(--color-card)] rounded border-l-4 border-l-slate-400 border border-[var(--color-border)] py-1.5 px-2 animate-pulse flex items-center gap-2">
      <div className="h-4 w-3/4 rounded bg-white/10" />
      <div className="h-3 w-12 rounded bg-white/10" />
    </div>
  )
}

export function TableRowSkeleton() {
  return (
    <tr className="animate-pulse border-b border-[var(--color-border)]">
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
    <div className="space-y-3 animate-pulse">
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
    <div className="space-y-4 animate-pulse">
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
        {Array.from({ length: 8 }).map((_, i) => (
          <TableRowSkeleton key={i} />
        ))}
      </div>
    </div>
  )
}

export function KanbanBoardSkeleton() {
  return (
    <div className="space-y-6">
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
