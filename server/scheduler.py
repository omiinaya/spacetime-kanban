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
  dead_board_monitor  :900s — detect zero-throughput, fire webhook
  metrics_collector   :300s — board metrics snapshot, fire webhook
  template_trigger    :900s — fire recurring task templates
"""

import asyncio
import json
import os
import signal
import subprocess
import time
from datetime import datetime
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


async def _api_get(path: str, timeout: float = 15) -> Any:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{API_BASE}{path}")
            if resp.status_code == 200:
                return resp.json()
        return None
    except Exception:
        return None


async def _api_post(path: str, data: dict, timeout: float = 15) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{API_BASE}{path}", json=data)
            if resp.status_code < 500:
                return resp.json() if resp.content else {"status": "ok"}
        return None
    except Exception:
        return None


async def _api_delete(path: str, timeout: float = 15) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.delete(f"{API_BASE}{path}")
            return resp.status_code == 200
    except Exception:
        return False


def _now_ms() -> int:
    return int(time.time() * 1000)


# ── Worker process management ───────────────────────────────────────

_worker_processes: dict[str, subprocess.Popen] = {}  # task_id -> Popen


def _spawn_worker(task_id: str, title: str, repo: str) -> bool:
    """Spawn a worker subprocess for a claimed task.

    Returns True if spawned successfully.
    Returns False if no worker is configured (manual mode — just manage lifecycle).
    """
    if not settings.worker_script:
        return False  # No worker configured — manual/dispatcher-disabled mode

    try:
        proc = subprocess.Popen(
            [settings.worker_command, settings.worker_script, "--repo", repo],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _worker_processes[task_id] = proc
        return True
    except Exception as e:
        print(f"[scheduler] Failed to spawn worker for {task_id[:20]}: {e}")
        return False


def _get_worker_count() -> int:
    """Count live worker processes."""
    alive = 0
    dead = []
    for tid, proc in _worker_processes.items():
        if proc.poll() is None:
            alive += 1
        else:
            dead.append(tid)
    for tid in dead:
        _worker_processes.pop(tid, None)
    return alive


def _kill_worker(task_id: str) -> bool:
    """Kill a worker process."""
    proc = _worker_processes.pop(task_id, None)
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

            # Filter out doomed and backoff tasks
            eligible = [
                t
                for t in available
                if t.get("fail_count", 0) < t.get("max_attempts", 3) and not t.get("fail_reason")
            ]

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

            in_progress = await _api_get("/api/tasks?status=in_progress&limit=500")
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
    """Detect zero-throughput board and fire webhook alert.

    Runs every `interval` seconds. Checks if board has 0 completions
    in the last hour while tasks exist and workers are running.
    """
    last_alert_ms = 0
    alert_cooldown_ms = 3600_000  # Don't re-alert within 1 hour

    while True:
        try:
            await asyncio.sleep(interval)

            overview = await _api_get("/api/analytics/overview")
            if not overview:
                continue

            completions = overview.get("completions_last_hour", 0)
            claims = overview.get("claims_last_hour", 0)
            ip = overview.get("by_status", {}).get("in_progress", 0)
            avail = overview.get("by_status", {}).get("available", 0)

            now_ms = _now_ms()

            # Check: 0 completions + work exists
            if completions == 0 and (ip > 0 or avail > 0):
                if now_ms - last_alert_ms > alert_cooldown_ms:
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
            if ratio > 20 and claims > 50 and completions == 0:
                if now_ms - last_alert_ms > alert_cooldown_ms:
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
    """Collect board metrics and fire periodic snapshot webhook.

    Runs every `interval` seconds. Fires a METRICS_SNAPSHOT event
    so configured webhooks (Discord, etc.) get periodic status updates.
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
                    "in_progress": overview.get("by_status", {}).get("in_progress", 0),
                    "blocked": overview.get("by_status", {}).get("blocked", 0),
                    "done": overview.get("total_done", 0),
                    "completions_last_hour": overview.get("completions_last_hour", 0),
                    "claims_last_hour": overview.get("claims_last_hour", 0),
                    "claim_complete_ratio": overview.get("claim_complete_ratio", 0),
                },
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler:metrics] Error: {e}")


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


# ── Scheduler lifecycle ──────────────────────────────────────────────

_scheduler_tasks: list[asyncio.Task] = []


async def start_scheduler():
    """Start all scheduler background tasks.

    Called from the FastAPI lifespan startup.
    Each loop is an independent asyncio task with configurable interval.
    """
    global _scheduler_tasks
    if not settings.scheduler_enabled:
        print("[scheduler] Disabled via config")
        return

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

    for name, interval, coro in loops:
        task = asyncio.create_task(coro(interval), name=f"scheduler-{name}")
        _scheduler_tasks.append(task)
        print(f"[scheduler] Started '{name}' (every {interval}s)")

    print(f"[scheduler] {len(loops)} loops running")


async def stop_scheduler():
    """Cancel all scheduler tasks. Called from lifespan shutdown."""
    global _scheduler_tasks
    for task in _scheduler_tasks:
        task.cancel()
    if _scheduler_tasks:
        await asyncio.gather(*_scheduler_tasks, return_exceptions=True)
    _scheduler_tasks = []
    print("[scheduler] All loops stopped")
