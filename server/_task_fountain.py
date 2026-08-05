#!/usr/bin/env python3
"""Ultra-fast task fountain — keeps a minimum pool of available tasks.

Only keeps the board healthy when tasks are running low.
Does NOT duplicate main scanner findings (unwraps, bare excepts, large files, etc.)
to prevent infinite task loops. The main scanner system (scanners/runner.py)
handles those on a longer interval with proper dedup.

Only scans a configurable set of repos (KANBAN_REPOS env, default: this
repo itself). No discover_repos overhead.

Dedup strategy (2026-07-31 fix): the old implementation fetched only
limit=200 per status (available/inProgress/blocked/done) = max 800 titles
on a 22k-task board, so any duplicate older than the newest 200 in its
status bucket was invisible. fetch_board_state() now queries per-repo with
a high limit (all statuses at once), covering the ENTIRE board. If any
repo query fails the run aborts — creating tasks with an incomplete dedup
set is exactly how duplicates got on the board in the first place.

Board-health gate (2026-07-31 fix): the available-count check moved into
run() and is evaluated ONCE per run. The old per-repo check created up to
9 identical "Review X" tasks in a single run; scan_board_health now emits
at most ONE task per run.
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("KANBAN_API", "http://localhost:8727")

# Board queries take 30s+ under load — the old 5s timeout failed, yielding
# an EMPTY dedup set → guaranteed duplicates. 60s gives per-repo full-board
# queries room to complete.
API_TIMEOUT = 60

# Per-repo query limit for dedup. Must exceed the largest repo's task count
# so the dedup set covers every task on the board (all statuses). One
# request per repo is a single sorted snapshot, so nothing is truncated
# or reordered between paginated requests.
DEDUP_LIMIT = 100_000

# The board-health scanner only fires when available tasks drop below this.
MIN_AVAILABLE_TASKS = 3

# Repos the fountain scans. Override with KANBAN_REPOS (comma-separated
# repo names) to target your own projects. Default: this repo itself only —
# no assumptions about sibling projects on the host.
_DEFAULT_REPOS = ["spacetime-kanban"]
REPOS = [r.strip() for r in os.environ.get("KANBAN_REPOS", "").split(",") if r.strip()] or list(
    _DEFAULT_REPOS
)

HOME = os.path.expanduser("~")

# Scanner registry — each is a function that returns findings
SCANNERS = []

# Set when scan_board_health emits its one task per run — guarantees the
# fountain creates AT MOST ONE health task per run, not one per repo.
_health_emitted = False


def register(fn):
    SCANNERS.append(fn)
    return fn


def api_get(path: str):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=API_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def api_post(path: str, data: dict):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{API}{path}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {"status": "ok"}
    except Exception:
        return None


def fetch_board_state() -> tuple[set[str], int] | None:
    """Fetch the WHOLE board's titles + available-task count for dedup/gating.

    Queries per-repo (GET /api/tasks?repo=X&limit=DEDUP_LIMIT) — one request
    per repo returns ALL statuses for that repo, so the union covers every
    task on the board. The old per-status limit=200 capped the set at 800
    titles on a 22k-task board, making old duplicates invisible.

    Returns (titles, available_count) or None if ANY repo query fails —
    callers must abort creation rather than risk duplicates from an
    incomplete dedup set.
    """
    existing: set[str] = set()
    available = 0
    for repo in REPOS:
        tasks = api_get(f"/api/tasks?repo={repo}&limit={DEDUP_LIMIT}")
        if tasks is None or not isinstance(tasks, list):
            return None
        for t in tasks:
            title = t.get("title", "")
            if title:
                existing.add(title.strip().lower())
            if t.get("status") == "available":
                available += 1
    return existing, available


def fetch_existing_titles() -> set[str] | None:
    """Whole-board titles only (wrapper over fetch_board_state)."""
    state = fetch_board_state()
    return state[0] if state is not None else None


def is_dup(title: str, existing: set[str]) -> bool:
    return title.strip().lower() in existing


# ── Scanner: Board health — keeps minimum task pool ──
# This is the ONLY scanner in the fountain. All other scanner types
# (unwraps, bare excepts, large files, test gaps, etc.) run via the
# main scanner system (scanners/runner.py) on a longer interval.
# Having duplicates here creates infinite task loops because the
# fountain runs every 60s while the main scanner dedup can't keep up.


@register
def scan_board_health(repo_name: str, repo_path: str) -> list[dict]:
    """Create at most ONE generic 'review repo' task per fountain run.

    The available-count gate lives in run() (checked ONCE per run, not per
    repo — per-repo checks created up to 9 identical review tasks in a
    single fountain run).
    """
    global _health_emitted
    if _health_emitted:
        return []
    _health_emitted = True
    return [
        {
            "title": f"Review {repo_name} for actionable improvements",
            "description": (
                f"Auto-generated by task fountain. "
                f"Review {repo_name} and create concrete tasks as needed."
            ),
            "priority": 4,
        }
    ]


# ── Main ──


def run() -> int:
    """Run all scanners on all repos. Returns number of tasks created."""
    state = fetch_board_state()
    if state is None:
        # Never create with an incomplete dedup set — that's how duplicates
        # got on the board. Retry next cycle (60s).
        print(
            "[fountain] dedup fetch failed — aborting run (incomplete dedup set)",
            file=sys.stderr,
        )
        return 0
    existing, available = state

    global _health_emitted
    _health_emitted = False

    # Board-health gate — evaluated ONCE per run, not once per repo.
    board_low = available < MIN_AVAILABLE_TASKS

    print(
        f"  existing={len(existing)} available={available} repos={len(REPOS)}",
        file=sys.stderr,
    )

    created = 0
    for repo_name in REPOS:
        repo_path = os.path.join(HOME, repo_name)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            continue

        for scanner in SCANNERS:
            if scanner is scan_board_health and not board_low:
                continue
            try:
                findings = scanner(repo_name, repo_path)
            except Exception:
                continue

            if not findings:
                continue

            for f in findings:
                title = f["title"]
                if is_dup(title, existing):
                    continue
                result = api_post(
                    "/api/tasks",
                    {
                        "title": title,
                        "description": f.get("description", ""),
                        "priority": f.get("priority", 2),
                        "repo": repo_name,
                        "roadmap_item": "Scanner: task-fountain",
                    },
                )
                if result:
                    existing.add(title.strip().lower())
                    created += 1

    return created


if __name__ == "__main__":
    n = run()
    print(f"[fountain] Created {n} task(s)", file=sys.stderr)
    sys.exit(0)
