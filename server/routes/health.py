"""Project health API — layered maturity scoring and reporting."""

import asyncio
import functools

from fastapi import APIRouter

router = APIRouter(tags=["health"])


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
    from scanners.health import compute_all_projects, compute_project_health
    from scanners import discover_repos

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
