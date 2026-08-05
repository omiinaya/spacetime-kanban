"""Scanner runner — runs all registered scanners, deduplicates, creates tasks.

Orchestration:
  1. Compute project health for progressive layer escalation
  2. Verify completed tasks (re-check fix stuck)
  3. Run each scanner against each repo
  4. Skip higher-layer tasks if lower layers are unresolved
  5. Deduplicate against existing board state (all statues)
  6. Create new tasks via API
  7. Report results
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Ensure server package is on path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(script_dir)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from scanners import SCANNERS, discover_repos, get_scanner_name  # noqa: E402

# ── Layer progression config ────────────────────────────────────────

# Scanner → layer mapping (0=critical, 4=polish)
SCANNER_LAYER: dict[str, int] = {
    "stdb_index": 0,
    "todos": 1,
    "deps": 1,
    "unused_code": 1,
    "test_gaps": 1,
    "architecture": 2,
    "docs_ci": 3,
    "prod_readiness": 4,
}

# Minimum layer score before allowing next layer tasks
LAYER_THRESHOLD = {0: 0.5, 1: 0.7, 2: 0.8, 3: 0.9, 4: 1.0}


# ── API helpers ─────────────────────────────────────────────────────

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")


def _api_get(path: str) -> Any:
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def _api_post(path: str, data: dict) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{API_BASE}{path}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=30)
        content = resp.read().decode()
        return json.loads(content) if content else {"status": "ok"}
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        print(f"[scanner] POST {path} HTTP {e.code}: {err}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[scanner] POST {path}: {e}", file=sys.stderr)
        return None


# ── Dedup & health ──────────────────────────────────────────────────

# Board-scale fetch limit for dedup. The API applies `limit` client-side
# AFTER fetching every matching row from the DB, so one request with a
# limit >= total board size returns the whole board in a single snapshot.
# The old per-status limit=500 capped dedup coverage at ~2,000 titles on
# a 22K-task board (~9%), so older done tasks (e.g. "Replace bare
# except:") were invisible to dedup and the scanner kept re-creating
# them. Same convention as _task_fountain.DEDUP_LIMIT.
DEDUP_LIMIT = 100_000


def _dedup_key(repo: str, title: str) -> tuple[str, str]:
    """Normalize (repo, title) into a case-insensitive dedup key.

    Dedup is scoped per-repo: a title like "Replace bare except:" is
    legitimate once per repo, but duplicates WITHIN a repo are bugs the
    scanner must not re-create. Keying on bare title alone also let one
    repo's task block an unrelated repo's task with the same title.
    """
    return (repo.strip().lower(), title.strip().lower())


def _fetch_existing_titles() -> set[tuple[str, str]]:
    """Fetch all task (repo, title) keys from the board (incl. done) for dedup.

    One unfiltered call (no status= filter) with a board-scale limit
    covers every status — available/inProgress/blocked/done/archived —
    in a single snapshot: no pagination, no per-status truncation.
    """
    existing = set()
    tasks = _api_get(f"/api/tasks?limit={DEDUP_LIMIT}")
    if not tasks:
        return existing
    for t in tasks:
        title = t.get("title", "")
        if title:
            existing.add(_dedup_key(t.get("repo", ""), title))
    return existing


def _is_duplicate(repo: str, title: str, existing: set[tuple[str, str]]) -> bool:
    return _dedup_key(repo, title) in existing


def _compute_project_layer_scores(repo_name: str) -> dict[int, float]:
    """Compute what % of each layer's tasks are done for a project."""
    from collections import Counter

    all_tasks = _api_get(f"/api/tasks?repo={repo_name}&limit={DEDUP_LIMIT}")
    if not all_tasks:
        return {}

    layer_total = Counter()
    layer_done = Counter()

    for t in all_tasks:
        ri = t.get("roadmap_item") or ""
        scanner = ri.replace("Scanner: ", "") if ri.startswith("Scanner:") else ""
        layer = SCANNER_LAYER.get(scanner, -1)
        if layer < 0:
            continue

        layer_total[layer] += 1
        status = t.get("status", "")
        if status == "done" or t.get("archived", False):
            layer_done[layer] += 1

    scores = {}
    for layer in range(5):
        total = layer_total.get(layer, 0)
        done = layer_done.get(layer, 0)
        scores[layer] = round(done / total, 2) if total > 0 else 1.0

    return scores


# ── Completion verifier ─────────────────────────────────────────────


def _verify_completed_tasks(
    repos: list[tuple[str, str]], existing: set[tuple[str, str]], deadline: float | None = None
) -> int:
    """Re-check done tasks to ensure the underlying issue is still fixed.

    Only checks tasks done in the last 7 days. Only re-runs the exact
    scanner that originally created each task (not all scanners).
    ``deadline`` (monotonic) bounds the whole verification pass.
    """
    regressed = 0
    now_ms = int(time.time() * 1000)
    seven_days_ms = 7 * 86400 * 1000

    def _over_budget() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    for repo_name, repo_path in repos:
        if _over_budget():
            break
        done_tasks = _api_get(f"/api/tasks?status=done&repo={repo_name}&limit={DEDUP_LIMIT}")
        if not done_tasks:
            continue

        # Group done tasks by scanner so we run each scanner once per repo
        by_scanner: dict[str, list[dict]] = {}
        for t in done_tasks:
            ri = t.get("roadmap_item") or ""
            scanner_name = ri.replace("Scanner: ", "") if ri.startswith("Scanner:") else ""
            if not scanner_name:
                continue
            # Only check recently completed tasks
            updated = t.get("updated_at", 0)
            if updated and (now_ms - updated) > seven_days_ms:
                continue
            if scanner_name not in by_scanner:
                by_scanner[scanner_name] = []
            by_scanner[scanner_name].append(t)

        if not by_scanner:
            continue

        # Find each scanner once and check all its done tasks
        for scanner_fn in SCANNERS:
            if _over_budget():
                break
            sname = get_scanner_name(scanner_fn)
            tasks_to_check = by_scanner.get(sname)
            if not tasks_to_check:
                continue

            try:
                fresh_findings = scanner_fn(repo_name, repo_path)
            except Exception:
                continue

            # Build dict mapping title→finding for skip_verify check
            fresh_map = {}
            for ff in fresh_findings:
                ff_title = ff["title"].strip().lower()
                fresh_map[ff_title] = ff

            for t in tasks_to_check:
                title = t.get("title", "").strip().lower()
                tid = t.get("id", "")
                if title not in fresh_map:
                    continue
                # skip_verify flag: find-only scanners (unwraps, bare excepts, etc.)
                # whose tasks can't be auto-fixed. Re-opening them creates an
                # infinite loop because the issue persists after completion.
                if fresh_map[title].get("skip_verify"):
                    continue
                _api_post(f"/api/tasks/{tid}/unarchive", {})
                # Unarchive transitions done→available; skip 409 errors silently
                existing.add(_dedup_key(repo_name, title))
                regressed += 1
                print(f"[scanner] ⚠ Re-opened regressed: {title[:60]}...", file=sys.stderr)

    return regressed


def _close_stale_available_tasks(
    repos: list[tuple[str, str]], existing: set[tuple[str, str]], deadline: float | None = None
) -> int:
    """Archive available scanner tasks whose finding no longer exists.

    Complement to _verify_completed_tasks (which re-opens regressed *done*
    tasks). If a task is still *available* — no worker ever claimed it — but
    its originating scanner no longer reports the finding, the issue was
    fixed (or the finding became obsolete, e.g. a smarter matcher). Leaving
    it available would let a worker burn turns on a non-issue.

    Closes the task via the block-with-reason endpoint (transitions
    available → blocked), then archives it so it leaves the active board.
    ``deadline`` (monotonic) bounds the whole pass.
    """
    closed = 0
    now_ms = int(time.time() * 1000)
    thirty_days_ms = 30 * 86400 * 1000

    def _over_budget() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    for repo_name, repo_path in repos:
        if _over_budget():
            break
        avail_tasks = _api_get(f"/api/tasks?status=available&repo={repo_name}&limit={DEDUP_LIMIT}")
        if not avail_tasks:
            continue

        # Group available tasks by originating scanner (roadmap_item "Scanner: X")
        by_scanner: dict[str, list[dict]] = {}
        for t in avail_tasks:
            ri = t.get("roadmap_item") or ""
            scanner_name = ri.replace("Scanner: ", "") if ri.startswith("Scanner:") else ""
            if not scanner_name:
                continue
            created = t.get("created_at", 0)
            if created and (now_ms - created) > thirty_days_ms:
                continue  # only touch recently-created tasks
            by_scanner.setdefault(scanner_name, []).append(t)

        # find each scanner once and close its stale available tasks
        for sname, tasks in by_scanner.items():
            if _over_budget():
                break
            fn = _scanner_by_name(sname)
            if fn is None:
                continue
            try:
                fresh = fn(repo_name, repo_path)
            except Exception:
                continue
            fresh_set = {f["title"].strip().lower() for f in fresh}

            for t in tasks:
                title = t.get("title", "").strip().lower()
                if title in fresh_set:
                    continue  # finding still present — leave alone
                tid = t.get("id", "")
                if not tid:
                    continue
                # Finding vanished → block + archive the stale task.
                _api_post(
                    f"/api/tasks/{tid}/block",
                    {"reason": "stale", "notes": "finding no longer detected by scanner"},
                )
                _api_post(f"/api/tasks/{tid}/archive", {})
                closed += 1
                print(f"[scanner] Closed stale available task: {title[:55]}...", file=sys.stderr)

    return closed


def _scanner_by_name(name: str):
    for fn in SCANNERS:
        if get_scanner_name(fn) == name:
            return fn
    return None


def run_all_scanners(repos: list[tuple[str, str]] | None = None, time_budget: float = 90.0) -> dict:
    """Run all scanners against all repos with progressive layer escalation.

    1. Verifies completed tasks (re-opens regressed ones)
    2. Computes layer scores per project
    3. Skips scanners above the highest unresolved layer
    4. Deduplicates and creates tasks

    ``time_budget`` bounds the WHOLE run in seconds. Scanners run inside
    the server process (low-backlog trigger → run_in_executor); an
    unbounded run (50 repos × cargo check / npx / git log with per-call
    timeouts up to 60s) can peg CPU for 20+ minutes and starve /api/health.
    The budget is checked between repos AND between scanners, so even one
    pathological repo cannot stall the server.
    """
    if repos is None:
        repos = discover_repos()

    print(
        f"[scanner] Scanning {len(repos)} repos with {len(SCANNERS)} scanner(s) "
        f"(budget {time_budget}s)...",
        file=sys.stderr,
    )

    deadline = time.monotonic() + time_budget

    def _over_budget() -> bool:
        if time.monotonic() >= deadline:
            print("[scanner] Time budget exhausted — stopping scan early", file=sys.stderr)
            return True
        return False

    existing = _fetch_existing_titles()
    print(f"[scanner] Found {len(existing)} existing tasks for dedup", file=sys.stderr)

    # Step 1: Verify completed tasks
    regressed = _verify_completed_tasks(repos, existing, deadline=deadline)
    if regressed:
        print(f"[scanner] Re-opened {regressed} regressed task(s)", file=sys.stderr)

    # Step 1b: Close stale available tasks whose finding no longer exists
    closed_stale = _close_stale_available_tasks(repos, existing, deadline=deadline)
    if closed_stale:
        print(f"[scanner] Closed {closed_stale} stale available task(s)", file=sys.stderr)

    results = {}
    total_findings = 0
    total_created = 0

    for repo_name, repo_path in repos:
        if _over_budget():
            break
        print(f"[scanner] Scanning {repo_name}...", file=sys.stderr)

        # Compute layer scores for progressive escalation
        layer_scores = _compute_project_layer_scores(repo_name)
        highest_unresolved = 0
        for layer in range(5):
            if layer_scores.get(layer, 1.0) < 0.8:
                highest_unresolved = layer
                break

        for scanner_fn in SCANNERS:
            if _over_budget():
                break
            scanner_name = get_scanner_name(scanner_fn)
            layer = SCANNER_LAYER.get(scanner_name, 0)

            # Progressive escalation: skip higher layers if lower ones unresolved.
            # Layer 3+ scanners (security, docs, prod_readiness) always run —
            # they shouldn't be blocked by trivial L0-L2 tasks flooding the board.
            if layer <= 2 and layer > highest_unresolved + 1:
                continue  # Too far ahead — wait for intermediate layers

            start = time.time()

            try:
                findings = scanner_fn(repo_name, repo_path)
            except Exception as e:
                print(f"[scanner] {scanner_name} on {repo_name} failed: {e}", file=sys.stderr)
                continue

            elapsed = time.time() - start
            total_findings += len(findings)

            if scanner_name not in results:
                results[scanner_name] = {"finding_count": 0, "created": 0}

            results[scanner_name]["finding_count"] += len(findings)

            for finding in findings:
                title = finding["title"]

                if _is_duplicate(repo_name, title, existing):
                    continue

                result = _api_post(
                    "/api/tasks",
                    {
                        "title": title,
                        "description": finding.get("description", ""),
                        "priority": finding.get("priority", 2),
                        "repo": repo_name,
                        "roadmap_item": f"Scanner: {scanner_name}",
                    },
                )

                if result:
                    existing.add(_dedup_key(repo_name, title))
                    results[scanner_name]["created"] += 1
                    total_created += 1
                    print(f"[scanner]  ✨ Created: {title[:70]}...", file=sys.stderr)

                    # Fire webhook for P0-P2 tasks
                    priority = finding.get("priority", 2)
                    if priority <= 2:
                        try:
                            webhook_url = os.environ.get("WEBHOOK_DEFAULT_URL", "")
                            if webhook_url:
                                webhook_content = (
                                    f"🔍 **Scanner: {scanner_name}**\\n"
                                    f"Priority P{priority} task created:\\n"
                                    f"**{title}**\\n"
                                    f"repo: `{repo_name}`"
                                )
                                payload = json.dumps(
                                    {
                                        "content": webhook_content,
                                    }
                                ).encode()
                                req = urllib.request.Request(
                                    webhook_url,
                                    data=payload,
                                    headers={"Content-Type": "application/json"},
                                )
                                urllib.request.urlopen(req, timeout=5)
                        except Exception:
                            pass

            print(
                f"[scanner]  {scanner_name}: {len(findings)} finding(s), "
                f"{results[scanner_name]['created']} created in {elapsed:.1f}s (layer {layer})",
                file=sys.stderr,
            )

    print(
        f"[scanner] Done: {total_findings} findings, {total_created} new tasks created, "
        f"{regressed} regressed",
        file=sys.stderr,
    )
    return results


# ── CLI entry point ─────────────────────────────────────────────────


if __name__ == "__main__":
    results = run_all_scanners()
    for scanner, counts in results.items():
        print(f"{scanner}: {counts['finding_count']} findings, {counts['created']} created")
    total_created = sum(c["created"] for c in results.values())
    sys.exit(0 if total_created > 0 else 1)
