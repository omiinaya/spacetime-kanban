import { createContext, useContext, useState, useRef, useCallback, type ReactNode } from 'react'

interface Toast {
  id: number
  emoji: string
  text: string
}

interface ToastContextValue {
  addToast: (emoji: string, text: string) => void
}

const ToastContext = createContext<ToastContextValue>({
  addToast: () => {},
})

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const idCounter = useRef(0)
  const timersRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
    const timer = timersRef.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timersRef.current.delete(id)
    }
  }, [])

  const addToast = useCallback((emoji: string, text: string) => {
    const id = ++idCounter.current
    setToasts(prev => [...prev, { id, emoji, text }])
    const timer = setTimeout(() => removeToast(id), 3500)
    timersRef.current.set(id, timer)
  }, [removeToast])

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      {/* Toast container — renders above everything */}
      <div className="fixed top-4 right-4 z-[100] space-y-2 max-w-sm pointer-events-none" role="status" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id}
            onClick={() => removeToast(t.id)}
            role="alert"
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] shadow-lg text-sm pointer-events-auto transition-all cursor-pointer"
          >
            <span aria-hidden="true" className="text-lg">{t.emoji}</span>
            <span className="truncate text-[var(--color-foreground)]">{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
