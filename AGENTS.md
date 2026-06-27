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
