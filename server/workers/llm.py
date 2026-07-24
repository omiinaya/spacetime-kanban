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
WORK_TIMEOUT = int(os.environ.get("KANBAN_LLM_TIMEOUT", "300"))  # 5 min (env-configurable)
GIT_TIMEOUT = 15  # git operations timeout
STDERR_LOG_LIMIT = 5000  # max stderr chars to include in block reason


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
            return True, f"{summary} ({len(changes_after)} file(s) changed)"
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
                return True, f"Completed ({len(changes_after)} file(s) changed)"

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
        return True, f"Task completed ({len(changes_after)} file(s) changed)"
    elif not meaningful and not has_new_changes:
        return False, "LLM returned empty/trivial response — no work done"
    elif not meaningful:
        # No actual content, but we see changes (rare)
        return True, "Changes detected despite minimal LLM output"

    # Default: couldn't determine outcome — provide stderr context
    stderr_log = stderr_data[-STDERR_LOG_LIMIT:] if stderr_data else ""
    if stderr_log:
        return False, f"LLM worker stderr: {stderr_log[:300]}"
    return False, f"LLM worker did not report completion. Response ({len(stdout_data)} chars)"
