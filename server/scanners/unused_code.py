"""Unused code scanner — finds dead code and unused imports.

Uses ruff (Python) and cargo (Rust) to detect:
  - Unused imports (F401 in Python, dead_code in Rust)
  - Unused variables (F841 in Python)
  - Dead functions/closures

Priority: P2 (medium) — code quality, not critical.
"""

import os
import re
import subprocess

from scanners import register_scanner


@register_scanner
def scan_unused_code(repo_name: str, repo_path: str) -> list[dict]:
    """Scan for unused imports and dead code."""
    findings = []

    # ── Python: ruff check for F401 (unused imports) and F841 (unused vars) ──
    has_python = any(
        os.path.isfile(os.path.join(repo_path, f))
        for f in ["pyproject.toml", "ruff.toml", "setup.py", "requirements.txt"]
    )
    if has_python:
        try:
            result = subprocess.run(
                ["ruff", "check", "--select", "F401,F841", "--output-format=concise", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = result.stdout + result.stderr
            # Count by file
            files = {}
            for line in output.split("\n"):
                if ":" in line and ("F401" in line or "F841" in line):
                    parts = line.split(":", 1)
                    filepath = parts[0].strip()
                    if filepath:
                        files[filepath] = files.get(filepath, 0) + 1

            if files:
                total = sum(files.values())
                top = sorted(files.items(), key=lambda x: -x[1])[:5]
                file_summary = "\n".join(f"  - {f} ({c} unused import(s))" for f, c in top)
                if len(files) > 5:
                    file_summary += f"\n  ... and {len(files) - 5} more file(s)"

                findings.append(
                    {
                        "title": (
                            f"Remove {total} unused import(s) "
                            f"across {len(files)} file(s) in {repo_name}"
                        ),
                        "description": (
                            f"Ruff found {total} unused import/"
                            f"variable violations:\\n\\n{file_summary}"
                        ),
                        "priority": 2,
                        "scanner": "unused_code",
                    }
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # ── Rust: check for dead_code warnings ──
    stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
    cargo_toml = os.path.join(repo_path, "Cargo.toml")
    if os.path.isdir(stdb_dir) or os.path.isfile(cargo_toml):
        target_dir = stdb_dir if os.path.isdir(stdb_dir) else repo_path
        try:
            result = subprocess.run(
                ["cargo", "check", "--message-format=short", "2>&1"],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout + result.stderr
            dead_code_lines = [
                line
                for line in output.split("\n")
                if "dead_code" in line or "unused import" in line
            ]
            if dead_code_lines and len(dead_code_lines) > 2:  # Ignore boilerplate
                findings.append(
                    {
                        "title": f"Fix {len(dead_code_lines)} dead_code warnings in {repo_name}",
                        "description": (
                            f"Cargo check reported "
                            f"{len(dead_code_lines)} dead code or "
                            f"unused import warnings. "
                            f"Run `cargo fix --allow-dirty` to auto-fix some of these.\n\n"
                            f"First warnings:\n" + "\n".join(dead_code_lines[:8])
                        ),
                        "priority": 2,
                        "scanner": "unused_code",
                        "skip_verify": True,
                    }
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # ── TypeScript/JS: check for unused exports via ts-prune or similar ──
    web_dir = os.path.join(repo_path, "web")
    if os.path.isfile(os.path.join(web_dir, "package.json")):
        # Check if ts-prune is available
        try:
            result = subprocess.run(
                ["npx", "--yes", "ts-prune", "--summary"],
                cwd=web_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            # Parse ts-prune output for count
            count_match = re.search(r"(\d+) unused exports?", output, re.IGNORECASE)
            if count_match:
                count = int(count_match.group(1))
                if count > 3:
                    findings.append(
                        {
                            "title": f"Remove {count} unused exports in {repo_name}/web",
                            "description": (
                                f"ts-prune found {count} unused exports "
                                f"in the web frontend. "
                                f"Cleaning these up reduces bundle size and improves clarity."
                            ),
                            "priority": 3,
                            "scanner": "unused_code",
                            "skip_verify": True,
                        }
                    )
        except Exception:
            pass

    return findings
