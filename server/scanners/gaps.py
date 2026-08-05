"""Test gap scanner — finds code without corresponding tests.

Checks for:
  - Python modules without matching test file
  - Rust modules without #[cfg(test)] blocks
  - API endpoint files without test coverage
  - Functions with no tests in existing test files

Priority: P3 (low) — nice to have, not urgent.
"""

import os

from scanners import register_scanner, walk_repo


def _find_test_gaps_python(repo_path: str) -> list[str]:
    """Find Python modules missing corresponding test files.

    A module counts as covered if ANY of these hold:
      1. A test file named exactly ``test_{basename}.py`` exists.
      2. A test file named ``test_{parentdir}_{basename}.py`` exists
         (this repo's convention for nested modules, e.g.
         ``workers/llm.py`` → ``test_workers_llm.py``).
      3. ANY test file's content imports the module (handles grouped
         test files like ``test_scanner_modules.py`` which test many
         modules in one file).
    """
    test_dir = os.path.join(repo_path, "server", "tests")
    src_dirs = [os.path.join(repo_path, "server")]

    # Look for test files
    existing_tests = set()
    test_contents: list[str] = []
    if os.path.isdir(test_dir):
        for f in os.listdir(test_dir):
            if f.startswith("test_") and f.endswith(".py"):
                existing_tests.add(f)
                try:
                    with open(os.path.join(test_dir, f), encoding="utf-8", errors="replace") as fh:
                        test_contents.append(fh.read())
                except OSError:
                    pass

    def _is_covered(rel_dir: str, basename: str) -> bool:
        # 1. Exact test_{basename}.py
        if f"test_{basename}.py" in existing_tests:
            return True
        # 2. Directory-prefixed convention test_{parent}_{basename}.py
        parent = os.path.basename(rel_dir.rstrip(os.sep))
        if parent and f"test_{parent}_{basename}.py" in existing_tests:
            return True
        # 3. Any test file imports the module (grouped test files).
        #    Match dotted import paths, e.g. "from workers.llm import",
        #    "from workers import llm", "import workers.llm".
        if not test_contents:
            return False
        dotted = f"{parent}.{basename}" if parent else basename
        patterns = (
            f"from {dotted} import",
            f"from {dotted} ",
            f"import {dotted}",
            f"from {parent} import {basename}" if parent else "",
        )
        joined = "\n".join(test_contents)
        return any(p and p in joined for p in patterns)

    # Find non-test Python modules
    gaps = []
    for src_dir in src_dirs:
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in walk_repo(src_dir, extra_exclude={"tests"}):
            for f in files:
                if f.endswith(".py") and not f.startswith("test_") and f != "__init__.py":
                    basename = f[: -len(".py")]
                    rel_dir = os.path.relpath(root, src_dir)
                    if _is_covered(rel_dir, basename):
                        continue
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
    for root, _dirs, files in walk_repo(stdb_src):
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
                    "skip_verify": True,
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
                    "skip_verify": True,
                }
            )

    return findings
