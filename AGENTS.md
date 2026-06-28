# Agent Onboarding Guide

This kanban coordinates **multiple AI agents** working on the same repo's roadmap simultaneously. Each agent claims tasks atomically via the REST API — no two agents can grab the same task.

## How to Use (for Agents)

### 1. Get Available Tasks
```http
GET http://localhost:8727/api/tasks?status=available&repo=sample-repo-p
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
POST http://localhost:8727/api/tasks/{task_id}/claim
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
  PATCH http://localhost:8727/api/tasks/{task_id}
  Content-Type: application/json
  {"branch": "feature/doh-fallback"}
  ```

### 4. Complete / Block
```http
POST http://localhost:8727/api/tasks/{task_id}/complete
Content-Type: application/json
{"result_notes": "Implemented DoH fallback + tests passed"}

POST http://localhost:8727/api/tasks/{task_id}/block
Content-Type: application/json
{"result_notes": "Blocked on upstream API rate limits"}
```

Or release the task back to available:
```http
POST http://localhost:8727/api/tasks/{task_id}/unclaim
```

### 5. Create New Tasks
```http
POST http://localhost:8727/api/tasks
Content-Type: application/json
{
  "title": "Add DNS-over-HTTPS fallback",
  "description": "...",
  "priority": 0,
  "repo": "sample-repo-p",
  "roadmap_item": "Phase 3 — DNS Resilience"
}
```

### 6. Set / Clear Task Dependencies
```http
POST http://localhost:8727/api/tasks/{task_id}/dependency
Content-Type: application/json

{"depends_on": "task_1748397912_abc12345"}
```

**Success** (200):
```json
{"status": "updated", "task_id": "...", "depends_on": "task_1748397912_abc12345"}
```

Pass an empty string to clear the dependency:
```http
POST http://localhost:8727/api/tasks/{task_id}/dependency
Content-Type: application/json

{"depends_on": ""}
```

**Dependency enforcement:** A task with a non-done dependency **cannot be claimed**. The claim call returns a 409 with a descriptive error:
```json
{"detail": "Reducer failed: Cannot claim — dependency 'task_abc' (Prerequisite task) is not done (status: available)"}
```

## Dependency Rule

```
task_B ──[depends_on]──→ task_A

task_B can only be claimed AFTER task_A is done (status == 'done')
- If task_A doesn't exist → claim fails with "dependency not found"
- If task_A is available/in_progress/blocked → claim fails with descriptive error
- If task_B has no dependency → can be claimed freely (same behavior as before)
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

## GitHub PR Linking

When a GitHub repository's branch follows the kanban naming convention, the kanban automatically links PRs to tasks via a webhook.

### Setup

1. Go to your GitHub repo → Settings → Webhooks → Add webhook
2. **Payload URL:** `http://your-server:8727/api/webhook/github`
3. **Content type:** `application/json`
4. **Events:** Select "Pull requests"
5. **Secret:** (optional — leave blank for now)

### Behavior

| Event | Action |
|-------|--------|
| PR **opened** with matching branch | Task gets `branch` + PR URL set |
| PR **reopened** | Same as opened |
| PR **merged** (closed+merged) | Task auto-claimed as `github-actions` and marked done |

The branch must match the kanban convention:
```
feature/kanban-task_1748397912_abc12345--my-feature
```

## Roadmap Import

Bulk-import pending tasks from a project's `ROADMAP.md` file into the kanban.

```bash
# From any directory with a ROADMAP.md:
kanban roadmap-import --repo=my-project

# Or specify a custom file path:
kanban roadmap-import --repo=my-project --file=/path/to/ROADMAP.md
```

The importer parses:
- `## Phase N — Name` headers → maps to `roadmap_item` field
- `- [ ] Task description` → pending tasks (skips `- [x]` done items)
- Priority is auto-derived from phase number (Phase 1 = urgent, Phase 4 = low)
