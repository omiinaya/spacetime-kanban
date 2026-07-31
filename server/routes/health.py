"""Project health API — layered maturity scoring and reporting."""

import asyncio
import functools
import threading
import time

from fastapi import APIRouter

router = APIRouter(tags=["health"])

# ── Board summary cache ────────────────────────────────────────────────
# /api/health is polled constantly (scheduler loops, agents, e2e probes).
# The naive implementation ran `SELECT * FROM tasks` (22K rows / ~12MB) and
# re-parsed every row on EVERY call to count by status — 2-4s per hit and
# it competed with real work for the thread pool. The summary only needs
# total + per-status counts, so we cache it. STDB can't GROUP BY and can't
# compare the status enum to a string literal, so a single COUNT(*) for
# total + a cached snapshot for the status breakdown is the fastest correct
# shape. TTL is 30s: the counts are informational (health dashboard, e2e
# probes), so sub-minute staleness is harmless and the full-table scan is
# only paid once per TTL window.
_BOARD_SUMMARY_CACHE: dict[str, tuple[float, dict]] = {}
_BOARD_SUMMARY_TTL = 30.0
_BOARD_SUMMARY_LOCK = threading.Lock()


@router.get("/api/health")
async def system_health():
    """System health — scheduler state and board overview.

    Returns scheduler process metrics, crash reporting, uptime,
    and a lightweight board summary. Never blocks on external APIs.
    """
    result = {
        "status": "ok",
        "workers": {"active": 0, "total_spawned": 0},
        "crashes": {"total": 0, "recent_tasks": []},
        "uptime_seconds": None,
        "board": {},
    }

    try:
        from scheduler import (
            _get_worker_count,
            _worker_crash_counts,
            _worker_spawn_times,
            scheduler_start_time,
        )

        result["workers"] = {
            "active": _get_worker_count(),
            "total_spawned": len(_worker_spawn_times),
        }

        crash_total = sum(_worker_crash_counts.values()) if _worker_crash_counts else 0
        recent_tasks = [
            {"task_id": tid, "crash_count": count}
            for tid, count in (_worker_crash_counts or {}).items()
            if count >= 2
        ]
        result["crashes"] = {
            "total": crash_total,
            "recent_tasks": recent_tasks,
        }

        if scheduler_start_time is not None:
            result["uptime_seconds"] = round(time.time() - scheduler_start_time, 1)
    except ImportError:
        pass  # scheduler not loaded — return defaults

    # Lightweight board overview — TTL-cached so the hot poll path never
    # pulls the full 22K-row table on every call.
    try:
        from shared import _sql

        result["board"] = await _get_board_summary(_sql)
    except ImportError:
        pass  # shared module not available
    except Exception:
        import logging

        logging.getLogger("health").exception("Board query failed")
        pass  # query failure — keep board as {}

    return result


async def _get_board_summary(sql_fn) -> dict:
    """Return {total, by_status} with a short TTL cache."""
    now = time.monotonic()
    with _BOARD_SUMMARY_LOCK:
        cached = _BOARD_SUMMARY_CACHE.get("board")
        if cached and cached[0] > now:
            return cached[1]

    # Fast path: COUNT(*) for total (8ms) — STDB can't GROUP BY status.
    total = 0
    try:
        total_rows = await sql_fn("SELECT COUNT(*) AS cnt FROM tasks")
        if total_rows:
            total = int(total_rows[0].get("cnt", 0))
    except Exception:  # noqa: S110 — treat count failure as 0, still try the scan
        pass

    by_status: dict[str, int] = {}
    if total > 0:
        # Slow path only on cache miss: pull the raw table once and count
        # statuses in Python (STDB's enum can't be compared to SQL strings).
        # Archived tasks are hidden from the board and must NOT inflate the
        # active counts — before this fix a 7K archived blocked backlog
        # showed up as "~32% of the board blocked" forever.
        tasks = await sql_fn("SELECT * FROM tasks")
        for t in tasks or []:
            if t.get("archived", False):
                continue
            s = t.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1

    summary = {"total": sum(by_status.values()), "by_status": by_status}
    with _BOARD_SUMMARY_LOCK:
        _BOARD_SUMMARY_CACHE["board"] = (now + _BOARD_SUMMARY_TTL, summary)
    return summary


@router.get("/api/health/projects")
async def project_health():
    """Get layered health scores for all scanned projects.

    Returns per-project health broken down by improvement layer:
      L0 (Critical) — missing indexes, security
      L1 (Code Quality) — unused imports, test gaps, deps
      L2 (Architecture) — large files, unwrap(), error handling
      L3 (Docs & CI) — README, LICENSE, CI pipeline
      L4 (Production) — Docker, healthcheck, build automation

    Also provides overall score and identifies projects needing attention.
    """
    from scanners import discover_repos
    from scanners.health import compute_all_projects

    loop = asyncio.get_event_loop()
    repos = discover_repos(max_repos=50)
    results = await loop.run_in_executor(None, functools.partial(compute_all_projects, repos))
    return results


@router.get("/api/health/projects/{repo_name}")
async def project_health_detail(repo_name: str):
    """Get detailed health score for a single project."""
    from scanners.health import compute_project_health

    result = compute_project_health(repo_name)
    return result
