"""Kanban System Improvements — patches applied to kanban-dispatcher.py

This consolidates all fundamental fixes into one document.

=== ISSUE 1: main() crashes silently on ANY Python error ===
- Wrapped main() in try/except that logs to BOTH log file and stderr
- The cron sees exit code 1 but had no way to surface the error
- Fix: main() always exits cleanly, errors are captured and logged

=== ISSUE 2: Worker crashes have no diagnostic data ===
- Added stderr capture pipe for worker subprocesses (not DEVNULL)
- When a worker has non-zero exit, log its last 2KB of stderr
- Fix: workers that crash leave breadcrumbs

=== ISSUE 3: Stale tasks can block the pipeline forever ===
- Added force-unclaim for tasks >60min old that uses DELETE as last resort
- The 2011-minute task was stuck because unclaim returned "not found"
- Fix: if normal unclaim fails, try block-with-reason, then DELETE

=== ISSUE 4: Dispatcher has no health monitoring ===
- Added heartbeat file written every tick with timestamp + worker count
- Added dead-dispatcher cron that alerts if no heartbeat >3min

=== ISSUE 5: Pool is static — wastes slots when few tasks ===
- Added adaptive MIN_WORKERS: min(fixed_min, available_tasks * 0.8)
- Prevents spawning 24 workers when only 10 tasks exist
- Still respects MAX_WORKERS and memory guard

=== ISSUE 6: No completion signaling ===
- Added repo completion milestone detection in telemetry
- Logs when a repo crosses 50%, 80%, 95%, 100% thresholds
"""

# The key architectural insight:
# The dispatcher is the CENTRAL NERVOUS SYSTEM of the kanban.
# It MUST be:
#   1. Crash-proof (try/except everything)
#   2. Observable (log ALL state changes)
#   3. Self-healing (auto-fix stale state)
#   4. Health-checkable (heartbeat for external monitoring)
# 
# Workers are CONSUMABLES. They will crash, OOM, timeout.
# The system should assume workers die and plan for it.
