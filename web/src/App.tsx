import { Routes, Route, Link, useLocation } from 'react-router-dom'
import { KanbanSquare, ListTodo, Clock, Users } from 'lucide-react'
import BoardPage from './pages/BoardPage'
import LogsPage from './pages/LogsPage'

const navItems = [
  { path: '/', label: 'Board', icon: KanbanSquare },
  { path: '/logs', label: 'Activity Log', icon: Clock },
]

export default function App() {
  const location = useLocation()

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 border-r border-[var(--color-border)] bg-[#1a2332] flex flex-col">
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
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                  active
                    ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                    : 'text-[var(--color-muted-foreground)] hover:bg-white/5 hover:text-[var(--color-foreground)]'
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
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Routes>
          <Route path="/" element={<BoardPage />} />
          <Route path="/logs" element={<LogsPage />} />
        </Routes>
      </main>
    </div>
  )
}
