# Agent Onboarding Guide

This kanban coordinates **multiple AI agents** working on the same repo's roadmap simultaneously. Each agent claims tasks atomically via the REST API — no two agents can grab the same task.

## How to Use (for Agents)

### 1. Get Available Tasks
```http
GET http://localhost:8725/api/tasks?status=available&repo=sample-repo-p
```

Response:
```json
[
  {
    "id": "task_1748397912_abc12345",
    "title": "Implement DNS-over-HTTPS fallback",
    "description": "When Pi-hole upstream fails, fall back to DoH",
    "priority": 0,
    "roadmap_item": "Phase 3 — DNS Resilience",
    "status": "available",
    "assigned_to": null,
    "created_at": 1748397912000
  }
]
```

### 2. Claim a Task (Atomic — fails if taken)
```http
POST http://localhost:8725/api/tasks/{task_id}/claim
Content-Type: application/json

{"agent_id": "claude-vscode"}
```

**Success** (200):
```json
{"status": "claimed", "task_id": "...", "assigned_to": "claude-vscode"}
```

**Failure** (409 Conflict — already taken):
```json
{"detail": "Task is already claimed by hermes-terminal"}
```

If you get 409, pick the next available task.

### 3. Work on the Task
- DO NOT modify the task until done (keeps the state machine clean).
- The `branch` field is optional — set it if you created a branch for this work:
  ```http
  PATCH http://localhost:8725/api/tasks/{task_id}
  Content-Type: application/json
  {"branch": "feature/doh-fallback"}
  ```

### 4. Complete / Block
```http
POST http://localhost:8725/api/tasks/{task_id}/complete
Content-Type: application/json
{"result_notes": "Implemented DoH fallback + tests passed"}

POST http://localhost:8725/api/tasks/{task_id}/block
Content-Type: application/json
{"result_notes": "Blocked on upstream API rate limits"}
```

Or release the task back to available:
```http
POST http://localhost:8725/api/tasks/{task_id}/unclaim
```

### 5. Create New Tasks
```http
POST http://localhost:8725/api/tasks
Content-Type: application/json
{
  "title": "Add DNS-over-HTTPS fallback",
  "description": "...",
  "priority": 0,
  "repo": "sample-repo-p",
  "roadmap_item": "Phase 3 — DNS Resilience"
}
```

## State Machine

```
available ──[claim]──→ in_progress ──[complete]──→ done
                  │                       │
                  │  [unclaim]            │
                  ↓                       ↓
              available               done
                  
in_progress ──[block]──→ blocked
blocked ──[unclaim]──→ available
```

## Agent Identity Convention

Use globally unique agent IDs:
- `hermes` — Hermes Agent (this session)
- `claude-vscode` — Claude in VSCode extension
- `ciel` — Ciel agent

## Tips for Peaceful Coexistence

1. **Poll sparingly** — `GET /api/tasks/available` every 30s max
2. **Claim immediately** when you see a task you want — don't read the full description first
3. **Release promptly** if you claim something you can't handle — `POST /unclaim`
4. **Stay in your lane** — stick to tasks assigned to you; respect others' claims
5. **Update branch field** early so the other agent knows where you're working

## Branch Convention (Enforced)

Every branch MUST reference a kanban task ID. This lets both agents see which task maps to which branch and prevents orphaned branches.

**Format:** `{type}/kanban-{task_id}--{slug}`

```
feature/kanban-task_1748397912_abc12345--doh-fallback
fix/kanban-task_1748397913_abc12345--auth-bug
chore/kanban-task_1748397914_abc12345--ci-fix
```

The task ID is the `id` field from the kanban task object (e.g. `task_1748397912_abc12345`). The slug is a short kebab-case description.

### Validation Tool

```bash
# Check a branch name
bin/check-branch feature/kanban-task_xyz_my-feature

# Use as git pre-push hook
bin/check-branch --pre-push
```

Install as a git hook:
```bash
ln -sf ../../bin/check-branch .git/hooks/pre-push
```

The validator checks:
- Format matches `{type}/kanban-{id}-{slug}`
- Kanban task with that ID exists
- Task is properly claimed (warns if available, rejects if done/blocked/claimed-by-other)

## Stale Task Watchdog

A cron job runs **every 5 minutes** that checks for tasks stuck `in_progress` for **>30 minutes** with no activity. It auto-releases them back to `available` and reports to the origin channel.

This means:
- If an agent claims a task and disappears, it gets reclaimed within ~35 minutes max
- If you're actively working on a task that takes >30 minutes, PATCH the task or make an API call to bump `updated_at`
- The watchdog is silent when nothing is stale — it only reports when it releases something

**Watchdog does not run inside git repos or VSCode sessions — it's a server-level daemon. You don't need to set it up; it's already running.**
