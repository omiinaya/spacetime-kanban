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
    params = {}
    if action:
        action_val = action.split(",")[0].strip()
        sql += " WHERE action = '{action_val}'"
        params["action_val"] = action_val

    rows = await _sql_param(sql, **params)
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

    # Use SQL aggregations instead of loading all rows into Python
    total_result = await _sql("SELECT COUNT(*) AS cnt FROM task_logs")
    total_events = total_result[0]["cnt"] if total_result else 0

    now_ms = int(time.time() * 1000)
    day_ms = 86_400_000

    today_result = await _sql_param(
        "SELECT COUNT(*) AS cnt FROM task_logs WHERE timestamp > {since}",
        since=str(now_ms - day_ms),
    )
    today_events = today_result[0]["cnt"] if today_result else 0

    # Get action breakdown via SQL grouping
    action_rows = await _sql("SELECT action, COUNT(*) AS cnt FROM task_logs GROUP BY action")
    action_breakdown: dict[str, int] = {}
    for r in action_rows:
        action_breakdown[r["action"]] = r["cnt"]

    # Get unique agent count for today
    agent_rows = await _sql_param(
        "SELECT COUNT(DISTINCT agent_id) AS cnt FROM task_logs "
        "WHERE timestamp > {since} AND agent_id IS NOT NULL",
        since=str(now_ms - day_ms),
    )
    active_agents_today = agent_rows[0]["cnt"] if agent_rows else 0

    # Top active agents
    top_agent_rows = await _sql_param(
        "SELECT agent_id, COUNT(*) AS cnt FROM task_logs "
        "WHERE agent_id IS NOT NULL AND timestamp > {since} "
        "GROUP BY agent_id ORDER BY cnt DESC LIMIT 10",
        since=str(now_ms - day_ms),
    )
    top_agents: dict[str, int] = {r["agent_id"]: r["cnt"] for r in top_agent_rows}

    return {
        "total_events": total_events,
        "today_events": today_events,
        "active_agents_today": active_agents_today,
        "action_breakdown": action_breakdown,
        "top_agents": top_agents,
    }
