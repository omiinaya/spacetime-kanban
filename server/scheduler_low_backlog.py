"""Low-backlog trigger — auto-runs scanner when available tasks run low.

Runs inside metrics_collector or as a standalone fast loop.
When available tasks drop below a threshold, triggers the repo scanner
immediately instead of waiting for the 6-hour interval.

This is the "never dead kanban" guarantee.
"""

import asyncio
import functools
import os
from typing import Any

import httpx

from config import settings

API_BASE = f"http://localhost:{settings.server_port}"

# ── Thresholds ──────────────────────────────────────────────────────

# When available drops below this, trigger scanner immediately
LOW_BACKLOG_THRESHOLD = 10

# When available drops below this, it's critical — trigger scanner AND alert
CRITICAL_BACKLOG_THRESHOLD = 3

# Cooldown: don't re-trigger scanner within this many seconds
TRIGGER_COOLDOWN_SECONDS = 1800  # 30 min

_last_trigger_ms: int = 0
_scanner_running: bool = False


async def _api_get(path: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{API_BASE}{path}")
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        return None
    return None


async def _api_post(path: str, data: dict) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{API_BASE}{path}", json=data)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        return None
    return None


async def _trigger_scanner() -> dict:
    """Trigger the scanner via its runner. Returns results dict."""
    global _scanner_running
    if _scanner_running:
        return {"status": "already_running"}

    _scanner_running = True
    try:
        # Import and run in executor (scanner is synchronous)
        from scanners.runner import run_all_scanners

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, functools.partial(run_all_scanners))
        total_created = sum(c.get("created", 0) for c in results.values())
        print(f"[scheduler:low-backlog] Scanner triggered: {total_created} new task(s)")
        return results
    except Exception as e:
        print(f"[scheduler:low-backlog] Scanner trigger failed: {e}")
        import traceback

        traceback.print_exc()
        return {"error": str(e)}
    finally:
        _scanner_running = False


async def _get_actionable_available_count() -> int:
    """Count available tasks that can actually be worked (fail_count < max_attempts)."""
    try:
        tasks = await _api_get("/api/tasks?status=available&limit=500")
        if not tasks:
            return 0
        return sum(1 for t in tasks if t.get("fail_count", 0) < t.get("max_attempts", 3))
    except Exception:
        return 0


async def _generate_improvement_tasks() -> int:
    """When scanners find nothing, generate self-improvement tasks from project files.

    Creates tasks from IMPROVEMENTS.md, PERFORMANCE.md, etc. — files that
    contain structured improvement suggestions that aren't in ROADMAP.md.
    Also checks for common quality issues (missing CI, stale docs, etc.).
    """
    try:
        from scanners.runner import discover_repos

        repos = discover_repos()
    except Exception:
        return 0

    existing_titles = set()
    try:
        for status in ("available", "inProgress", "blocked", "done"):
            tasks = await _api_get(f"/api/tasks?status={status}&limit=500")
            if tasks:
                existing_titles.update(t["title"].strip().lower() for t in tasks if t.get("title"))
    except Exception:  # noqa: S110
        pass  # seed tasks — fire and forget

    created = 0
    improvement_files = ["IMPROVEMENTS.md", "PERFORMANCE.md", "SCHEMA_EVOLUTION_POLICY.md"]

    for repo_name, repo_path in repos:
        if not os.path.isdir(repo_path):
            continue

        # Check for improvement files
        for imp_file in improvement_files:
            imp_path = os.path.join(repo_path, imp_file)
            if not os.path.isfile(imp_path):
                continue

            try:
                with open(imp_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:  # noqa: S112
                continue  # skip unreadable files

            # Parse markdown headings as potential task titles
            import re

            headings = re.findall(r"^##\s+(.*)", content, re.MULTILINE)
            for h in headings:
                h = h.strip()
                # Skip generic/section headings
                if not h or len(h) < 10:
                    continue
                # Skip headings that look like section headers
                if h.lower().startswith(("table of", "introduction", "overview", "appendix")):
                    continue
                norm = h.strip().lower()
                if norm in existing_titles:
                    continue
                result = await _api_post(
                    "/api/tasks",
                    {
                        "title": h[:200],
                        "description": f"Auto-detected from {imp_file} in {repo_name}",
                        "priority": 2,
                        "repo": repo_name,
                        "roadmap_item": f"Improvement: {imp_file}",
                    },
                )
                if result:
                    existing_titles.add(norm)
                    created += 1
                    print(f"[scheduler:improvement]  ✨ Created improvement: {h[:60]}...")

        # Check for stale CI — if repo has .github/workflows but no CI badge
        ci_dir = os.path.join(repo_path, ".github", "workflows")
        has_ci = os.path.isdir(ci_dir) and bool(os.listdir(ci_dir))
        readme_path = os.path.join(repo_path, "README.md")
        has_badge = False
        if has_ci and os.path.isfile(readme_path):
            try:
                with open(readme_path, encoding="utf-8", errors="replace") as f:
                    readme = f.read(5000)
                has_badge = (
                    "github/actions" in readme.lower()
                    or "ci" in readme.lower()
                    and "badge" in readme.lower()
                    or "[![ci" in readme.lower()
                )
            except Exception:  # noqa: S110
                pass  # optional readme scan

        title = f"Add CI badge to README for {repo_name}"
        norm = title.strip().lower()
        if has_ci and not has_badge and norm not in existing_titles:
            result = await _api_post(
                "/api/tasks",
                {
                    "title": title,
                    "description": f"{repo_name} has CI workflows but no status badge in README.md",
                    "priority": 3,
                    "repo": repo_name,
                    "roadmap_item": "Improvement: CI Visibility",
                },
            )
            if result:
                existing_titles.add(norm)
                created += 1
                print(f"[scheduler:improvement] ✨ Created CI badge task for {repo_name}")

    return created


async def check_backlog_and_trigger(overview: dict | None = None) -> bool:
    """Check if backlog is low and trigger scanner if needed.

    Counts ONLY actionable tasks (fail_count < max_attempts) — zombies
    that have exhausted their retries don't count toward the threshold.

    Returns True if scanner was triggered.
    Designed to be called from metrics_collector or dead_board_monitor.
    """
    global _last_trigger_ms

    import time

    now_ms = int(time.time() * 1000)

    # Cooldown check
    if now_ms - _last_trigger_ms < TRIGGER_COOLDOWN_SECONDS * 1000:
        return False

    # Count actionable tasks, not zombies
    actionable = await _get_actionable_available_count()

    if overview is None:
        overview = await _api_get("/api/analytics/overview")
    done = overview.get("total_done", 0) if overview else 0

    print(f"[scheduler:low-backlog] Actionable available: {actionable} / total done: {done}")

    # Critical: almost nothing actionable
    if actionable <= CRITICAL_BACKLOG_THRESHOLD and done > 5:
        print(f"[scheduler:low-backlog] CRITICAL: only {actionable} actionable, triggering scanner")
        _last_trigger_ms = now_ms
        scanner_result = await _trigger_scanner()
        total_created = (
            sum(c.get("created", 0) for c in scanner_result.values())
            if isinstance(scanner_result, dict)
            else 0
        )
        # If scanner found nothing, generate improvement tasks
        if total_created == 0:
            imp_created = await _generate_improvement_tasks()
            print(
                f"[scheduler:low-backlog] Scanner found nothing, "
                f"generated {imp_created} improvement task(s)"
            )
        return True

    # Low: running out of work
    if actionable <= LOW_BACKLOG_THRESHOLD and done > 5:
        print(f"[scheduler:low-backlog] Low backlog: {actionable} actionable, triggering scanner")
        _last_trigger_ms = now_ms
        scanner_result = await _trigger_scanner()
        total_created = (
            sum(c.get("created", 0) for c in scanner_result.values())
            if isinstance(scanner_result, dict)
            else 0
        )
        if total_created == 0:
            imp_created = await _generate_improvement_tasks()
            print(
                f"[scheduler:low-backlog] Scanner found nothing, "
                f"generated {imp_created} improvement task(s)"
            )
        return True

    return False
