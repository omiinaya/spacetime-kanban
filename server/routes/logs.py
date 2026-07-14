"""Log endpoints for spacetimedb-kanban."""

from fastapi import APIRouter

from shared import _row_to_log, _sql
from shared import LogOut

router = APIRouter()


@router.get("/api/logs", response_model=list[LogOut])
async def list_logs(
    task_id: str | None = None,
    action: str | None = None,
    agent_id: str | None = None,
    search: str | None = None,
    since: int | None = None,
    until: int | None = None,
    offset: int = 0,
    limit: int = 50,
):
    """List activity logs with filtering and pagination."""
    rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]

    # Apply filters
    if task_id:
        logs = [l for l in logs if l.task_id == task_id]
    if action:
        action_set = set(a.strip() for a in action.split(",") if a.strip())
        logs = [l for l in logs if l.action in action_set]
    if agent_id:
        logs = [l for l in logs if l.agent_id == agent_id]
    if search:
        q = search.lower()
        logs = [l for l in logs if
                (l.notes and q in l.notes.lower()) or
                q in l.task_id.lower() or
                q in l.action.lower()]
    if since:
        logs = [l for l in logs if l.timestamp >= since]
    if until:
        logs = [l for l in logs if l.timestamp <= until]

    logs.sort(key=lambda l: -l.timestamp)
    total = len(logs)
    page = logs[offset:offset + limit]
    return page


@router.get("/api/logs/stats")
async def logs_stats():
    """Get activity log summary statistics."""
    import time

    rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]

    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000

    today = [l for l in logs if l.timestamp >= now_ms - day_ms]

    action_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    for l in logs:
        action_counts[l.action] = action_counts.get(l.action, 0) + 1
        if l.agent_id:
            agent_counts[l.agent_id] = agent_counts.get(l.agent_id, 0) + 1

    # Get unique agents who have been active today
    today_agents = set()
    for l in today:
        if l.agent_id:
            today_agents.add(l.agent_id)

    return {
        "total_events": len(logs),
        "today_events": len(today),
        "active_agents_today": len(today_agents),
        "action_breakdown": action_counts,
        "top_agents": dict(sorted(agent_counts.items(), key=lambda x: -x[1])[:10]),
    }
