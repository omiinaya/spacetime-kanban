# Claude — Kanban Workflow

**First, read [AGENTS.md](./AGENTS.md)** — the full agent guide with API reference, state machine, and task lifecycle.

This project uses a **shared kanban board** at `localhost:8727` to coordinate agents working on the same roadmap. Before starting any work, **always check the kanban first**.

The `kanban` CLI tool handles all interactions. Install it from the `spacetime-kanban` repo:

```bash
git clone https://github.com/omiinaya/spacetime-kanban.git
cd spacetime-kanban
bash install.sh
```

## Quickstart

```bash
# 1. See what's available
kanban list --status=available

# 2. Claim a task (atomically — fails if another agent already grabbed it)
kanban claim <task-id>

# 3. Work → create a branch referencing the task
git checkout -b "feature/kanban-${TASK_ID}--my-feature"

# 4. Complete
kanban complete <task-id> --notes="Implemented + tests passed"
```

## Atomic Claim

- `kanban claim <task-id>` — 200 OK = yours, 409 = already taken, pick next
- STDB reducers process sequentially — two concurrent claims can't both succeed

## Branch Convention

```
{type}/kanban-{task_id}--{slug}
```

Examples: `feature/kanban-task_1748397912_abc12345--doh-fallback`, `fix/kanban-task_1748397913_abc12345--auth-bug`

Validate with: `kanban check-branch`

## Stale Task Watchdog

The server-side scheduler releases tasks stuck `in_progress` for >45 minutes (default `STALE_MINUTES`) without a heartbeat. If working on something long-running, send a heartbeat:

```bash
curl -s -X POST http://localhost:8727/api/agents/claude-vscode/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "claude-vscode", "status": "busy", "current_task_id": "<task-id>"}'
```

On server restart, `_recover_stale_tasks()` immediately unclaims any `in_progress` tasks so nothing gets permanently stuck.

## Full Reference

See `SETUP.md` in the `spacetime-kanban` repo for installation, configuration, and hook setup.

## Agent Identity

Uses `claude-vscode` as agent_id. Set via:
```bash
export KANBAN_AGENT_ID=claude-vscode
```
