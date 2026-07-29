"""Project health API — layered maturity scoring and reporting."""

import asyncio
import functools
import time

from fastapi import APIRouter

router = APIRouter(tags=["health"])


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

    # Lightweight board overview — fetch via shared client, don't block
    try:
        from shared import _sql

        tasks = await _sql("SELECT * FROM tasks")
        total = 0
        by_status = {}
        for t in tasks or []:
            s = t.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
            total += 1
        result["board"] = {
            "total": total,
            "by_status": by_status,
        }
    except ImportError:
        pass  # shared module not available
    except Exception:  # noqa: S110
        pass  # query failure — keep board as {}

    return result


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
