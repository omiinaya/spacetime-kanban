---
name: SpacetimedbKanban
description: "Atomic multi-agent kanban on SpacetimeDB — shared task coordination for AI agents with atomic claiming and state machine"
stack: [python, fastapi, react, typescript]
ports:
  api: 8727
  stdb: 3001
deps: [python3, node, npm, spacetime]
stdb: true
---

# Agent Onboarding Guide

This file is read by AI coding agents. For Claude Code specifically, also see [CLAUDE.md](./CLAUDE.md). Complements [README.md](./README.md).

## 📌 Architecture (Jul 2026)

This kanban server is **fully self-contained** — no external cron jobs. The server-side scheduler replaces all cron jobs with asyncio background tasks (stale_watcher, dead_board_monitor, metrics_collector, task_dispatcher, template_trigger) running inside the FastAPI process.

See `server/.env.example` for configuration. Alerts fire via webhook to Discord.

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

The server-side scheduler's `stale_watcher` loop runs every **120 seconds** and checks for tasks stuck `in_progress` for **>35 minutes** with no heartbeat. It auto-releases them back to `available` and fires a webhook event.

This means:
- If an agent claims a task and disappears, it gets reclaimed within ~35 minutes max
- If you're actively working on a long task, send heartbeats via `POST /api/agents/{agent_id}/heartbeat` to keep the task alive
- On server restart, `_recover_stale_tasks()` immediately unclaims any `in_progress` tasks from the previous lifecycle — no tasks get permanently stuck
- The watchdog is silent when nothing is stale — it only fires webhooks when it releases something

The scheduler runs as asyncio background tasks inside the FastAPI server process. No external cron setup is needed.

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

## Task Skills / Capability Tags (Phase 4)

Tasks can be tagged with **required skills** — comma-separated tags like `"rust,typescript,react"`. Agents can declare their capabilities during registration for smart task matching.

### Setting Skills on a Task
```http
POST http://localhost:8727/api/tasks/{task_id}/skills
Content-Type: application/json
{"skills": "rust,typescript,dns"}
```

Clear skills:
```http
POST http://localhost:8727/api/tasks/{task_id}/skills
Content-Type: application/json
{"skills": ""}
```

### CLI
```bash
kanban skills <task-id> --skills=rust,typescript
kanban skills <task-id> --skills=""    # clear
```

## Priority Scoring (Phase 4)

The kanban automatically scores available tasks to recommend the highest-value work. Score breakdown:

| Factor | Weight | Cap |
|--------|--------|-----|
| Base (Urgent=80 → Low=20) | `(4-priority)×20` | — |
| Stale time bonus | +5/hr | +30 |
| Unblock value | +10 per dependent | +30 |
| Skill match | +15 per match | +30 |

### Get Suggestions
```http
GET http://localhost:8727/api/tasks/suggest?limit=3
GET http://localhost:8727/api/tasks/suggest?agent_id=hermes&limit=5
```

Response includes per-task reasoning:
```json
[
  {
    "task": { "id": "...", "title": "Add DNS fallback", "priority": 0, "required_skills": "rust" },
    "score": 115,
    "reason": "+5 stale (1.2h old); +10 unblocks 1 task(s)"
  }
]
```

### CLI
```bash
kanban suggest                     # top 5 recommendations
kanban suggest --agent=hermes      # skill-matched to agent
kanban suggest --limit=3 --json    # JSON output
```

## Swarm Mode — Agent Registry (Phase 4)

Agents register with the kanban and send periodic heartbeats. The swarm shows who's online, what they're working on, and what skills they have.

### Register
```http
POST http://localhost:8727/api/agents/register
Content-Type: application/json
{
  "agent_id": "hermes-terminal",
  "host": "dev-server-1",
  "capabilities": "rust,python,typescript,react",
  "repo_focus": "spacetimedb-kanban"
}
```

### Heartbeat (every 30s recommended)
```http
POST http://localhost:8727/api/agents/hermes-terminal/heartbeat
Content-Type: application/json
{"status": "busy", "current_task_id": "task_xxx"}
```

### View Swarm
```http
GET http://localhost:8727/api/agents
```

Returns all registered agents with status, capabilities, and heartbeat freshness.

### CLI
```bash
kanban register --capabilities=rust,typescript --repo=sample-repo-p
kanban heartbeat                   # send online pulse
kanban heartbeat --status=busy --task=task_xxx
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `kanban list` | List tasks |
| `kanban claim <id>` | Claim a task |
| `kanban complete <id>` | Complete a task |
| `kanban block <id>` | Block a task |
| `kanban unclaim <id>` | Release a task |
| `kanban create --title=...` | Create a task |
| `kanban skills <id> --skills=...` | Set required skills |
| `kanban suggest` | Show recommended tasks |
| `kanban register` | Join the swarm |
| `kanban heartbeat` | Send agent pulse |
| `kanban roadmap-import` | Bulk-import from ROADMAP.md |
| `kanban check-branch` | Validate branch name |

---

## Fragile Interface Registry

These string-name contracts break silently if renamed. Check both `server/` and `web/` before changing.

| Contract | Location | Type |
|----------|----------|------|
| `GET /api/tasks` | `server/main.py` | API route |
| `POST /api/tasks` | `server/main.py` | API route |
| `GET /api/tasks/{task_id}` | `server/main.py` | API route |
| `PATCH /api/tasks/{task_id}` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/claim` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/complete` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/block` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/unclaim` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/dependency` | `server/main.py` | API route |
| `POST /api/webhook/github` | `server/main.py` | GitHub webhook |
| `status=available\|claimed\|blocked\|done` | `server/main.py` | Task state machine values |
| `repo` query param | `GET /api/tasks` | Filter parameter |
| `agent_id` | Claim/complete operations | Identity string |
| `hermes`, `claude-vscode`, `ciel` | Convention | Reserved agent IDs |
| `task_*` ID format | Task creation | ID prefix convention |

**Note:** All task-state strings (`available`, `claimed`, `blocked`, `done`) appear in both server code and frontend UI components. Renaming them breaks the state machine.
