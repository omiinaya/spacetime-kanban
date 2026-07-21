#!/usr/bin/env python3
"""Kanban worker entry point — spawned by the scheduler for each claimed task.

Usage:
    python3 -m server.workers.run <task_id>

The script:
  1. Loads task details from the kanban API
  2. Matches task title against mechanical handler patterns
  3. If matched → runs the mechanical handler (no LLM cost)
  4. If unmatched → runs the LLM-driven worker (hermes chat -q)
  5. Reports completion or block via the kanban API

Environment variables:
    KANBAN_API      — base URL for the kanban API (default: http://localhost:8727)
    AGENT_ID        — agent identity (default: hermes)
    KANBAN_LLM_WORKER — LLM command (default: hermes chat -q)
"""
import sys
import os

# Ensure the server package is on the path
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.dirname(script_dir)
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from server.workers.base import WorkerContext, run_worker
from server.workers.mechanical import match_handler
from server.workers.llm import run_llm_worker


def route_task(ctx: WorkerContext) -> tuple[bool, str]:
    """Route a task to the right worker based on its title.

    Returns (success, message) like all handlers.
    """
    title = ctx.title
    repo = ctx.repo

    # Step 1: Check mechanical handlers
    handler = match_handler(title)
    if handler:
        ctx.add_log("worker_routed", f"Mechanical handler: {handler.__name__}")
        print(f"[worker] Routing to mechanical handler: {handler.__name__}", file=sys.stderr)
        return handler(ctx)

    # Step 2: Fall back to LLM worker
    ctx.add_log("worker_routed", "LLM worker (no mechanical pattern matched)")
    print(f"[worker] Routing to LLM worker (no mechanical pattern matched)", file=sys.stderr)
    return run_llm_worker(ctx)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m server.workers.run <task_id>", file=sys.stderr)
        sys.exit(2)

    task_id = sys.argv[1]
    exit_code = run_worker(task_id, route_task)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
