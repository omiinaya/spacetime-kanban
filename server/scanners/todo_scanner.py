"""TODO scanner — finds TODO/FIXME/HACK/XXX markers and creates tasks.

For repos with >5 accumulated markers, creates a bulk-cleanup task.
Avoids creating tasks for trivial or single-marker repos.

Priority: P2 (medium) — good hygiene but not urgent.
"""

import os
import subprocess

from scanners import register_scanner


@register_scanner
def scan_todos(repo_name: str, repo_path: str) -> list[dict]:
    """Scan the repo for TODO/FIXME/HACK/XXX markers."""
    try:
        result = subprocess.run(
            ["git", "grep", "-n", "-c", r"(TODO|FIXME|HACK|XXX)"],
            cwd=repo_path,
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    if not result.stdout.strip():
        return []

    lines = [l for l in result.stdout.strip().split("\n") if ":" in l]
    total = 0
    file_hits = []
    for line in lines:
        try:
            filepath, count_str = line.rsplit(":", 1)
            count = int(count_str)
            total += count
            file_hits.append((filepath, count))
        except (ValueError, IndexError):
            pass

    if total == 0:
        return []

    findings = []

    # If >5 markers, bulk cleanup task
    if total >= 5:
        # Count by tag type
        tag_counts = {"TODO": 0, "FIXME": 0, "HACK": 0, "XXX": 0}
        try:
            for tag in tag_counts:
                r = subprocess.run(
                    ["git", "grep", "-n", "-c", tag],
                    cwd=repo_path, capture_output=True, text=True, timeout=15,
                )
                for l in r.stdout.strip().split("\n"):
                    if ":" in l:
                        try:
                            tag_counts[tag] += int(l.rsplit(":", 1)[1])
                        except (ValueError, IndexError):
                            pass
        except Exception:
            pass

        tag_summary = ", ".join(f"{k}={v}" for k, v in tag_counts.items() if v > 0)

        # Top files for description
        top_files = sorted(file_hits, key=lambda x: -x[1])[:5]

        desc_parts = [
            f"Total TODO/FIXME/HACK markers: {total} across {len(lines)} file(s).\n",
            f"Tags: {tag_summary}\n",
            "\nTop files:",
        ]
        for fp, cnt in top_files:
            desc_parts.append(f"  - {fp} ({cnt} markers)")

        if len(file_hits) > 5:
            desc_parts.append(f"  ... and {len(file_hits) - 5} more file(s)")

        desc_parts.append(
            "\nRun the mechanical 'scan todos' handler after cleanup to verify."
        )

        findings.append({
            "title": f"Clean up {total} TODO/FIXME markers in {repo_name}",
            "description": "\n".join(desc_parts),
            "priority": 2,
            "scanner": "todos",
        })

    # Also create tasks for very stale TODOs (>1 year old)
    try:
        r = subprocess.run(
            ["git", "log", "--diff-filter=A", "--since=1.year.ago",
             "-S", "TODO", "--name-only", "--pretty=format:", "--", "*.py", "*.rs", "*.ts", "*.tsx"],
            cwd=repo_path, capture_output=True, text=True, timeout=30,
        )
        new_files = set(f.strip() for f in r.stdout.split("\n") if f.strip())
        new_todo_files = [f for f in new_files if os.path.isfile(os.path.join(repo_path, f))]
        if new_todo_files:
            findings.append({
                "title": f"Review recently-added TODOs in {len(new_todo_files)} file(s)",
                "description": (
                    f"{len(new_todo_files)} file(s) added in the last year contain TODO markers "
                    f"that may need review. First files: {', '.join(new_todo_files[:5])}"
                ),
                "priority": 2,
                "scanner": "todos",
            })
    except Exception:
        pass

    return findings
