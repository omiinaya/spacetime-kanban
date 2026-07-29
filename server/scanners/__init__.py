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
