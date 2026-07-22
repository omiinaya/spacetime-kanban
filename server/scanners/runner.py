"""Scanner runner — runs all registered scanners, deduplicates, creates tasks.

Orchestration:
  1. Discover repos (or use configured list)
  2. Run each scanner against each repo
  3. Deduplicate against existing board state (similar titles)
  4. Create new tasks via API
  5. Report results

Dedup strategy:
  - Before creating, fetch all non-done tasks from the API
  - Compare by: scanner_name + repo (exact match on title prefix)
  - Skip if a matching task already exists
"""

import os
import sys
import time
from typing import Any

# Ensure server package is on path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(script_dir)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from scanners import SCANNERS, discover_repos, get_scanner_name


# ── API helpers ─────────────────────────────────────────────────────

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")


def _api_get(path: str) -> Any:
    import urllib.request, json
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def _api_post(path: str, data: dict) -> dict | None:
    import urllib.error
    import urllib.request, json
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


# ── Dedup ────────────────────────────────────────────────────────────


def _fetch_existing_titles() -> set[str]:
    """Fetch all non-done task titles from the board."""
    existing = set()
    for status in ("available", "in_progress", "blocked"):
        tasks = _api_get(f"/api/tasks?status={status}&limit=500")
        if tasks:
            for t in tasks:
                title = t.get("title", "")
                if title:
                    existing.add(title.strip().lower())
    return existing


def _is_duplicate(title: str, existing: set[str]) -> bool:
    """Check if a task title is a duplicate of an existing task.

    Uses exact match only — scanner-generated titles are unique enough
    (e.g. 'Add #[index(btree)] to X.Y' differs per field/struct).
    """
    return title.strip().lower() in existing


# ── Main scan function ──────────────────────────────────────────────


def run_all_scanners(repos: list[tuple[str, str]] | None = None) -> dict:
    """Run all scanners against all repos and create tasks for new findings.

    Args:
        repos: List of (repo_name, repo_path) tuples. If None, auto-discover.

    Returns:
        dict with scan results: {scanner_name: {"finding_count": N, "created": N}}
    """
    if repos is None:
        repos = discover_repos()

    print(f"[scanner] Scanning {len(repos)} repos with {len(SCANNERS)} scanner(s)...", file=sys.stderr)

    # Fetch existing tasks for dedup
    existing = _fetch_existing_titles()
    print(f"[scanner] Found {len(existing)} existing active tasks for dedup", file=sys.stderr)

    results = {}
    total_findings = 0
    total_created = 0

    for repo_name, repo_path in repos:
        print(f"[scanner] Scanning {repo_name}...", file=sys.stderr)

        for scanner_fn in SCANNERS:
            scanner_name = get_scanner_name(scanner_fn)
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

                if _is_duplicate(title, existing):
                    continue

                # Create the task
                result = _api_post("/api/tasks", {
                    "title": title,
                    "description": finding.get("description", ""),
                    "priority": finding.get("priority", 2),
                    "repo": repo_name,
                    "roadmap_item": f"Scanner: {scanner_name}",
                })

                if result:
                    existing.add(title.strip().lower())
                    results[scanner_name]["created"] += 1
                    total_created += 1
                    print(f"[scanner]  ✨ Created: {title[:70]}...", file=sys.stderr)

            print(f"[scanner]  {scanner_name}: {len(findings)} finding(s), "
                  f"{results[scanner_name]['created']} created in {elapsed:.1f}s", file=sys.stderr)

    print(f"[scanner] Done: {total_findings} findings, {total_created} new tasks created", file=sys.stderr)
    return results


# ── CLI entry point ─────────────────────────────────────────────────


if __name__ == "__main__":
    results = run_all_scanners()
    for scanner, counts in results.items():
        print(f"{scanner}: {counts['finding_count']} findings, {counts['created']} created")
    total_created = sum(c["created"] for c in results.values())
    sys.exit(0 if total_created > 0 else 1)
