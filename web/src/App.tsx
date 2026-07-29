import { lazy, Suspense, useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { KanbanSquare, Clock, BarChart3, Menu, X, Github, Webhook, Activity, Tag, FolderKanban, LayoutDashboard, CalendarDays, Key, LifeBuoy, Database } from 'lucide-react'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ToastProvider } from './hooks/useToast'

const APP_VERSION = import.meta.env.VITE_APP_VERSION ?? '0.1.0'

const BoardPage = lazy(() => import('./pages/BoardPage'))
const LogsPage = lazy(() => import('./pages/LogsPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const IssuesPage = lazy(() => import('./pages/IssuesPage'))
const WebhooksPage = lazy(() => import('./pages/WebhooksPage'))
const AgentHealthPage = lazy(() => import('./pages/AgentHealthPage'))
const LabelsPage = lazy(() => import('./pages/LabelsPage'))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'))
const CrossProjectPage = lazy(() => import('./pages/CrossProjectPage'))
const CalendarPage = lazy(() => import('./pages/CalendarPage'))
const ApiKeysPage = lazy(() => import('./pages/ApiKeysPage'))
const TriagePage = lazy(() => import('./pages/TriagePage'))
const SchemaMigrationsPage = lazy(() => import('./pages/SchemaMigrationsPage'))

const navItems = [
  { path: '/', label: 'Board', icon: KanbanSquare },
  { path: '/triage', label: 'Triage', icon: LifeBuoy },
  { path: '/projects', label: 'Projects', icon: FolderKanban },
  { path: '/labels', label: 'Labels', icon: Tag },
  { path: '/issues', label: 'GitHub Issues', icon: Github },
  { path: '/webhooks', label: 'Webhooks', icon: Webhook },
  { path: '/agents', label: 'Agents', icon: Activity },
  { path: '/logs', label: 'Activity Log', icon: Clock },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/cross-project', label: 'Cross-Project', icon: LayoutDashboard },
  { path: '/calendar', label: 'Calendar', icon: CalendarDays },
  { path: '/schema-migrations', label: 'Migrations', icon: Database },
  { path: '/api-keys', label: 'API Keys', icon: Key },
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
      <nav aria-label="Sidebar navigation" className="flex-1 p-2 space-y-1">
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
        spacetimedb-kanban v{APP_VERSION}
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
          <button onClick={() => setMobileOpen(false)} aria-label="Close menu" className="p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <X className="w-5 h-5" />
          </button>
        </div>
        {sidebar}
      </aside>

      {/* Main area */}
      <main className="flex-1 min-w-0 overflow-auto">
        {/* Mobile header with hamburger */}
        <div className="sticky top-0 z-30 lg:hidden bg-[var(--color-background)] border-b border-[var(--color-border)] px-3 py-2 flex items-center gap-3">
          <button onClick={() => setMobileOpen(true)} aria-label="Open menu" className="p-1 text-[var(--color-muted)] hover:text-[var(--color-foreground)]">
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <KanbanSquare className="w-4 h-4 text-[var(--color-primary)]" />
            <span className="text-sm font-medium">Kanban</span>
          </div>
        </div>

        <Suspense fallback={
          <div className="flex items-center justify-center h-64" aria-busy="true">
            <div className="w-6 h-6 border-2 border-[var(--color-primary)] border-t-transparent rounded-full animate-spin" />
          </div>
        }>
          <ToastProvider>
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<ErrorBoundary><BoardPage /></ErrorBoundary>} />
                <Route path="/triage" element={<ErrorBoundary><TriagePage /></ErrorBoundary>} />
                <Route path="/projects" element={<ErrorBoundary><ProjectsPage /></ErrorBoundary>} />
                <Route path="/labels" element={<ErrorBoundary><LabelsPage /></ErrorBoundary>} />
                <Route path="/issues" element={<ErrorBoundary><IssuesPage /></ErrorBoundary>} />
                <Route path="/webhooks" element={<ErrorBoundary><WebhooksPage /></ErrorBoundary>} />
                <Route path="/agents" element={<ErrorBoundary><AgentHealthPage /></ErrorBoundary>} />
                <Route path="/logs" element={<ErrorBoundary><LogsPage /></ErrorBoundary>} />
                <Route path="/analytics" element={<ErrorBoundary><AnalyticsPage /></ErrorBoundary>} />
                <Route path="/cross-project" element={<ErrorBoundary><CrossProjectPage /></ErrorBoundary>} />
                <Route path="/calendar" element={<ErrorBoundary><CalendarPage /></ErrorBoundary>} />
                <Route path="/schema-migrations" element={<ErrorBoundary><SchemaMigrationsPage /></ErrorBoundary>} />
                <Route path="/api-keys" element={<ErrorBoundary><ApiKeysPage /></ErrorBoundary>} />
              </Routes>
            </ErrorBoundary>
          </ToastProvider>
        </Suspense>
      </main>
    </div>
  )
}
