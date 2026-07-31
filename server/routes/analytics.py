"""Analytics endpoints for spacetimedb-kanban."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter

from shared import _row_to_task, _sql, _sql_param

router = APIRouter()


@router.get("/api/analytics/overview")
async def analytics_overview():
    """High-level metrics: total, per-status, completed today/this week.

    Fetches all tasks and aggregates in Python because STDB v2.x doesn't
    support GROUP BY. The task count (~18K rows @ ~200 bytes each = ~3.6MB
    total transfer) is manageable for this cache-friendly endpoint.
    """  # noqa: E501
    now = int(time.time() * 1000)
    day_ms = 86_400_000
    week_ms = 7 * day_ms
    hour_ago = now - 3_600_000

    # ── Fetch all tasks once, aggregate in Python ────────────────────
    all_tasks = await _sql("SELECT * FROM tasks")

    by_status: dict[str, int] = {}
    repos: dict[str, dict] = {}
    completed_today = 0
    completed_week = 0
    completions_last_hour = 0

    for t in all_tasks:
        # Archived tasks are hidden from the board — they must not inflate
        # the active by_status / repo / completion metrics. Before this fix
        # a 7K archived blocked backlog read as "32% of the board blocked".
        if t.get("archived", False):
            continue
        status = t.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        repo = t.get("repo") or "none"
        if repo not in repos:
            repos[repo] = {"total": 0, "done": 0, "inProgress": 0, "blocked": 0, "available": 0}
        repos[repo]["total"] += 1
        if status in repos[repo]:
            repos[repo][status] += 1

        if status == "done":
            updated = t.get("updated_at", 0)
            if updated > now - day_ms:
                completed_today += 1
            if updated > now - week_ms:
                completed_week += 1
            if updated > hour_ago:
                completions_last_hour += 1

    total = sum(by_status.values())  # active board size (archived excluded)
    total_done = by_status.get("done", 0)

    # ── Claim churn canary (last hour) — filtered in SQL ─────────────
    churn_logs = await _sql_param(
        "SELECT * FROM task_logs WHERE timestamp > {hour_ago} AND action = 'claimed'",
        hour_ago=str(hour_ago),
    )
    claims_last_hour = len(churn_logs)

    return {
        "total": total,
        "by_status": by_status,
        "completed_today": completed_today,
        "completed_week": completed_week,
        "total_done": total_done,
        "repos": repos,
        "claims_last_hour": claims_last_hour,
        "completions_last_hour": completions_last_hour,
        "claim_complete_ratio": round(claims_last_hour / max(completions_last_hour, 1), 1),
    }


@router.get("/api/analytics/claim-churn")
async def analytics_claim_churn(minutes: int = 60, threshold: int = 6):
    """Tasks claimed >=threshold times in the last N minutes without completing.

    Poison-pill detector: catches claim→fail→unclaim loops that never
    increment fail_count (unclaim path) and cycle too fast for the
    dispatcher's per-tick zombie tracker to observe."""
    now = int(time.time() * 1000)
    since = now - minutes * 60_000
    logs = await _sql_param(
        "SELECT * FROM task_logs WHERE timestamp > {since}"
        " AND (action = 'claimed' OR action = 'completed')",
        since=str(since),
    )
    claims: dict[str, int] = {}
    completed: set[str] = set()
    for log in logs:
        tid = log.get("task_id", "")
        if log.get("action") == "claimed":
            claims[tid] = claims.get(tid, 0) + 1
        elif log.get("action") == "completed":
            completed.add(tid)

    churning = [
        {"task_id": tid, "claims": count}
        for tid, count in sorted(claims.items(), key=lambda kv: -kv[1])
        if count >= threshold and tid not in completed
    ]
    return {
        "window_minutes": minutes,
        "threshold": threshold,
        "churning": churning,
        "total_claims": sum(claims.values()),
        "total_completed": len(completed),
    }


@router.get("/api/analytics/throughput")
async def analytics_throughput(days: int = 14):
    """Tasks completed per day for the last N days."""
    rows = await _sql("SELECT * FROM tasks")
    now = int(time.time() * 1000)
    day_ms = 86_400_000

    # Build a map of date -> count (only done tasks)
    daily: dict[str, int] = {}
    for t in rows:
        if t.get("status") != "done":
            continue
        updated = t.get("updated_at", 0)
        age_days = (now - updated) // day_ms
        if age_days > days:
            continue
        # Use actual date string
        dt = datetime.fromtimestamp(updated / 1000, tz=UTC)
        date_str = dt.strftime("%b %d")
        daily[date_str] = daily.get(date_str, 0) + 1

    # Fill in missing days
    result = []
    for i in range(days, -1, -1):
        dt = datetime.fromtimestamp((now - i * day_ms) / 1000, tz=UTC)
        date_str = dt.strftime("%b %d")
        result.append({"date": date_str, "completed": daily.get(date_str, 0)})
    return result


@router.get("/api/analytics/cycle-times")
async def analytics_cycle_times(repo: str = ""):
    """Average time from created to done per repo.

    Filters server-side: task_logs has 460K+ rows (93% claim/unclaim churn);
    we only need created/completed (~1.3K rows). Unfiltered this endpoint
    took ~38s and blocked the event loop parsing SATS rows.

    Optional ?repo= parameter filters to a specific repo's tasks.
    """
    logs = await _sql("SELECT * FROM task_logs WHERE action = 'created' OR action = 'completed'")

    # Group logs by task_id and find created vs completed timestamps
    task_times: dict[str, dict] = {}
    for log in logs:
        tid = log.get("task_id", "")
        action = log.get("action", "")
        ts = log.get("timestamp", 0)
        if tid not in task_times:
            task_times[tid] = {}
        if action == "created":
            task_times[tid]["created"] = ts
        elif action == "completed":
            task_times[tid]["completed"] = ts

    # Fetch task repos — filtered if repo param given
    if repo:
        tasks = await _sql_param(
            "SELECT id, repo FROM tasks WHERE repo = '{repo}'",
            repo=repo,
        )
    else:
        tasks = await _sql("SELECT id, repo FROM tasks")
    task_repo = {t["id"]: t.get("repo", "") for t in tasks}

    repo_cycles: dict[str, list[int]] = {}
    for tid, times in task_times.items():
        if "created" in times and "completed" in times:
            cycle_ms = times["completed"] - times["created"]
            if cycle_ms > 0:
                repo = task_repo.get(tid, "")
                if repo not in repo_cycles:
                    repo_cycles[repo] = []
                repo_cycles[repo].append(cycle_ms)

    result = []
    for repo, cycles in sorted(repo_cycles.items()):
        avg_ms = sum(cycles) / len(cycles)
        result.append(
            {
                "repo": repo or "(none)",
                "count": len(cycles),
                "avg_hours": round(avg_ms / 3_600_000, 1),
                "min_hours": round(min(cycles) / 3_600_000, 1),
                "max_hours": round(max(cycles) / 3_600_000, 1),
            }
        )
    return result


@router.get("/api/analytics/burndown")
async def analytics_burndown(repo: str = "", sprint: str = "", days: int = 14):
    """Burndown chart data for the last N days."""
    rows = await _sql("SELECT * FROM tasks")
    now = int(time.time() * 1000)
    day_ms = 86_400_000

    # Apply optional filters
    if repo:
        rows = [t for t in rows if t.get("repo") == repo]
    if sprint:
        rows = [t for t in rows if t.get("roadmap_item") == sprint]

    # Build date boundaries (end-of-day epoch ms)
    dates: list[str] = []
    day_ends: list[int] = []
    for i in range(days - 1, -1, -1):
        # End of day i days ago
        end_of_day = now - i * day_ms
        dt = datetime.fromtimestamp(end_of_day / 1000, tz=UTC)
        date_str = dt.strftime("%Y-%m-%d")
        dates.append(date_str)
        day_ends.append(end_of_day)

    # Count open tasks at start of window
    first_day_end = day_ends[0]
    total_open_start = sum(
        1 for t in rows if t.get("created_at", 0) <= first_day_end and t.get("status") != "done"
    )

    day_data = []
    for idx, (date_str, day_end) in enumerate(zip(dates, day_ends, strict=False)):
        # Open: created on or before this day AND not yet completed
        open_count = sum(
            1
            for t in rows
            if t.get("created_at", 0) <= day_end
            and (t.get("status") != "done" or t.get("updated_at", 0) > day_end)
        )

        # Completed: done on this exact day
        completed_count = sum(
            1
            for t in rows
            if t.get("status") == "done"
            and t.get("updated_at", 0) > day_end - day_ms
            and t.get("updated_at", 0) <= day_end
        )

        # Ideal: linear trend from total_open_start to 0
        ideal = total_open_start * (1 - idx / (days - 1)) if days > 1 else 0.0

        day_data.append(
            {
                "date": date_str,
                "open": open_count,
                "completed": completed_count,
                "ideal": round(ideal, 1),
            }
        )

    return {
        "days": day_data,
        "total_open_start": total_open_start,
        "total_completed": sum(d["completed"] for d in day_data),
        "total_remaining": day_data[-1]["open"] if day_data else 0,
        "days_total": days,
    }


@router.get("/api/analytics/agents")
async def analytics_agents(repo: str = ""):
    """Per-agent stats: tasks completed, stale rate.

    Optional ?repo= parameter filters to tasks in a specific repo.
    """
    agents = await _sql("SELECT * FROM swarm_agents")

    # Filter logs by action and optionally by repo
    if repo:
        logs = await _sql_param(
            "SELECT * FROM task_logs WHERE "
            "(action = 'completed' OR action = 'blocked') AND repo = '{repo}'",
            repo=repo,
        )
    else:
        logs = await _sql(
            "SELECT * FROM task_logs WHERE action = 'completed' OR action = 'blocked'"
        )

    # Count completed tasks per agent from logs
    agent_completions: dict[str, int] = {}
    agent_stales: dict[str, int] = {}
    for log in logs:
        agent = log.get("agent_id") or ""
        action = log.get("action", "")
        if agent:
            if action == "completed":
                agent_completions[agent] = agent_completions.get(agent, 0) + 1
            elif action == "blocked":
                agent_stales[agent] = agent_stales.get(agent, 0) + 1

    result = []
    for a in agents:
        aid = a.get("id", "")
        result.append(
            {
                "id": aid,
                "status": a.get("status", "offline"),
                "completed": agent_completions.get(aid, 0),
                "blocked": agent_stales.get(aid, 0),
                "capabilities": a.get("capabilities"),
                "repo_focus": a.get("repo_focus"),
                "last_heartbeat": a.get("last_heartbeat", 0),
            }
        )
    return result


@router.get("/api/analytics/cross-project")
async def analytics_cross_project():
    """Cross-project dashboard data: per-repo status, priority, sprints."""
    tasks = await _sql("SELECT * FROM tasks")
    projects = await _sql("SELECT * FROM projects")
    project_map = {p["id"]: p for p in projects}

    repos = {}
    for t in tasks:
        r = t.get("repo") or "none"
        if r not in repos:
            repos[r] = {
                "project": project_map.get(r, {}),
                "total": 0,
                "by_status": {},
                "by_priority": {},
                "sprints": set(),
            }
        repos[r]["total"] += 1
        s = t.get("status", "unknown")
        repos[r]["by_status"][s] = repos[r]["by_status"].get(s, 0) + 1
        p = t.get("priority", 2)
        repos[r]["by_priority"][p] = repos[r]["by_priority"].get(p, 0) + 1
        sprint = t.get("sprint") or t.get("roadmap_item", "")
        if sprint:
            repos[r]["sprints"].add(sprint)

    # Convert sets to lists for JSON
    result = {}
    for r, data in repos.items():
        data["sprints"] = sorted(data["sprints"])
        result[r] = data

    return result


@router.get("/api/analytics/calendar")
async def analytics_calendar(year: int = 0, month: int = 0):
    """Tasks with due_by dates for calendar view. If year/month not specified, uses current."""
    import calendar as cal_mod

    now = int(time.time() * 1000)
    if not year:
        year = datetime.fromtimestamp(now / 1000, tz=UTC).year
    if not month:
        month = datetime.fromtimestamp(now / 1000, tz=UTC).month

    tasks = await _sql("SELECT * FROM tasks WHERE due_by IS NOT NULL AND due_by > 0")

    # Filter to tasks in the requested month
    month_start = int(datetime(year, month, 1, tzinfo=UTC).timestamp() * 1000)
    _, last_day = cal_mod.monthrange(year, month)
    month_end = int(datetime(year, month, last_day, 23, 59, 59, tzinfo=UTC).timestamp() * 1000)

    month_tasks = []
    for t in tasks:
        due = t.get("due_by", 0)
        if month_start <= due <= month_end:
            task_out = _row_to_task(t)
            month_tasks.append(task_out.model_dump())

    return {
        "year": year,
        "month": month,
        "tasks": month_tasks,
    }
