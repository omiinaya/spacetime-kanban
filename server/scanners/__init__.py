"""Repo improvement scanners — find issues, create kanban tasks.

Each scanner is a module with a `scan(repo_name: str, repo_path: str) -> list[dict]`
function that returns findings:
  {
    "title": str,
    "description": str,
    "priority": int (0=urgent, 1=high, 2=medium, 3=low),
    "scanner": str,  # scanner name for dedup
  }
"""

import os
import subprocess
from collections.abc import Callable

# ── Scanner registry (defined BEFORE importing modules to avoid circular deps) ──

SCANNERS: list[Callable] = []


def register_scanner(fn):
    """Decorator: register a scanner module."""
    SCANNERS.append(fn)
    return fn


def get_scanner_name(fn: Callable) -> str:
    """Get the scanner name from a function."""
    return fn.__name__.replace("scan_", "")


# ── Pruned directory walker ────────────────────────────────────────────
# Scanning repos naively with os.walk() walks EVERYTHING — .git, node_modules,
# target/, venv, dist, build — millions of files across 50+ repos. The scanner
# runs inside the server process (run_in_executor), so an unpruned walk pegs
# CPU at 100% for minutes and starves /api/health (observed: 5s timeouts while
# run_all_scanners walked ~/sample-repo-m's 92K files).
_SCAN_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "target",
        "dist",
        "build",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        ".cache",
        "coverage",
        ".coverage",
        "htmlcov",
        ".eggs",
        "*.egg-info",
        ".gradle",
        ".cargo",
        ".rustup",
        ".hermes",
        ".config",
        ".local",
        "site-packages",
        "vendor",
        "third_party",
        "third-party",
        "bower_components",
    }
)


def walk_repo(repo_path: str, extra_exclude: set[str] | frozenset[str] | None = None):
    """Yield (root, dirs, files) for a repo, pruning heavy/build dirs.

    Every scanner must use this instead of raw os.walk() — the pruning is
    what keeps a full-board scan bounded (seconds, not minutes of CPU).
    ``dirs`` is mutated in place so os.walk skips pruned subtrees entirely.
    ``extra_exclude`` adds caller-specific dir names (e.g. {"tests"}).
    """
    exclude = _SCAN_EXCLUDE_DIRS
    if extra_exclude:
        exclude = exclude | frozenset(extra_exclude)
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in exclude and not d.endswith(".egg-info")]
        yield root, dirs, files


# ── Import all scanner modules so their @register_scanner decorators run ──
from . import (  # noqa: E402
    dep_scanner,
    gaps,
    layer_architecture,
    layer_docs,
    layer_security,
    stdb_index,
    todo_scanner,
    unused_code,
)


def discover_repos(max_repos: int = 50) -> list[tuple[str, str]]:
    """Discover repos in ~/ that have a .git directory.

    Returns list of (repo_name, repo_path).
    Excludes dot-directories and known non-project dirs.
    Prioritizes repos with code (not forks/templates).
    """
    home = os.path.expanduser("~")
    exclude = {
        ".hermes",
        ".config",
        ".cache",
        ".local",
        ".rustup",
        ".cargo",
        ".n",
        ".npm",
        ".oci",
        ".ssh",
        ".git",
        "test",
        "depot_tools",
        "emsdk",
    }

    def score_repo(name: str) -> int:
        """Higher score = higher priority for scanning."""
        if any(name.startswith(p) for p in ["spacetime-"]):
            return 10  # STDB projects are highest priority
        if any(name.startswith(p) for p in ["hermes-", "factoring", "nightms", "kimi-"]):
            return 8
        if any(name.startswith(p) for p in ["ca-", "akamai", "stealth", "browser"]):
            return 7
        # Check for actual project files to boost priority
        return 5

    repos = []
    for entry in sorted(os.listdir(home)):
        if entry.startswith(".") or entry in exclude:
            continue
        repo_path = os.path.join(home, entry)
        git_dir = os.path.join(repo_path, ".git")
        if not os.path.isdir(git_dir):
            continue

        score = score_repo(entry)
        # Fast check for project structure
        has_code = any(
            os.path.isfile(os.path.join(repo_path, f))
            for f in [
                "Cargo.toml",
                "pyproject.toml",
                "package.json",
                "setup.py",
                "go.mod",
                "CMakeLists.txt",
            ]
        )
        if not has_code and score < 8:
            continue

        repos.append((entry, repo_path, score))

    # Sort by score descending, then name
    repos.sort(key=lambda x: (-x[2], x[0]))
    return [(name, path) for name, path, _ in repos[:max_repos]]
