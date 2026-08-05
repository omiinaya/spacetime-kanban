#!/usr/bin/env python3
"""Fast task seeder — scans repos, creates tasks matching mechanical workers.

Runs simple shell/file checks and creates tasks directly via the kanban API.
Much faster than the full scanner pipeline (avoids 50-repo crawl).
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("KANBAN_API", "http://localhost:8727")
# Repos to scan — override with KANBAN_REPOS (comma-separated). Default:
# this repo itself only; no assumptions about sibling projects on the host.
_DEFAULT_REPOS = ["spacetime-kanban"]
REPOS = [r.strip() for r in os.environ.get("KANBAN_REPOS", "").split(",") if r.strip()] or list(
    _DEFAULT_REPOS
)
HOME = os.path.expanduser("~")


def api_get(path: str) -> list | dict | None:
    try:
        req = urllib.request.Request(f"{API}{path}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def api_post(path: str, data: dict) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{API}{path}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {"status": "ok"}
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:200]
        print(f"  [error] POST {path} HTTP {e.code}: {err}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [error] POST {path}: {e}", file=sys.stderr)
        return None


def create_task(title: str, description: str, repo: str, priority: int = 2) -> bool:
    result = api_post(
        "/api/tasks",
        {
            "title": title,
            "description": description,
            "priority": priority,
            "repo": repo,
            "roadmap_item": "Scanner: task-generator",
        },
    )
    if result:
        print(f"  ✅ Created: {title[:70]}")
        return True
    return False


def fetch_existing_titles() -> set[str]:
    existing = set()
    for status in ("available", "inProgress", "blocked", "done"):
        tasks = api_get(f"/api/tasks?status={status}&limit=200")
        if tasks:
            for t in tasks:
                raw = t.get("title", "")
                stripped = raw.strip().lower()
                if stripped:
                    existing.add(stripped)
    print(f"[seed] Loaded {len(existing)} existing titles for dedup", file=sys.stderr)
    return existing


def is_dup(title: str, existing: set[str]) -> bool:
    return title.strip().lower() in existing


def find_test_gaps(repo_name: str, repo_path: str) -> list[dict]:
    """Find Python/JS modules missing tests."""
    findings = []
    src_dirs = [
        os.path.join(repo_path, "server"),
        os.path.join(repo_path, "src"),
        os.path.join(repo_path, "web", "src"),
    ]
    test_names = set()

    # Collect existing test files
    for src_dir in src_dirs:
        test_dir = os.path.join(src_dir, "tests")
        if os.path.isdir(test_dir):
            for f in os.listdir(test_dir):
                if f.startswith("test_") and f.endswith(".py"):
                    test_names.add(f)

    # Find untested modules
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        untested = []
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [
                d for d in dirs if not d.startswith((".", "__", "venv", "node_modules", "target"))
            ]
            for f in files:
                if f.endswith(".py") and not f.startswith("test_") and f != "__init__.py":
                    test_name = f"test_{f}"
                    if test_name not in test_names and test_name not in [
                        os.path.basename(p) for p in untested
                    ]:
                        rel = os.path.relpath(os.path.join(root, f), repo_path)
                        untested.append(rel)
        if untested:
            # Chunk into batches
            for i in range(0, len(untested), 5):
                batch = untested[i : i + 5]
                findings.append(
                    {
                        "title": (
                            f"Add tests for {len(batch)} untested python module(s) in {repo_name}"
                        ),
                        "description": "Add unit tests for the following untested modules:\n"
                        + "\n".join(f"  - {p}" for p in batch),
                        "priority": 3,
                        "repo": repo_name,
                    }
                )
    return findings


def find_missing_init(repo_name: str, repo_path: str) -> list[dict]:
    """Find Python packages missing __init__.py."""
    findings = []
    src_dirs = [
        os.path.join(repo_path, "server"),
        os.path.join(repo_path, "src"),
    ]
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        missing = []
        for root, dirs, files in os.walk(src_dir):
            dirs[:] = [
                d for d in dirs if not d.startswith((".", "__", "venv", "node_modules", "target"))
            ]
            if root == src_dir:
                continue
            has_py = any(f.endswith(".py") for f in files)
            has_init = "__init__.py" in files
            if has_py and not has_init:
                rel = os.path.relpath(root, repo_path)
                missing.append(rel)
        if missing:
            findings.append(
                {
                    "title": f"Add __init__.py to {len(missing)} python package(s) in {repo_name}",
                    "description": (
                        "The following directories contain Python files but lack __init__.py:\n"
                    )
                    + "\n".join(f"  - {p}" for p in missing),
                    "priority": 3,
                    "repo": repo_name,
                }
            )
    return findings


def find_stale_todos(repo_name: str, repo_path: str) -> list[dict]:
    """Find files with TODO/FIXME/HACK/XXX markers."""
    try:
        result = subprocess.run(
            ["git", "grep", "-n", "-c", r"(TODO|FIXME|HACK|XXX)"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if not result.stdout.strip():
        return []
    lines = [entry for entry in result.stdout.strip().split("\n") if ":" in entry]
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
    if total < 3:
        return []
    findings = []
    # Bulk cleanup for >10 markers
    if total >= 10:
        findings.append(
            {
                "title": f"Review {total} stale todo(s) in {repo_name}",
                "description": (
                    f"Found {total} TODO/FIXME/HACK/XXX markers"
                    f" across {len(file_hits)} files:\n"
                    + "\n".join(f"  - {fp} ({c} markers)" for fp, c in file_hits[:10])
                ),
                "priority": 2,
                "repo": repo_name,
            }
        )
    return findings


def find_large_files(repo_name: str, repo_path: str) -> list[dict]:
    """Find large source files suitable for splitting."""
    try:
        cmd = [
            "find",
            repo_path,
            "-type",
            "f",
            "(",
            "-name",
            "*.rs",
            "-o",
            "-name",
            "*.py",
            ")",
            "!",
            "-path",
            "*/test*",
            "!",
            "-path",
            "*/tests/*",
            "!",
            "-path",
            "*/node_modules/*",
            "!",
            "-path",
            "*/target/*",
            "!",
            "-path",
            "*/__pycache__/*",
            "!",
            "-path",
            "*/.git/*",
            "!",
            "-path",
            "*/venv/*",
            "!",
            "-path",
            "*/migrations/*",
            "-exec",
            "wc",
            "-l",
            "{}",
            "+",
        ]
        wc_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if not wc_result.stdout.strip():
        return []
    findings = []
    files = []
    for line in wc_result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.endswith("total"):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            try:
                count = int(parts[0])
                path = parts[1]
                if count >= 300:  # Large file threshold
                    files.append((path, count))
            except ValueError:
                continue
    if files:
        files.sort(key=lambda x: x[1], reverse=True)
        batch = files[:5]
        findings.append(
            {
                "title": (
                    f"Split {len(batch)} large source file(s)"
                    f" in {repo_name} ({len(batch)}/{len(batch)})"
                ),
                "description": (
                    f"Found {len(files)} large source file(s) ≥300 lines."
                    f" Recommend splitting:\n" + "\n".join(f"  - {p} ({c} lines)" for p, c in batch)
                ),
                "priority": 2,
                "repo": repo_name,
            }
        )
    return findings


def find_missing_project_files(repo_name: str, repo_path: str) -> list[dict]:
    """Find missing community-standard project files."""
    findings = []
    missing = []
    for fname, label in [
        ("LICENSE", "LICENSE file"),
        ("CONTRIBUTING.md", "CONTRIBUTING.md"),
        (".github/ISSUE_TEMPLATE/bug_report.md", "issue template"),
        (".github/PULL_REQUEST_TEMPLATE.md", "PR template"),
    ]:
        full = os.path.join(repo_path, fname)
        if not os.path.isfile(full):
            missing.append(label)
    if missing:
        findings.append(
            {
                "title": f"Add {', '.join(missing)}"
                if len(missing) < 3
                else f"Add {len(missing)} project template file(s)",
                "description": f"Missing project files: {', '.join(missing)}",
                "priority": 3,
                "repo": repo_name,
            }
        )
    return findings


def create_tasks_existing(repo_name: str, existing: set[str]) -> int:
    repo_path = os.path.join(HOME, repo_name)
    if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, ".git")):
        print(f"  [skip] {repo_path} not found or not a git repo", file=sys.stderr)
        return 0

    print(f"\n[seed] Scanning {repo_name}...", file=sys.stderr)
    created = 0

    scanners = [
        ("test gaps", lambda: find_test_gaps(repo_name, repo_path)),
        ("__init__.py", lambda: find_missing_init(repo_name, repo_path)),
        ("stale todos", lambda: find_stale_todos(repo_name, repo_path)),
        ("large files", lambda: find_large_files(repo_name, repo_path)),
        ("project files", lambda: find_missing_project_files(repo_name, repo_path)),
    ]

    for name, scanner in scanners:
        try:
            findings = scanner()
        except Exception as e:
            print(f"  [error] {name}: {e}", file=sys.stderr)
            continue

        for f in findings:
            title = f["title"]
            if is_dup(title, existing):
                continue
            ok = create_task(
                title, f.get("description", ""), f.get("repo", repo_name), f.get("priority", 2)
            )
            if ok:
                existing.add(title.strip().lower())
                created += 1

    return created


def main():
    existing = fetch_existing_titles()
    total = 0
    for repo_name in REPOS:
        total += create_tasks_existing(repo_name, existing)

    print(f"\n[seed] Done: {total} new task(s) created across {len(REPOS)} repos")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
