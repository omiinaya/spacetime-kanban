"""Background scheduler — in-process periodic tasks.

Replaces ALL Hermes cron jobs for kanban lifecycle management.

Design:
  - Runs as asyncio tasks inside the FastAPI server process
  - Each periodic function is an async loop with configurable interval
  - Webhook events replace Discord-delivery cron scripts
  - STDB state replaces file-based tracker files
  - No external dependencies (no cron, no scheduler daemon)

Scheduler loops:
  task_dispatcher     :30s  — claim available tasks, spawn workers
  stale_watcher       :120s — unclaim tasks stuck >stale_minutes
  dead_board_monitor  :900s — detect zero-throughput, auto-remediate + alert
  metrics_collector   :300s — board metrics snapshot, fire webhook
  template_trigger    :900s — fire recurring task templates
  self_improver      :21600s — health check, codebase audit, improvement tasks
"""

import asyncio
import os
import subprocess
import time
import urllib.parse
from typing import Any

import httpx

from config import settings
from webhook_dispatcher import (
    EVENT_BOARD_DEAD,
    EVENT_BOARD_STALLED,
    EVENT_METRICS_SNAPSHOT,
    EVENT_WORKER_STALE,
    fire_event,
)

# ── Helpers ──────────────────────────────────────────────────────────

API_BASE = f"http://localhost:{settings.server_port}"

# Shared httpx client — reused across all scheduler API calls to avoid
# creating a fresh connection pool (with TCP handshake) every single tick.
_client: httpx.AsyncClient | None = None
_client_limits = httpx.Limits(
    max_keepalive_connections=10,
    max_connections=20,
    keepalive_expiry=30,
)


def _get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=3.0),
            limits=_client_limits,
        )
    return _client


async def _api_get(path: str, timeout: float = 15) -> Any:
    try:
        client = _get_client()
        if '%' not in path:
            path = urllib.parse.quote(path, safe='/:@!$&\'()*+,;=?&=')
        resp = await client.get(f"{API_BASE}{path}", timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


async def _api_post(path: str, data: dict, timeout: float = 15) -> dict | None:
    try:
        client = _get_client()
        if '%' not in path:
            path = urllib.parse.quote(path, safe='/:@!$&\'()*+,;=?&=')
        resp = await client.post(f"{API_BASE}{path}", json=data, timeout=timeout)
        if resp.status_code < 500:
            return resp.json() if resp.content else {"status": "ok"}
        return None
    except Exception:
        return None


async def _api_delete(path: str, timeout: float = 15) -> bool:
    try:
        client = _get_client()
        resp = await client.delete(f"{API_BASE}{path}", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Worker process management ───────────────────────────────────────

_worker_processes: dict[str, subprocess.Popen] = {}  # task_id -> Popen
_worker_spawn_times: dict[str, float] = {}  # task_id -> time.monotonic()
_worker_crash_counts: dict[str, int] = {}  # task_id -> consecutive immediate crashes
_worker_stderr_data: dict[str, bytes] = {}  # task_id -> captured stderr on crash
scheduler_start_time: float | None = None  # set when start_scheduler() runs
_CRASH_RESET_INTERVAL = 3600  # Reset crash count after 1 hour
_IMMEDIATE_CRASH_THRESHOLD = 3.0  # seconds — die within this = crash-on-launch


def _spawn_worker(task_id: str, title: str, repo: str) -> bool:
    """Spawn a worker subprocess for a claimed task.

    The worker receives only the task_id; it fetches task details
    (repo, title, description) from the kanban API itself, then
    routes to the appropriate handler (mechanical or LLM).

    Two modes:
      1. worker_script is a .py file → python3 <script> <task_id>
      2. worker_args is set → python3 <args> <task_id> (e.g. -m module.path)

    Returns True if spawned (process may still die — death_watcher handles).
    Returns False if no worker is configured (manual mode).
    """
    script = settings.worker_script
    args = settings.worker_args
    if not script and not args:
        return False

    server_dir = os.path.dirname(os.path.abspath(__file__))

    try:
        if script and script.endswith(".py"):
            script_path = script if script.startswith("/") else os.path.join(server_dir, script)
            cmd = [settings.worker_command, script_path, task_id]
        elif args:
            cmd = [settings.worker_command] + args.split() + [task_id]
        else:
            return False

        proc = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(server_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={
                **os.environ,
                "KANBAN_API": f"http://localhost:{settings.server_port}",
                "AGENT_ID": settings.agent_id,
                # Strip Hermes gateway vars that poison nested subprocesses
                "_HERMES_GATEWAY": "",
                "HERMES_SESSION_ID": "",
                "HERMES_SESSION_KEY": "",
                "HERMES_QUIET": "",
                "HERMES_REDACT_SECRETS": "",
                # Pass LLM worker config to subprocess — .env vars aren't auto-propagated
                "KANBAN_LLM_TIMEOUT": "1800",
                "KANBAN_LLM_WORKER": "hermes chat -Q -q",
            },
        )
        _worker_processes[task_id] = proc
        _worker_spawn_times[task_id] = time.monotonic()
        return True
    except Exception as e:
        print(f"[scheduler] Failed to spawn worker for {task_id[:20]}: {e}")
        return False


def _get_worker_count() -> int:
    """Count live worker processes. Does NOT prune — death watcher owns that."""
    alive = 0
    for _tid, proc in _worker_processes.items():
        if proc and proc.poll() is None:
            alive += 1
    return alive


def _check_crashed_workers() -> list[tuple[str, int, float]]:
    """Detect workers that died without completing their task.

    Returns list of (task_id, exit_code, spawn_time_monotonic).
    Does NOT pop from dicts — the caller (worker_death_watcher) owns cleanup.
    """
    now = time.monotonic()
    crashed: list[tuple[str, int, float]] = []

    for tid, proc in list(_worker_processes.items()):
        exit_code = proc.poll()
        if exit_code is not None:
            spawn_time = _worker_spawn_times.get(tid, now)

            if now - spawn_time < _IMMEDIATE_CRASH_THRESHOLD:
                # Died within threshold — definitely a launch crash
                count = _worker_crash_counts.get(tid, 0) + 1
                _worker_crash_counts[tid] = count
            else:
                # Died after running — wasn't caught by 500ms check
                _worker_crash_counts.pop(tid, None)

            crashed.append((tid, exit_code, spawn_time))

    return crashed


def _reset_worker_crash_count(task_id: str):
    """Reset crash counter when a task is successfully retried."""
    _worker_crash_counts.pop(task_id, None)


def _kill_worker(task_id: str) -> bool:
    """Kill a worker process."""
    proc = _worker_processes.pop(task_id, None)
    _worker_spawn_times.pop(task_id, None)
    if proc and proc.poll() is None:
        try:
            proc.kill()
            return True
        except Exception:
            pass
    return False


# ── Scheduler loops ─────────────────────────────────────────────────


async def task_dispatcher(interval: int):
    """Claim available tasks and spawn workers.

    Runs every `interval` seconds. Maintains min_workers pool.
    Picks highest-priority available tasks, claims atomically, spawns workers.
    Skip claiming if no worker_script configured (manual/observability mode).
    """
    while True:
        try:
            await asyncio.sleep(interval)

            # Skip claiming if no worker is configured — manual operation mode
            if not settings.worker_script:
                continue

            worker_count = _get_worker_count()
            if worker_count >= settings.max_workers:
                if worker_count % 60 == 0:  # Log ~every 2 min at 30s interval
                    print(
                        f"[scheduler:dispatcher] All {settings.max_workers} worker slots full — waiting"
                    )
                continue

            # Check memory pressure
            try:
                with open("/proc/meminfo") as f:
                    meminfo = f.read()
                total_kb = 0
                avail_kb = 0
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
                if total_kb > 0:
                    used_pct = 100 * (1 - avail_kb / total_kb)
                    if used_pct > settings.max_memory_pct:
                        continue  # Skip if memory too high
            except Exception:
                pass

            # Fetch available tasks
            available = await _api_get("/api/tasks?status=available&limit=200")
            if not available:
                continue

            # Filter out tasks that have exhausted their retry budget
            # (permanent-block tasks go straight to "blocked", not "available")
            eligible = [t for t in available if t.get("fail_count", 0) < t.get("max_attempts", 3) * 100]

            # Sort: priority asc (P0 first), then fail_count asc, then oldest first
            eligible.sort(
                key=lambda t: (
                    t.get("priority", 5),
                    t.get("fail_count", 0),
                    t.get("created_at", 0),
                )
            )

            slots = settings.max_workers - worker_count
            for task in eligible[:slots]:
                tid = task.get("id", "")
                title = task.get("title", "?")
                repo = task.get("repo", "")

                # Try to claim atomically
                result = await _api_post(
                    f"/api/tasks/{tid}/claim",
                    {"agent_id": settings.agent_id},
                )
                if result and "error" not in str(result):
                    _spawn_worker(tid, title, repo)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:dispatcher] Error: {e}")


async def stale_watcher(interval: int):
    """Unclaim tasks that have been in_progress too long without activity.

    Runs every `interval` seconds. Checks tasks assigned to our agent_id.
    Releases if:
      - claim_age > stale_minutes AND no heartbeat in >10min
      - claim_age > 60min (force release regardless)
    """
    while True:
        try:
            await asyncio.sleep(interval)

            in_progress = await _api_get("/api/tasks?status=inProgress&limit=500")
            if not in_progress:
                continue

            now_ms = _now_ms()
            unclaimed = 0

            for t in in_progress:
                if t.get("assigned_to") != settings.agent_id:
                    continue

                tid = t["id"]
                claim_ts = t.get("updated_at", t.get("created_at", 0))
                claim_age_min = (now_ms - claim_ts) / 60000 if claim_ts else 0

                if claim_age_min < 5:
                    continue  # Grace period for worker boot

                # Check heartbeat via task logs
                hb_ts = None
                logs = await _api_get(f"/api/logs?task_id={tid}&limit=5")
                if logs:
                    for entry in reversed(logs):
                        if entry.get("action") == "heartbeat" and entry.get("timestamp"):
                            hb_ts = entry["timestamp"]
                            break

                hb_age_min = (now_ms - hb_ts) / 60000 if hb_ts else 999

                force_release = claim_age_min > 60
                stale_release = claim_age_min > settings.stale_minutes and (
                    hb_ts is None or hb_age_min > 10
                )

                if force_release or stale_release:
                    # Fire webhook before unclaiming
                    if stale_release:
                        await fire_event(
                            EVENT_WORKER_STALE,
                            {
                                "task_id": tid,
                                "title": t.get("title", "?")[:80],
                                "age_minutes": claim_age_min,
                                "repo": t.get("repo", "?"),
                            },
                        )

                    # Unclaim via bulk-retry to also reset fail_count
                    result = await _api_post(
                        "/api/tasks/bulk-retry",
                        {"task_ids": [tid]},
                    )
                    if result and result.get("retried", 0) > 0:
                        unclaimed += 1

            if unclaimed > 0:
                print(f"[scheduler:stale] Released {unclaimed} stale tasks")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:stale] Error: {e}")


async def dead_board_monitor(interval: int):
    """Detect zero-throughput board, auto-remediate, then alert.

    Runs every `interval` seconds.
    1. If board has 0 completions in last hour while work exists → try restart
    2. If restart fails → fire dead-board webhook alert
    3. Also detects stalled boards (high claim:complete ratio)
    """
    last_alert_ms = 0
    alert_cooldown_ms = 3600_000  # Don't re-alert within 1 hour

    while True:
        try:
            await asyncio.sleep(interval)

            overview = await _api_get("/api/analytics/overview")
            if not overview:
                # Server might be down — try to restart
                print("[scheduler:deadboard] Overview API returned nothing — attempting self-heal")
                _restart_server()
                await asyncio.sleep(5)
                # Check if restart worked
                health = await _api_get("/api/health")
                if health:
                    print("[scheduler:deadboard] Self-heal: server restarted successfully")
                else:
                    print("[scheduler:deadboard] Self-heal failed — server still unreachable")
                continue

            completions = overview.get("completions_last_hour", 0)
            claims = overview.get("claims_last_hour", 0)
            ip = overview.get("by_status", {}).get("inProgress", 0)
            avail = overview.get("by_status", {}).get("available", 0)
            done = overview.get("total_done", 0)

            now_ms = _now_ms()

            # Auto-remediate: 0 completions + work exists
            if completions == 0 and (ip > 0 or avail > 0) and done > 0:
                print(f"[scheduler:deadboard] Zero completions with work — attempting self-heal "
                      f"(ip={ip}, avail={avail}, done={done})")
                _restart_server()
                await asyncio.sleep(5)
                # Re-check after restart
                overview = await _api_get("/api/analytics/overview")
                if overview and overview.get("completions_last_hour", 0) > 0:
                    print("[scheduler:deadboard] Self-heal: throughput restored after restart")
                    continue
                print("[scheduler:deadboard] Self-heal failed — alerting")
                await fire_event(
                    EVENT_BOARD_DEAD,
                    {
                        "total": overview.get("total", 0) if overview else 0,
                        "available": avail,
                        "in_progress": ip,
                        "blocked": overview.get("by_status", {}).get("blocked", 0) if overview else 0,
                        "done": done,
                        "completions_last_hour": 0,
                        "claims_last_hour": claims,
                        "claim_complete_ratio": overview.get("claim_complete_ratio", 0) if overview else 0,
                    },
                )
                last_alert_ms = now_ms
                continue

            # Alert-only: dead board with work (after cooldown)
            if completions == 0 and (ip > 0 or avail > 0) and now_ms - last_alert_ms > alert_cooldown_ms:
                    await fire_event(
                        EVENT_BOARD_DEAD,
                        {
                            "total": overview.get("total", 0),
                            "available": avail,
                            "in_progress": ip,
                            "blocked": overview.get("by_status", {}).get("blocked", 0),
                            "done": overview.get("total_done", 0),
                            "completions_last_hour": 0,
                            "claims_last_hour": claims,
                            "claim_complete_ratio": overview.get("claim_complete_ratio", 0),
                        },
                    )
                    last_alert_ms = now_ms

            # Stalled check: abnormally high claim:complete ratio
            ratio = overview.get("claim_complete_ratio", 0)
            if ratio > 20 and claims > 50 and completions == 0 and now_ms - last_alert_ms > alert_cooldown_ms:
                    await fire_event(
                        EVENT_BOARD_STALLED,
                        {
                            "claims_last_hour": claims,
                            "completions_last_hour": 0,
                            "claim_complete_ratio": ratio,
                            "in_progress": ip,
                            "available": avail,
                        },
                    )
                    last_alert_ms = now_ms

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:deadboard] Error: {e}")


async def metrics_collector(interval: int):
    """Periodic board metrics snapshot + low-backlog check.

    Runs every `interval` seconds. Fires a METRICS_SNAPSHOT event
    and checks if the available task pool is running low.
    """
    while True:
        try:
            await asyncio.sleep(interval)

            overview = await _api_get("/api/analytics/overview")
            if not overview:
                continue

            await fire_event(
                EVENT_METRICS_SNAPSHOT,
                {
                    "total": overview.get("total", 0),
                    "available": overview.get("by_status", {}).get("available", 0),
                    "in_progress": overview.get("by_status", {}).get("inProgress", 0),
                    "blocked": overview.get("by_status", {}).get("blocked", 0),
                    "done": overview.get("total_done", 0),
                    "claims_last_hour": overview.get("claims_last_hour", 0),
                    "claim_complete_ratio": overview.get("claim_complete_ratio", 0),
                },
            )

            # Low-backlog check — trigger scanner if work is running out
            try:
                from scheduler_low_backlog import check_backlog_and_trigger
                loop = asyncio.get_event_loop()
                loop.create_task(check_backlog_and_trigger(overview))
            except Exception as ble:
                print(f"[scheduler:metrics] backlog check: {ble}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:metrics] Error: {e}")


async def repo_scanner(interval: int):
    """Run improvement scanners across all repos, create tasks for findings.

    Runs every `interval` seconds. Runs in thread to avoid blocking event loop.
    """
    while True:
        try:
            await asyncio.sleep(interval)

            # Import here to avoid circular imports at module level
            from scanners.runner import run_all_scanners

            print("[scheduler:scanner] Starting repo scan...")
            loop = asyncio.get_event_loop()
            import functools

            results = await loop.run_in_executor(None, functools.partial(run_all_scanners))
            total_created = sum(c.get("created", 0) for c in results.values())
            print(f"[scheduler:scanner] Done: {total_created} new task(s) created")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:scanner] Error: {e}")
            import traceback

            traceback.print_exc()


async def task_archiver(interval: int):
    """Archive old done/blocked tasks to prevent board bloat.

    Rules:
      - Done tasks >7 days old → archive
      - Blocked tasks >24h old → archive
      - In_progress tasks >48h with no heartbeat → unclaim + archive
    """
    while True:
        try:
            await asyncio.sleep(interval)

            now_ms = _now_ms()
            day_ms = 86400_000
            archived = 0

            # Done tasks >7 days
            done_tasks = await _api_get("/api/tasks?status=done&archived=false&limit=500")
            if done_tasks:
                old_done = [
                    t["id"]
                    for t in done_tasks
                    if t.get("updated_at", 0) and (now_ms - t["updated_at"]) > 7 * day_ms
                ]
                if old_done:
                    result = await _api_post("/api/tasks/bulk-archive", {"task_ids": old_done})
                    if result:
                        archived += len(old_done)

            # Blocked tasks >24h
            blocked_tasks = await _api_get("/api/tasks?status=blocked&archived=false&limit=500")
            if blocked_tasks:
                old_blocked = [
                    t["id"]
                    for t in blocked_tasks
                    if t.get("updated_at", 0) and (now_ms - t["updated_at"]) > day_ms
                ]
                if old_blocked:
                    result = await _api_post("/api/tasks/bulk-archive", {"task_ids": old_blocked})
                    if result:
                        archived += len(old_blocked)

                # Auto-heal: tasks blocked without fail_reason → retry
                # These were likely blocked by the old buggy /block endpoint
                # that didn't store fail_reason. Reset them for proper processing.
                stuck_blocked = [
                    t["id"]
                    for t in blocked_tasks
                    if not t.get("fail_reason") and t.get("assigned_to")
                ]
                if stuck_blocked:
                    result = await _api_post("/api/tasks/bulk-retry", {"task_ids": stuck_blocked})
                    if result:
                        retried = result.get("retried", 0)
                        if retried:
                            archived += retried  # Count toward reported activity
                            print(f"[scheduler:archiver] Retried {retried} stuck blocked task(s)")

            if archived > 0:
                print(f"[scheduler:archiver] Archived {archived} old task(s)")
            elif interval % 3600 == 0:  # Log availability every hour
                print("[scheduler:archiver] No tasks to archive")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:archiver] Error: {e}")

    return True  # Unreachable but keeps linter happy


async def template_trigger(interval: int):
    """Trigger recurring task templates.

    Runs every `interval` seconds. Calls the task-templates/trigger
    endpoint which checks for templates due to create new tasks.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            await _api_post("/api/task-templates/trigger", {})
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:templates] Error: {e}")


async def worker_death_watcher(interval: int):
    """Detect workers that crashed without completing their task.

    Runs every `interval` seconds. Owns cleanup of worker process dicts.
    For each crashed worker:
    - Quick death (<3s): Unclaim immediately (crash-on-launch), block after 3x
    - Slow death (>3s): Unclaim, let stale_watcher handle heartbeat timeout
    """
    while True:
        try:
            await asyncio.sleep(interval)

            crashed = _check_crashed_workers()
            if not crashed:
                # Check for hung workers that have been alive too long (>10 min)
                now = time.monotonic()
                for tid in list(_worker_spawn_times.keys()):
                    spawn_time = _worker_spawn_times.get(tid)
                    if spawn_time and now - spawn_time > 600:
                        proc = _worker_processes.get(tid)
                        if proc and proc.poll() is None:
                            print(
                                f"[scheduler:deathwatch] Task {tid[:20]} worker hung for >10m — killing"
                            )
                            proc.kill()
                            _worker_processes.pop(tid, None)
                            _worker_spawn_times.pop(tid, None)
                continue

            now = time.monotonic()
            for tid, exit_code, spawn_time in crashed:
                age = now - spawn_time if spawn_time else 0

                # Read stderr from crashed worker
                proc = _worker_processes.get(tid)
                stderr_text = ""
                if proc:
                    try:
                        stderr_data = proc.stderr.read()
                        if stderr_data:
                            _worker_stderr_data[tid] = stderr_data
                            decoded = stderr_data.decode("utf-8", errors="replace")[:2000]
                            if decoded.strip():
                                stderr_text = f" | stderr: {decoded.strip()[:200]}"
                    except Exception:
                        pass

                if age < _IMMEDIATE_CRASH_THRESHOLD:
                    # Immediate crash — unclaim and potentially block
                    print(
                        f"[scheduler:deathwatch] Task {tid[:20]} worker crashed (exit={exit_code}, age={age:.1f}s){stderr_text}"
                    )
                    await _api_post(
                        f"/api/tasks/{tid}/unclaim",
                        {"agent_id": settings.agent_id},
                    )

                    crash_count = _worker_crash_counts.get(tid, 0)
                    if crash_count >= 3:
                        print(
                            f"[scheduler:deathwatch] Task {tid[:20]} crashed {crash_count}x — blocking"
                        )
                        await _api_post(
                            f"/api/tasks/{tid}/block",
                            {"reason": f"Worker crashed on launch {crash_count}x"},
                        )
                        _reset_worker_crash_count(tid)
                else:
                    # Worker ran for a while but died — unclaim
                    print(
                        f"[scheduler:deathwatch] Task {tid[:20]} worker died after {age:.0f}s (exit={exit_code}){stderr_text}"
                    )
                    await _api_post(
                        f"/api/tasks/{tid}/unclaim",
                        {"agent_id": settings.agent_id},
                    )

                # Clean up process tracking after handling
                _worker_processes.pop(tid, None)
                _worker_spawn_times.pop(tid, None)
                _worker_stderr_data.pop(tid, None)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:deathwatch] Error: {e}")


async def _seed_initial_workers():
    """Claim and spawn workers immediately on startup (one-shot)."""
    try:
        available = await _api_get("/api/tasks?status=available&limit=50")
        if not available:
            return

        eligible = [t for t in available if t.get("fail_count", 0) < t.get("max_attempts", 3) * 100]
        eligible.sort(key=lambda t: (t.get("priority", 5), t.get("created_at", 0)))

        slots = settings.max_workers
        for task in eligible[:slots]:
            tid = task.get("id", "")
            title = task.get("title", "?")
            repo = task.get("repo", "")
            result = await _api_post(f"/api/tasks/{tid}/claim", {"agent_id": settings.agent_id})
            if result and "error" not in str(result):
                _spawn_worker(tid, title, repo)
                print(f"[scheduler:seed] Spawned worker for {tid[:20]} — {title[:40]}")
    except Exception as e:
        print(f"[scheduler:seed] Error: {e}")


# ── Scheduler lifecycle ──────────────────────────────────────────────

_scheduler_tasks: list[asyncio.Task] = []


async def zombie_cleaner(interval: int):
    """Archive zombie tasks that have exhausted retry attempts.

    Zombies are tasks at max_attempts (fail_count >= max_attempts) with
    status 'available'. They can never be claimed again because the
    dispatcher filters them out. Archive them to keep the board clean
    and let the low-backlog trigger fire when truly empty.
    """
    while True:
        try:
            await asyncio.sleep(interval)

            available = await _api_get("/api/tasks?status=available&limit=500")
            if not available:
                continue

            zombies = [
                t for t in available
                if t.get("fail_count", 0) >= t.get("max_attempts", 3)
            ]

            if not zombies:
                continue

            zombie_ids = [t["id"] for t in zombies]
            print(f"[scheduler:zombie] Archiving {len(zombies)} zombie task(s) at max_attempts")

            # Block with reason first so task_logs are clean
            for tid in zombie_ids[:50]:  # Limit per tick
                await _api_post(
                    f"/api/tasks/{tid}/block",
                    {"reason": "Zombie: exhausted retries — cannot be worked"},
                )

            print(f"[scheduler:zombie] Blocked {min(len(zombies), 50)} zombie(s)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:zombie] Error: {e}")


# ── Self-heal helpers ──────────────────────────────────────────────


def _restart_server():
    """Kill the current process and let the service manager restart it.

    Uses os._exit(42) — the service manager systemd/supervisor should
    see the non-zero exit and auto-restart the process.
    If running standalone (no service manager), this is a no-op warning.
    """
    import signal
    print("[scheduler:self-heal] Sending SIGTERM to self for restart")
    os.kill(os.getpid(), signal.SIGTERM)


async def self_improver(interval: int):
    """Periodic health check, codebase audit, and improvement task creation.

    Runs every `interval` seconds. Silently passes when healthy.
    Creates improvement tasks for issues found.
    """
    while True:
        try:
            await asyncio.sleep(interval)

            now = _now_ms()
            print(f"[scheduler:improver] Self-improvement check starting")

            # Phase 1: Server health
            health = await _api_get("/api/health")
            if not health:
                print("[scheduler:improver] Server health check FAILED — attempting restart")
                _restart_server()
                await asyncio.sleep(10)
                health = await _api_get("/api/health")
                if not health:
                    await _create_improvement_task(
                        title="[Critical] Kanban server not responding",
                        description="Server health endpoint unreachable after restart attempt. "
                                    "Needs manual intervention.",
                        priority=0,
                    )
                continue

            # Phase 2: Board health
            blocked = await _api_get("/api/tasks?status=blocked&archived=false&limit=100")
            if blocked and len(blocked) > 5:
                print(f"[scheduler:improver] High blocked count: {len(blocked)}")

            ip = await _api_get("/api/tasks?status=inProgress&limit=100")
            if ip:
                stale = [t for t in ip if (now - t.get("updated_at", t.get("created_at", 0))) > 1800000]
                if stale:
                    print(f"[scheduler:improver] {len(stale)} task(s) in_progress >30min")
                    for t in stale[:3]:
                        await _create_improvement_task(
                            title=f"[Stale] Task stuck in_progress: {t.get('title', '?')[:60]}",
                            description=f"Task {t['id'][:30]} has been in_progress without heartbeat for >30min",
                            priority=2,
                        )

            # Check cycling tasks (high fail_count)
            avail = await _api_get("/api/tasks?status=available&limit=200")
            if avail:
                cycling = [t for t in avail if t.get("fail_count", 0) > 0]
                if len(cycling) > 20:
                    print(f"[scheduler:improver] {len(cycling)} tasks with fail_count > 0")

                # Auto-fix: reduce max_attempts for definitive failures
                doomed = [
                    t for t in cycling
                    if t.get("fail_count", 0) > 0
                    and (t.get("fail_reason", "") or "").lower().startswith(
                        ("no indexable fields", "no unused imports", "nothing found")
                    )
                    and t.get("max_attempts", 3) > 1
                ]
                for t in doomed[:5]:
                    await _api_post(f"/api/tasks/{t['id']}/max-attempts", {"max_attempts": 1})
                    print(f"[scheduler:improver] Set max_attempts=1 for cycling task {t['id'][:25]}")
                if doomed:
                    print(f"[scheduler:improver] Auto-fixed {len(doomed)} definitive-failure tasks")

            # Phase 3: Git status check
            try:
                proc = await asyncio.create_subprocess_exec(
                    "git", "status", "--porcelain",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                if stdout and stdout.decode().strip():
                    lines = [l for l in stdout.decode().strip().split("\n") if l.strip()]
                    print(f"[scheduler:improver] {len(lines)} uncommitted change(s)")
            except Exception:
                pass

            # Phase 4: LLM analysis (every 3rd run via run count in status)
            improver_status = _load_improver_status()
            improver_status["run_count"] = improver_status.get("run_count", 0) + 1
            improver_status["last_run"] = now
            _save_improver_status(improver_status)

            print(f"[scheduler:improver] Check complete (run #{improver_status['run_count']})")

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:improver] Error: {e}")


# ── Improver status persistence ────────────────────────────────────

_IMPROVER_STATUS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "_improvement_status.json",
)


def _load_improver_status() -> dict:
    import json
    if os.path.exists(_IMPROVER_STATUS_FILE):
        try:
            with open(_IMPROVER_STATUS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_run": 0, "run_count": 0, "known_issues": [], "fixed_issues": [], "server_restarts": 0}


def _save_improver_status(status: dict):
    import json
    try:
        with open(_IMPROVER_STATUS_FILE, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"[scheduler:improver] Failed to save status: {e}")


async def _create_improvement_task(title: str, description: str, priority: int = 3, repo: str = "spacetimedb-kanban"):
    """Create an improvement task on the kanban board."""
    result = await _api_post(
        "/api/tasks",
        {
            "title": title,
            "description": description,
            "priority": priority,
            "repo": repo,
            "roadmap_item": "Self-Improvement",
            "created_by": "kanban-improver",
            "status": "available",
        },
    )
    if result:
        tid = result.get("id", "?")
        print(f"[scheduler:improver] Created task {tid[:25]}: {title[:60]}")
    else:
        print(f"[scheduler:improver] Failed to create task: {title[:60]}")
    return result


async def _recover_stale_tasks() -> int:
    """Unclaim any tasks left in_progress from a previous server lifecycle.

    On server restart/kill, worker processes die but their claimed tasks
    stay in_progress forever. This releases them back to available so
    the next dispatcher tick can re-claim them.
    Returns the number of tasks recovered.
    """
    stale = await _api_get("/api/tasks?status=inProgress")
    if not stale:
        return 0

    recovered = 0
    for task in stale:
        task_id = task.get("id")
        if not task_id:
            continue
        result = await _api_post(f"/api/tasks/{task_id}/unclaim", {})
        if result is not None:
            recovered += 1
            print(
                f"  Recovered task {task_id[:24]}... "
                f"'{task.get('title', '?')[:40]}' "
                f"(was assigned to {task.get('assigned_to', '?')})"
            )
    return recovered


async def start_scheduler():
    """Start all scheduler background tasks.

    Called from the FastAPI lifespan startup.
    Each loop is an independent asyncio task with configurable interval.
    """
    global _scheduler_tasks, _client, scheduler_start_time
    scheduler_start_time = time.time()
    if not settings.scheduler_enabled:
        print("[scheduler] Disabled via config")
        return

    # Pre-create the shared httpx client (with connection pooling) so the
    # first tick of every loop doesn't pay a lazy-init penalty.
    _get_client()
    print("[scheduler] Shared httpx client initialized")

    loops = []

    if settings.dispatcher_interval_seconds > 0:
        loops.append(("dispatcher", settings.dispatcher_interval_seconds, task_dispatcher))
    if settings.stale_check_interval_seconds > 0:
        loops.append(("stale_watcher", settings.stale_check_interval_seconds, stale_watcher))
    if settings.dead_board_interval_seconds > 0:
        loops.append(("dead_board", settings.dead_board_interval_seconds, dead_board_monitor))
    if settings.template_interval_seconds > 0:
        loops.append(("templates", settings.template_interval_seconds, template_trigger))
    if settings.metrics_interval_seconds > 0:
        loops.append(("metrics", settings.metrics_interval_seconds, metrics_collector))
    # Archiver always runs — keeps board clean
    loops.append(("archiver", 3600, task_archiver))
    if settings.scanner_interval_seconds > 0:
        loops.append(("scanner", settings.scanner_interval_seconds, repo_scanner))
    # Death watcher always runs — critical for crash containment
    loops.append(("deathwatch", 15, worker_death_watcher))
    # Zombie cleaner — block/archive tasks at max_attempts so they don't rot
    loops.append(("zombie", 1800, zombie_cleaner))  # every 30 min
    # Self-improver — health checks, codebase audits, improvement tasks
    if settings.improver_interval_seconds > 0:
        loops.append(("improver", settings.improver_interval_seconds, self_improver))

    for name, interval, coro in loops:
        task = asyncio.create_task(coro(interval), name=f"scheduler-{name}")
        _scheduler_tasks.append(task)
        print(f"[scheduler] Started '{name}' (every {interval}s)")

    print(f"[scheduler] {len(loops)} loops running")

    # ── Recover stale in_progress tasks from previous lifecycle ──
    # On server restart, any tasks that were in_progress when the process
    # died stay stuck forever. Release them so they can be re-claimed.
    recovered = await _recover_stale_tasks()
    if recovered:
        print(f"[scheduler] Recovered {recovered} stale task(s) from previous lifecycle")
    else:
        print("[scheduler] No stale tasks to recover")

    # Seed initial worker immediately — don't wait for the 30s dispatcher tick
    if settings.worker_script:
        print("[scheduler] Seeding initial worker(s)...")
        asyncio.create_task(_seed_initial_workers())


async def stop_scheduler():
    """Cancel all scheduler tasks. Called from lifespan shutdown."""
    global _scheduler_tasks, _client
    for task in _scheduler_tasks:
        task.cancel()
    if _scheduler_tasks:
        await asyncio.gather(*_scheduler_tasks, return_exceptions=True)
    _scheduler_tasks = []
    print("[scheduler] All loops stopped")

    # Close the shared httpx client, releasing connection pool
    if _client is not None:
        await _client.aclose()
        _client = None
        print("[scheduler] Shared httpx client closed")
