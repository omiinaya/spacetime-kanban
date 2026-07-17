import { X, Play, CheckCircle2, Ban, RotateCcw, Trash2, Tag, Archive } from 'lucide-react'
import type { KanbanLabel } from '../../api'

export type BatchAction = 'claim' | 'complete' | 'block' | 'unclaim' | 'delete' | 'archive'

interface BulkActionBarProps {
  selectedIds: Set<string>
  filteredLength: number
  batchProcessing: boolean
  allLabels: KanbanLabel[]
  showLabelPicker: boolean
  setShowLabelPicker: (v: boolean) => void
  selectedLabelIds: Set<string>
  setSelectedLabelIds: (v: Set<string>) => void
  onSelectAll: () => void
  onClearSelection: () => void
  onBatch: (action: BatchAction) => void
  onBatchLabels: (assign: boolean) => void
}

export function BulkActionBar({
  selectedIds, filteredLength, batchProcessing, allLabels,
  showLabelPicker, setShowLabelPicker, selectedLabelIds, setSelectedLabelIds,
  onSelectAll, onClearSelection, onBatch, onBatchLabels,
}: BulkActionBarProps) {
  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 border-t border-[var(--color-border)] bg-[var(--color-card)]/95 backdrop-blur-sm px-4 py-3 flex items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <button onClick={onSelectAll} className="text-xs text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors">
          {selectedIds.size === filteredLength ? 'Deselect all' : 'Select all'}
        </button>
        <span className="text-xs text-[var(--color-muted)]">
          {selectedIds.size} of {filteredLength} selected
        </span>
        <button onClick={onClearSelection} className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-white/5 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors">
          <X className="w-3 h-3" /> Clear
        </button>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={() => onBatch('claim')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors disabled:opacity-40"
        ><Play className="w-3 h-3" /> Claim</button>
        <button onClick={() => onBatch('complete')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-40"
        ><CheckCircle2 className="w-3 h-3" /> Complete</button>
        <button onClick={() => onBatch('block')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 transition-colors disabled:opacity-40"
        ><Ban className="w-3 h-3" /> Block</button>
        <button onClick={() => onBatch('unclaim')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors disabled:opacity-40"
        ><RotateCcw className="w-3 h-3" /> Release</button>
        <button onClick={() => onBatch('archive')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-white/10 text-[var(--color-muted-foreground)] hover:bg-white/15 transition-colors disabled:opacity-40"
        ><Archive className="w-3 h-3" /> Archive</button>
        <button onClick={() => onBatch('delete')}
          disabled={batchProcessing}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-40"
        ><Trash2 className="w-3 h-3" /> Delete</button>
        {/* Labels button */}
        <div className="relative">
          <button
            onClick={() => { setShowLabelPicker(!showLabelPicker); if (!showLabelPicker) setSelectedLabelIds(new Set()) }}
            disabled={batchProcessing}
            className="flex items-center gap-1 text-xs px-3 py-1.5 rounded bg-violet-500/20 text-violet-400 hover:bg-violet-500/30 transition-colors disabled:opacity-40"
          ><Tag className="w-3 h-3" /> Labels</button>
          {showLabelPicker && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowLabelPicker(false)} />
              <div className="absolute bottom-full right-0 mb-2 z-50 w-64 rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-3 shadow-xl space-y-2">
                <p className="text-xs font-medium text-[var(--color-muted)]">Assign labels to {selectedIds.size} task(s)</p>
                {allLabels.length === 0 ? (
                  <p className="text-xs text-[var(--color-muted)]">No labels exist.</p>
                ) : (
                  <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                    {allLabels.map(lbl => (
                      <button
                        key={lbl.id}
                        onClick={() => {
                          const next = new Set(selectedLabelIds)
                          if (next.has(lbl.id)) next.delete(lbl.id)
                          else next.add(lbl.id)
                          setSelectedLabelIds(next)
                        }}
                        className={`text-xs px-2 py-1 rounded-full border transition-colors ${
                          selectedLabelIds.has(lbl.id)
                            ? 'border-transparent text-white font-medium'
                            : 'border-[var(--color-border)] text-[var(--color-muted)] hover:border-[var(--color-muted)]'
                        }`}
                        style={selectedLabelIds.has(lbl.id) ? { backgroundColor: lbl.color } : {}}
                      >{lbl.name}</button>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-2 pt-1 border-t border-[var(--color-border)]">
                  <button
                    onClick={() => onBatchLabels(true)}
                    disabled={selectedLabelIds.size === 0 || batchProcessing}
                    className="flex-1 text-xs px-2 py-1.5 rounded bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors disabled:opacity-40"
                  >Assign</button>
                  <button
                    onClick={() => onBatchLabels(false)}
                    disabled={selectedLabelIds.size === 0 || batchProcessing}
                    className="flex-1 text-xs px-2 py-1.5 rounded bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-40"
                  >Remove</button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
