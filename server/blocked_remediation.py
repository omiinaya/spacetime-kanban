"""Blocked-task remediation — audit and clear the blocked-task backlog.

Why this exists (verified 2026-07-31):
  The board accumulated 7,021+ blocked tasks (~32% of all tasks). Root causes:

  1. Scanner artifacts that can never complete. The large-file generator
     once emitted tasks listing ``.venv`` site-packages files (fixed: the
     repo walker now excludes .venv), and the stdb_index scanner emitted
     per-chunk tasks that workers blocked with "No indexable fields found —
     all foreign keys already indexed".
  2. The self_improver's stale-task watcher created NEW "[Stale]" tasks
     under the wrong repo (spacetimedb-kanban) instead of tagging the
     original task's repo.
  3. The hourly archiver silently no-oped: its 15s HTTP timeout was shorter
     than the board query (30s+ under load), so the fetch returned None and
     the >24h blocked archival never ran.

This module classifies blocked tasks and archives the un-actionable ones so
the active board reflects reality and the backlog cannot re-accumulate.
It is importable standalone (no scheduler dependency) — the scheduler loop
and the one-time CLI cleanup both use ``run_blocked_remediation``.
"""

import os
import re
import sys
import time

# Scanner-fixed markers: descriptions/fail_reasons that reference paths the
# scanners no longer produce (the walker excludes .venv / site-packages).
_PATH_MARKERS = (".venv", "site-packages", "/venv/", "\\venv\\")

# Path-looking tokens in scanner descriptions are lines like
#   - path/to/file.py
#   - /abs/path/to/file.rs (1234 lines)
_SOURCE_EXTENSIONS = (
    ".py",
    ".rs",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".java",
    ".rb",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".sh",
    ".sql",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".html",
    ".css",
    ".scss",
    ".vue",
    ".svelte",
)

# Board-scale fetch limit — mirrors the scanner/fountain dedup convention.
# list_tasks applies `limit` client-side AFTER fetching all matching rows,
# so one request with limit >= board size returns the whole blocked set.
BLOCKED_FETCH_LIMIT = 100_000

# Stale blocked tasks: no activity for this many days → archive.
DEFAULT_STALE_DAYS = 3


def _repo_path_for(repo: str) -> str | None:
    """Resolve a repo name to its on-disk path (None when not present)."""
    if not repo:
        return None
    path = os.path.join(os.path.expanduser("~"), repo)
    return path if os.path.isdir(os.path.join(path, ".git")) else None


def _extract_referenced_paths(description: str) -> list[str]:
    """Pull file-path-looking tokens out of a scanner task description.

    Scanner descriptions list files as markdown bullets:
      - server/routes/tasks.py
      - /home/.../site-packages/idna/uts46data.py (16896 lines)
    Only tokens that look like paths are returned — bullet text like
    "  - 2 files need attention" is not path-like and is skipped.
    """
    paths: list[str] = []
    for raw in (description or "").splitlines():
        line = raw.strip()
        if not line.startswith("- "):
            continue
        token = line[2:].strip()
        # Strip trailing " (NNNN lines)" annotations and punctuation.
        token = re.sub(r"\s*\(\d+\s+lines?\)\s*$", "", token)
        token = token.rstrip(".,;:")
        if not token:
            continue
        if "/" not in token and not token.endswith(_SOURCE_EXTENSIONS):
            continue  # not path-like
        paths.append(token)
    return paths


def _path_exists(candidate: str, repo_path: str) -> bool:
    """Check a referenced path on disk (absolute or repo-relative)."""
    if candidate.startswith("/"):
        return os.path.exists(candidate)
    return os.path.exists(os.path.join(repo_path, candidate))


def blocked_dismiss_reason(task: dict, repo_path: str | None = None) -> str | None:
    """Return an auto-dismiss reason for an un-actionable blocked task.

    Returns ``None`` when the task is potentially actionable (leave it).

    Dismiss categories:
      1. ``[Stale]`` artifacts — new tasks the self_improver created instead
         of fixing the original in_progress task; the stale_watcher's
         unclaim is the real fix, these copies are superseded.
      2. Scanner false positives — worker already confirmed there is nothing
         to do ("No indexable fields found", "No extractable functions").
      3. Descriptions/fail reasons referencing ``.venv`` / ``site-packages``
         paths — the scanner was fixed to exclude them, so these tasks can
         never be done.
      4. Descriptions referencing files that no longer exist on disk.
    """
    title = task.get("title") or ""
    desc = task.get("description") or ""
    fail = task.get("fail_reason") or ""

    if title.startswith("[Stale]"):
        return "stale-watcher artifact — original task handled by stale_watcher"

    if "No indexable fields found" in fail:
        return "stdb_index scanner false positive — fields already indexed"

    if "No extractable functions/classes found" in fail:
        return "task-generator false positive — nothing to extract/split"

    if "only has one top-level item" in fail:
        return "task-generator false positive — nothing to extract/split"

    if "No test files created" in fail:
        return "test_gaps scanner false positive — tests already exist"

    if "No __init__.py files created" in fail:
        return "architecture scanner false positive — __init__.py already exists"

    if "No .rs or .py source files found" in fail:
        return "scanner artifact — repo has no scannable source files"

    if any(m in desc for m in _PATH_MARKERS) or any(m in fail for m in _PATH_MARKERS):
        return "references excluded .venv/site-packages path(s)"

    # File-existence audit: if the description names files and NONE of them
    # exist anymore, the task is un-actionable. Only trust this when the repo
    # is resolvable on disk (otherwise we cannot verify and must not guess).
    if repo_path:
        refs = _extract_referenced_paths(desc)
        if refs and not any(_path_exists(p, repo_path) for p in refs):
            return "referenced file(s) no longer exist on disk"

    return None


async def run_blocked_remediation(
    api_get,
    api_post,
    fire_event,
    now_ms: int | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
    max_archive_per_tick: int = 3000,
    batch_size: int = 25,
    timeout: float = 300.0,
) -> dict:
    """Fetch blocked tasks, classify, archive the un-actionable/stale ones.

    ``api_get``/``api_post`` are async callables with the scheduler's
    signatures (path[, data], timeout=...). ``fire_event(event, data)`` is
    called once per run when anything was archived (human-review visibility).

    Returns a summary dict:
      fetched, auto_dismissed, stale_archived, archived, samples, active_blocked
    """
    import asyncio

    from webhook_dispatcher import EVENT_BLOCKED_REMEDIATED

    now = now_ms if now_ms is not None else int(time.time() * 1000)

    blocked = await api_get(
        f"/api/tasks?status=blocked&archived=false&limit={BLOCKED_FETCH_LIMIT}",
        timeout=timeout,
    )
    if not blocked:
        return {
            "fetched": 0,
            "auto_dismissed": 0,
            "stale_archived": 0,
            "archived": 0,
            "samples": [],
            "active_blocked": 0,
        }

    cutoff = now - stale_days * 86_400_000
    to_archive: list[tuple[str, str, str]] = []  # (task_id, title, reason)
    for t in blocked:
        tid = t.get("id")
        if not tid:
            continue
        reason = blocked_dismiss_reason(t, _repo_path_for(t.get("repo") or ""))
        if not reason:
            updated = t.get("updated_at") or 0
            if updated and updated < cutoff:
                reason = f"blocked >{stale_days}d with no activity"
        if reason:
            to_archive.append((tid, t.get("title") or "?", reason))

    to_archive = to_archive[:max_archive_per_tick]

    archived = 0
    for i in range(0, len(to_archive), batch_size):
        batch = [tid for tid, _title, _reason in to_archive[i : i + batch_size]]
        result = await api_post("/api/tasks/bulk-archive", {"task_ids": batch}, timeout=timeout)
        if isinstance(result, dict) and isinstance(result.get("archived"), int):
            archived += result["archived"]
        # else: batch failed (timeout/error) — do NOT count it; the hourly
        # loop retries next run. Counting failures inflated the report.
        await asyncio.sleep(0)  # yield to the event loop between batches

    auto_dismissed = sum(
        1 for _tid, _title, reason in to_archive if not reason.startswith("blocked >")
    )
    stale_archived = sum(1 for _tid, _title, reason in to_archive if reason.startswith("blocked >"))

    samples = [
        {"task_id": tid, "title": title[:60], "reason": reason}
        for tid, title, reason in to_archive[:5]
    ]

    if archived:
        try:
            await fire_event(
                EVENT_BLOCKED_REMEDIATED,
                {
                    "archived": archived,
                    "auto_dismissed": auto_dismissed,
                    "stale_archived": stale_archived,
                    "active_blocked": max(len(blocked) - archived, 0),
                    "samples": samples,
                },
            )
        except Exception as e:  # noqa: BLE001 — webhook failure must never abort remediation
            print(f"  [webhook] {EVENT_BLOCKED_REMEDIATED} failed: {e}", file=sys.stderr)

    return {
        "fetched": len(blocked),
        "auto_dismissed": auto_dismissed,
        "stale_archived": stale_archived,
        "archived": archived,
        "samples": samples,
        "active_blocked": max(len(blocked) - archived, 0),
    }


if __name__ == "__main__":
    # One-shot CLI cleanup: python3 blocked_remediation.py
    import asyncio
    import json
    import sys
    import urllib.error
    import urllib.request

    API = os.environ.get("KANBAN_API", "http://localhost:8727")

    if not API.startswith(("http://", "https://")):
        raise SystemExit(f"KANBAN_API must be http(s)://, got: {API}")

    async def _api_get(path: str, timeout: float = 60.0):
        try:
            req = urllib.request.Request(f"{API}{path}")  # noqa: S310 — localhost API only
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return json.loads(resp.read().decode())
        except Exception:
            return None

    async def _api_post(path: str, data: dict, timeout: float = 60.0):
        try:
            body = json.dumps(data).encode()
            req = urllib.request.Request(  # noqa: S310 — localhost API only
                f"{API}{path}", data=body, method="POST"
            )
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                content = resp.read().decode()
                return json.loads(content) if content else {"status": "ok"}
        except urllib.error.HTTPError as e:
            print(f"  POST {path} HTTP {e.code}: {e.read().decode()[:200]}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"  POST {path}: {e}", file=sys.stderr)
            return None

    async def _fire(event: str, data: dict):
        print(f"[webhook] {event}: {json.dumps(data)[:300]}")

    summary = asyncio.run(
        run_blocked_remediation(
            api_get=_api_get,
            api_post=_api_post,
            fire_event=_fire,
            timeout=60.0,
        )
    )
    print(json.dumps(summary, indent=2))
