#!/usr/bin/env python3
"""
SpacetimeKanban Self-Improvement Agent

A smart LLM-driven cron that periodically:
1. Checks server health and board state
2. Analyzes the codebase for issues and improvement opportunities
3. Fixes simple things directly (import bugs, config tweaks, restart if needed)
4. Creates improvement tasks on the kanban board for deeper work
5. Reports notable findings

Runs every 6 hours. Designed to be robust — never crashes the server.
Uses the kanban's own task system for improvements so workers handle the heavy lifting.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ── Config ──────────────────────────────────────────────────────────
KANBAN_API = os.environ.get("KANBAN_API", "http://localhost:8727")
KANBAN_AGENT = os.environ.get("HERMES_AGENT_ID", "kanban-improver")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER_DIR = os.path.join(PROJECT_ROOT, "server")
LLM_CMD = os.environ.get("KANBAN_IMPROVER_LLM", "hermes chat -Q -q")
STATUS_FILE = os.path.join(PROJECT_ROOT, "_improvement_status.json")

# Track what we already know to avoid repeat work
DEFAULT_STATUS = {
    "last_run": 0,
    "known_issues": [],        # issues we've already created tasks for
    "fixed_issues": [],        # issues we've already fixed
    "server_restarts": 0,      # count of server restarts we've done
    "run_count": 0,
}

# ── Helpers ─────────────────────────────────────────────────────────


def _api_get(path: str, timeout: int = 10) -> dict | list | None:
    """Call a kanban GET endpoint."""
    try:
        url = f"{KANBAN_API}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[improver] GET {path} failed: {e}", file=sys.stderr)
        return None


def _api_post(path: str, data: dict, timeout: int = 10) -> dict | None:
    """Call a kanban POST endpoint."""
    try:
        url = f"{KANBAN_API}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[improver] POST {path} failed: {e}", file=sys.stderr)
        return None


def _load_status() -> dict:
    """Load persistent state from disk."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_STATUS)


def _save_status(status: dict):
    """Save persistent state to disk."""
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"[improver] Failed to save status: {e}", file=sys.stderr)


def _run_cmd(cmd: list[str], timeout: int = 30, cwd: str | None = None) -> tuple[int, str]:
    """Run a shell command and return (exit_code, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or PROJECT_ROOT,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, f"TIMEOUT after {timeout}s"
    except Exception as e:
        return -1, str(e)


def _llm_analysis(prompt: str, timeout: int = 60) -> str:
    """Run an LLM analysis via hermes CLI and return the response."""
    try:
        result = subprocess.run(
            LLM_CMD.split() + [prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (result.stdout or "")[:2000]
    except subprocess.TimeoutExpired:
        return "[LLM analysis timed out]"
    except Exception as e:
        return f"[LLM error: {e}]"


def _task_exists_on_board(title_keyword: str) -> bool:
    """Check if a task with a matching keyword already exists in available/in_progress."""
    tasks = _api_get("/api/tasks?status=available&limit=200")
    if tasks:
        for t in tasks:
            if title_keyword.lower() in (t.get("title", "") or "").lower():
                return True
    tasks = _api_get("/api/tasks?status=in_progress&limit=100")
    if tasks:
        for t in tasks:
            if title_keyword.lower() in (t.get("title", "") or "").lower():
                return True
    return False


def _create_task(title: str, description: str, priority: int = 3, repo: str = "spacetimedb-kanban"):
    """Create an improvement task on the kanban board."""
    if _task_exists_on_board(title[:40]):
        print(f"[improver] Task already on board, skipping: {title[:60]}")
        return None
    result = _api_post("/api/tasks", {
        "title": title,
        "description": description,
        "priority": priority,
        "repo": repo,
        "roadmap_item": "Self-Improvement",
        "created_by": KANBAN_AGENT,
        "status": "available",
    })
    if result:
        tid = result.get("id", "?")
        print(f"[improver] Created task {tid[:25]}: {title[:60]}")
    else:
        print(f"[improver] Failed to create task: {title[:60]}")
    return result


def _fix_import_path():
    """Fix the import path issue: server/main.py uses `import issue_sync` which
    only works when running from the server/ directory. Fix by adding the
    server directory to sys.path early, or converting to a relative import."""
    main_py = os.path.join(SERVER_DIR, "main.py")
    if not os.path.exists(main_py):
        return False

    with open(main_py) as f:
        content = f.read()

    # Check if the fix is already in place
    if "sys.path.insert" in content and "issue_sync" in content:
        return True  # Already fixed

    # Add sys.path fix after the imports but before the issue_sync import
    old = "import issue_sync"
    new = """import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import issue_sync"""

    if old in content:
        with open(main_py, "w") as f:
            f.write(content.replace(old, new, 1))
        print("[improver] Fixed import path in main.py")
        return True

    return False


def _ensure_server_dir_env():
    """Ensure the server's .env has the WORKER_SCRIPT pointing to an absolute path."""
    env_file = os.path.join(SERVER_DIR, ".env")
    if not os.path.exists(env_file):
        return False

    with open(env_file) as f:
        content = f.read()

    # Check if WORKER_SCRIPT is already absolute
    for line in content.split("\n"):
        if line.startswith("WORKER_SCRIPT="):
            val = line.split("=", 1)[1].strip()
            if val.startswith("/"):
                return True  # Already absolute
            # Fix relative to absolute
            abs_path = os.path.join(SERVER_DIR, val)
            new_line = f"WORKER_SCRIPT={abs_path}"
            content = content.replace(line, new_line)
            with open(env_file, "w") as f:
                f.write(content)
            print(f"[improver] Fixed WORKER_SCRIPT to absolute path: {abs_path}")
            return True

    return False


# ── Checks ──────────────────────────────────────────────────────────


def check_server_health(status: dict) -> list[str]:
    """Check if the kanban server is alive and responding."""
    issues = []
    health = _api_get("/api/health")
    if health is None:
        issues.append("Server is DOWN — API not responding")
        # Try to restart
        code, out = _run_cmd(
            ["pkill", "-f", "uvicorn main:app"],
            timeout=5,
        )
        time.sleep(2)
        code, out = _run_cmd(
            [
                "python3", "-m", "uvicorn", "main:app",
                "--host", "0.0.0.0", "--port", "8727",
            ],
            timeout=10,
            cwd=SERVER_DIR,
        )
        status["server_restarts"] = status.get("server_restarts", 0) + 1
        print(f"[improver] Restarted server (attempt #{status['server_restarts']})")
        time.sleep(3)
        health = _api_get("/api/health")
        if health is None:
            issues.append("Server restart FAILED")
        else:
            issues.append("Server was restarted successfully")
    return issues


def check_board_health(status: dict) -> list[str]:
    """Check board state for anomalies."""
    issues = []

    # Check blocked tasks
    blocked = _api_get("/api/tasks?status=blocked&archived=false&limit=100")
    if blocked:
        blocked_count = len(blocked)
        if blocked_count > 5:
            issues.append(f"High blocked count: {blocked_count} tasks blocked")

        # Check for tasks that have been blocked too long
        now_ms = int(time.time() * 1000)
        old_blocked = [t for t in blocked if (now_ms - t.get("updated_at", 0)) > 86400000]
        if old_blocked:
            issues.append(f"{len(old_blocked)} tasks blocked >24h without retry")

    # Check in_progress tasks
    ip = _api_get("/api/tasks?status=in_progress&limit=100")
    if ip:
        now_ms = int(time.time() * 1000)
        stale_ip = [
            t for t in ip
            if (now_ms - t.get("updated_at", t.get("created_at", 0))) > 1800000
        ]
        if stale_ip:
            issues.append(f"{len(stale_ip)} tasks in_progress >30min")

    # Check available tasks cycling (fail_count > 0)
    avail = _api_get("/api/tasks?status=available&limit=200")
    if avail:
        cycling = [t for t in avail if t.get("fail_count", 0) > 0]
        if len(cycling) > 20:
            issues.append(f"High cycling count: {len(cycling)} tasks have fail_count > 0")

        # Check for definitive failures that should be permanent-blocked
        doomed = [
            t for t in cycling
            if t.get("fail_count", 0) > 0
            and (t.get("fail_reason", "") or "").lower().startswith(
                ("no indexable fields", "no unused imports", "nothing found")
            )
            and t.get("max_attempts", 3) > 1
        ]
        for t in doomed[:5]:
            tid = t["id"]
            _api_post(f"/api/tasks/{tid}/max-attempts", {"max_attempts": 1})
            print(f"[improver] Set max_attempts=1 for cycling task {tid[:25]}")
        if doomed:
            issues.append(f"Set max_attempts=1 for {len(doomed)} definitive-failure tasks")

    # Check agent/worker health
    agents = _api_get("/api/agents")
    if agents is not None:
        if not agents:
            pass  # No agents registered is OK for self-hosted mode

    # Check completion rate (tasks done in last hour)
    done = _api_get("/api/tasks?status=done&archived=false&limit=500")
    if done:
        now_ms = int(time.time() * 1000)
        recent = [t for t in done if (now_ms - t.get("updated_at", 0)) < 3600000]
        if not recent:
            pass  # Low activity is OK — might just be idle

    return issues


def check_codebase_health(status: dict) -> list[str]:
    """Analyze the codebase for issues to fix."""
    issues = []

    # Check if server starts properly from project root (import path issue)
    if not _fix_import_path():
        issues.append("Failed to fix import path in main.py")

    # Check WORKER_SCRIPT path
    _ensure_server_dir_env()

    # Check git status for uncommitted improvement work
    code, out = _run_cmd(["git", "status", "--porcelain"], timeout=10)
    if code == 0 and out.strip():
        changed_files = [l.strip() for l in out.strip().split("\n") if l.strip()]
        issues.append(f"{len(changed_files)} uncommitted change(s) in repo")

    # Check disk usage near the server
    code, out = _run_cmd(["df", "-h", PROJECT_ROOT], timeout=5)
    if code == 0:
        for line in out.split("\n"):
            if "%" in line and PROJECT_ROOT.split("/")[1] in line:
                try:
                    pct = int(line.split()[-1].rstrip("%"))
                    if pct > 80:
                        issues.append(f"Disk usage at {pct}% — nearly full")
                except (ValueError, IndexError):
                    pass

    return issues


def _run_llm_improvement_scan(status: dict) -> list[str]:
    """Use LLM to analyze recent server logs and suggest improvements."""
    issues = []

    # Check server log for recent errors
    log_files = [
        "/tmp/kanban-server-restart.log",
        "/home/user/kanban-server.log",
    ]
    log_snippets = ""
    for lf in log_files:
        if os.path.exists(lf):
            code, out = _run_cmd(["tail", "-50", lf], timeout=5)
            if code == 0 and out.strip():
                log_snippets += f"\n--- {lf} ---\n{out[:2000]}"

    if log_snippets:
        # Check for known error patterns
        for line in log_snippets.split("\n"):
            if "ERROR" in line or "Traceback" in line or "ModuleNotFoundError" in line:
                error_key = line.strip()[:100]
                if error_key not in [i.get("error", "") for i in status.get("known_issues", [])]:
                    issues.append(f"Server error detected: {error_key[:80]}")
                    status.setdefault("known_issues", []).append({
                        "error": error_key,
                        "found_at": int(time.time()),
                        "fixed": False,
                    })
                break

    # LLM-based analysis for improvement ideas
    if len(log_snippets) > 200:
        prompt = (
            f"You are analyzing the spacetime-kanban server. Here are the latest log "
            f"snippets, board state, and git status. Identify the TOP 3 improvements "
            f"that would make this kanban system more reliable or efficient. "
            f"Return only a short bullet list with 1-2 sentences each:\n\n"
            f"Logs: {log_snippets[:1500]}"
        )
        llm_result = _llm_analysis(prompt, timeout=120)
        if llm_result and llm_result != "[LLM analysis timed out]":
            for line in llm_result.split("\n"):
                line = line.strip()
                if line.startswith("-") and len(line) > 20:
                    idea_key = line[:60]
                    if not _task_exists_on_board(idea_key[:30]):
                        _create_task(
                            title=f"[AI Suggestion] {line.lstrip('- ')[:80]}",
                            description=f"Auto-detected by kanban improvement agent:\n{line}\n\nSource: log analysis at {time.strftime('%Y-%m-%d %H:%M:%S')}",
                            priority=2,
                        )
                        status.setdefault("ai_suggestions", []).append({
                            "idea": idea_key,
                            "created_at": int(time.time()),
                        })

    return issues


# ── Main ────────────────────────────────────────────────────────────


def main():
    status = _load_status()
    status["run_count"] = status.get("run_count", 0) + 1
    status["last_run"] = int(time.time())

    print(f"[improver] Run #{status['run_count']} — {time.strftime('%Y-%m-%d %H:%M:%S')}")

    all_issues = []

    # Phase 1: Check server health
    all_issues.extend(check_server_health(status))

    # Phase 2: Check board health
    all_issues.extend(check_board_health(status))

    # Phase 3: Check codebase
    all_issues.extend(check_codebase_health(status))

    # Phase 4: LLM analysis for improvement ideas (every 3rd run)
    if status["run_count"] % 3 == 0:
        all_issues.extend(_run_llm_improvement_scan(status))

    # Report
    critical = [i for i in all_issues if "DOWN" in i or "FAILED" in i or "error" in i.lower()]
    warnings = [i for i in all_issues if i not in critical]

    if critical:
        print(f"\n[improver] ⚠️  {len(critical)} critical issue(s):")
        for i in critical:
            print(f"  🔴 {i}")

    if warnings:
        print(f"\n[improver] ℹ️  {len(warnings)} finding(s):")
        for i in warnings:
            print(f"  • {i}")

    if not critical and not warnings:
        print("[improver] ✅ Board healthy, no issues found")

    # Create a task for critical issues
    for issue in critical:
        if "DOWN" in issue:
            _create_task(
                title=f"[Critical] Server health issue: {issue[:60]}",
                description=f"Auto-detected by kanban improvement agent:\n{issue}\n\nAction needed to restore server reliability.",
                priority=0,
            )

    _save_status(status)
    print(f"[improver] Done — status saved to {STATUS_FILE}")


if __name__ == "__main__":
    main()
