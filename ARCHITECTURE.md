# spacetime-kanban — System Architecture

> **Version:** 0.1.0
> **Last updated:** July 2026
> **Stack:** Python 3.11+ / FastAPI / SpacetimeDB v2.6.1 / React 18 / TypeScript

---

## Table of Contents

1. [Overview](#overview)
2. [ASCII Architecture Diagram](#ascii-architecture-diagram)
3. [Stack Decisions & Rationale](#stack-decisions--rationale)
4. [Component Detail](#component-detail)
5. [Data Flow](#data-flow)
6. [Task State Machine](#task-state-machine)
7. [STDB Table Reference](#stdb-table-reference)
8. [Scheduler Reference](#scheduler-reference)
9. [MCP Integration](#mcp-integration)
10. [Testing & Quality](#testing--quality)

---

## Overview

spacetime-kanban is a **multi-agent task coordination board** designed for AI agents working on the same repository's roadmap simultaneously. It is fully self-contained — all state lives in SpacetimeDB tables, all scheduler loops run as asyncio tasks inside the FastAPI process (no external cron), and a React frontend provides the human interface.

**Key design tenets:**

- **STDB is the source of truth** — every mutation goes through a SpacetimeDB reducer. The REST API is a thin proxy over STDB SQL queries and reducer calls.
- **Atomic claiming** — task claims use STDB's sequential reducer processing, guaranteeing no two agents can claim the same task.
- **Self-healing** — scheduler loops detect stale/dead workers, crashed processes, zombie tasks, and board stalls, then auto-remediate.
- **No external dependencies** for orchestration — no cron, no Redis, no message broker. Everything lives in the FastAPI process.
- **GitHub bidirectional sync** — kanban tasks can be linked to GitHub issues with automatic status sync.

---

## ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        spacetime-kanban SYSTEM                                │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         FastAPI Server (:8727)                          │   │
│  │                                                                         │   │
│  │  ┌──────────────┐  ┌──────────────────────────────────────────────┐    │   │
│  │  │   REST API   │  │           Scheduler (asyncio loops)          │    │   │
│  │  │  (/api/*)    │  │                                              │    │   │
│  │  │              │  │  task_dispatcher        (5s)                 │    │   │
│  │  │  tasks.py    │  │  stale_watcher         (120s)                │    │   │
│  │  │  agents.py   │  │  dead_board_monitor    (3600s)               │    │   │
│  │  │  analytics.py│  │  metrics_collector     (900s)                │    │   │
│  │  │  labels.py   │  │  template_trigger      (900s)                │    │   │
│  │  │  logs.py     │  │  repo_scanner          (1800s)               │    │   │
│  │  │  projects.py │  │  improver              (3600s)               │    │   │
│  │  │  webhook_subs│  │  blocked_remediator    (3600s)               │    │   │
│  │  │  github.py   │  │  zombie_cleaner        (1800s)               │    │   │
│  │  │  ops.py      │  │  worker_death_watcher  (15s)                 │    │   │
│  │  │  rules.py    │  │  task_archiver         (3600s)               │    │   │
│  │  │  ...         │  │  _task_fountain_loop   (60s)                 │    │   │
│  │  │  ...         │  │  _recover_stale_tasks  (once on startup)     │    │   │
│  │  └──────┬───────┘  └──────────────────────┬───────────────────────┘    │   │
│  │         │                                  │                             │   │
│  │         ▼                                  ▼                             │   │
│  │  ┌──────────────────────────────────────────────────────────┐           │   │
│  │  │               shared.py / _sql() / _call()               │           │   │
│  │  │   httpx AsyncClient → STDB SQL Gateway (:3001)          │           │   │
│  │  └──────────────────────────┬───────────────────────────────┘           │   │
│  │                             │                                             │   │
│  │         ┌───────────────────┴───────────────────┐                        │   │
│  │         ▼                                       ▼                        │   │
│  │  ┌──────────────┐                    ┌──────────────────┐               │   │
│  │  │  Worker      │                    │  Webhook         │               │   │
│  │  │  Subprocess  │                    │  Dispatcher      │               │   │
│  │  │  Mgmt        │                    │  (httpx POST)    │               │   │
│  │  └──────────────┘                    └────────┬─────────┘               │   │
│  │         │                                     │                           │   │
│  │         ▼                                     ▼                           │   │
│  │  ┌──────────────┐                    ┌──────────────────┐               │   │
│  │  │  workers/    │                    │  Discord/Slack   │               │   │
│  │  │  base.py     │                    │  Webhook URL     │               │   │
│  │  │  llm.py      │                    └──────────────────┘               │   │
│  │  │  mechanical/ │                                                       │   │
│  │  └──────────────┘                                                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────┐     ┌──────────────────────────┐                  │
│  │    React + Vite SPA     │     │   MCP Server (stdio)     │                  │
│  │    (:4444 / :8727)      │     │   mcp_server.py          │                  │
│  │                         │     │   36 MCP tools           │                  │
│  │  shadcn/ui components   │     │   Hermes native          │                  │
│  │  Tailwind CSS v4        │     │   integration            │                  │
│  │  react-router-dom v7    │     └──────────────────────────┘                  │
│  └─────────────────────────┘                                                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          SpacetimeDB v2.6.1 (:3001)                             │
│                                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐  ┌──────────────────┐     │
│  │   tasks     │  │  task_logs  │  │  swarm_agents  │  │  webhook_subs   │     │
│  ├─────────────┤  ├─────────────┤  ├───────────────┤  ├──────────────────┤     │
│  │...tables... │  │...tables... │  │...tables...   │  │...tables...      │     │
│  └─────────────┘  └─────────────┘  └───────────────┘  └──────────────────┘     │
│                                                                                  │
│  Rust WASM module (spacetime-kanban.wasm) with reducers:                       │
│  claim_task, complete_task, block_task, unclaim_task, add_task, ...             │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Stack Decisions & Rationale

### SpacetimeDB v2.6.1 as State Layer

| Decision | Rationale |
|---|---|
| **STDB instead of PostgreSQL** | SpacetimeDB provides atomic reducer execution with built-in SQL querying. No need for external transaction management — reducers execute sequentially, guaranteeing no race conditions on task claims. Tables map directly to typed Rust structs compiled to WASM. |
| **SQL Gateway instead of client SDK** | The FastAPI server uses `POST /v1/database/{db}/sql` for all reads and `POST /v1/database/{db}/call/{reducer}` for mutations. This avoids coupling to any STDB client SDK version and keeps the Python backend lightweight (pure httpx). |
| **SATS parser** | Custom `_parse_sats_rows()` in `shared.py` converts STDB's SATS-encoded JSON responses into plain Python dicts. Parsing is offloaded to a thread pool to avoid blocking the event loop on large result sets. |

### FastAPI as Application Server

- Single process (workers=1) — scheduler asyncio tasks run in-process alongside the HTTP server
- Lifespan hooks start/stop all scheduler loops
- CORS + GZip + security headers middleware
- SPA fallback for client-side routing
- 15 route modules under `routes/`

### In-Process Scheduler (No Cron)

All scheduler loops run as `asyncio.create_task()` inside the FastAPI process. This eliminates:

- External cron dependencies
- State file tracking
- Port conflicts from separate scheduler processes
- Race conditions between HTTP handler and cron task

The scheduler uses its own shared `httpx.AsyncClient` with connection pooling to hit the local REST API — conceptually looping back on itself. This decouples scheduler logic from direct STDB access, ensuring it exercises the same code paths as external API consumers.

### Worker Subprocess Management

The server spawns child processes for task execution. Two modes:

1. **Mechanical workers** — Python scripts (`workers/mechanical/`) for automated maintenance tasks
2. **LLM workers** — Hermes chat sessions (`workers/llm.py`, `workers/run.py`) for AI-powered task execution

The `worker_death_watcher` loop (15s interval) monitors subprocess health:

- Exit code 0 → graceful completion
- Exit code 1 → graceful block/permanent-block
- Exit code 2+ or negative → crash; auto-unclaims and re-queues the task
- Crash-on-launch (<3s) after 3 attempts → task is permanently blocked

### Frontend: React 18 + Vite + shadcn/ui

- Built with TypeScript, Tailwind CSS v4, and shadcn/ui components
- SPACETIMEDB client SDK (`spacetimedb@^2.7.0`) for TypeScript table definitions and reducer wrappers in `web/src/stdb/`
- Static files served by FastAPI at `GET /` and mounted under `/assets/`
- E2E tests via Playwright, unit tests via Vitest

### MCP Server (stdio transport)

A standalone MCP server (`mcp_server.py`) runs over stdio for Hermes Agent integration. It exposes 36 tools covering the full task lifecycle, agent management, project CRUD, GitHub issue sync, and checklist/comment operations. Uses the raw `urllib` (no httpx) to avoid blocking Hermes' asyncio loop.

---

## Component Detail

### 1. FastAPI Server (`server/main.py`)

| Aspect | Detail |
|---|---|
| Port | `:8727` (configurable via `SERVER_PORT` env) |
| Workers | `1` (scheduler loops are in-process asyncio tasks) |
| Startup | Waits for STDB gateway (retries up to 30x), creates database if missing, starts scheduler, recovers stale tasks, seeds initial workers |
| Shutdown | Cancels all scheduler asyncio tasks, closes shared httpx client |
| Routes | 15 route modules + inline `/health` + SPA fallback |

**Route modules:**

| Module | Prefix | Purpose |
|---|---|---|
| `routes/tasks.py` | `/api/tasks` | CRUD, claim, complete, block, unclaim, split, suggest, bulk ops, comments, checklists |
| `routes/agents.py` | `/api/agents` | Register, heartbeat, capabilities |
| `routes/analytics.py` | `/api/analytics` | Board overview, burndown, calendar, throughput |
| `routes/labels.py` | `/api/labels` | Label CRUD, batch assign/unassign |
| `routes/logs.py` | `/api/logs` | Activity log querying |
| `routes/projects.py` | `/api/projects` | Project CRUD |
| `routes/github.py` | `/api/issues` | GitHub issue link, create, status |
| `routes/templates.py` | `/api/task-templates` | Recurring task template CRUD + trigger |
| `routes/webhook_subs.py` | `/api/webhooks` | Webhook subscription management |
| `routes/apikeys.py` | `/api/api-keys` | API key management |
| `routes/health.py` | `/api/health` | Health check endpoint |
| `routes/ops.py` | `/api/ops` | Operational endpoints (bulk archive, retry) |
| `routes/rules.py` | `/api/automation-rules` | Automation rule CRUD |
| `routes/scanner.py` | `/api/scanner` | Repo scanner endpoints |
| `routes/dispatcher.py` | `/api/dispatcher` | Dispatcher state management |

### 2. STDB SQL Layer (`server/shared.py`)

- `_sql(query)` — Executes raw SQL via `POST /v1/database/{db}/sql`
- `_sql_param(template, **params)` — Safe parameterised SQL with single-quote escaping
- `_call(reducer, args)` — Calls a STDB reducer via `POST /v1/database/{db}/call/{reducer}`
- `_compute_score(task, caps, blockers)` — Priority scoring engine for task suggestions
- `_parse_sats_rows(resp_json)` — Custom SATS decoder (Sum/Product/Array/Ref/Set)

### 3. Webhook Dispatcher (`server/webhook_dispatcher.py`)

Fires HTTP POSTs to configured webhook URLs. Events:

| Event | Trigger |
|---|---|
| `task.blocked` | Task blocked |
| `task.completed` | Task completed |
| `task.claimed` | Task claimed (not yet wired) |
| `task.deleted` | Task deleted |
| `board.dead` | 0 completions in last hour with work available |
| `board.stalled` | Abnormally high claim:complete ratio (>20:1) |
| `metrics.snapshot` | Periodic board metrics |

Discord-compatible payload format with `content`, `_event`, `_timestamp`, `_data` fields. Retries with exponential backoff (1s, 2s, 4s) up to 3 attempts.

### 4. Workers (`server/workers/`)

| Module | Purpose |
|---|---|
| `base.py` | Base worker class with API helpers |
| `llm.py` | LLM-powered task worker (spawns Hermes chat) |
| `run.py` | Main worker entry point (dispatches to mechanical or LLM) |
| `mechanical/__init__.py` | Mechanical (automated) worker implementations |

### 5. Scanners (`server/scanners/`)

| Module | Purpose |
|---|---|
| `runner.py` | Orchestrates all scanners |
| `dep_scanner.py` | Dependency scanning |
| `gaps.py` | Gap analysis |
| `health.py` | Health scanning |
| `layer_architecture.py` | Architecture layer analysis |
| `layer_docs.py` | Documentation scanning |
| `layer_security.py` | Security scanning |
| `stdb_index.py` | STDB index analysis |
| `todo_scanner.py` | TODO/FIXME scanning |
| `unused_code.py` | Unused code detection |

---

## Data Flow

### Task Creation → Completion (Full Lifecycle)

```
External Agent                     FastAPI Server                     SpacetimeDB
─────────────                      ─────────────                      ──────────
     │                                   │                                │
     │  POST /api/tasks                  │                                │
     │  {title, description,            │                                │
     │   priority, repo}                │                                │
     │──────────────────────────────────►│                                │
     │                                   │  _call("add_task", [...])     │
     │                                   │───────────────────────────────►│
     │                                   │  Reducer: add_task             │
     │                                   │  INSERT INTO tasks             │
     │                                   │◄───────────────────────────────│
     │                                   │                                │
     │  201 {id, status: "available"}    │                                │
     │◄──────────────────────────────────│                                │
     │                                   │                                │
     │  POST /api/tasks/{id}/claim       │                                │
     │  {agent_id: "claude-vscode"}      │                                │
     │──────────────────────────────────►│                                │
     │                                   │  _call("claim_task",          │
     │                                   │    [id, agent_id])            │
     │                                   │───────────────────────────────►│
     │                                   │  Reducer: claim_task           │
     │                                   │  ● Checks status == available  │
     │                                   │  ● Checks depends_on is done   │
     │                                   │  ● SET status = "claimed"      │
     │                                   │  ● SET assigned_to = agent_id  │
     │                                   │◄───────────────────────────────│
     │                                   │                                │
     │  200 {status: "claimed"}          │                                │
     │◄──────────────────────────────────│                                │
     │                                   │                                │
     │  ...agent works on task...        │                                │
     │                                   │                                │
     │  POST /api/tasks/{id}/complete    │                                │
     │  {result_notes: "..."}            │                                │
     │──────────────────────────────────►│                                │
     │                                   │  _call("complete_task",       │
     │                                   │    [id, notes])               │
     │                                   │───────────────────────────────►│
     │                                   │  Reducer: complete_task        │
     │                                   │  SET status = "done"           │
     │                                   │  SET updated_at = now          │
     │                                   │◄───────────────────────────────│
     │                                   │                                │
     │                                   │  _notify("completed", task)   │
     │                                   │  → webhook_dispatcher         │
     │                                   │                                │
     │  200 {status: "done"}             │                                │
     │◄──────────────────────────────────│                                │
```

### Task Claiming (Atomic — Race Condition Prevention)

```
Agent A                          Agent B                         STDB
───────                          ───────                         ────
  │                                │                              │
  │ claim(task_1)                  │                              │
  │───────────────────────────────►│                              │
  │                                │ claim(task_1)                │
  │                                │─────────────────────────────►│
  │                                │                              │
  │                                │    STDB reducers are         │
  │                                │    PROCESSED SEQUENTIALLY    │
  │                                │                              │
  │                                │  Reducer for A runs first:   │
  │                                │  Task available → claimed    │
  │                                │                              │
  │                                │  Reducer for B runs second:  │
  │                                │  Task NOT available → FAIL   │
  │                                │                              │
  │  200 {claimed}                 │                              │
  │◄───────────────────────────────│                              │
  │                                │  409 {already claimed}       │
  │                                │◄─────────────────────────────│
  │                                │                              │
```

### Scheduler Auto-Discovery (Dispatcher Loop)

```
   task_dispatcher (every 5s)
         │
         ├── GET /api/tasks?status=available&limit=200
         ├── Filter: fail_count < max_attempts
         ├── Sort: priority ASC → fail_count ASC → created_at ASC
         ├── Check: _get_worker_count() < max_workers
         ├── Check: memory_pressure < max_memory_pct
         │
         └── For each eligible task:
              ├── POST /api/tasks/{id}/claim {agent_id}
              ├── If claimed → _spawn_worker(task_id, title, repo)
              └── If spawn fails → POST /api/tasks/{id}/unclaim
```

---

## Task State Machine

```
                 ┌─────────────────────────────────────┐
                 │                                     │
                 ▼                                     │
           ┌──────────┐                               │
    ┌─────►│ available│                               │
    │      └────┬─────┘                               │
    │           │                                     │
    │           │ claim()                              │
    │           ▼                                     │
    │      ┌────────────┐                             │
    │      │  claimed / │──(auto-transition)────┐     │
    │      │ in_progress│                       │     │
    │      └──┬──────┬──┘                       │     │
    │         │      │                          │     │
    │         │      │ complete()                │     │
    │         │      ▼                          │     │
    │         │  ┌──────┐                       │     │
    │         │  │ done │                       │     │
    │         │  └──────┘                       │     │
    │         │                                 │     │
    │         │ unclaim()                        │     │
    │         └───────────(stale/heartbeat)──────┘     │
    │                                                  │
    │         block()                                  │
    │         ▼                                        │
    │      ┌─────────┐                                 │
    │      │ blocked │──unclaim()──────────────────────┘
    │      └─────────┘
    │
    │         (archiver auto-archives old done/blocked)
    │
    └──────────── archived (terminal, not a DB status)

Transitions:
  available ──[claim]──→ in_progress
  in_progress ──[complete]──→ done
  in_progress ──[block]──→ blocked
  in_progress ──[unclaim]──→ available
  blocked ──[unclaim]──→ available
  done ──[auto-archive >7 days]──→ archived (soft-delete)
  blocked ──[auto-archive >24h]──→ archived

Guards:
  - claim() fails with 409 if status != "available"
  - claim() fails if dependency (depends_on) is not "done"
  - dispatcher skips tasks with fail_count >= max_attempts
  - 3 crash-on-launch → auto-blocked
```

---

## STDB Table Reference

All tables live in the `kanban` database on SpacetimeDB v2.6.1. The TypeScript table definitions in `web/src/stdb/*_table.ts` are the authoritative schema. Reducers are defined in the Rust WASM module (`server/spacetimedb/`).

### Core Tables

| Table | TypeScript Definition | Purpose | Key Columns |
|---|---|---|---|
| **tasks** | `tasks_table.ts` | Primary task storage | id, title, description, priority, status, assigned_to, repo, branch, roadmap_item, depends_on, required_skills, fail_count, max_attempts, fail_reason, subtask_of, subtasks, due_by, sprint, archived, estimated_hours, spent_hours, created_by, created_at, updated_at, position, score |
| **task_logs** | `task_logs_table.ts` | Activity log for each task | id, task_id, action, agent_id, notes, timestamp |
| **swarm_agents** | `swarm_agents_table.ts` | Registered agent directory | id, host, capabilities, repo_focus, current_task_id, status, last_heartbeat, first_seen |

### Labeling & Comments

| Table | Definition | Purpose |
|---|---|---|
| **kanban_labels** | `kanban_labels_table.ts` | Label definitions | id, name, color, description, created_at |
| **task_label_assignments** | `task_label_assignments_table.ts` | M:N task ↔ label mapping | task_id, label_id |
| **task_comments** | `task_comments_table.ts` | Comments on tasks | id, task_id, author, body, created_at |
| **task_checklists** | `task_checklists_table.ts` | Checklist items | id, task_id, text, completed, position, created_at |

### Task Relations & Dependencies

| Table | Definition | Purpose |
|---|---|---|
| **task_relations** | `task_relations_table.ts` | General task ↔ task relations (blocks, blocked_by, relates_to, duplicates) | id, task_id, related_task_id, relation_type, created_at |

**Note:** The `depends_on` column on `tasks` is the primary dependency mechanism checked at claim time. `task_relations` provides richer relation types for display and analysis.

### Webhooks

| Table | Definition | Purpose |
|---|---|---|
| **webhook_subscriptions** | `webhook_subscriptions_table.ts` | Configured webhook endpoints | id, url, type, events, label, active, created_at |
| **webhook_deliveries** | `webhook_deliveries_table.ts` | Delivery history | id, webhook_id, event, status, response_code, delivered_at |

### Projects

| Table | Definition | Purpose |
|---|---|---|
| **kanban_projects** | `kanban_projects_table.ts` | Registered projects/repos | id, name, description, color, priority, active, created_at, updated_at |

### Issues (GitHub Sync)

| Table | Definition | Purpose |
|---|---|---|
| **issue_links** | `issue_links_table.ts` | Kanban task ↔ GitHub issue mapping | task_id, repo, issue_number, issue_url, html_url, status, created_at |

### Automation

| Table | Definition | Purpose |
|---|---|---|
| **automation_rules** | `automation_rules_table.ts` | Event-triggered automation rules | id, name, description, trigger_event, condition, action_type, action_config, repo, active, created_at, updated_at |
| **automation_rule_logs** | `automation_rule_logs_table.ts` | Rule execution history | id, rule_id, trigger_event, result, details, created_at |

### Tasks Templates

| Table | Definition | Purpose |
|---|---|---|
| **task_templates** | `task_templates_table.ts` | Recurring task templates | id, title, description, priority, repo, roadmap_item, required_skills, cron_schedule, created_by, created_at, last_triggered_at, active |

### Dispatcher & API Keys

| Table | Definition | Purpose |
|---|---|---|
| **dispatcher_state** | `dispatcher_state_table.ts` | Task dispatcher internal state | key, value |
| **api_keys** | `api_keys_table.ts` | API key authentication | id, key_hash, name, repo_scope, permissions, created_by, created_at, last_used_at, active |

### Schema Migrations

| Table | Definition | Purpose |
|---|---|---|
| **schema_migrations** | `schema_migrations_table.ts` | Database migration tracking | version, description, applied_at, applied_by, checksum |

### Reducers (Rust WASM)

The STDB module at `server/spacetimedb/` compiles to WASM and defines all reducers. TypeScript proxy reducers in `web/src/stdb/*_reducer.ts` mirror the Rust definitions for frontend use.

Key reducers: `add_task`, `claim_task`, `complete_task`, `block_task`, `block_task_with_reason`, `unclaim_task`, `update_task`, `delete_task`, `archive_task`, `unarchive_task`, `add_comment`, `delete_comment`, `add_checklist_item`, `toggle_checklist_item`, `remove_checklist_item`, `reorder_checklist_items`, `set_dependency`, `set_due_by`, `set_sprint`, `set_time_estimates`, `set_task_skills`, `set_max_attempts`, `split_task`, `add_label`, `update_label`, `remove_label`, `assign_label_to_task`, `unassign_label_from_task`, `batch_assign_labels`, `batch_unassign_labels`, `reorder_task`, `bulk_reorder_tasks`, `add_log`, `register_agent`, `agent_heartbeat`, `set_agent_capabilities`, `add_project`, `update_project`, `delete_project`, `add_webhook_subscription`, `update_webhook_subscription`, `remove_webhook_subscription`, `log_webhook_delivery`, `link_issue`, `unlink_issue`, `update_issue_link_status`, `create_automation_rule`, `update_automation_rule`, `delete_automation_rule`, `add_task_relation`, `remove_task_relation`, `seed_sample_tasks`, `trigger_task_templates`, `record_migration`, `create_api_key`, `revoke_api_key`, `reset_fail_count`, `set_dispatcher_state`, `delete_dispatcher_state_row`, `add_task_template`, `update_task_template`, `remove_task_template`, `toggle_archive`.

---

## Scheduler Reference

All loops run as `asyncio.create_task()` inside the FastAPI process. Intervals are configurable via environment variables.

| Loop | Interval | Config Key | Default | Description |
|---|---|---|---|---|
| **task_dispatcher** | 5s | `dispatcher_interval_seconds` | `5` | Claims available tasks by priority, spawns worker subprocesses up to `max_workers`. Checks memory pressure before claiming. |
| **stale_watcher** | 120s | `stale_check_interval_seconds` | `120` | Unclaims tasks stuck `in_progress` > `stale_minutes` (45) without heartbeat. Force-releases after 60 min regardless. |
| **dead_board_monitor** | 3600s | `dead_board_interval_seconds` | `3600` | Detects zero-throughput board (0 completions in 1h with work present). Fires webhook alert. Never kills active workers. |
| **metrics_collector** | 900s | `metrics_interval_seconds` | `900` | Snapshots board metrics, fires `metrics.snapshot` webhook, triggers low-backlog check. |
| **template_trigger** | 900s | `template_interval_seconds` | `900` | Calls `/api/task-templates/trigger` to create recurring tasks per cron schedule. |
| **repo_scanner** | 1800s | `scanner_interval_seconds` | `1800` | Runs all scanners (TODO, unused code, deps, security, etc.) via `run_all_scanners()`. |
| **improver (self_improver)** | 3600s | `improver_interval_seconds` | `3600` | Checks server health, board health, stale tasks, git status, cycling tasks. Creates improvement tasks. |
| **zombie_cleaner** | 1800s | (always runs) | `1800` | Archives tasks at `max_attempts` (fail_count >= max_attempts) that can never be worked again. |
| **worker_death_watcher** | 15s | (always runs) | `15` | Detects crashed/exited worker subprocesses. Handles crash-on-launch (blocks after 3x) and hung workers (>KANBAN_LLM_TIMEOUT+300s). |
| **task_archiver** | 3600s | (always runs) | `3600` | Archives old done (>7d), blocked (>24h), and seed (>24h) tasks. Also retries stuck blocked tasks without fail_reason. |
| **_task_fountain_loop** | 60s | (always runs) | `60` | Fast task-creation loop running `_task_fountain.py` as subprocess to keep workers fed. |
| **_recover_stale_tasks** | once | (startup) | — | One-shot on server startup: unclaims any tasks left `in_progress` from a previous lifecycle. Retries up to 3x if API unavailable. |

### Startup Sequence

```
1. FastAPI lifespan startup
2. Wait for STDB gateway (:3001) — retry up to 30x
3. Create database if 404
4. Start all scheduler loops as asyncio tasks
5. Recover stale tasks (in_progress from previous lifecycle)
6. Seed initial workers (if worker_script configured)
7. Accept HTTP requests
```

---

## MCP Integration

The MCP server (`server/mcp_server.py`) runs on **stdio transport** for native Hermes Agent integration. It exposes 36 tools:

| Category | Tools |
|---|---|
| **Task Lifecycle** (9) | `kanban_list_tasks`, `kanban_get_task`, `kanban_create_task`, `kanban_update_task`, `kanban_claim`, `kanban_complete`, `kanban_block`, `kanban_block_with_reason`, `kanban_unclaim` |
| **Task Management** (4) | `kanban_delete_task`, `kanban_set_dependency`, `kanban_set_skills`, `kanban_split_task` |
| **Suggestions** (2) | `kanban_suggest`, `kanban_suggest_by_project` |
| **Agents** (4) | `kanban_list_agents`, `kanban_register_agent`, `kanban_heartbeat`, `kanban_set_capabilities` |
| **Projects** (5) | `kanban_list_projects`, `kanban_add_project`, `kanban_update_project`, `kanban_delete_project` |
| **Logs** (2) | `kanban_add_log`, `kanban_get_logs` |
| **GitHub Issues** (4) | `kanban_issue_link`, `kanban_issue_create`, `kanban_issue_status`, `kanban_issue_list` |
| **Comments** (3) | `kanban_add_comment`, `kanban_list_comments`, `kanban_delete_comment` |
| **Checklists** (3) | `kanban_add_checklist_item`, `kanban_list_checklist`, `kanban_toggle_checklist_item`, `kanban_remove_checklist_item` |

**Total: 36 tools.**

The MCP server uses `urllib` (not httpx) for API calls to avoid event loop conflicts with Hermes' own asyncio loop. It auto-registers Hermes in the swarm on startup.

---

## Testing & Quality

| Layer | Count | Framework | Location |
|---|---|---|---|
| Python tests | 449 | pytest (asyncio_mode=auto) | `server/tests/*.py` |
| Frontend tests | 188 | Vitest + Testing Library | `web/src/__tests__/*.tsx` |
| E2E tests | — | Playwright | `web/e2e/*.spec.ts` |

### Python Test Coverage

| Test File | Focus |
|---|---|
| `test_api.py` | REST API endpoints |
| `test_main.py` | Server startup, lifespan, middleware |
| `test_scheduler.py` | All scheduler loops |
| `test_scheduler_helpers.py` | Scheduler utility functions |
| `test_scheduler_low_backlog.py` | Low-backlog detection |
| `test_models.py` | Pydantic model validation |
| `test_shared.py` | STDB helpers, SATS parser |
| `test_mcp_server.py` | MCP tool functions |
| `test_webhooks.py` | Webhook subscription management |
| `test_webhook_dispatcher.py` | Webhook event dispatch |
| `test_auth.py` | Authentication |
| `test_config.py` | Settings/configuration |
| `test_analytics.py` | Analytics endpoints |
| `test_issue_sync.py` | GitHub issue sync |
| `test_integration_stdb.py` | STDB integration |
| `test_e2e_http.py` | End-to-end HTTP |
| `test__fast_seed.py` | Fast seed utility |
| `test__task_fountain.py` | Task fountain |
| `test_workers_base.py` | Base worker |
| `test_workers_llm.py` | LLM worker |
| `test_workers_mechanical.py` | Mechanical worker |
| `test_workers_run.py` | Worker entry point |
| `test_responses.py` | Response serialization |

### Linting & Formatting

- **Python:** Ruff (select: E, F, W, I, N, UP, B, SIM, S)
- **TypeScript:** ESLint + Prettier
- **Pre-commit:** `.pre-commit-config.yaml`

---

## Configuration

All configuration is via environment variables (or `.env` file), loaded by `server/config.py` using `pydantic-settings`.

| Variable | Default | Description |
|---|---|---|
| `STDB_HOST` | `localhost` | SpacetimeDB host |
| `STDB_PORT` | `3001` | SpacetimeDB port |
| `STDB_DB` | `kanban` | Database name |
| `SERVER_PORT` | `8727` | FastAPI server port |
| `CORS_ORIGIN` | `http://localhost:4444` | Allowed CORS origin |
| `API_KEY` | `""` | API key for auth on mutations |
| `SCHEDULER_ENABLED` | `true` | Enable scheduler loops |
| `DISPATCHER_INTERVAL_SECONDS` | `5` | Task dispatcher interval |
| `STALE_CHECK_INTERVAL_SECONDS` | `120` | Stale watcher interval |
| `DEAD_BOARD_INTERVAL_SECONDS` | `3600` | Dead board monitor interval |
| `TEMPLATE_INTERVAL_SECONDS` | `900` | Template trigger interval |
| `METRICS_INTERVAL_SECONDS` | `900` | Metrics collector interval |
| `SCANNER_INTERVAL_SECONDS` | `1800` | Repo scanner interval |
| `IMPROVER_INTERVAL_SECONDS` | `3600` | Self-improver interval |
| `WORKER_COMMAND` | `python3` | Worker subprocess command |
| `WORKER_SCRIPT` | `""` | Worker script path |
| `WORKER_ARGS` | `""` | Worker extra args |
| `MIN_WORKERS` | `2` | Minimum worker pool |
| `MAX_WORKERS` | `8` | Maximum worker pool |
| `STALE_MINUTES` | `45` | Stale task threshold |
| `AGENT_ID` | `hermes` | This server's agent identity |
| `WEBHOOK_DEFAULT_URL` | `""` | Default webhook destination |
| `GITHUB_TOKEN` | `""` | GitHub API token |

---

## Deployment

### Docker (Recommended)

Multi-stage build (`Dockerfile`):
1. **Stage 1:** Build React frontend (Node 20)
2. **Stage 2:** Build STDB WASM module (Rust 1.93)
3. **Stage 3:** Python 3.12 runtime with `spacetime` CLI

```bash
docker build -t spacetime-kanban .
docker run -p 8727:8727 -p 3001:3001 spacetime-kanban
```

### Manual

```bash
# Start SpacetimeDB
spacetime start

# Build frontend
cd web && npm install && npm run build && cd ..

# Start server
cd server && python main.py
```

### docker-compose.yml

Provides both STDB (`spacetime/standalone:latest`) and the kanban server, with health checks.

---

## Security

- **SSRF protection:** Webhook URLs validated against private IP ranges, internal hostnames, and non-HTTPS schemes (`shared.py:validate_webhook_url`)
- **SQL injection:** Single-quote sanitisation via `_sanitize()` in all parameterised queries
- **API key auth:** Optional `API_KEY` env var; validated via `verify_auth` dependency
- **Security headers:** CSP, X-Frame-Options, HSTS, X-Content-Type-Options set via middleware
- **Branch validation:** Regex `{type}/kanban-{id}--{slug}` enforced for git branches

---

## Glossary

| Term | Definition |
|---|---|
| **STDB** | SpacetimeDB — the database engine |
| **Reducer** | STDB atomic state mutation (like a stored procedure, but sequential) |
| **SATS** | SpacetimeDB Algebraic Type System — the JSON encoding for STDB data |
| **MCP** | Model Context Protocol — the protocol for AI ↔ tool integration |
| **Worker** | A subprocess spawned by the server to execute a claimed task |
| **Zombie task** | A task at max_attempts (fail_count >= max_attempts) that can never be retried |
| **Dead board** | Zero task completions in the last hour despite available work |
