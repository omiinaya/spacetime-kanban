# Claude — Kanban Workflow

This repo has a **shared kanban board** on SpacetimeDB that coordinates agents working on the same roadmap. Before starting any work, **always check the kanban first**.

## Quickstart

```bash
# 1. See what's available
curl -s http://localhost:8725/api/tasks?status=available | python3 -m json.tool

# 2. Claim a task (atomically — fails if another agent already grabbed it)
curl -s -X POST http://localhost:8725/api/tasks/{task_id}/claim \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "claude-vscode"}'

# 3. Work → create a branch referencing the task
git checkout -b "feature/kanban-${TASK_ID}--my-feature"

# 4. Complete
curl -s -X POST http://localhost:8725/api/tasks/{task_id}/complete \
  -H 'Content-Type: application/json' \
  -d '{"result_notes": "Implemented + tests passed"}'

curl -s -X PATCH http://localhost:8725/api/tasks/{task_id} \
  -H 'Content-Type: application/json' \
  -d "{\"branch\": \"$(git branch --show-current)\"}"
```

## Atomic Claim

- `POST /api/tasks/{id}/claim` with `{"agent_id": "claude-vscode"}`
- **200 OK** → you own it. Start working.
- **409 Conflict** → already taken. Pick the next available task.
- This is enforced at the SpacetimeDB reducer level — STDB processes reducers sequentially, so two concurrent claims can't both succeed.

## Branch Convention

```
{type}/kanban-{task_id}--{slug}
```

Examples: `feature/kanban-task_1748397912_abc12345--doh-fallback`, `fix/kanban-task_1748397913_abc12345--auth-bug`

Validate with: `python3 bin/check-branch <branch-name>`

## State Machine

```
available → claim → in_progress → complete → done
in_progress → block → blocked → unclaim → available
in_progress → unclaim → available
```

## Stale Task Watchdog

A cron auto-releases tasks stuck `in_progress` for >30 minutes. If you're actively working on something long-running, update the task's branch field or description periodically to bump `updated_at`.

## Full API Reference

See [AGENTS.md](AGENTS.md) for the complete API: creating tasks, listing by repo/status, activity logs, agent listing, and all endpoint details.

## Agent Identity

Use `claude-vscode` as your agent_id when claiming tasks.
