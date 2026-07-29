# spacetimedb-kanban

**Atomic multi-agent kanban board** built on SpacetimeDB. Multiple AI agents can simultaneously grab tasks from a shared queue without conflicts.

## Architecture

```
SpacetimeDB (v2.6.1) — source of truth, atomic reducers
     ↓
FastAPI REST server (:8727) — HTTP bridge + scheduler loops + static frontend
```

- **Single process** — server-side scheduler replaces all cron jobs. Scheduler loops (stale_watcher, dead_board_monitor, metrics_collector, task_dispatcher, template_trigger) run as asyncio background tasks inside the FastAPI process
- **Atomic claim** — STDB's sequential reducer processing ensures only one agent can claim a task at a time
- **No polling conflicts** — claim returns 409 if already taken, agent moves to next task
- **Full audit log** — every claim/completion/block event is recorded
- **Web dashboard** — React + shadcn UI served by FastAPI static files at port 8727

## Quick Start

```bash
# Publish the STDB module
cd server/spacetimedb
spacetime publish spacetimedb-kanban --delete-data=never -y

# Start the API server (serves API + frontend)
cd ..
python3 main.py
```

> **Note:** Use `--delete-data=always` only when migrating STDB enum types or schema-breaking changes. For routine development, `--delete-data=never` preserves your data.

The server runs under the hermes-agent systemd service in production. For local dev, just run `python3 main.py` from `server/`.

## API Overview

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/tasks` | GET | List tasks (filterable by status, repo) |
| `/api/tasks` | POST | Create a new task |
| `/api/tasks/{id}` | GET | Get task details |
| `/api/tasks/{id}` | PATCH | Update task fields |
| `/api/tasks/{id}/claim` | POST | **Atomically** claim a task |
| `/api/tasks/{id}/unclaim` | POST | Release a task back to available |
| `/api/tasks/{id}/complete` | POST | Mark task as done |
| `/api/tasks/{id}/block` | POST | Mark task as blocked |
| `/api/tasks/{id}/dependency` | POST | Set/clear a task dependency |
| `/api/tasks/{id}/delete` | DELETE | Delete a task |
| `/api/tasks/seed` | POST | Seed sample data |
| `/api/roadmap/import` | POST | Bulk-import tasks from ROADMAP.md |
| `/api/webhook/github` | POST | GitHub webhook for PR linking |
| `/api/logs` | GET | List audit log entries |
| `/api/agents` | GET | List active agents |

See [AGENTS.md](AGENTS.md) for the full agent API guide with state machine and conventions.

## Cleanup — Legacy Cron Scripts

The following scripts have been replaced by the server-side scheduler and are removed:

- `server/watchdog.py` — replaced by `scheduler.stale_watcher` (120s loop)
- `server/kanban_heartbeat.py` — replaced by agent heartbeat API + scheduler
- `server/kanban_improver.py` — replaced by scheduler dispatcher + worker spawning
