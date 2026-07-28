"""Log endpoints for spacetimedb-kanban."""

from fastapi import APIRouter

from shared import LogOut, _row_to_log, _sql, _sql_param

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
    # Build targeted SQL query instead of loading ALL rows
    conditions = []
    params: dict[str, str] = {}
    if task_id:
        conditions.append("task_id = '{task_id}'")
        params["task_id"] = task_id
    if action:
        # Multiple actions: "claimed,completed,blocked"
        actions = [a.strip() for a in action.split(",") if a.strip()]
        if actions:
            # STDB doesn't support OR or IN — filter in Python
            pass
    if agent_id:
        conditions.append("agent_id = '{agent_id}'")
        params["agent_id"] = agent_id
    if since:
        conditions.append(f"timestamp > {since}")
    if until:
        conditions.append(f"timestamp < {until}")

    sql = "SELECT * FROM task_logs"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    rows = await _sql_param(sql, **params) if params else await _sql(sql)
    logs = [_row_to_log(r) for r in rows]

    # Apply Python-side filters for unsupported SQL patterns
    if action:
        action_set = set(a.strip() for a in action.split(",") if a.strip())
        logs = [rec for rec in logs if rec.action in action_set]
    if search:
        q = search.lower()
        logs = [
            rec
            for rec in logs
            if (rec.notes and q in rec.notes.lower())
            or q in rec.task_id.lower()
            or q in rec.action.lower()
        ]

    logs.sort(key=lambda rec: -rec.timestamp)
    page = logs[offset : offset + limit]
    return page


@router.get("/api/logs/batch")
async def batch_logs(
    task_ids: str,
    action: str = "heartbeat",
    limit: int = 1,
):
    """Batch fetch the latest log entries for multiple task IDs.

    Returns dict of {task_id: latest_log_or_null} for up to 100 task IDs.
    Used by the scheduler stale_watcher to check heartbeats in one API call
    instead of N individual calls.
    """
    tids = [t.strip() for t in task_ids.split(",") if t.strip()][:100]
    if not tids:
        return {}

    # SQL WHERE on action (String field) to reduce rows — STDB doesn't support IN
    sql = "SELECT * FROM task_logs"
    if action:
        # Single action only (default: "heartbeat") — no multi-action support in SQL
        action_val = action.split(",")[0].strip()
        sql += f" WHERE action = '{action_val}'"

    rows = await _sql(sql)
    logs = [_row_to_log(r) for r in rows]

    # Filter to requested task IDs (Python-side — STDB has no IN)
    tid_set = set(tids)
    matching = [rec for rec in logs if rec.task_id in tid_set]

    # Filter by rest of actions (if multi-action)
    if action and len(action.split(",")) > 1:
        action_set = set(a.strip() for a in action.split(",") if a.strip())
        matching = [rec for rec in matching if rec.action in action_set]

    # Sort by timestamp descending per task
    matching.sort(key=lambda rec: (rec.task_id, -rec.timestamp))

    # Take the latest entry per task
    result: dict[str, dict | None] = {}
    for rec in matching:
        tid = rec.task_id
        if tid not in result:
            result[tid] = rec.model_dump()

    # Ensure all requested task IDs appear (None = no heartbeat found)
    for tid in tids:
        if tid not in result:
            result[tid] = None

    return result


@router.get("/api/logs/stats")
async def logs_stats():
    """Get activity log summary statistics."""
    import time

    rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]

    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000

    today = [rec for rec in logs if rec.timestamp >= now_ms - day_ms]

    action_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    for rec in logs:
        action_counts[rec.action] = action_counts.get(rec.action, 0) + 1
        if rec.agent_id:
            agent_counts[rec.agent_id] = agent_counts.get(rec.agent_id, 0) + 1

    # Get unique agents who have been active today
    today_agents = set()
    for rec in today:
        if rec.agent_id:
            today_agents.add(rec.agent_id)

    return {
        "total_events": len(logs),
        "today_events": len(today),
        "active_agents_today": len(today_agents),
        "action_breakdown": action_counts,
        "top_agents": dict(sorted(agent_counts.items(), key=lambda x: -x[1])[:10]),
    }
