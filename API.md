# SpacetimeDB Kanban — REST API Reference

> **Base URL:** `http://<host>:8727/api`
> **All endpoints return JSON.**
> **Auth:** Optional — if the `API_KEY` env var is set, all mutating endpoints require an `X-API-Key` header. Read-only endpoints (GET) are open.
> **Error format:** `{"detail": "<message>"}` with the appropriate HTTP status code.
> **Rate limiting:** None currently.

---

## Table of Contents

1. [Task Object Schema](#1-task-object-schema)
2. [Tasks](#2-tasks)
   - [List, Create, Get, Update, Delete](#21-crud)
   - [State Machine Actions](#22-state-machine-actions)
   - [Metadata (Comments, Checklist, Labels, Logs, Relations)](#23-metadata)
   - [Bulk Operations & Miscellaneous](#24-bulk--misc)
3. [Agents](#3-agents)
4. [Analytics](#4-analytics)
5. [Logs](#5-logs)
6. [Webhooks](#6-webhooks)
7. [Labels](#7-labels)
8. [Projects](#8-projects)
9. [GitHub Issues](#9-github-issues)
10. [API Keys](#10-api-keys)
11. [Task Templates](#11-task-templates)
12. [Automation Rules](#12-automation-rules)
13. [Schema Migrations](#13-schema-migrations)
14. [Dispatcher State](#14-dispatcher-state)
15. [Scanner](#15-scanner)
16. [Health](#16-health)
17. [Other Operations](#17-other-operations)
18. [Error Handling](#18-error-handling)

---

## 1. Task Object Schema

Most task endpoints return the `TaskOut` object:

```json
{
  "id": "task_1748397912_abc12345",
  "title": "Implement DNS-over-HTTPS fallback",
  "description": "When upstream fails, fall back to DoH",
  "priority": 0,
  "status": "available",
  "assigned_to": null,
  "repo": "sample-repo-p",
  "branch": null,
  "roadmap_item": "Phase 3 — DNS Resilience",
  "created_by": "web-user",
  "created_at": 1748397912000,
  "updated_at": 1748397912000,
  "depends_on": null,
  "required_skills": null,
  "score": 0,
  "position": null,
  "fail_count": 0,
  "max_attempts": 3,
  "fail_reason": null,
  "subtask_of": null,
  "subtasks": null,
  "due_by": null,
  "sprint": null,
  "archived": false,
  "estimated_hours": null,
  "spent_hours": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique task identifier |
| `title` | string | Task title |
| `description` | string | Full description |
| `priority` | int | 0 (highest) – 3 (lowest) |
| `status` | string | `available`, `in_progress`, `done`, `blocked` |
| `assigned_to` | string\|null | Agent ID that claimed this task |
| `repo` | string | Repository/project slug |
| `branch` | string\|null | Git branch where work occurs |
| `roadmap_item` | string | Parent roadmap phase |
| `created_by` | string | Creator identifier |
| `created_at` | int | Unix timestamp (ms) |
| `updated_at` | int | Unix timestamp (ms) |
| `depends_on` | string\|null | Task ID this task depends on |
| `required_skills` | string\|null | Comma-separated required capabilities |
| `score` | int | Computed suggestion score |
| `position` | int\|null | Display order position |
| `fail_count` | int | Number of failed attempts |
| `max_attempts` | int | Max allowed attempts before blocking |
| `fail_reason` | string\|null | Last failure reason |
| `subtask_of` | string\|null | Parent task ID if a subtask |
| `subtasks` | string\|null | Comma-separated child task IDs |
| `due_by` | int\|null | Due date (ms timestamp) |
| `sprint` | string\|null | Sprint assignment |
| `archived` | bool | Whether the task is archived |
| `estimated_hours` | int\|null | Estimated effort |
| `spent_hours` | int\|null | Actual time spent |

### Task State Machine

```
available ──[claim]──→ in_progress ──[complete]──→ done
                  │                       │
                  │  [unclaim]            │
                  ↓                       ↓
              available               done

in_progress ──[block]──→ blocked
blocked ──[unclaim]──→ available
```

A task with a non-`done` dependency **cannot be claimed** — the claim call returns `409 Conflict`.

---

## 2. Tasks

### 2.1 CRUD

#### `GET /api/tasks`
List tasks with filtering.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | Filter by status: `available`, `in_progress`, `done`, `blocked` |
| `repo` | string | Filter by repo slug |
| `label` | string | Filter by label ID |
| `search` | string | Full-text search (title, description, repo, assigned_to, id) |
| `archived` | bool | Filter archived (`true`) or unarchived (`false`) |
| `limit` | int | Max results (default: 2000) |
| `offset` | int | Pagination offset |

**Example:**
```bash
curl 'http://localhost:8727/api/tasks?status=available&repo=sample-repo-p&limit=10'
```

**Response:** `200` — array of [TaskOut](#1-task-object-schema)

---

#### `POST /api/tasks`
Create a new task.

**Request Body:**

```json
{
  "title": "Add DNS-over-HTTPS fallback",
  "description": "When upstream fails, fall back to DoH",
  "priority": 0,
  "repo": "sample-repo-p",
  "roadmap_item": "Phase 3 — DNS Resilience",
  "required_skills": "dns,networking",
  "created_by": "web-user",
  "status": "",
  "fail_count": 0,
  "max_attempts": 3,
  "fail_reason": null,
  "subtask_of": null,
  "subtasks": null,
  "due_by": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | **yes** | — | Task title |
| `description` | string | no | `""` | Full description |
| `priority` | int | no | `2` | 0–3 (0 = highest) |
| `repo` | string | no | `""` | Repository slug |
| `roadmap_item` | string | no | `""` | Roadmap phase |
| `required_skills` | string | no | `""` | Comma-separated skills |
| `created_by` | string | no | `"web-user"` | Creator identifier |
| `status` | string | no | `""` | Override initial status |
| `fail_count` | int | no | `0` | Initial fail count |
| `max_attempts` | int | no | `3` | Max retry attempts |
| `fail_reason` | string\|null | no | `null` | Initial fail reason |
| `subtask_of` | string\|null | no | `null` | Parent task ID |
| `subtasks` | string\|null | no | `null` | Child task IDs |
| `due_by` | int\|null | no | `null` | Due date ms timestamp |

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Implement DoH fallback","priority":0,"repo":"sample-repo-p"}'
```

**Response:** `201` — [TaskOut](#1-task-object-schema)

---

#### `GET /api/tasks/{task_id}`
Get a single task by ID.

**Example:**
```bash
curl http://localhost:8727/api/tasks/task_1748397912_abc12345
```

**Response:** `200` — [TaskOut](#1-task-object-schema)
**Error:** `404` — `{"detail": "Task not found"}`

---

#### `PATCH /api/tasks/{task_id}`
Update task fields. Only provided fields are changed.

**Request Body:**

```json
{
  "title": "Updated title",
  "description": "New description",
  "priority": 1,
  "branch": "feature/kanban-task_1748397912_abc12345--doh-fallback",
  "required_skills": "dns,networking,go",
  "due_by": 1749000000000,
  "sprint": "Sprint 12",
  "archived": false,
  "estimated_hours": 8,
  "spent_hours": 3
}
```

All fields are optional.

**Example:**
```bash
curl -X PATCH http://localhost:8727/api/tasks/task_1748397912_abc12345 \
  -H 'Content-Type: application/json' \
  -d '{"branch":"feature/kanban-task_1748397912_abc12345--doh-fallback"}'
```

**Response:** `200` — [TaskOut](#1-task-object-schema)
**Error:** `404` — `{"detail": "Task not found"}`

---

#### `DELETE /api/tasks/{task_id}`
Delete a task permanently.

**Example:**
```bash
curl -X DELETE http://localhost:8727/api/tasks/task_1748397912_abc12345
```

**Response:** `200` — `{"status": "deleted"}`

---

### 2.2 State Machine Actions

#### `POST /api/tasks/{task_id}/claim`
Atomically claim a task. Fails if already claimed.

**Request Body:**

```json
{"agent_id": "claude-vscode"}
```

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/claim \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "claude-vscode"}'
```

**Response:** `200` — `{"status": "claimed", "task_id": "...", "assigned_to": "claude-vscode"}`
**Error:** `409` — `{"detail": "Task is already claimed by hermes-terminal"}`

---

#### `POST /api/tasks/{task_id}/unclaim`
Release a claimed task back to `available`.

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/unclaim
```

**Response:** `200` — `{"status": "unclaimed", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/complete`
Mark a task as done.

**Request Body:**

```json
{"result_notes": "Implemented DoH fallback + tests passed"}
```

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/complete \
  -H 'Content-Type: application/json' \
  -d '{"result_notes": "All tests passing"}'
```

**Response:** `200` — `{"status": "completed", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/block`
Block a task (e.g. waiting on external dependency).

**Request Body:**

```json
{"reason": "Blocked on upstream API rate limits"}
```

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/block \
  -H 'Content-Type: application/json' \
  -d '{"reason": "Waiting for DNS provider"}'
```

**Response:** `200` — `{"status": "blocked", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/block-with-reason`
Block with a persistent reason stored on the task record.

**Request Body:**

```json
{"reason": "API key provisioning blocked by upstream team"}
```

**Response:** `200` — `{"status": "blocked", "task_id": "...", "reason": "..."}`

---

#### `POST /api/tasks/{task_id}/permanent-block`
Permanently block a task (skipped in suggestion scoring).

**Request Body:**

```json
{"reason": "Feature cancelled — won't implement"}
```

**Response:** `200` — `{"status": "permanently_blocked", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/dependency`
Set or clear a task dependency.

**Request Body:**

```json
{"depends_on": "task_1748397912_abc12345"}
```

Pass an empty string to clear:

```json
{"depends_on": ""}
```

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/dependency \
  -H 'Content-Type: application/json' \
  -d '{"depends_on": "task_1748397911_xyz67890"}'
```

**Response:** `200` — `{"status": "updated", "task_id": "...", "depends_on": "task_..."}`

> **Dependency enforcement:** A task with a non-done dependency cannot be claimed. The claim call returns `409` with a message like `"Cannot claim — dependency 'task_abc' (Prerequisite task) is not done (status: available)"`.

---

#### `POST /api/tasks/{task_id}/skills`
Set the required skills for a task.

**Request Body:**

```json
{"skills": "dns,networking,go"}
```

**Response:** `200` — `{"status": "updated"}`

---

#### `POST /api/tasks/{task_id}/split`
Split a task into multiple subtasks.

**Request Body:**

```json
{
  "child_titles": [
    "Research DoH providers",
    "Implement fallback logic",
    "Write tests"
  ]
}
```

**Response:** `200` — `{"status": "split", "parent_id": "...", "children": ["task_...", "task_...", "task_..."]}`

---

#### `POST /api/tasks/{task_id}/reset-fails`
Reset the `fail_count` to 0.

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/reset-fails
```

**Response:** `200` — `{"status": "reset", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/max-attempts`
Set the maximum allowed attempts for a task.

**Request Body:**

```json
{"max_attempts": 5}
```

**Response:** `200` — `{"status": "updated", "max_attempts": 5}`

---

#### `POST /api/tasks/{task_id}/archive`
Archive a task (hides from default listings).

**Response:** `200` — `{"status": "archived", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/unarchive`
Unarchive a task.

**Response:** `200` — `{"status": "unarchived", "task_id": "..."}`

---

#### `POST /api/tasks/{task_id}/sprint`
Assign a task to a sprint.

**Request Body:**

```json
{"sprint": "Sprint 12"}
```

**Response:** `200` — `{"status": "updated", "task_id": "...", "sprint": "Sprint 12"}`

---

#### `POST /api/tasks/{task_id}/time-estimates`
Set estimated and/or spent hours on a task.

**Request Body:**

```json
{"estimated_hours": 8, "spent_hours": 3}
```

**Response:** `200` — `{"status": "updated", "task_id": "...", "estimated_hours": 8, "spent_hours": 3}`

---

### 2.3 Metadata (Comments, Checklist, Labels, Logs, Relations)

#### Comments

##### `POST /api/tasks/{task_id}/comments`
Add a comment to a task.

**Request Body:**

```json
{
  "body": "Investigating DNS timeout issue",
  "author": "claude-vscode"
}
```

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/comments \
  -H 'Content-Type: application/json' \
  -d '{"body": "Looking into this now", "author": "claude-vscode"}'
```

**Response:** `201` — `{"status": "created", "id": "cmt_..."}`

---

##### `GET /api/tasks/{task_id}/comments`
List all comments for a task (oldest first).

**Response:** `200` — array of `CommentOut`:

```json
[
  {
    "id": "cmt_abc123",
    "task_id": "task_1748397912_abc12345",
    "author": "claude-vscode",
    "body": "Looking into this now",
    "created_at": 1748397912000
  }
]
```

---

##### `DELETE /api/tasks/{task_id}/comments/{comment_id}`
Delete a comment.

**Response:** `200` — `{"status": "deleted"}`

---

#### Checklist

##### `POST /api/tasks/{task_id}/checklist`
Add a checklist item.

**Request Body:**

```json
{"text": "Research DoH providers"}
```

**Response:** `201` — `{"status": "created", "id": "cl_..."}`

---

##### `GET /api/tasks/{task_id}/checklist`
List all checklist items (ordered by position).

**Response:** `200` — array of `ChecklistItemOut`:

```json
[
  {
    "id": "cl_abc123",
    "task_id": "task_1748397912_abc12345",
    "text": "Research DoH providers",
    "completed": false,
    "position": 0,
    "created_at": 1748397912000
  }
]
```

---

##### `POST /api/tasks/{task_id}/checklist/{item_id}/toggle`
Toggle a checklist item's completed state.

**Response:** `200` — `{"status": "toggled"}`

---

##### `DELETE /api/tasks/{task_id}/checklist/{item_id}`
Remove a checklist item.

**Response:** `200` — `{"status": "deleted"}`

---

##### `POST /api/tasks/{task_id}/checklist/{item_id}/reorder?new_position=N`
Reorder a checklist item to a new position.

**Response:** `200` — `{"status": "reordered"}`

---

#### Labels (per-task)

##### `GET /api/tasks/{task_id}/labels`
Get all labels assigned to a task.

**Response:** `200` — array of `LabelOut` (see [Labels section](#7-labels))

---

##### `POST /api/tasks/{task_id}/labels`
Set labels for a task (replaces all current assignments).

**Request Body:**

```json
{"label_ids": ["label_abc123", "label_def456"]}
```

**Response:** `200` — `{"status": "updated", "assigned": ["label_abc123", "label_def456"]}`

---

#### Logs (per-task)

##### `GET /api/logs?task_id={task_id}`
Get activity logs for a task. See [Logs section](#5-logs) for full details.

---

##### `POST /api/tasks/{task_id}/log`
Add a custom log entry to a task.

**Request Body:**

```json
{
  "action": "custom_action",
  "agent_id": "claude-vscode",
  "notes": "Started investigation"
}
```

**Response:** `200` — `{"status": "logged", "id": "log_..."}`

---

#### Relations

##### `GET /api/tasks/{task_id}/relations`
List all relations for a task (both directions).

**Response:** `200` — array of `TaskRelationOut`:

```json
[
  {
    "id": "rel_abc123",
    "task_id": "task_1748397912_abc12345",
    "related_task_id": "task_1748397911_xyz67890",
    "relation_type": "blocks",
    "created_at": 1748397912000
  }
]
```

Valid `relation_type` values: `blocks`, `blocked_by`, `relates_to`, `duplicates`, `is_duplicated_by`.

---

##### `POST /api/tasks/{task_id}/relations`
Add a relation.

**Request Body:**

```json
{
  "related_task_id": "task_1748397911_xyz67890",
  "relation_type": "blocks"
}
```

**Response:** `200` — `{"status": "created", "task_id": "...", "related_task_id": "..."}`

---

##### `DELETE /api/tasks/{task_id}/relations/{relation_id}`
Remove a relation.

**Response:** `200` — `{"status": "deleted"}`

---

### 2.4 Bulk & Misc

#### `POST /api/tasks/suggest?limit=5&agent_id=claude-vscode`
Get top-N task suggestions based on priority scoring and optional agent capability matching.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 5 | Max suggestions |
| `agent_id` | string | — | If provided, capabilities are matched against task `required_skills` |

**Example:**
```bash
curl 'http://localhost:8727/api/tasks/suggest?limit=3&agent_id=claude-vscode'
```

**Response:** `200` — array of `SuggestResult`:

```json
[
  {
    "task": { /* TaskOut */ },
    "score": 85,
    "reason": "High priority + skills match + no dependency blockers"
  }
]
```

---

#### `POST /api/tasks/seed`
Seed the database with sample tasks.

**Response:** `200` — `{"status": "seeded"}`

---

#### `POST /api/tasks/clear`
Delete ALL tasks from the database.

**Response:** `200` — `{"status": "cleared", "deleted": 42}`

---

#### `GET /api/tasks/export?format=json&status=done&repo=sample-repo-p`
Export tasks as JSON or CSV with optional filters.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `format` | string | `"json"` | Output format: `json` or `csv` |
| `status` | string | — | Filter by status |
| `repo` | string | — | Filter by repo slug |

**Example:**
```bash
curl 'http://localhost:8727/api/tasks/export?format=csv&repo=sample-repo-p' -o tasks.csv
```

**Response:** `200` — Array (JSON) or CSV file download.

---

#### `POST /api/tasks/reorder`
Reorder a single task.

**Request Body:**

```json
{"task_id": "task_1748397912_abc12345", "position": 1}
```

**Response:** `200` — `{"status": "reordered"}`

---

#### `POST /api/tasks/bulk-reorder`
Reorder multiple tasks at once.

**Request Body:**

```json
{
  "items": [
    {"task_id": "task_1748397912_abc12345", "position": 1},
    {"task_id": "task_1748397911_xyz67890", "position": 2}
  ]
}
```

**Response:** `200` — `{"status": "reordered", "count": 2}`

---

#### `POST /api/tasks/batch/labels`
Batch-assign labels to multiple tasks.

**Request Body:**

```json
{
  "task_ids": ["task_1748397912_abc12345", "task_1748397911_xyz67890"],
  "label_ids": ["label_abc123", "label_def456"]
}
```

**Response:** `200` — `{"status": "assigned", "task_count": 2, "label_count": 2}`

---

#### `POST /api/tasks/batch/unlabels`
Batch-unassign labels from multiple tasks.

**Request Body:**

```json
{
  "task_ids": ["task_1748397912_abc12345", "task_1748397911_xyz67890"],
  "label_ids": ["label_abc123"]
}
```

**Response:** `200` — `{"status": "unassigned"}`

---

#### `POST /api/tasks/bulk-retry`
Retry failed tasks — resets their state to `available`.

**Request Body:**

```json
{
  "task_ids": ["task_1748397912_abc12345", "task_1748397911_xyz67890"],
  "reset_fails": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_ids` | string[] | **yes** | — | IDs of tasks to retry |
| `reset_fails` | bool | no | `true` | Whether to reset `fail_count` to 0 |

**Response:** `200` — `{"status": "retried", "count": 2}`

---

#### `POST /api/tasks/bulk-archive`
Archive multiple tasks at once.

**Request Body:**

```json
{
  "task_ids": ["task_1748397912_abc12345", "task_1748397911_xyz67890"]
}
```

**Response:** `200` — `{"status": "archived", "count": 2}`

---

#### `POST /api/tasks/bulk`
Perform a bulk action on multiple tasks.

**Request Body:**

```json
{
  "action": "claim",
  "task_ids": ["task_1748397912_abc12345", "task_1748397911_xyz67890"],
  "agent_id": "claude-vscode",
  "reason": "",
  "result_notes": ""
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `action` | string | **yes** | — | One of: `claim`, `complete`, `block`, `unclaim`, `delete` |
| `task_ids` | string[] | **yes** | — | IDs of tasks to act on |
| `agent_id` | string | no | `"web-user"` | Agent performing the action |
| `reason` | string | no | `""` | Reason (for `block`) |
| `result_notes` | string | no | `""` | Notes (for `complete`) |

**Example:**
```bash
curl -X POST http://localhost:8727/api/tasks/bulk \
  -H 'Content-Type: application/json' \
  -d '{"action": "claim", "task_ids": ["task_abc", "task_def"], "agent_id": "claude-vscode"}'
```

**Response:** `200` — `{"status": "completed", "results": [{"task_id": "...", "success": true}, ...]}`

---

## 3. Agents

### `GET /api/agents`
List all registered swarm agents.

**Example:**
```bash
curl http://localhost:8727/api/agents
```

**Response:** `200` — array of `AgentOut`:

```json
[
  {
    "id": "claude-vscode",
    "host": "dev-workstation",
    "capabilities": "python,go,terraform",
    "repo_focus": "sample-repo-p",
    "current_task_id": "task_1748397912_abc12345",
    "status": "online",
    "last_heartbeat": 1748397912000,
    "first_seen": 1748397912000
  }
]
```

---

### `GET /api/agents/health`
Get agent health status with heartbeat staleness and current task info.

**Example:**
```bash
curl http://localhost:8727/api/agents/health
```

**Response:** `200` — array of enriched agent status:

```json
[
  {
    "id": "claude-vscode",
    "host": "dev-workstation",
    "status": "online",
    "capabilities": "python,go",
    "repo_focus": "sample-repo-p",
    "current_task": {
      "id": "task_1748397912_abc12345",
      "title": "Implement DoH fallback",
      "status": "in_progress",
      "priority": 0,
      "repo": "sample-repo-p"
    },
    "last_heartbeat": 1748397912000,
    "heartbeat_age_seconds": 30,
    "stale": false,
    "first_seen": 1748397912000
  }
]
```

An agent is considered **stale** when its last heartbeat is >5 minutes old.

---

### `GET /api/agents/{agent_id}`
Get a specific agent's details.

**Example:**
```bash
curl http://localhost:8727/api/agents/claude-vscode
```

**Response:** `200` — `AgentOut`
**Error:** `404` — `{"detail": "Agent not found"}`

---

### `POST /api/agents/register`
Register (or re-connect) an agent in the swarm.

**Request Body:**

```json
{
  "agent_id": "claude-vscode",
  "host": "dev-workstation",
  "capabilities": "python,go,terraform",
  "repo_focus": "sample-repo-p"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `agent_id` | string | **yes** | — | Globally unique agent ID |
| `host` | string | no | `""` | Hostname where the agent runs |
| `capabilities` | string | no | `""` | Comma-separated capabilities |
| `repo_focus` | string | no | `""` | Default repo this agent works on |

**Example:**
```bash
curl -X POST http://localhost:8727/api/agents/register \
  -H 'Content-Type: application/json' \
  -d '{"agent_id": "claude-vscode", "capabilities": "python,go"}'
```

**Response:** `200` — `{"status": "registered", "agent_id": "claude-vscode"}`

---

### `POST /api/agents/{agent_id}/heartbeat`
Send a heartbeat. Agents should heartbeat periodically (every 30–60s).

**Request Body:**

```json
{
  "status": "online",
  "current_task_id": "task_1748397912_abc12345"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `status` | string | no | `"online"` | `online`, `busy`, `idle` |
| `current_task_id` | string | no | `""` | ID of the task currently being worked on |

**Example:**
```bash
curl -X POST http://localhost:8727/api/agents/claude-vscode/heartbeat \
  -H 'Content-Type: application/json' \
  -d '{"status": "online", "current_task_id": "task_1748397912_abc12345"}'
```

**Response:** `200` — `{"status": "ok", "agent_id": "claude-vscode"}`

---

### `PUT /api/agents/{agent_id}/capabilities`
Update an agent's capabilities and repo focus.

**Request Body:**

```json
{
  "capabilities": "python,go,rust",
  "repo_focus": "sample-repo-p"
}
```

**Example:**
```bash
curl -X PUT http://localhost:8727/api/agents/claude-vscode/capabilities \
  -H 'Content-Type: application/json' \
  -d '{"capabilities": "python,go,rust"}'
```

**Response:** `200` — `{"status": "updated", "agent_id": "claude-vscode"}`

---

## 4. Analytics

### `GET /api/analytics/overview`
High-level board metrics.

**Example:**
```bash
curl http://localhost:8727/api/analytics/overview
```

**Response:** `200`

```json
{
  "total": 142,
  "by_status": {
    "available": 45,
    "in_progress": 12,
    "done": 78,
    "blocked": 7
  },
  "completed_today": 3,
  "completed_week": 18,
  "total_done": 78,
  "repos": {
    "sample-repo-p": {
      "total": 62,
      "done": 35,
      "inProgress": 5,
      "blocked": 3,
      "available": 19
    }
  },
  "claims_last_hour": 5,
  "completions_last_hour": 3,
  "claim_complete_ratio": 1.7
}
```

---

### `GET /api/analytics/claim-churn?minutes=60&threshold=6`
Detect poison-pill tasks — tasks claimed many times without completing.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `minutes` | int | 60 | Look-back window |
| `threshold` | int | 6 | Min claim count to flag |

**Response:** `200`

```json
{
  "churned_tasks": [
    {"task_id": "task_abc", "claim_count": 8, "completed": false}
  ],
  "checked_tasks": 12,
  "window_minutes": 60
}
```

---

### `GET /api/analytics/throughput?days=14`
Daily completion counts.

**Example:**
```bash
curl 'http://localhost:8727/api/analytics/throughput?days=14'
```

**Response:** `200`

```json
{
  "daily": {
    "2026-07-15": 5,
    "2026-07-16": 3,
    ...
  },
  "total": 42,
  "days": 14
}
```

---

### `GET /api/analytics/cycle-times`
Average cycle time (time from creation to completion) per repo.

**Response:** `200`

```json
{
  "repos": {
    "sample-repo-p": {"avg_hours": 8.2, "task_count": 35},
    "spacetime-web": {"avg_hours": 12.1, "task_count": 22}
  }
}
```

---

### `GET /api/analytics/burndown?days=30`
Burndown chart data — remaining open tasks per day.

**Example:**
```bash
curl 'http://localhost:8727/api/analytics/burndown?days=30'
```

**Response:** `200`

```json
{
  "days": [
    {"date": "2026-07-01", "open": 50, "completed": 3},
    {"date": "2026-07-02", "open": 48, "completed": 5}
  ],
  "total_completed": 42
}
```

---

### `GET /api/analytics/agents`
Per-agent performance statistics.

**Response:** `200`

```json
{
  "agents": {
    "claude-vscode": {
      "tasks_completed": 15,
      "tasks_claimed": 22,
      "completion_rate": 0.68,
      "avg_cycle_hours": 6.5
    }
  }
}
```

---

### `GET /api/analytics/cross-project`
Cross-project comparison data.

**Response:** `200`

```json
{
  "projects": [
    {
      "repo": "sample-repo-p",
      "total": 62,
      "done": 35,
      "completion_pct": 56.5
    }
  ]
}
```

---

### `GET /api/analytics/calendar?year=2026&month=7`
Calendar view of tasks grouped by due date.

**Example:**
```bash
curl 'http://localhost:8727/api/analytics/calendar?year=2026&month=7'
```

**Response:** `200`

```json
{
  "year": 2026,
  "month": 7,
  "days": {
    "15": [ /* TaskOut objects due on July 15 */ ],
    "16": [ /* TaskOut objects due on July 16 */ ]
  }
}
```

---

## 5. Logs

### `GET /api/logs?limit=50&offset=0&action=claimed&agent_id=claude-vscode&search=DoH&since=1748397912000&task_id=task_abc`
Search activity logs with filtering and pagination.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `task_id` | string | — | Filter by task ID |
| `action` | string | — | Filter by action(s) — comma-separated for multiple |
| `agent_id` | string | — | Filter by agent ID |
| `search` | string | — | Full-text search in notes, task_id, action |
| `since` | int | — | Only logs after this ms timestamp |
| `until` | int | — | Only logs before this ms timestamp |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 50 | Max results |

**Example:**
```bash
curl 'http://localhost:8727/api/logs?action=claimed,completed&limit=20'
```

**Response:** `200` — array of `LogOut`:

```json
[
  {
    "id": "log_abc123",
    "task_id": "task_1748397912_abc12345",
    "action": "claimed",
    "agent_id": "claude-vscode",
    "notes": "",
    "timestamp": 1748397912000
  }
]
```

---

### `GET /api/logs/batch?task_ids=task_abc,task_def&action=heartbeat&limit=1`
Batch fetch the latest log entries for multiple task IDs. Used by the scheduler for efficient staleness checking.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `task_ids` | string | **required** | Comma-separated task IDs (max 100) |
| `action` | string | `"heartbeat"` | Action to filter by |
| `limit` | int | 1 | Max entries per task |

**Example:**
```bash
curl 'http://localhost:8727/api/logs/batch?task_ids=task_abc,task_def&action=heartbeat'
```

**Response:** `200`

```json
{
  "task_abc": {
    "id": "log_123",
    "task_id": "task_abc",
    "action": "heartbeat",
    "agent_id": "claude-vscode",
    "notes": "",
    "timestamp": 1748397912000
  },
  "task_def": null
}
```

---

### `GET /api/logs/stats`
Get activity log summary statistics.

**Example:**
```bash
curl http://localhost:8727/api/logs/stats
```

**Response:** `200`

```json
{
  "total_events": 15234,
  "today_events": 312,
  "active_agents_today": 5,
  "action_breakdown": {
    "claimed": 4200,
    "completed": 3800,
    "blocked": 500,
    "heartbeat": 6200,
    "created": 500,
    "unclaimed": 34
  },
  "top_agents": {
    "claude-vscode": 89,
    "hermes": 72
  }
}
```

---

## 6. Webhooks

### `GET /api/webhooks`
List all registered webhook subscriptions.

**Example:**
```bash
curl http://localhost:8727/api/webhooks
```

**Response:** `200` — array of webhook objects:

```json
[
  {
    "id": "wh_abc123",
    "url": "https://discord.com/api/webhooks/...",
    "type": "discord",
    "events": ["created", "claimed", "completed", "blocked"],
    "label": "Discord alerts",
    "created_at": 1748397912
  }
]
```

---

### `POST /api/webhooks`
Create a new webhook subscription.

**Request Body:**

```json
{
  "url": "https://discord.com/api/webhooks/...",
  "type": "discord",
  "events": ["created", "claimed", "completed", "blocked"],
  "label": "Discord alerts"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `url` | string | **yes** | — | Webhook destination URL |
| `type` | string | no | `"generic"` | `generic`, `discord`, `telegram` |
| `events` | string[] | no | `["created","claimed","unclaimed","completed","blocked"]` | Events to subscribe to |
| `label` | string | no | `""` | Human-readable label |

**Example:**
```bash
curl -X POST http://localhost:8727/api/webhooks \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://discord.com/api/webhooks/...","type":"discord","label":"Alerts"}'
```

**Response:** `201` — webhook object

---

### `GET /api/webhooks/{webhook_id}`
Get a specific webhook subscription.

**Response:** `200` — webhook object
**Error:** `404` — `{"detail": "Webhook not found"}`

---

### `PATCH /api/webhooks/{webhook_id}`
Update a webhook subscription.

**Request Body:**

```json
{
  "url": "https://new-url.com/webhook",
  "events": ["created", "completed"],
  "label": "Updated label"
}
```

All fields optional.

**Response:** `200` — updated webhook object
**Error:** `404` — `{"detail": "Webhook not found"}`

---

### `DELETE /api/webhooks/{webhook_id}`
Remove a webhook subscription.

**Response:** `200` — `{"status": "deleted"}`
**Error:** `404` — `{"detail": "Webhook not found"}`

---

### `POST /api/webhooks/{webhook_id}/test`
Send a test ping to verify the webhook is working.

**Response:** `200` — `{"status": "sent", "webhook_id": "...", "response_code": 200}`
**Error:** `502` — `{"detail": "Webhook test failed: ..."}`

---

### `GET /api/webhooks/{webhook_id}/deliveries?limit=20`
Get delivery history for a webhook.

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 20 | Max deliveries to return |

**Response:** `200` — array of delivery records

---

## 7. Labels

### `GET /api/labels`
List all labels.

**Example:**
```bash
curl http://localhost:8727/api/labels
```

**Response:** `200` — array of `LabelOut`:

```json
[
  {
    "id": "label_abc123",
    "name": "bug",
    "color": "#ef4444",
    "description": "Something isn't working",
    "created_at": 1748397912000
  }
]
```

---

### `POST /api/labels`
Create a new label.

**Request Body:**

```json
{
  "name": "enhancement",
  "color": "#22c55e",
  "description": "New feature or request"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **yes** | — | Label name |
| `color` | string | no | `"#0ea5e9"` | Hex color code |
| `description` | string | no | `""` | Label description |
| `id` | string | no | auto | Explicit label ID (auto-generated if empty) |

**Example:**
```bash
curl -X POST http://localhost:8727/api/labels \
  -H 'Content-Type: application/json' \
  -d '{"name":"bug","color":"#ef4444","description":"Bug report"}'
```

**Response:** `201` — `LabelOut`

---

### `PATCH /api/labels/{label_id}`
Update a label.

**Request Body:**

```json
{
  "name": "critical-bug",
  "color": "#dc2626",
  "description": "Critical severity bug"
}
```

All fields optional.

**Response:** `200` — `LabelOut`

---

### `DELETE /api/labels/{label_id}`
Delete a label and remove it from all tasks.

**Response:** `200` — `{"status": "deleted"}`

---

## 8. Projects

### `GET /api/projects`
List all registered projects/repos.

**Example:**
```bash
curl http://localhost:8727/api/projects
```

**Response:** `200` — array of `ProjectOut`:

```json
[
  {
    "id": "sample-repo-p",
    "name": "Spacetime AB",
    "description": "Main project repository",
    "color": "#0ea5e9",
    "priority": 0,
    "active": true,
    "created_at": 1748397912000,
    "updated_at": 1748397912000
  }
]
```

---

### `POST /api/projects`
Register a new project/repo.

**Request Body:**

```json
{
  "id": "spacetime-web",
  "name": "Spacetime Web UI",
  "description": "Frontend project",
  "color": "#22c55e",
  "priority": 1,
  "active": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `id` | string | **yes** | — | Repo slug (unique) |
| `name` | string | no | `""` | Display name |
| `description` | string | no | `""` | Project description |
| `color` | string | no | `"#0ea5e9"` | Theme colour |
| `priority` | int | no | `2` | Project priority (0 = highest) |
| `active` | bool | no | `true` | Whether project is active |

**Example:**
```bash
curl -X POST http://localhost:8727/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"id":"spacetime-web","name":"Web UI","color":"#22c55e"}'
```

**Response:** `201` — `ProjectOut`

---

### `PATCH /api/projects/{project_id}`
Update a project.

**Request Body:**

```json
{
  "name": "Updated Name",
  "description": "New description",
  "color": "#a855f7",
  "priority": 2,
  "active": true
}
```

**Response:** `200` — `ProjectOut`

---

### `DELETE /api/projects/{project_id}`
Delete a project registration.

**Response:** `200` — `{"status": "deleted"}`

---

### `GET /api/suggest-by-project?limit=10`
Get task suggestions using the project-aware scoring engine.

**Example:**
```bash
curl 'http://localhost:8727/api/suggest-by-project?limit=5'
```

**Response:** `200` — array of scored tasks

---

## 9. GitHub Issues

### `GET /api/issues?repo=sample-repo-p`
List all kanban-task ⟷ GitHub-issue links, optionally filtered by repo.

**Example:**
```bash
curl 'http://localhost:8727/api/issues?repo=sample-repo-p'
```

**Response:** `200` — array of link objects:

```json
[
  {
    "task_id": "task_1748397912_abc12345",
    "repo": "sample-repo-p",
    "issue_number": 42,
    "issue_url": "https://api.github.com/repos/sample-repo-p/issues/42",
    "html_url": "https://github.com/sample-repo-p/issues/42",
    "linked_at": 1748397912
  }
]
```

---

### `GET /api/issues/{task_id}`
Get the GitHub issue link for a specific kanban task.

**Response:** `200` — `{"kanban_task_id": "...", "repo": "...", "issue_number": 42, ...}`
**Error:** `404` — `{"detail": "No GitHub issue linked to this task"}`

---

### `POST /api/issues/link`
Link a kanban task to an existing GitHub issue.

**Request Body:**

```json
{
  "task_id": "task_1748397912_abc12345",
  "repo": "sample-repo-p",
  "issue_number": 42
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | string | **yes** | — | Kanban task ID |
| `repo` | string | **yes** | — | GitHub repo (owner/repo) |
| `issue_number` | int | **yes** | — | GitHub issue number |
| `issue_url` | string | no | auto | API URL (auto-built if omitted) |
| `html_url` | string | no | auto | Browser URL (auto-built if omitted) |

**Example:**
```bash
curl -X POST http://localhost:8727/api/issues/link \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"task_abc","repo":"sample-repo-p","issue_number":42}'
```

**Response:** `200` — `{"status": "linked", ...}`
**Error:** `409` — `{"detail": "Task already linked to https://github.com/.../issues/42"}`

---

### `POST /api/issues/unlink?task_id=task_abc`
Unlink a task from its GitHub issue.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | **yes** | Task to unlink |

**Example:**
```bash
curl -X POST 'http://localhost:8727/api/issues/unlink?task_id=task_abc'
```

**Response:** `200` — `{"status": "unlinked"}`

---

### `POST /api/issues/create`
Create a GitHub issue from a kanban task and auto-link them.

**Request Body:**

```json
{
  "task_id": "task_1748397912_abc12345",
  "repo": "sample-repo-p",
  "labels": "bug,automation",
  "assignee": "someuser"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | string | **yes** | — | Kanban task ID |
| `repo` | string | no | `""` | Target repo (uses task's repo if empty) |
| `labels` | string | no | `""` | Comma-separated GitHub labels |
| `assignee` | string | no | `""` | GitHub username to assign |

**Example:**
```bash
curl -X POST http://localhost:8727/api/issues/create \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"task_abc","labels":"bug"}'
```

**Response:** `200` — `{"status": "created", "issue_number": 43, "html_url": "https://github.com/.../issues/43"}`

---

### `POST /api/webhook/github`
GitHub webhook receiver — listens for issue events and syncs status back to kanban tasks.

**Response:** `200` — `{"status": "received"}`

---

## 10. API Keys

### `GET /api/api-keys`
List all API keys.

**Example:**
```bash
curl http://localhost:8727/api/api-keys
```

**Response:** `200` — array of `ApiKeyOut`:

```json
[
  {
    "id": "apikey-example-01",
    "key_hash": "sha256$...",
    "name": "CI Pipeline",
    "repo_scope": "sample-repo-p",
    "permissions": "read",
    "created_by": "web-user",
    "created_at": 1748397912000,
    "last_used_at": 1748397912000,
    "active": true
  }
]
```

---

### `POST /api/api-keys`
Create a new API key.

**Request Body:**

```json
{
  "key_hash": "sha256$...",
  "name": "CI Pipeline",
  "repo_scope": "sample-repo-p",
  "permissions": "read",
  "created_by": "web-user"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `key_hash` | string | **yes** | — | Hashed API key value |
| `name` | string | **yes** | — | Human-readable name |
| `repo_scope` | string | no | `""` | Restrict to a specific repo |
| `permissions` | string | no | `"read"` | `read` or `write` |
| `created_by` | string | no | `"web-user"` | Creator identifier |
| `id` | string | no | auto | Explicit key ID |

**Response:** `201` — `{"status": "created", "id": "apikey_..."}`

---

### `POST /api/api-keys/{key_id}/revoke`
Revoke an API key (sets `active` to `false`).

**Example:**
```bash
curl -X POST http://localhost:8727/api/api-keys/apikey-example-01/revoke
```

**Response:** `200` — `{"status": "revoked", "key_id": "apikey-example-01"}`

---

## 11. Task Templates

### `GET /api/task-templates`
List all task templates (recurring task definitions with cron schedules).

**Response:** `200` — array of `TemplateOut`:

```json
[
  {
    "id": "tpl_abc123",
    "title": "Weekly Security Scan",
    "description": "Run vulnerability scan on all repos",
    "priority": 1,
    "repo": "sample-repo-p",
    "roadmap_item": "Security",
    "required_skills": "security",
    "cron_schedule": "0 8 * * 1",
    "created_by": "web-user",
    "created_at": 1748397912000,
    "last_triggered_at": 1748397912000,
    "active": true
  }
]
```

---

### `POST /api/task-templates`
Create a new task template.

**Request Body:**

```json
{
  "title": "Weekly Security Scan",
  "description": "Run vulnerability scan on all repos",
  "priority": 1,
  "repo": "sample-repo-p",
  "roadmap_item": "Security",
  "required_skills": "security",
  "cron_schedule": "0 8 * * 1",
  "created_by": "web-user"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `title` | string | **yes** | — | Template title |
| `cron_schedule` | string | **yes** | — | Cron expression for scheduling |
| `description` | string | no | `""` | Template description |
| `priority` | int | no | `2` | Default priority for created tasks |
| `repo` | string | no | `""` | Default repo |
| `roadmap_item` | string | no | `""` | Default roadmap phase |
| `required_skills` | string | no | `""` | Default required skills |
| `created_by` | string | no | `"web-user"` | Creator |
| `id` | string | no | auto | Explicit template ID |

**Response:** `201` — `TemplateOut`

---

### `PATCH /api/task-templates/{template_id}`
Update a task template.

**Request Body:**

```json
{
  "title": "Updated title",
  "cron_schedule": "0 9 * * 1",
  "active": false
}
```

All fields optional.

**Response:** `200` — `TemplateOut`
**Error:** `404` — `{"detail": "Template not found"}`

---

### `DELETE /api/task-templates/{template_id}`
Delete a task template.

**Response:** `200` — `{"status": "deleted"}`

---

### `POST /api/task-templates/trigger`
Manually trigger all active templates — creates tasks for any that are due based on their cron schedule.

**Response:** `200` — `{"status": "triggered", "notes": "completed"}`

---

## 12. Automation Rules

### `GET /api/rules`
List all automation rules.

**Response:** `200` — array of `AutomationRuleOut`:

```json
[
  {
    "id": "rule_abc123",
    "name": "Auto-assign label",
    "description": "Assign 'automation' label when task created",
    "trigger_event": "created",
    "condition": null,
    "action_type": "assign_label",
    "action_config": "{\"label\": \"automation\"}",
    "repo": null,
    "active": true,
    "created_at": 1748397912000,
    "updated_at": 1748397912000
  }
]
```

---

### `POST /api/rules`
Create an automation rule.

**Request Body:**

```json
{
  "name": "Auto-assign label",
  "description": "Assign 'automation' label when task created",
  "trigger_event": "created",
  "condition": "",
  "action_type": "assign_label",
  "action_config": "{\"label\": \"automation\"}",
  "repo": "",
  "active": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | **yes** | — | Rule name |
| `trigger_event` | string | **yes** | — | `created`, `claimed`, `completed`, `blocked`, etc. |
| `action_type` | string | **yes** | — | Action to perform |
| `action_config` | string | **yes** | — | JSON config for the action |
| `description` | string | no | `""` | Description |
| `condition` | string | no | `""` | Filter condition |
| `repo` | string | no | `""` | Scope to a repo |
| `active` | bool | no | `true` | Whether the rule is active |
| `id` | string | no | auto | Explicit rule ID |

**Response:** `201` — `AutomationRuleOut`

---

### `GET /api/rules/{rule_id}`
Get a specific automation rule.

**Response:** `200` — `AutomationRuleOut`

---

### `PATCH /api/rules/{rule_id}`
Update an automation rule.

**Response:** `200` — `AutomationRuleOut`

---

### `DELETE /api/rules/{rule_id}`
Delete an automation rule.

**Response:** `200` — `{"status": "deleted"}`

---

## 13. Schema Migrations

### `GET /api/schema-migrations`
List all recorded schema migrations.

**Alias:** `GET /api/migrations`

**Example:**
```bash
curl http://localhost:8727/api/schema-migrations
```

**Response:** `200` — array of `MigrationOut`:

```json
[
  {
    "version": "20260701_001",
    "description": "Initial task schema",
    "applied_at": 1748397912000,
    "applied_by": "web-user",
    "checksum": "sha256:..."
  }
]
```

---

### `POST /api/schema-migrations`
Record a new schema migration.

**Alias:** `POST /api/migrations`

**Request Body:**

```json
{
  "version": "20260701_002",
  "description": "Add task_relations table",
  "applied_by": "web-user",
  "checksum": "sha256:..."
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `version` | string | **yes** | — | Unique version identifier |
| `description` | string | no | `""` | Human-readable description |
| `applied_by` | string | no | `"web-user"` | Who applied the migration |
| `checksum` | string | no | `""` | Integrity checksum |

**Response:** `201` — `{"status": "recorded", "version": "20260701_002"}`

---

## 14. Dispatcher State

### `GET /api/dispatcher/state?key=scheduler_state`
Get dispatcher state from STDB. If `key` is provided, return only that key's value.

**Response:** `200`

```json
{
  "scheduler_state": {"last_run": 1748397912000, "tick_count": 42},
  "last_assignment": {"task_id": "task_abc", "agent_id": "claude-vscode"}
}
```

---

### `POST /api/dispatcher/state`
Set a single key in dispatcher state.

**Request Body:**

```json
{
  "key": "scheduler_state",
  "value": {"last_run": 1748397912000, "tick_count": 43}
}
```

**Response:** `200` — `{"status": "ok", "key": "scheduler_state"}`

---

### `DELETE /api/dispatcher/state/{key}`
Delete a key from dispatcher state.

**Response:** `200` — `{"status": "deleted", "key": "..."}`
**Error:** `404` — `{"detail": "Key not found: ..."}`

---

## 15. Scanner

### `POST /api/scanner/scan`
Trigger all repo scanners on demand. Scanners analyze repositories for issues and auto-create kanban tasks.

**Response:** `200`

```json
{
  "status": "scan_completed",
  "scanners_run": 3,
  "tasks_created": 5,
  "errors": []
}
```

---

## 16. Health

### `GET /api/health`
System health check — returns scheduler process metrics, crash reporting, uptime, and a lightweight board summary.

**Example:**
```bash
curl http://localhost:8727/api/health
```

**Response:** `200`

```json
{
  "status": "ok",
  "workers": {
    "active": 3,
    "total_spawned": 12
  },
  "crashes": {
    "total": 0,
    "recent_tasks": []
  },
  "uptime_seconds": 86400,
  "board": {
    "total": 142,
    "available": 45,
    "in_progress": 12,
    "done": 78,
    "blocked": 7
  }
}
```

---

### `GET /api/health/projects`
Get layered health scores for all scanned projects.

**Response:** `200` — array of project health reports

---

### `GET /api/health/projects/{repo_name}`
Get detailed health score for a specific project.

**Response:** `200` — project health report

---

## 17. Other Operations

### `POST /api/roadmap/import`
Parse ROADMAP.md content and bulk-create tasks from unchecked checklist items.

**Request Body:**

```json
{
  "content": "## Phase 1 — Foundation\n- [ ] Set up CI pipeline\n- [ ] Configure monitoring\n- [x] Deploy initial version\n\n## Phase 2 — Features\n- [ ] Add user auth\n",
  "repo": "sample-repo-p",
  "created_by": "roadmap-import"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `content` | string | **yes** | — | Raw ROADMAP.md content |
| `repo` | string | no | `""` | Default repo slug for imported tasks |
| `created_by` | string | no | `"roadmap-import"` | Creator identifier |

Tasks are deduplicated by title+repo — if an existing task with the same title and repo exists and is not `done`, it's skipped.

**Example:**
```bash
curl -X POST http://localhost:8727/api/roadmap/import \
  -H 'Content-Type: application/json' \
  -d '{"content":"## Phase 1\n- [ ] Task one\n- [ ] Task two","repo":"my-repo"}'
```

**Response:** `200`

```json
{
  "status": "imported",
  "task_count": 2,
  "repo": "sample-repo-p",
  "phases_found": ["Phase 1 — Foundation"]
}
```

---

## 18. Error Handling

All errors follow a consistent format:

```json
{
  "detail": "Human-readable error message"
}
```

### HTTP Status Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| `200` | Success | Request processed |
| `201` | Created | Resource successfully created |
| `400` | Bad Request | Missing required fields, invalid values |
| `404` | Not Found | Task, agent, webhook, or other resource not found |
| `409` | Conflict | Task already claimed, dependency not met, task already linked |
| `422` | Unprocessable Entity | Validation error (invalid JSON schema, wrong types) |
| `500` | Internal Server Error | STDB reducer failure, unexpected exception |
| `502` | Bad Gateway | Webhook test delivery failure, external API error |

### Common Error Examples

**Task already claimed:**
```json
// HTTP 409
{"detail": "Task is already claimed by hermes-terminal"}
```

**Dependency not met:**
```json
// HTTP 409
{"detail": "Reducer failed: Cannot claim — dependency 'task_abc' (Prerequisite task) is not done (status: available)"}
```

**Resource not found:**
```json
// HTTP 404
{"detail": "Task not found"}
```

**Webhook test failure:**
```json
// HTTP 502
{"detail": "Webhook test failed: Connection refused"}
```

---

## Quick Reference: curl Examples

```bash
# ── Tasks ──────────────────────────────────────────────────────

# List available tasks
curl 'http://localhost:8727/api/tasks?status=available&limit=10'

# Create a task
curl -X POST http://localhost:8727/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Implement X","priority":0,"repo":"my-repo"}'

# Get task details
curl http://localhost:8727/api/tasks/task_1748397912_abc12345

# Update a task
curl -X PATCH http://localhost:8727/api/tasks/task_1748397912_abc12345 \
  -H 'Content-Type: application/json' \
  -d '{"branch":"feature/kanban-task_...--description"}'

# Delete a task
curl -X DELETE http://localhost:8727/api/tasks/task_1748397912_abc12345

# Claim a task
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/claim \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"claude-vscode"}'

# Complete a task
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/complete \
  -H 'Content-Type: application/json' \
  -d '{"result_notes":"Done"}'

# Block a task
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/block \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Waiting on upstream"}'

# Unclaim a task
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/unclaim

# Set dependency
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/dependency \
  -H 'Content-Type: application/json' \
  -d '{"depends_on":"task_other"}'

# Get suggested tasks
curl 'http://localhost:8727/api/tasks/suggest?limit=5&agent_id=claude-vscode'

# Add comment
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/comments \
  -H 'Content-Type: application/json' \
  -d '{"body":"Looking into this","author":"claude-vscode"}'

# Add checklist item
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/checklist \
  -H 'Content-Type: application/json' \
  -d '{"text":"Step one"}'

# Add log entry
curl -X POST http://localhost:8727/api/tasks/task_1748397912_abc12345/log \
  -H 'Content-Type: application/json' \
  -d '{"action":"investigation","notes":"Found root cause"}'

# Seed sample data
curl -X POST http://localhost:8727/api/tasks/seed

# Export tasks as CSV
curl 'http://localhost:8727/api/tasks/export?format=csv' -o tasks.csv

# ── Agents ─────────────────────────────────────────────────────

# Register agent
curl -X POST http://localhost:8727/api/agents/register \
  -H 'Content-Type: application/json' \
  -d '{"agent_id":"claude-vscode","capabilities":"python,go"}'

# Send heartbeat
curl -X POST http://localhost:8727/api/agents/claude-vscode/heartbeat \
  -H 'Content-Type: application/json' \
  -d '{"status":"online","current_task_id":"task_abc"}'

# Agent health
curl http://localhost:8727/api/agents/health

# List agents
curl http://localhost:8727/api/agents

# ── Analytics ──────────────────────────────────────────────────

curl http://localhost:8727/api/analytics/overview
curl 'http://localhost:8727/api/analytics/throughput?days=14'
curl 'http://localhost:8727/api/analytics/burndown?days=30'
curl http://localhost:8727/api/analytics/cycle-times
curl http://localhost:8727/api/analytics/agents
curl 'http://localhost:8727/api/analytics/calendar?year=2026&month=7'

# ── Logs ───────────────────────────────────────────────────────

curl 'http://localhost:8727/api/logs?limit=20&action=claimed'
curl 'http://localhost:8727/api/logs/stats'

# ── Webhooks ───────────────────────────────────────────────────

# Create webhook
curl -X POST http://localhost:8727/api/webhooks \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://hooks.example.com","type":"generic","events":["created","completed"]}'

# Test webhook
curl -X POST http://localhost:8727/api/webhooks/wh_abc123/test

# ── Labels ────────────────────────────────────────────────────

curl http://localhost:8727/api/labels
curl -X POST http://localhost:8727/api/labels \
  -H 'Content-Type: application/json' \
  -d '{"name":"bug","color":"#ef4444"}'

# ── Projects ───────────────────────────────────────────────────

curl http://localhost:8727/api/projects
curl -X POST http://localhost:8727/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"id":"my-repo","name":"My Repo"}'

# ── GitHub Issues ─────────────────────────────────────────────

curl 'http://localhost:8727/api/issues?repo=my-repo'
curl -X POST http://localhost:8727/api/issues/link \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"task_abc","repo":"my-repo","issue_number":42}'

# ── API Keys ──────────────────────────────────────────────────

curl http://localhost:8727/api/api-keys
curl -X POST http://localhost:8727/api/api-keys \
  -H 'Content-Type: application/json' \
  -d '{"key_hash":"sha256$...","name":"CI Key"}'

# ── Schema Migrations ─────────────────────────────────────────

curl http://localhost:8727/api/schema-migrations

# ── Health ────────────────────────────────────────────────────

curl http://localhost:8727/api/health

# ── Task Templates ────────────────────────────────────────────

curl http://localhost:8727/api/task-templates

# ── Automation Rules ──────────────────────────────────────────

curl http://localhost:8727/api/rules

# ── Scan ──────────────────────────────────────────────────────

curl -X POST http://localhost:8727/api/scanner/scan

# ── Auth Example ───────────────────────────────────────────────

curl -X POST http://localhost:8727/api/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -d '{"title":"Authenticated task creation"}'
```
