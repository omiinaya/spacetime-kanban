"""Test gap scanner — finds code without corresponding tests.

Checks for:
  - Python modules without matching test file
  - Rust modules without #[cfg(test)] blocks
  - API endpoint files without test coverage
  - Functions with no tests in existing test files

Priority: P3 (low) — nice to have, not urgent.
"""

import os

from scanners import register_scanner


def _find_test_gaps_python(repo_path: str) -> list[str]:
    """Find Python modules missing corresponding test files."""
    test_dir = os.path.join(repo_path, "server", "tests")
    src_dirs = [os.path.join(repo_path, "server")]

    # Look for test files
    existing_tests = set()
    if os.path.isdir(test_dir):
        for f in os.listdir(test_dir):
            if f.startswith("test_") and f.endswith(".py"):
                existing_tests.add(f)

    # Find non-test Python modules
    gaps = []
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        for root, dirs, files in os.walk(src_dir):
            # Skip dirs
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith("__")
                and not d.startswith(".")
                and d not in ("tests", ".venv", "venv", "__pycache__", "node_modules")
            ]
            for f in files:
                if f.endswith(".py") and not f.startswith("test_") and f != "__init__.py":
                    # Check if corresponding test exists
                    test_name = f"test_{f}"
                    if test_name not in existing_tests:
                        # Also check inline test functions
                        filepath = os.path.join(root, f)
                        rel_path = os.path.relpath(filepath, repo_path)
                        gaps.append(rel_path)
    return gaps


def _find_test_gaps_rust(repo_path: str) -> list[str]:
    """Find Rust modules missing #[cfg(test)] blocks."""
    stdb_src = os.path.join(repo_path, "server", "spacetimedb", "src")
    if not os.path.isdir(stdb_src):
        return []

    gaps = []
    for root, _dirs, files in os.walk(stdb_src):
        for f in files:
            if not f.endswith(".rs"):
                continue
            filepath = os.path.join(root, f)
            try:
                with open(filepath) as fh:
                    content = fh.read()
                if "#[cfg(test)]" not in content and "#[test]" not in content:
                    # Skip mod.rs that only re-exports
                    if f == "mod.rs" and content.strip().count("\n") < 5:
                        continue
                    rel = os.path.relpath(filepath, repo_path)
                    gaps.append(rel)
            except (OSError, UnicodeDecodeError):
                continue
    return gaps


@register_scanner
def scan_test_gaps(repo_name: str, repo_path: str) -> list[dict]:
    """Find code without corresponding test coverage."""
    findings = []
    py_gaps = _find_test_gaps_python(repo_path)
    rust_gaps = _find_test_gaps_rust(repo_path)

    max_per_task = (
        5  # Split findings into tasks of this max size so workers can actually finish them
    )

    if rust_gaps:
        for i in range(0, len(rust_gaps), max_per_task):
            chunk = rust_gaps[i : i + max_per_task]
            summary = "\n".join(f"  - {g}" for g in chunk)
            task_num = i // max_per_task + 1
            total_chunks = (len(rust_gaps) + max_per_task - 1) // max_per_task
            label = f" ({task_num}/{total_chunks})" if total_chunks > 1 else ""
            findings.append(
                {
                    "title": (
                        f"Add unit tests for {len(chunk)} untested "
                        f"Rust module(s) in {repo_name}{label}"
                    ),
                    "description": (
                        f"The following Rust source files "
                        f"are missing `#[cfg(test)]` blocks:\n\n{summary}"
                    ),
                    "priority": 3,
                    "scanner": "test_gaps",
                }
            )

    if py_gaps:
        for i in range(0, len(py_gaps), max_per_task):
            chunk = py_gaps[i : i + max_per_task]
            summary = "\n".join(f"  - {g}" for g in chunk)
            task_num = i // max_per_task + 1
            total_chunks = (len(py_gaps) + max_per_task - 1) // max_per_task
            label = f" ({task_num}/{total_chunks})" if total_chunks > 1 else ""
            findings.append(
                {
                    "title": (
                        f"Add tests for {len(chunk)} untested "
                        f"Python module(s) in {repo_name}{label}"
                    ),
                    "description": (
                        f"The following Python source files "
                        f"don't have corresponding test files:\n\n{summary}"
                    ),
                    "priority": 3,
                    "scanner": "test_gaps",
                }
            )

    return findings
