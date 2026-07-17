import { useState, useEffect } from 'react'
import { Loader2, MessageSquare, Send } from 'lucide-react'
import { api, type TaskComment } from '../../api'

export function TaskComments({ taskId }: { taskId: string }) {
  const [comments, setComments] = useState<TaskComment[]>([])
  const [loading, setLoading] = useState(true)
  const [newComment, setNewComment] = useState('')
  const [sending, setSending] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.comments.list(taskId).then(c => {
      if (!cancelled) { setComments(c); setLoading(false) }
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [taskId])

  const handleAdd = async () => {
    const text = newComment.trim()
    if (!text) return
    setSending(true)
    try {
      const result = await api.comments.add(taskId, text, 'web-user')
      if (result.id) {
        setComments(prev => [...prev, {
          id: result.id,
          task_id: taskId,
          author: 'web-user',
          body: text,
          created_at: Date.now(),
        }])
        setNewComment('')
      }
    } catch (e: unknown) {
      alert(`Failed to add comment: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setSending(false)
    }
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)] mb-2 flex items-center gap-1">
        <MessageSquare className="w-3 h-3" /> Comments
      </p>
      {loading ? (
        <div className="flex items-center gap-2 text-xs text-[var(--color-muted)] py-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading...
        </div>
      ) : (
        <div className="space-y-2 max-h-60 overflow-y-auto mb-3">
          {comments.length === 0 ? (
            <p className="text-xs text-[var(--color-muted)] py-1">No comments yet.</p>
          ) : (
            comments.map(cmt => (
              <div key={cmt.id} className="flex items-start gap-2 p-2 rounded bg-white/[0.03] border border-[var(--color-border)]">
                <div className="w-6 h-6 rounded-full bg-[var(--color-primary)]/20 text-[var(--color-primary)] flex items-center justify-center text-[10px] font-semibold shrink-0 mt-0.5">
                  {cmt.author.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium">{cmt.author}</span>
                    <span className="text-[10px] text-[var(--color-muted)]">
                      {new Date(cmt.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--color-muted-foreground)] mt-0.5 whitespace-pre-wrap break-words">{cmt.body}</p>
                </div>
              </div>
            ))
          )}
        </div>
      )}
      <div className="flex items-start gap-2">
        <textarea
          value={newComment}
          onChange={e => setNewComment(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleAdd()
            }
          }}
          placeholder="Add a comment... (Enter to send, Shift+Enter for newline)"
          rows={2}
          className="flex-1 px-3 py-2 text-xs rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-ring)] placeholder:text-[var(--color-muted)]"
        />
        <button
          onClick={handleAdd}
          disabled={!newComment.trim() || sending}
          className="flex items-center gap-1 text-xs px-3 py-2 rounded-lg bg-[var(--color-primary)] text-white hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
        >
          {sending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
          Send
        </button>
      </div>
    </div>
  )
}
