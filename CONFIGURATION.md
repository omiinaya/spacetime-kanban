# Configuration

All configuration is via environment variables. The project uses `python-dotenv` to load a `.env` file at startup, so you can place these in a `.env` file in the project root or export them in your shell.

---

## Server

| Variable | Default | Description |
|---|---|---|
| `SERVER_PORT` | `8727` | HTTP port for the FastAPI server. |
| `CORS_ORIGIN` | `http://localhost:4444` | CORS origin for the frontend. Vite dev server runs on `:4444`; production serves the frontend from the backend. |
| `API_KEY` | *(empty)* | If set, mutation endpoints require this API key via an `X-API-Key` header. Empty means no authentication is required (demo mode — not for production). |
| `KANBAN_REPOS` | `spacetime-kanban` | Comma-separated list of repos the task fountain and seed scripts operate on. Overrides the built-in default of just this repo. |

---

## SpacetimeDB

| Variable | Default | Description |
|---|---|---|
| `STDB_HOST` | `localhost` | SpacetimeDB hostname. |
| `STDB_PORT` | `3001` | SpacetimeDB HTTP port. |
| `STDB_DB` | `kanban` | SpacetimeDB database name. |
| `KANBAN_STDB_RETRIES` | `60` | Maximum number of retries when waiting for SpacetimeDB to become available on startup. |

---

## Agent / Swarm Identity

| Variable | Default | Description |
|---|---|---|
| `AGENT_ID` | `hermes` | Identity for this server instance in the swarm. |
| `KANBAN_AGENT_ID` | *(empty)* | Overrides the agent identity for CLI operations. Takes priority over `AGENT_ID` when set. |

---

## Scheduler

The scheduler runs background loops for task dispatching, health checks, metrics, and maintenance. `SCHEDULER_ENABLED` is the master switch.

| Variable | Default | Description |
|---|---|---|
| `SCHEDULER_ENABLED` | `true` | Master switch for all background scheduler loops. Set to `false` to disable all scheduled jobs. |
| `DISPATCHER_INTERVAL_SECONDS` | `5` | How often the task dispatcher checks for work to assign. |
| `STALE_CHECK_INTERVAL_SECONDS` | `120` | How often to check for stuck / stale tasks. |
| `DEAD_BOARD_INTERVAL_SECONDS` | `3600` | Board health check interval. Auto-restarts the board if it is detected as dead. |
| `TEMPLATE_INTERVAL_SECONDS` | `900` | Task template processing interval. |
| `METRICS_INTERVAL_SECONDS` | `900` | Metrics snapshot collection interval. |
| `SCANNER_INTERVAL_SECONDS` | `1800` | Repository improvement scanner interval. Set to `0` to disable. |
| `IMPROVER_INTERVAL_SECONDS` | `3600` | Self-improvement agent interval. |
| `REMEDIATOR_INTERVAL_SECONDS` | `3600` | Blocked-task remediation interval (audits + archives stale blocked tasks). |

---

## Workers

Subprocess workers for executing tasks.

| Variable | Default | Description |
|---|---|---|
| `WORKER_COMMAND` | `python3` | Command used to spawn worker subprocesses. |
| `WORKER_SCRIPT` | *(empty)* | Path to the worker entry point script. |
| `WORKER_ARGS` | *(empty)* | Extra arguments passed to the worker command. |
| `MIN_WORKERS` | `2` | Minimum number of worker subprocesses to keep running. |
| `MAX_WORKERS` | `8` | Maximum number of worker subprocesses. |
| `STALE_MINUTES` | `45` | Minutes after which an `in_progress` task is considered stale. |
| `MAX_MEMORY_PCT` | `80` | Maximum system memory percentage before worker dispatch is throttled. |
| `KANBAN_WORKTREE` | `1` | Isolate each task worker in its own git worktree (`~/<repo>-kanban-<task-id>`) so concurrent workers don't collide in the main clone. Set `0` to work directly in the main clone. |
| `KANBAN_VERIFY_TESTS` | `1` | After an LLM worker reports completion, run the repo's test suite and only mark the task done if it passes. Set `0` to skip verification. |
| `KANBAN_VERIFY_TESTS_TIMEOUT` | `180` | Max seconds to run the test-suite verification before giving up (a timeout is not counted as a failure). |
| `KANBAN_API` | `http://localhost:8727` | Internal API URL used by the MCP server and workers to reach the kanban backend. |
| `KANBAN_LLM_WORKER` | *(empty)* | Command for launching LLM-driven task workers. |

---

## Webhooks

Notifications sent to Discord, Slack, or similar webhook endpoints.

| Variable | Default | Description |
|---|---|---|
| `WEBHOOK_DEFAULT_URL` | *(empty)* | Default webhook URL for notifications. |
| `WEBHOOK_MAX_RETRIES` | `3` | Number of retries for a failed webhook delivery. |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` | HTTP timeout in seconds for webhook delivery. |

---

## GitHub

Integration for issue synchronization.

| Variable | Default | Description |
|---|---|---|
| `GITHUB_TOKEN` | *(empty)* | GitHub personal access token for issue sync operations. |
| `GITHUB_DEFAULT_REPO` | *(empty)* | Default repository for GitHub issue operations (format: `owner/repo`). |
---

## Docker Compose

When running via `docker-compose`, the following volumes are used:

| Volume | Mount point | Purpose |
|---|---|---|
| `stdb-data` | `/var/spacetime` | Persists SpacetimeDB data across restarts. |

The `docker-compose.yml` typically exposes:

- **`8727`** — FastAPI server (mapped to host port `8727`).
- **`3001`** — SpacetimeDB HTTP API (mapped to host port `3001`).
- **`3002`** — SpacetimeDB WebSocket (mapped to host port `3002`).

Example `docker-compose` environment block:

```yaml
environment:
  - SERVER_PORT=8727
  - CORS_ORIGIN=http://localhost:4444
  - STDB_HOST=spacetime
  - STDB_PORT=3001
  - STDB_DB=kanban
  - KANBAN_STDB_RETRIES=60
  - API_KEY=
  - AGENT_ID=hermes
  - SCHEDULER_ENABLED=true
  - DISPATCHER_INTERVAL_SECONDS=5
  - STALE_CHECK_INTERVAL_SECONDS=120
  - DEAD_BOARD_INTERVAL_SECONDS=3600
  - TEMPLATE_INTERVAL_SECONDS=900
  - METRICS_INTERVAL_SECONDS=900
  - SCANNER_INTERVAL_SECONDS=1800
  - IMPROVER_INTERVAL_SECONDS=3600
  - REMEDIATOR_INTERVAL_SECONDS=3600
  - WORKER_COMMAND=python3
  - WORKER_SCRIPT=
  - WORKER_ARGS=
  - MIN_WORKERS=2
  - MAX_WORKERS=8
  - STALE_MINUTES=45
  - MAX_MEMORY_PCT=80
  - WEBHOOK_DEFAULT_URL=
  - WEBHOOK_MAX_RETRIES=3
  - WEBHOOK_TIMEOUT_SECONDS=10
  - GITHUB_TOKEN=
  - GITHUB_DEFAULT_REPO=
  - KANBAN_API=http://localhost:8727
  - KANBAN_LLM_WORKER=
```
