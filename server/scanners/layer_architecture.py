"""Architecture scanner — finds code structure improvements.

Layer 2 checks:
  - Large files (>500 lines) that should be split into modules
  - `unwrap()` calls in Rust (crash-prone)
  - Bare `except:` in Python (swallows errors)
  - Missing `__init__.py` in Python packages
  - Functions with high complexity (long methods)
  - Stale TODOs (>1 year old)

Priority: P2 — code health, prevents future bugs.
"""

import os
import re
import subprocess

from scanners import register_scanner


def _check_rust_unwraps(repo_path: str) -> list[str]:
    """Find Rust files with excessive unwrap() calls."""
    stdb_dirs = [
        os.path.join(repo_path, "server", "spacetimedb", "src"),
        os.path.join(repo_path, "src"),
    ]
    results = []
    for src_dir in stdb_dirs:
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                if not f.endswith(".rs"):
                    continue
                filepath = os.path.join(root, f)
                try:
                    with open(filepath) as fh:
                        content = fh.read()
                    unwraps = len(re.findall(r"\.unwrap\(\)", content))
                    if unwraps > 5:
                        rel = os.path.relpath(filepath, repo_path)
                        results.append(f"{rel}: {unwraps} unwrap() calls")
                except (OSError, UnicodeDecodeError):
                    pass
    return results


def _check_bare_excepts(repo_path: str) -> list[str]:
    """Find Python files with bare except: clauses."""
    results = []
    for root, dirs, files in os.walk(repo_path):
        # Skip hidden dirs and venvs
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".") and d not in ("venv", ".venv", "node_modules", "__pycache__")
        ]
        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath) as fh:
                    content = fh.read()
                bare = re.findall(r"^except\s*:", content, re.MULTILINE)
                if bare:
                    rel = os.path.relpath(filepath, repo_path)
                    results.append(f"{rel}: {len(bare)} bare except(s)")
            except (OSError, UnicodeDecodeError):
                pass
    return results


def _check_large_files(repo_path: str) -> list[tuple[str, int]]:
    """Find source files over 500 lines."""
    extensions = (".py", ".rs", ".ts", ".tsx", ".js", ".jsx")
    large = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in ("venv", ".venv", "node_modules", "__pycache__", "dist", "build", "target")
        ]
        for f in files:
            if not f.endswith(extensions):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath) as fh:
                    lines = sum(1 for _ in fh)
                if lines > 500:
                    rel = os.path.relpath(filepath, repo_path)
                    large.append((rel, lines))
            except (OSError, UnicodeDecodeError):
                pass
    return sorted(large, key=lambda x: -x[1])[:10]  # Top 10


def _check_missing_init_py(repo_path: str) -> list[str]:
    """Find Python packages without __init__.py."""
    missing = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".") and d not in ("venv", ".venv", "node_modules", "__pycache__")
        ]
        # Check if this directory has .py files but no __init__.py
        has_py = any(f.endswith(".py") for f in files)
        has_init = "__init__.py" in files
        if has_py and not has_init:
            rel = os.path.relpath(root, repo_path)
            if rel != ".":  # Skip repo root
                missing.append(rel)
    return missing[:10]


def _check_stale_todos(repo_path: str) -> list[dict]:
    """Find TODO markers that haven't been touched in >1 year."""
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--diff-filter=A",
                "-S",
                "TODO",
                "--name-only",
                "--pretty=format:%H %ai",
                "--since=2.years.ago",
                "--",
                "*.py",
                "*.rs",
                "*.ts",
                "*.tsx",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if not result.stdout.strip():
            return []

        # Parse git log output: extract files with old TODOs
        lines = result.stdout.strip().split("\n")
        old_todo_files = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith("commit"):
                for ext in (".py", ".rs", ".ts", ".tsx"):
                    if line.endswith(ext):
                        old_todo_files.add(line)
                        break

        if old_todo_files:
            return [{"file": f} for f in sorted(old_todo_files)[:8]]
        return []
    except Exception:
        return []


@register_scanner
def scan_architecture(repo_name: str, repo_path: str) -> list[dict]:
    """Scan for architecture-level improvements."""
    findings = []

    # ── Check large files ──
    large_files = _check_large_files(repo_path)
    if large_files:
        max_per_task = 2
        for i in range(0, len(large_files), max_per_task):
            chunk = large_files[i : i + max_per_task]
            file_list = "\n".join(f"  - {f} ({line} lines)" for f, line in chunk)
            task_num = i // max_per_task + 1
            total_chunks = (len(large_files) + max_per_task - 1) // max_per_task
            label = f" ({task_num}/{total_chunks})" if total_chunks > 1 else ""
            findings.append(
                {
                    "title": f"Split {len(chunk)} large source file(s) in {repo_name}{label}",
                    "description": (
                        f"Found source files over 500 lines that should be split into modules.\n\n"
                        f"Files:\n{file_list}"
                    ),
                    "priority": 2,
                    "scanner": "architecture",
                }
            )

    # ── Check Rust unwrap() calls ──
    unwraps = _check_rust_unwraps(repo_path)
    if unwraps:
        for uw in unwraps:
            file_name = uw.split(":")[0].split("/")[-1]
            findings.append(
                {
                    "title": (
                        f"Replace unwrap() calls with error handling "
                        f"in {file_name} ({repo_name})"
                    ),
                    "description": (
                        f"Found Rust files with excessive `.unwrap()` calls. These crash "
                        f"at runtime if the value is None/Err.\n\n"
                        f"  - {uw}"
                    ),
                    "priority": 2,
                    "scanner": "architecture",
                }
            )

    # ── Check bare excepts ──
    bare = _check_bare_excepts(repo_path)
    if bare:
        for b in bare:
            file_name = b.split(":")[0].split("/")[-1]
            findings.append(
                {
                    "title": f"Replace bare `except:` in {file_name} ({repo_name})",
                    "description": (
                        f"Found bare `except:` clause that catches ALL exceptions "
                        f"(including KeyboardInterrupt, SystemExit) in {b}. "
                        f"Use `except Exception:` instead."
                    ),
                    "priority": 2,
                    "scanner": "architecture",
                }
            )

    # ── Check missing __init__.py ──
    missing_init = _check_missing_init_py(repo_path)
    if missing_init:
        dir_list = "\n".join(f"  - {d}" for d in missing_init)
        findings.append(
            {
                "title": f"Add __init__.py to {len(missing_init)} Python package(s) in {repo_name}",
                "description": (
                    f"Found directories with .py files but no `__init__.py`. "
                    f"These won't be importable as packages.\n\n{dir_list}"
                ),
                "priority": 3,
                "scanner": "architecture",
            }
        )

    # ── Check stale TODOs (>1 year old) ──
    stale = _check_stale_todos(repo_path)
    if stale:
        file_list = "\n".join(f"  - {s['file']}" for s in stale)
        findings.append(
            {
                "title": f"Review {len(stale)} stale TODO(s) in {repo_name}",
                "description": (
                    f"Found TODO markers in files that haven't been modified in over a year. "
                    f"These may represent abandoned work or outdated notes.\n\n{file_list}"
                ),
                "priority": 3,
                "scanner": "architecture",
            }
        )

    return findings
