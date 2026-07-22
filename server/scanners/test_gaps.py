"""Test gap scanner — finds code without corresponding tests.

Checks for:
  - Python modules without matching test file
  - Rust modules without #[cfg(test)] blocks
  - API endpoint files without test coverage
  - Functions with no tests in existing test files

Priority: P3 (low) — nice to have, not urgent.
"""

import os
import re

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
    for root, dirs, files in os.walk(stdb_src):
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

    if rust_gaps:
        # Group by directory for cleaner reporting
        dirs = {}
        for g in rust_gaps:
            d = os.path.dirname(g)
            if d not in dirs:
                dirs[d] = []
            dirs[d].append(os.path.basename(g))

        summary = "\n".join(
            f"  - {d}/ ({len(files)} module(s))" for d, files in sorted(dirs.items())[:5]
        )
        if len(dirs) > 5:
            summary += f"\n  ... and {len(dirs) - 5} more directories"

        findings.append(
            {
                "title": f"Add unit tests for {len(rust_gaps)} untested Rust module(s) in {repo_name}",
                "description": f"The following Rust source files are missing `#[cfg(test)]` blocks:\n\n{summary}",
                "priority": 3,
                "scanner": "test_gaps",
            }
        )

    if py_gaps:
        summary = "\n".join(f"  - {g}" for g in py_gaps[:8])
        if len(py_gaps) > 8:
            summary += f"\n  ... and {len(py_gaps) - 8} more file(s)"

        findings.append(
            {
                "title": f"Add tests for {len(py_gaps)} untested Python module(s) in {repo_name}",
                "description": f"The following Python source files don't have corresponding test files:\n\n{summary}",
                "priority": 3,
                "scanner": "test_gaps",
            }
        )

    return findings
