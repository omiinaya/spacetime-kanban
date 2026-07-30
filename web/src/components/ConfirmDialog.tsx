import { AlertTriangle, X } from 'lucide-react'
import { useState, useCallback, createContext, useContext, type ReactNode } from 'react'

interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  variant?: 'danger' | 'warning' | 'info'
  children?: ReactNode
}

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
})

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<ConfirmOptions & { resolve: (v: boolean) => void } | null>(null)

  const confirm = useCallback((opts: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setDialog({ ...opts, resolve })
    })
  }, [])

  const handleClose = (result: boolean) => {
    dialog?.resolve(result)
    setDialog(null)
  }

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {dialog && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
          onClick={() => handleClose(false)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="w-full max-w-md bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-5 space-y-4 shadow-2xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className={`w-5 h-5 ${
                  dialog.variant === 'danger' ? 'text-red-400' :
                  dialog.variant === 'warning' ? 'text-amber-400' :
                  'text-blue-400'
                }`} />
                <h3 className="font-semibold text-sm">{dialog.title}</h3>
              </div>
              <button
                onClick={() => handleClose(false)}
                aria-label="Cancel"
                className="p-1 rounded hover:bg-white/10 text-[var(--color-muted)] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-sm text-[var(--color-muted-foreground)]">{dialog.message}</p>
            {dialog.children}
            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                onClick={() => handleClose(false)}
                className="px-3 py-1.5 text-xs rounded text-[var(--color-muted)] hover:bg-white/10 transition-colors"
              >
                {dialog.cancelLabel || 'Cancel'}
              </button>
              <button
                onClick={() => handleClose(true)}
                className={`px-4 py-1.5 text-xs rounded text-white transition-opacity hover:opacity-90 ${
                  dialog.variant === 'danger' ? 'bg-red-500' :
                  dialog.variant === 'warning' ? 'bg-amber-500' :
                  'bg-[var(--color-primary)]'
                }`}
              >
                {dialog.confirmLabel || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm() {
  return useContext(ConfirmContext)
}
