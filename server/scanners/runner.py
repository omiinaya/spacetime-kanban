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

from scanners import SCANNERS, discover_repos, get_scanner_name

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


def _fetch_existing_titles() -> set[str]:
    """Fetch all task titles from the board (including done tasks) for dedup."""
    existing = set()
    for status in ("available", "in_progress", "blocked", "done"):
        tasks = _api_get(f"/api/tasks?status={status}&limit=500")
        if tasks:
            for t in tasks:
                title = t.get("title", "")
                if title:
                    existing.add(title.strip().lower())
    return existing


def _is_duplicate(title: str, existing: set[str]) -> bool:
    return title.strip().lower() in existing


def _compute_project_layer_scores(repo_name: str) -> dict[int, float]:
    """Compute what % of each layer's tasks are done for a project."""
    from collections import Counter

    all_tasks = _api_get(f"/api/tasks?repo={repo_name}&limit=500")
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


def _verify_completed_tasks(repos: list[tuple[str, str]], existing: set[str]) -> int:
    """Re-check done tasks to ensure the underlying issue is still fixed.

    Only checks tasks done in the last 7 days. Only re-runs the exact
    scanner that originally created each task (not all scanners).
    """
    regressed = 0
    now_ms = int(time.time() * 1000)
    seven_days_ms = 7 * 86400 * 1000

    for repo_name, repo_path in repos:
        done_tasks = _api_get(f"/api/tasks?status=done&repo={repo_name}&limit=200")
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
            sname = get_scanner_name(scanner_fn)
            tasks_to_check = by_scanner.get(sname)
            if not tasks_to_check:
                continue

            try:
                fresh_findings = scanner_fn(repo_name, repo_path)
            except Exception:
                continue

            fresh_titles = {ff["title"].strip().lower() for ff in fresh_findings}
            for t in tasks_to_check:
                title = t.get("title", "").strip().lower()
                tid = t.get("id", "")
                if title in fresh_titles:
                    _api_post(f"/api/tasks/{tid}/unarchive", {})
                    _api_post(
                        f"/api/tasks/{tid}/block",
                        {"reason": "Regression: issue still present after prior fix"},
                    )
                    existing.add(title)
                    regressed += 1
                    print(f"[scanner] ⚠ Re-opened regressed: {title[:60]}...", file=sys.stderr)

    return regressed


# ── Main scan function ──────────────────────────────────────────────


def run_all_scanners(repos: list[tuple[str, str]] | None = None) -> dict:
    """Run all scanners against all repos with progressive layer escalation.

    1. Verifies completed tasks (re-opens regressed ones)
    2. Computes layer scores per project
    3. Skips scanners above the highest unresolved layer
    4. Deduplicates and creates tasks
    """
    if repos is None:
        repos = discover_repos()

    print(
        f"[scanner] Scanning {len(repos)} repos with {len(SCANNERS)} scanner(s)...", file=sys.stderr
    )

    existing = _fetch_existing_titles()
    print(f"[scanner] Found {len(existing)} existing tasks for dedup", file=sys.stderr)

    # Step 1: Verify completed tasks
    regressed = _verify_completed_tasks(repos, existing)
    if regressed:
        print(f"[scanner] Re-opened {regressed} regressed task(s)", file=sys.stderr)

    results = {}
    total_findings = 0
    total_created = 0

    for repo_name, repo_path in repos:
        print(f"[scanner] Scanning {repo_name}...", file=sys.stderr)

        # Compute layer scores for progressive escalation
        layer_scores = _compute_project_layer_scores(repo_name)
        highest_unresolved = 0
        for layer in range(5):
            if layer_scores.get(layer, 1.0) < 0.8:
                highest_unresolved = layer
                break

        for scanner_fn in SCANNERS:
            scanner_name = get_scanner_name(scanner_fn)
            layer = SCANNER_LAYER.get(scanner_name, 0)

            # Progressive escalation: skip higher layers if lower ones unresolved
            if layer > highest_unresolved + 1:
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

                if _is_duplicate(title, existing):
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
                    existing.add(title.strip().lower())
                    results[scanner_name]["created"] += 1
                    total_created += 1
                    print(f"[scanner]  ✨ Created: {title[:70]}...", file=sys.stderr)

                    # Fire webhook for P0-P2 tasks
                    priority = finding.get("priority", 2)
                    if priority <= 2:
                        try:
                            webhook_url = os.environ.get("WEBHOOK_DEFAULT_URL", "")
                            if webhook_url:
                                payload = json.dumps(
                                    {
                                        "content": f"🔍 **Scanner: {scanner_name}**\\nPriority P{priority} task created:\\n**{title}**\\nrepo: `{repo_name}`"
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
