#!/usr/bin/env python3
"""Kanban watchdog: auto-releases stale claimed tasks.

Runs every 5 minutes via cron. Checks for tasks that have been
in_progress for >STALE_THRESHOLD_MINUTES with no activity.
Auto-releases them back to available and logs the event.

HTTP 409/404 on release is expected (concurrent unclaim) — silently ignored.
"""

import os
import sys
import time

import httpx

API_BASE = os.environ.get("KANBAN_API_BASE", "http://localhost:8727")
STALE_THRESHOLD_MINUTES = int(os.environ.get("STALE_THRESHOLD_MINUTES", "30"))
SILENT_IF_EMPTY = os.environ.get("SILENT_IF_EMPTY", "1") == "1"


def now_ms() -> int:
    return int(time.time() * 1000)


def main():
    try:
        r = httpx.get(f"{API_BASE}/api/tasks?status=in_progress", timeout=10)
        r.raise_for_status()
        tasks = r.json()
    except Exception as e:
        print(f"❌ WATCHDOG ERROR: could not fetch tasks: {e}")
        sys.exit(1)

    if not tasks:
        if not SILENT_IF_EMPTY:
            print("✓ No in_progress tasks — nothing to do")
        return

    now = now_ms()
    released = []
    errors = []

    for t in tasks:
        updated_at = t.get("updated_at", 0)
        age_minutes = (now - updated_at) / 60000
        if age_minutes < STALE_THRESHOLD_MINUTES:
            continue

        task_id = t["id"]
        title = t.get("title", "?")
        agent = t.get("assigned_to", "unknown")

        try:
            r = httpx.post(
                f"{API_BASE}/api/tasks/{task_id}/unclaim",
                timeout=10,
            )
            if r.status_code == 200:
                released.append((task_id, title, agent, age_minutes))
                print(
                    f'  RELEASED: {task_id[:20]} "{title}" (agent={agent}, age={age_minutes:.0f}m)'
                )
            elif r.status_code in (409, 404):
                # Concurrent unclaim or task already gone — not an error
                pass
            else:
                errors.append(f"  {r.status_code} for {task_id[:20]}: {r.text[:80]}")
        except Exception as e:
            errors.append(f"  EXCEPTION for {task_id[:20]}: {e}")

    if errors:
        print("⚠ WATCHDOG PARTIAL: some releases had issues")
        for err in errors:
            print(err)
        sys.exit(1)

    if not released and not SILENT_IF_EMPTY:
        print(f"✓ All {len(tasks)} in_progress tasks are active (under {STALE_THRESHOLD_MINUTES}m)")


if __name__ == "__main__":
    main()
