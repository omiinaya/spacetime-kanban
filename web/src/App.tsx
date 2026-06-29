import { useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { KanbanSquare, Clock, BarChart3, Menu, X, Github, Webhook, Activity } from 'lucide-react'
import BoardPage from './pages/BoardPage'
import LogsPage from './pages/LogsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import IssuesPage from './pages/IssuesPage'
import WebhooksPage from './pages/WebhooksPage'
import AgentHealthPage from './pages/AgentHealthPage'

const navItems = [
  { path: '/', label: 'Board', icon: KanbanSquare },
  { path: '/issues', label: 'GitHub Issues', icon: Github },
  { path: '/webhooks', label: 'Webhooks', icon: Webhook },
  { path: '/agents', label: 'Agent Health', icon: Activity },
  { path: '/logs', label: 'Activity Log', icon: Clock },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
]

export default function App() {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  const sidebar = (
    <>
      <div className="p-4 border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <KanbanSquare className="w-5 h-5 text-[var(--color-primary)]" />
          <span className="font-semibold text-sm">Kanban</span>
        </div>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map((item) => {
          const active = location.pathname === item.path
          return (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                active
                  ? 'bg-white/10 text-[var(--color-foreground)]'
                  : 'text-[var(--color-muted)] hover:bg-white/5 hover:text-[var(--color-foreground)]'
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>
      <div className="p-3 border-t border-[var(--color-border)] text-xs text-[var(--color-muted)]">
        spacetimedb-kanban v0.1
      </div>
    </>
  )

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-56 flex-col border-r border-[var(--color-border)] bg-[var(--color-card)] flex-shrink-0">
        {sidebar}
      </aside>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile sidebar drawer */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-64 bg-[var(--color-card)] border-r border-[var(--color-border)] transform transition-transform duration-200 lg:hidden ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex justify-end p-2">
          <button onClick={() => setMobileOpen(false)} className="p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <X className="w-5 h-5" />
          </button>
        </div>
        {sidebar}
      </aside>

      {/* Main area */}
      <main className="flex-1 min-w-0 overflow-auto">
        {/* Mobile header with hamburger */}
        <div className="sticky top-0 z-30 lg:hidden bg-[var(--color-background)] border-b border-[var(--color-border)] px-3 py-2 flex items-center gap-3">
          <button onClick={() => setMobileOpen(true)} className="p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <KanbanSquare className="w-4 h-4 text-[var(--color-primary)]" />
            <span className="text-sm font-medium">Kanban</span>
          </div>
        </div>

        <Routes>
          <Route path="/" element={<BoardPage />} />
          <Route path="/issues" element={<IssuesPage />} />
          <Route path="/webhooks" element={<WebhooksPage />} />
          <Route path="/agents" element={<AgentHealthPage />} />
          <Route path="/logs" element={<LogsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
        </Routes>
      </main>
    </div>
  )
}
