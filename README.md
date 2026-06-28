# spacetimedb-kanban

**Atomic multi-agent kanban board** built on SpacetimeDB. Multiple AI agents (Hermes, Claude, Ciel) can simultaneously grab tasks from a shared queue without conflicts.

## Architecture

```
SpacetimeDB (v2.4.1) — source of truth, atomic reducers
     ↓
FastAPI REST server (:8727) — HTTP bridge for all agents
     ↓
Hermes Agent ←→ Claude (VSCode) ←→ Web Dashboard (:5189)
```

- **Atomic claim** — STDB's sequential reducer processing ensures only one agent can claim a task at a time
- **No polling conflicts** — claim returns 409 if already taken, agent moves to next task
- **Full audit log** — every claim/completion/block event is recorded
- **Web dashboard** — React + shadcn visual board for human oversight

## Quick Start

```bash
# Publish the STDB module
cd server/spacetimedb
spacetime publish spacetimedb-kanban --delete-data=always -y

# Start the API server
cd ..
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py

# Web dashboard (dev mode)
cd ../web
npm install
npm run dev
```

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
