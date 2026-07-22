"""Project health tracker — layered maturity scoring per repo.

Tracks which improvement layers have been addressed per project.
Used by the progressive scanner to escalate to higher-value work.

Layer definitions:
  L0 - Critical (P0-P1):   Missing indexes, build failures, security
  L1 - Code Quality (P2):   Unused imports, lint, test gaps, deps, TODOs
  L2 - Architecture (P2):   Large files, unwrap(), bare excepts, init files
  L3 - Docs & CI (P3):      README, LICENSE, CI pipeline, CONTRIBUTING
  L4 - Production (P3):     Docker, healthcheck, build automation, secrets

Score is computed from the board state — what % of tasks at each layer
are completed or archived (resolved).
"""

import os
import sys
from collections import Counter
from typing import Any

# Ensure server is on path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(script_dir)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from scanners import get_scanner_name, SCANNERS

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")

# Scanner → Layer mapping
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

LAYER_NAMES = {
    0: "Critical",
    1: "Code Quality",
    2: "Architecture",
    3: "Docs & CI",
    4: "Production Readiness",
}


def _api_get(path: str) -> Any:
    import json, urllib.request
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def compute_project_health(repo_name: str) -> dict:
    """Compute health scores for a single project.

    Returns:
        {
            "repo": str,
            "layer_scores": {0: 0.0..1.0, ...},
            "overall": float,
            "by_scanner": {scanner: {"total": N, "done": N, "pct": float}},
            "next_layer": int | None,  # layer to escalate to
        }
    """
    # Fetch all tasks for this repo
    all_tasks = _api_get(f"/api/tasks?repo={repo_name}&limit=500")
    if not all_tasks:
        return {
            "repo": repo_name,
            "layer_scores": {},
            "overall": 0.0,
            "by_scanner": {},
            "next_layer": 0,
        }

    # Count per scanner
    scanner_stats: dict[str, dict] = {}
    for t in all_tasks:
        ri = (t.get("roadmap_item") or "")
        scanner_name = ri.replace("Scanner: ", "") if ri.startswith("Scanner:") else "manual"
        if scanner_name == "manual":
            continue  # Don't score manual tasks

        if scanner_name not in scanner_stats:
            scanner_stats[scanner_name] = {"total": 0, "done": 0}
        scanner_stats[scanner_name]["total"] += 1

        status = t.get("status", "")
        if status == "done" or t.get("archived", False):
            scanner_stats[scanner_name]["done"] += 1

    # Compute per-layer scores
    layer_totals = Counter()
    layer_done = Counter()
    for scanner, stats in scanner_stats.items():
        layer = SCANNER_LAYER.get(scanner, 1)
        layer_totals[layer] += stats["total"]
        layer_done[layer] += stats["done"]

    layer_scores = {}
    for layer in range(5):
        total = layer_totals.get(layer, 0)
        done = layer_done.get(layer, 0)
        layer_scores[layer] = round(done / total, 2) if total > 0 else 1.0

    # Compute overall (weighted by layer — lower layers matter more)
    weights = {0: 0.35, 1: 0.30, 2: 0.20, 3: 0.10, 4: 0.05}
    overall = sum(
        layer_scores.get(layer, 1.0) * weights[layer]
        for layer in range(5)
    )

    # Determine next layer to escalate (lowest layer with score < 0.8)
    next_layer = None
    for layer in range(5):
        if layer_scores.get(layer, 1.0) < 0.8:
            next_layer = layer
            break

    by_scanner = {}
    for scanner, stats in scanner_stats.items():
        pct = round(stats["done"] / stats["total"] * 100, 1) if stats["total"] > 0 else 100.0
        by_scanner[scanner] = {**stats, "pct": pct}

    return {
        "repo": repo_name,
        "layer_scores": layer_scores,
        "layer_names": {str(k): v for k, v in LAYER_NAMES.items()},
        "overall": round(overall, 2),
        "by_scanner": by_scanner,
        "next_layer": next_layer,
        "next_layer_name": LAYER_NAMES.get(next_layer, "Complete") if next_layer is not None else "Complete",
    }


def compute_all_projects(repos: list[tuple[str, str]] | None = None) -> dict:
    """Compute health for all projects.

    Returns:
        {
            "projects": [...],
            "summary": {
                "total": N,
                "avg_overall": float,
                "by_layer": {0: avg, ...},
                "needs_attention": [repo names with L0 issues]
            }
        }
    """
    from scanners import discover_repos
    if repos is None:
        repos = discover_repos()

    results = []
    layer_sums = Counter()
    layer_counts = Counter()
    overall_sum = 0.0
    needs_attention = []

    for repo_name, repo_path in repos:
        health = compute_project_health(repo_name)
        if not health["by_scanner"]:
            continue  # No scanner tasks for this project yet

        results.append(health)
        overall_sum += health["overall"]

        for layer, score in health["layer_scores"].items():
            layer_sums[layer] += score
            layer_counts[layer] += 1

        # Flag projects with L0 issues
        if health["layer_scores"].get(0, 1.0) < 0.8:
            needs_attention.append(repo_name)

    total = len(results)
    return {
        "projects": sorted(results, key=lambda x: -x["overall"]),
        "summary": {
            "total": total,
            "avg_overall": round(overall_sum / total, 2) if total > 0 else 0,
            "by_layer": {
                str(k): round(layer_sums[k] / layer_counts[k], 2) if layer_counts[k] > 0 else 1.0
                for k in sorted(layer_sums.keys())
            },
            "needs_attention_count": len(needs_attention),
            "needs_attention": needs_attention[:15],
        },
    }
