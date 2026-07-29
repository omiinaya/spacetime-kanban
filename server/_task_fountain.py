#!/usr/bin/env python3
"""Ultra-fast task fountain — runs in <3s, creates tasks for workers.

Only scans a hardcoded set of known-good repos. No discover_repos overhead.
Skips repos that are known to be large or slow to scan.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = os.environ.get("KANBAN_API", "http://localhost:8727")

# REPOS is a hardcoded list of repos that are fast to scan (<1s each)
REPOS = [
    "spacetimedb-kanban",
    "sample-repo-f",
    "sample-repo-r",
    "sample-repo-o",
    "sample-repo-m",
    "sample-repo-p",
    "sample-repo-n",
    "sample-repo-d",
    "sample-repo-e",
]

HOME = os.path.expanduser("~")

# Scanner registry — each is a function that returns findings
SCANNERS = []


def register(fn):
    SCANNERS.append(fn)
    return fn


def api_get(path: str):
    try:
        with urllib.request.urlopen(f"{API}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def api_post(path: str, data: dict):
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{API}{path}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read().decode()
            return json.loads(content) if content else {"status": "ok"}
    except Exception:
        return None


def fetch_existing_titles() -> set[str]:
    """Lightweight — only check available + inProgress (cheapest calls)."""
    existing = set()
    for status in ("available", "inProgress"):
        try:
            with urllib.request.urlopen(
                f"{API}/api/tasks?status={status}&limit=50", timeout=3
            ) as resp:
                tasks = json.loads(resp.read().decode())
                if tasks:
                    for t in tasks:
                        title = t.get("title", "")
                        if title:
                            existing.add(title.strip().lower())
        except Exception:
            pass
    return existing


def is_dup(title: str, existing: set[str]) -> bool:
    return title.strip().lower() in existing


# ── Scanner: Find untested modules ──


@register
def scan_test_gaps(repo_name: str, repo_path: str) -> list[dict]:
    findings = []
    for src_dir_name in ("server", "src"):
        src_dir = os.path.join(repo_path, src_dir_name)
        test_dir = os.path.join(src_dir, "tests")
        if not os.path.isdir(test_dir):
            continue
        existing_tests = {
            f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py")
        }
        untested = []
        for f in os.listdir(src_dir):
            if f.endswith(".py") and not f.startswith("test_") and f != "__init__.py":
                test_name = f"test_{f}"
                if test_name not in existing_tests:
                    untested.append(f"{src_dir_name}/{f}")
        if untested:
            for i in range(0, len(untested), 5):
                batch = untested[i : i + 5]
                findings.append(
                    {
                        "title": (
                            f"Add tests for {len(batch)} untested python module(s) in {repo_name}"
                        ),
                        "description": "Add unit tests for:\n"
                        + "\n".join(f"  - {p}" for p in batch),
                        "priority": 3,
                    }
                )
    return findings


# ── Scanner: Missing __init__.py ──


@register
def scan_init_py(repo_name: str, repo_path: str) -> list[dict]:
    findings = []
    for src_dir_name in ("server", "src"):
        src_dir = os.path.join(repo_path, src_dir_name)
        if not os.path.isdir(src_dir):
            continue
        missing = []
        for entry in os.listdir(src_dir):
            subdir = os.path.join(src_dir, entry)
            if not os.path.isdir(subdir) or entry.startswith((".", "__", "venv")):
                continue
            has_py = any(f.endswith(".py") for f in os.listdir(subdir))
            if has_py and "__init__.py" not in os.listdir(subdir):
                missing.append(f"{src_dir_name}/{entry}")
        if missing:
            findings.append(
                {
                    "title": f"Add __init__.py to {len(missing)} python package(s) in {repo_name}",
                    "description": "Directories with Python files but no __init__.py:\n"
                    + "\n".join(f"  - {p}" for p in missing),
                    "priority": 3,
                }
            )
    return findings


# ── Scanner: Large files ──
@register
def scan_large_files(repo_name: str, repo_path: str) -> list[dict]:
    findings = []
    try:
        result = subprocess.run(
            [
                "find",
                repo_path,
                "-maxdepth",
                "2",
                "-type",
                "f",
                "(",
                "-name",
                "*.py",
                "-o",
                "-name",
                "*.rs",
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
                "-exec",
                "wc",
                "-l",
                "{}",
                "+",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    files = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.endswith("total"):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            try:
                count = int(parts[0])
                if count >= 300:
                    files.append((parts[1], count))
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
                "description": "Large files ≥300 lines:\n"
                + "\n".join(f"  - {p} ({c} lines)" for p, c in batch),
                "priority": 2,
            }
        )
    return findings


# ── Scanner: unwrap() calls ──
@register
def scan_unwrap(repo_name: str, repo_path: str) -> list[dict]:
    findings = []
    try:
        result = subprocess.run(
            [
                "grep",
                "-r",
                "-l",
                r"\.unwrap()",
                "--include",
                "*.rs",
                "--exclude-dir",
                "node_modules",
                "--exclude-dir",
                "target",
                "--exclude-dir",
                ".git",
                "--exclude-dir",
                "__pycache__",
                "--exclude-dir",
                ".venv",
                "--exclude-dir",
                "venv",
                "--exclude-dir",
                "build",
                "--exclude-dir",
                "dist",
                repo_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    files = [entry.strip() for entry in result.stdout.strip().split("\n") if entry.strip()]
    if files:
        findings.append(
            {
                "title": "Replace unwrap() calls with error handling",
                "description": "Found .unwrap() calls in:\n"
                + "\n".join(f"  - {f.replace(repo_path + '/', '')}" for f in files[:10]),
                "priority": 2,
            }
        )
    return findings


# ── Scanner: bare except: ──
@register
def scan_bare_except(repo_name: str, repo_path: str) -> list[dict]:
    findings = []
    try:
        result = subprocess.run(
            [
                "grep",
                "-r",
                "-l",
                r"except\s*:",
                "--include",
                "*.py",
                "--exclude-dir",
                "node_modules",
                "--exclude-dir",
                "target",
                "--exclude-dir",
                ".git",
                "--exclude-dir",
                "__pycache__",
                "--exclude-dir",
                ".venv",
                "--exclude-dir",
                "venv",
                "--exclude-dir",
                "build",
                "--exclude-dir",
                "dist",
                repo_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    files = [entry.strip() for entry in result.stdout.strip().split("\n") if entry.strip()]
    if files:
        findings.append(
            {
                "title": f"Replace bare except: in {repo_name}",
                "description": "Found bare except: in:\n"
                + "\n".join(f"  - {f.replace(repo_path + '/', '')}" for f in files[:10]),
                "priority": 2,
            }
        )
    return findings


# ── Main ──


def run() -> int:
    """Run all scanners on all repos. Returns number of tasks created."""
    existing = fetch_existing_titles()
    created = 0

    # debugging: print how many we got
    import sys

    print(f"  existing={len(existing)} repos={len(REPOS)}", file=sys.stderr)

    for repo_name in REPOS:
        repo_path = os.path.join(HOME, repo_name)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            continue

        for scanner in SCANNERS:
            try:
                findings = scanner(repo_name, repo_path)
            except Exception:
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
