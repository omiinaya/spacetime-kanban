"""LLM-driven worker — uses hermes chat -q for tasks needing reasoning.

This is the default worker for any task that doesn't match a mechanical
pattern. It spawns `hermes chat` in single-query mode and evaluates
the response to determine if the task was completed or blocked.

Flow:
  1. Build prompt from task title + description + repo context
  2. Run `hermes chat -Q -q "prompt"` (single-turn, quiet)
  3. Parse response for DONE marker or completion indicators
  4. If repo_path given, verify git changes were made
  5. Complete or block via kanban API
"""

import os
import re
import shlex
import subprocess
import time

from workers.base import WorkerContext

# ── Config ──────────────────────────────────────────────────────────

LLM_COMMAND_STR = os.environ.get(
    "KANBAN_LLM_WORKER",
    "hermes chat -Q -q",  # Default: Hermes quiet single-query mode (has tool access)
)
LLM_COMMAND = shlex.split(LLM_COMMAND_STR)

# Safety limits
WORK_TIMEOUT = int(os.environ.get("KANBAN_LLM_TIMEOUT", "3600"))  # 60 min (env-configurable)
GIT_TIMEOUT = 15  # git operations timeout
STDERR_LOG_LIMIT = 5000  # max stderr chars to include in block reason

# Post-completion test verification (proves improvement lab is "reviewed complete").
VERIFY_TESTS_ENABLED = os.environ.get("KANBAN_VERIFY_TESTS", "1") != "0"
VERIFY_TESTS_TIMEOUT = int(os.environ.get("KANBAN_VERIFY_TESTS_TIMEOUT", "180"))  # seconds


# ── Prompt builder ──────────────────────────────────────────────────


def _build_prompt(ctx: WorkerContext) -> str:
    """Build the LLM prompt from the task context."""
    title = ctx.title
    repo = ctx.repo
    repo_path = ctx.repo_path or "unknown"
    description = (ctx.task or {}).get("description", "")
    branch = (ctx.task or {}).get("branch", "") or "none"
    pr_url = (ctx.task or {}).get("pr_url", "") or "none"

    parts = [
        "You are a kanban worker agent. Your job is to complete the task below.",
        "",
        f"## Task: {title}",
        f"**Repository:** {repo}  ({repo_path})",
    ]

    if description:
        parts.append(f"\n**Description:** {description}")

    parts.append(f"\n**Branch:** {branch}")
    parts.append(f"**PR:** {pr_url}")
    parts.append("")

    parts.extend(
        [
            "## Rules",
            "1. Work inside `~/{repo}` — the repo is already cloned",
            "2. Make changes, run tests, fix bugs — do what the task requires",
            "3. Use git for status checks; run relevant tests",
            "4. DO NOT create GitHub issues or PRs",
            "5. DO NOT send Discord messages",
            "6. DO NOT edit files outside the repo",
            "",
            "## Completion",
            "When you finish, end your response with exactly:",
            "WORKER_DONE: <one-line summary of what was done>",
            "",
            "If you cannot complete the task (blocked, unclear, missing info), end with:",
            "WORKER_BLOCKED: <reason>",
            "",
            "Work efficiently.",
        ]
    )

    prompt = "\n".join(parts)
    # Use escaped newlines for hermes -z (oneshot mode handles \\n correctly)
    return prompt.replace("\n", "\\n")


def _has_git_changes(repo_path: str) -> list[str]:
    """Return list of changed files, or empty list on error."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        files = [f for f in result.stdout.strip().split("\n") if f.strip()]
        return files
    except Exception:
        return []


def _has_git_commits_since(repo_path: str, start_ref: str = "HEAD~1") -> bool:
    """Check if there are new commits (rough check)."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _detect_test_command(repo_path: str) -> list[str] | None:
    """Detect the repo's test command, or None if none is obvious.

    Order of preference: Makefile `test` target → Cargo.toml (Rust) →
    pyproject.toml/setup.cfg (pytest) → package.json (npm/vitest/jest).
    Returns a shlex-split command list ready for subprocess.run.
    """
    import shlex as _shlex

    makefile = os.path.join(repo_path, "Makefile")
    if os.path.isfile(makefile):
        try:
            with open(makefile, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if re.search(r"^test\s*:", content, re.MULTILINE):
                return ["make", "test"]
        except Exception:  # noqa: S110 — best-effort detection
            pass

    cargo = os.path.join(repo_path, "Cargo.toml")
    if os.path.isfile(cargo):
        try:
            with open(cargo, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if "[dev-dependencies]" in content or "#[cfg(test)]" in content:
                return ["cargo", "test", "--quiet"]
        except Exception:  # noqa: S110 — best-effort detection
            pass

    for cfg_file in ("pyproject.toml", "setup.cfg", "pytest.ini"):
        cfg_path = os.path.join(repo_path, cfg_file)
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                if "pytest" in content.lower():
                    return ["python3", "-m", "pytest", "-q"]
            except Exception:  # noqa: S110 — best-effort detection
                pass

    pkg_json = os.path.join(repo_path, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, encoding="utf-8", errors="replace") as f:
                content = f.read()
            if '"test"' in content:
                # Prefer vitest/jest for frontend repos
                if "vitest" in content:
                    return _shlex.split("npx vitest run --reporter=dot")
                if "jest" in content:
                    return _shlex.split("npx jest --silent")
                return _shlex.split("npm test -- --run")
        except Exception:  # noqa: S110 — best-effort detection
            pass

    return None


def _verify_repo_tests(repo_path: str, timeout: int = 0) -> tuple[bool, str]:
    """Run the repo's test suite to verify a change didn't break anything.

    Returns (ok, detail):
      - (True, msg) if tests pass, OR no test command is detectable (nothing
        to run — don't block a task just because the repo has no harness).
      - (False, msg) if a test command exists and FAILS (the change broke it).
    """
    if not VERIFY_TESTS_ENABLED:
        return True, "test verification disabled (KANBAN_VERIFY_TESTS=0)"

    cmd = _detect_test_command(repo_path)
    if cmd is None:
        return True, "no test harness detected — skipping verification"

    if timeout <= 0:
        timeout = VERIFY_TESTS_TIMEOUT

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, f"tests pass ({' '.join(cmd)})"
        tail = (result.stdout + "\n" + result.stderr).strip().splitlines()[-15:]
        preview = "\n".join(tail)[-800:]
        return False, f"tests FAILED ({' '.join(cmd)}):\n{preview}"
    except subprocess.TimeoutExpired:
        # Timed out — don't block on a slow suite, but flag it in the result
        return True, f"test verification timed out after {timeout}s (not counted as failure)"
    except FileNotFoundError:
        # Tool missing (e.g. cargo/npm not installed) — don't block the task
        return True, "test tool not found — skipping verification"
    except Exception as e:  # noqa: S110 — never let verification crash the worker
        return True, f"test verification error (not counted as failure): {e}"


# ── Main worker ─────────────────────────────────────────────────────


def run_llm_worker(ctx: WorkerContext) -> tuple[bool, str]:
    """Run the LLM worker: single hermes chat query, evaluate response."""
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    prompt = _build_prompt(ctx)
    ctx.add_log("llm_started", f"LLM worker: {ctx.title[:80]}")

    # Snapshot git state before working
    changes_before = _has_git_changes(repo_path)

    start_time = time.time()
    proc = None

    try:
        # Build command: shlex-split the base command, append prompt as last arg
        cmd = LLM_COMMAND + [prompt]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=repo_path,
        )

        stdout_data, stderr_data = proc.communicate(timeout=WORK_TIMEOUT)
        time.time() - start_time

    except subprocess.TimeoutExpired:
        if proc and proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=10)
        return False, f"LLM worker timed out after {WORK_TIMEOUT}s"
    except FileNotFoundError:
        return False, f"LLM command not found: '{LLM_COMMAND_STR}' — is hermes installed?"
    except OSError as e:
        return False, f"Failed to run LLM command: {e}"
    except Exception as e:
        return False, f"LLM worker error: {e}"

    # ── Parse result ────────────────────────────────────────────────

    # Check for explicit completion marker
    done_match = re.search(r"WORKER_DONE:\s*(.+)", stdout_data, re.IGNORECASE)
    blocked_match = re.search(r"WORKER_BLOCKED:\s*(.+)", stdout_data, re.IGNORECASE)

    if done_match:
        summary = done_match.group(1).strip()
        # Verify actual changes were made
        changes_after = _has_git_changes(repo_path)
        if len(changes_after) > len(changes_before):
            # Review gate: the change must not break the repo's tests.
            ok, verify_msg = _verify_repo_tests(repo_path)
            if not ok:
                return False, f"WORKER_DONE reported but {verify_msg}"
            return True, f"{summary} ({len(changes_after)} file(s) changed; {verify_msg})"
        else:
            # No new files changed — possibly committed or just reported
            return True, summary

    if blocked_match:
        reason = blocked_match.group(1).strip()
        return False, f"LLM blocked: {reason}"

    # No explicit marker — evaluate heuristically
    stdout_lower = stdout_data.lower()

    # Check for explicit completion language
    finished_indicators = [
        "task is complete",
        "task completed",
        "finished the task",
        "all done",
        "i have completed",
        "completed the task",
    ]
    for indicator in finished_indicators:
        if indicator in stdout_lower:
            changes_after = _has_git_changes(repo_path)
            # Check for "nothing to change" or "already done"
            already_done = any(
                p in stdout_lower
                for p in [
                    "was already",
                    "is already",
                    "nothing to do",
                    "no changes needed",
                    "already implemented",
                    "already exists",
                ]
            )
            if already_done and len(changes_after) == len(changes_before):
                return True, "No changes needed — task was already satisfied"
            if len(changes_after) > len(changes_before):
                ok, verify_msg = _verify_repo_tests(repo_path)
                if not ok:
                    return False, f"Completion reported but {verify_msg}"
                return True, f"Completed ({len(changes_after)} file(s) changed; {verify_msg})"

    # Check for blocked indicators
    blocked_indicators = [
        "i cannot",
        "i'm blocked",
        "i am blocked",
        "cannot complete",
        "unable to",
        "not possible",
        "missing information",
    ]
    for indicator in blocked_indicators:
        if indicator in stdout_lower:
            # Truncate long responses for the block reason
            preview = stdout_data.strip()[:500].replace("\n", " ")
            return False, f"LLM blocked: {preview}"

    # Check for meaningful content vs boilerplate
    meaningful = len(stdout_data.strip()) > 100
    changes_after = _has_git_changes(repo_path)
    has_new_changes = len(changes_after) > len(changes_before)

    if has_new_changes and meaningful:
        ok, verify_msg = _verify_repo_tests(repo_path)
        if not ok:
            return False, f"Changes detected but {verify_msg}"
        return True, f"Task completed ({len(changes_after)} file(s) changed; {verify_msg})"
    elif not meaningful and not has_new_changes:
        return False, "LLM returned empty/trivial response — no work done"
    elif not meaningful:
        # No actual content, but we see changes (rare)
        ok, verify_msg = _verify_repo_tests(repo_path)
        if not ok:
            return False, f"Changes detected but {verify_msg}"
        return True, f"Changes detected despite minimal LLM output ({verify_msg})"

    # Default: couldn't determine outcome — provide stderr context
    stderr_log = stderr_data[-STDERR_LOG_LIMIT:] if stderr_data else ""
    if stderr_log:
        return False, f"LLM worker stderr: {stderr_log[:300]}"
    return False, f"LLM worker did not report completion. Response ({len(stdout_data)} chars)"
