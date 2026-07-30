import { useState, useEffect } from 'react'
import { Github, ExternalLink, RefreshCw, Search, Trash2 } from 'lucide-react'
import { api, type IssueLink } from '../api'
import { ListViewSkeleton } from '../components/Skeleton'
import { useConfirm } from '../components/ConfirmDialog'
import { useToast } from '../hooks/useToast'

export default function IssuesPage() {
  const { confirm } = useConfirm()
  const { addToast } = useToast()
  const [links, setLinks] = useState<IssueLink[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchLinks = () => {
    setLoading(true)
    setError(null)
    api.issues.list()
      .then(data => {
        setLinks(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch(e => {
        setError(e.message)
        setLoading(false)
      })
  }

  useEffect(() => {
    fetchLinks()
    const interval = setInterval(() => {
      if (document.hidden) return
      fetchLinks()
    }, 30000)
    const onVis = () => { if (document.hidden) clearInterval(interval) }
    document.addEventListener('visibilitychange', onVis)
    return () => { clearInterval(interval); document.removeEventListener('visibilitychange', onVis) }
  }, [])

  const filtered = searchQuery
    ? links.filter(l =>
        l.repo.toLowerCase().includes(searchQuery.toLowerCase()) ||
        String(l.issue_number).includes(searchQuery) ||
        l.kanban_task_id.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : links

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <Github className="w-5 h-5 text-[var(--color-primary)]" />
          <h1 className="text-lg font-semibold">GitHub Issue Links</h1>
          <span className="text-xs text-[var(--color-muted)] bg-white/5 px-2 py-0.5 rounded">
            {links.length} linked
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-muted)]" />
            <input
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Filter links..."
              className="pl-7 pr-3 py-1.5 text-xs rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] w-40 sm:w-56"
            />
          </div>
          <button onClick={fetchLinks} disabled={loading}
            className="p-1.5 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)] transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Content */}
      {loading && !error ? <ListViewSkeleton /> : error ? (
        <div className="flex flex-col items-center justify-center py-16 text-center" role="alert">
          <p className="text-sm text-red-400 mb-2">Failed to load issue links</p>
          <p className="text-xs text-[var(--color-muted)] mb-3">{error}</p>
          <button onClick={fetchLinks}
            className="text-xs px-3 py-1.5 rounded bg-[var(--color-primary)] text-white hover:bg-blue-600 transition-colors"
          >Retry</button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Github className="w-8 h-8 text-[var(--color-muted)] mb-2" />
          <p className="text-sm text-[var(--color-muted)]">
            {searchQuery ? 'No links match your filter' : 'No GitHub issue links configured'}
          </p>
          <p className="text-xs text-[var(--color-muted)] mt-1">
            {searchQuery ? 'Try a different search term' : 'Link tasks to GitHub issues via the detail modal or CLI'}
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {filtered.map(link => (
            <div key={link.kanban_task_id}
              className="flex items-center gap-3 p-3 rounded-lg bg-[var(--color-card)] border border-[var(--color-border)] hover:bg-white/[0.02] transition-colors"
            >
              <div className="flex-shrink-0">
                <div className={`w-2 h-2 rounded-full ${
                  link.status === 'closed' ? 'bg-red-500' : 'bg-emerald-500'
                }`} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <a href={link.html_url} target="_blank" rel="noopener noreferrer"
                    className="text-sm font-medium text-blue-400 hover:text-blue-300 underline underline-offset-2"
                  >
                    {link.repo}#{link.issue_number}
                  </a>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    link.status === 'closed'
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-emerald-500/20 text-emerald-400'
                  }`}>{link.status}</span>
                </div>
                <p className="text-xs text-[var(--color-muted)] mt-0.5 font-mono truncate">
                  kanban: {link.kanban_task_id.slice(0, 28)}...
                </p>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <span className="text-[10px] text-[var(--color-muted)]">
                  {new Date(link.linked_at).toLocaleDateString()}
                </span>
                <a href={link.html_url} target="_blank" rel="noopener noreferrer"
                  aria-label="Open in new tab"
                  className="p-1 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-[var(--color-foreground)]"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                </a>
                <button onClick={async () => {
                  const ok = await confirm({ title: 'Unlink Issue', message: 'Unlink this issue from the task?', confirmLabel: 'Unlink', variant: 'danger' })
                  if (!ok) return
                  try {
                    await api.issues.unlink(link.kanban_task_id)
                    fetchLinks()
                  } catch(e) {
                    addToast('❌', `Failed to unlink: ${e instanceof Error ? e.message : String(e)}`)
                  }
                }} aria-label="Unlink issue" className="p-1 rounded hover:bg-white/10 text-[var(--color-muted)] hover:text-red-400"
                ><Trash2 className="w-3 h-3" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
