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


# ── Actionable-heading extraction ──────────────────────────────────
# Improvement docs (IMPROVEMENTS.md, PERFORMANCE.md, ...) use `## ` for
# SECTION headers and `### ` for concrete items. The old code created a
# task from every `## ` line, so structural sections like "Recently
# Completed", "Deferred / Blocked", "Status: PENDING" and "Summary"
# became kanban tasks that workers burned turns on. Only headings that
# describe something DOABLE become tasks.

import re as _re

# Sections whose CHILDREN are never tasks (they're status/log/done lists).
_SECTION_SKIP_CHILDREN = {
    "recently completed",
    "recently completed:",
    "deferred",
    "deferred / blocked",
    "deferred / won't do",
    "deferred / wont do",
    "deferred/won't do",
    "won't do",
    "wont do",
    "research log",
    "research log:",
    "reference results",
    "reference results (full suite)",
    "build verification results",
    "build verification",
    "known deficiencies vs reference browsers",
    "known deficiencies",
    "summary",
    "summary:",
    "current audit — what exists",
    "current audit - what exists",
    "legacy",
    "legacy / future backlog (not yet scoped as tasks)",
    "future improvements",
    "next steps",
    "next most important",
    "table of contents",
    "introduction",
    "overview",
    "appendix",
    "related documents",
    "executive summary",
    "why this policy?",
    "why this policy",
    "references",
    "architecture",
    "background",
    "conclusion",
    "completion",
    "completed",
    "all implemented",
    "checklist",
    "todo:",
    "todo",
    "what we're building",
}

# Sections to skip as a TASK TITLE themselves, but whose children may be
# actionable (e.g. "## Status: PENDING" → children are the pending tasks).
_SECTION_SKIP_SELF = {
    "pending",
    "pending:",
    "blocked",
    "blocked:",
    "status: pending",
    "status: complete",
    "status: completed",
    "status: all implemented",
    "status: complete (all items implemented)",
}

# Prefixes that mark a heading as structural/status even with extra text.
# NOTE: "status:" is deliberately NOT here — a "## Status: PENDING" section's
# children ARE the pending tasks and must be evaluated. Only done/deferred-
# style prefixes skip children.
_SECTION_PREFIXES = (
    "recently completed",
    "deferred",
    "won't do",
    "wont do",
    "table of",
    "build verification",
    "reference results",
    "known deficiencies",
    "research log",
    "status: complete",
    "status: completed",
    "status: all implemented",
)

# Action verbs — a heading containing one of these is very likely actionable.
_ACTION_VERBS = (
    "add",
    "fix",
    "implement",
    "refactor",
    "update",
    "remove",
    "optimize",
    "migrate",
    "replace",
    "support",
    "document",
    "test",
    "create",
    "improve",
    "reduce",
    "increase",
    "enable",
    "expose",
    "port",
    "rewrite",
    "rename",
    "reorganize",
    "split",
    "merge",
    "extract",
    "deduplicate",
    "audit",
    "verify",
    "publish",
    "release",
    "deprecate",
    "clean",
    "unpin",
    "pin",
    "write",
    "cover",
    "handle",
    "respect",
    "preserve",
    "avoid",
    "prevent",
    "monitor",
    "log",
    "ship",
    "standardize",
    "unify",
    "simplify",
    "harden",
    "secure",
    "configure",
    "make",
    "ensure",
    "investigate",
    "research",
    "track",
    "integrate",
    "triage",
    "prioritize",
    "align",
    "match",
    "keep",
    "share",
    "build",
    "establish",
    "define",
    "propose",
    "republish",
    "refresh",
    "resolve",
    "backfill",
    "bootstrap",
    "seed",
    "scaffold",
    "normalize",
    "enrich",
    "retry",
    "rework",
    "redesign",
    "restructure",
    "reorganize",
    "expand",
    "extend",
    "catch",
    "raise",
    "tune",
    "calibrate",
    "validate",
    "cleanup",
)

# Markers that mean the heading describes something already done / not to do.
_NON_ACTIONABLE_MARKERS = (
    "blocked",
    "won't do",
    "wont do",
    "deferred",
    "not scoped",
    "not yet",
    "future",
    "done",
    "completed",
    "implemented",
    "no longer",
    "retired",
    "removed",
    "baseline",  # "Ungoogled Chromium (baseline)" = comparison section, not a task
    "wip",
    "research log",
    "reconciliation",
)

# Status emojis that mark a heading as a status list, not a task.
_EMOJI_STATUS = ("✅", "❌", "🟡", "📝", "🔴", "🟢", "✔", "☑", "🔜")


def _extract_actionable_headings(content: str) -> list[dict]:
    """Return actionable headings as [{title, context}].

    Rules:
      - Parse both `## ` (sections) and `### ` (items) headings in order.
      - Sections whose children are status lists (Recently Completed,
        Deferred, Research Log, ...) are skipped along with their children.
      - Sections like "Status: PENDING" are skipped as titles but their
        children ARE evaluated (those are the pending tasks).
      - A heading is actionable if it contains an action verb, a priority
        marker (P0-P3), or a strong action signal (should/needs/missing...),
        AND does not contain a non-actionable marker (blocked/done/etc).
      - Short headings (<10 chars) are skipped.
    """
    headings = []
    for match in _re.finditer(r"^(#{2,3})\s+(.*)$", content, _re.MULTILINE):
        level = len(match.group(1))
        text = match.group(2).strip()
        headings.append({"level": level, "text": text})

    # Current ## section name (lowercased) — children inherit its skip state.
    current_section = ""
    results: list[dict] = []

    for h in headings:
        text = h["text"]
        lowered = text.lower().strip()

        if h["level"] == 2:
            current_section = lowered
            if lowered in _SECTION_SKIP_SELF:
                continue  # skip the title itself; children evaluated below
            if lowered in _SECTION_SKIP_CHILDREN or any(
                lowered.startswith(p) for p in _SECTION_PREFIXES
            ):
                continue  # skip the title AND its children (state persists)
            if not _is_actionable(text):
                continue
            results.append({"title": text, "context": text})
            continue

        # ### item — skip if inside a children-skipped section
        if current_section in _SECTION_SKIP_CHILDREN or any(
            current_section.startswith(p) for p in _SECTION_PREFIXES
        ):
            continue
        if not _is_actionable(text):
            continue
        results.append({"title": text, "context": text})

    return results


def _is_actionable(text: str) -> bool:
    """Decide whether a heading describes something a worker can actually do."""
    t = text.strip()
    if len(t) < 10:
        return False
    lowered = t.lower()

    # Status emoji → skip (e.g. "✅ Fully Implemented")
    if any(e in text for e in _EMOJI_STATUS):
        return False

    # Non-actionable markers (blocked/deferred/done/etc) → skip
    if any(m in lowered for m in _NON_ACTIONABLE_MARKERS):
        return False

    # Priority marker (P0/P1/P2/P3) → actionable (e.g. "STDB: republish (P0)")
    if _re.search(r"\(?\s*p[0-9]\s*\)?", lowered):
        return True

    # Action verb anywhere in the heading → actionable
    if any(v in lowered for v in _ACTION_VERBS):
        return True

    # Strong action signal
    if any(s in lowered for s in ("should", "needs", "must", "missing", "broken", "fails")):
        return True

    # Default: plain noun phrases ("Retrieval Quality") are research topics,
    # not doable tasks — skip to avoid junk.
    return False


async def _generate_improvement_tasks() -> int:
    """When scanners find nothing, generate self-improvement tasks from project files.

    Creates tasks from IMPROVEMENTS.md, PERFORMANCE.md, etc. — files that
    contain structured improvement suggestions that aren't in ROADMAP.md.
    Also checks for common quality issues (missing CI, stale docs, etc.).

    CRITICAL: only ACTUALLY ACTIONABLE headings become tasks. The old code
    created a task for every ``## `` heading, which turned document section
    headers ("Recently Completed", "Deferred / Blocked", "Status: PENDING",
    "Summary", "Reference Results") into kanban tasks that workers then
    burned LLM turns on pointlessly. Structural/status sections and
    blocked/deferred items are skipped; sub-headings (###) under an
    actionable section are preferred.
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

            for heading in _extract_actionable_headings(content):
                norm = heading["title"].strip().lower()
                if norm in existing_titles:
                    continue
                result = await _api_post(
                    "/api/tasks",
                    {
                        "title": heading["title"][:200],
                        "description": (
                            f"Auto-detected from {imp_file} in {repo_name}. "
                            f"Context: {heading['context'][:300]}"
                        ),
                        "priority": 2,
                        "repo": repo_name,
                        "roadmap_item": f"Improvement: {imp_file}",
                    },
                )
                if result:
                    existing_titles.add(norm)
                    created += 1
                    print(f"[scheduler:improvement]  ✨ Created improvement: {heading['title'][:60]}...")

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
