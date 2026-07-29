import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary] Uncaught error:', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      // Custom fallback provided via props
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default fallback UI with dark theme
      return (
        <div className="flex items-center justify-center min-h-[200px] p-8" role="alert">
          <div className="bg-[var(--color-card)] rounded-xl border border-[var(--color-border)] p-6 max-w-md w-full text-center space-y-4">
            {/* Error icon */}
            <div className="flex justify-center">
              <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-red-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
            </div>

            {/* Title */}
            <h2 className="text-base font-semibold text-[var(--color-foreground)]">
              Something went wrong
            </h2>

            {/* Error message */}
            {this.state.error && (
              <p className="text-sm text-[var(--color-muted)] font-mono bg-[var(--color-background)] rounded-md p-3 text-left break-words border border-[var(--color-border)]">
                {this.state.error.message || 'An unexpected error occurred'}
              </p>
            )}

            {/* Reload button */}
            <button
              onClick={this.handleReload}
              className="inline-flex items-center gap-1.5 text-sm px-4 py-2 rounded-lg bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Reload page
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
