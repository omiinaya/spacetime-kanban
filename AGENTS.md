---
name: SpacetimeKanban
description: "Atomic multi-agent kanban on SpacetimeDB — shared task coordination for AI agents with atomic claiming and state machine"
stack: [python, fastapi, react, typescript]
ports:
  api: 8727
  stdb: 3001
deps: [python3, node, npm, spacetime]
stdb: true
---

# Agent Onboarding Guide

This file is read by AI coding agents. For Claude Code specifically, also see [CLAUDE.md](./CLAUDE.md).

**Complementary documentation:**
- [INSTALL.md](./INSTALL.md) — Full installation guide (Docker, manual, production)
- [CONFIGURATION.md](./CONFIGURATION.md) — All environment variables explained
- [API.md](./API.md) — Complete REST API reference
- [ARCHITECTURE.md](./ARCHITECTURE.md) — System architecture and data flow
- [MCP.md](./MCP.md) — MCP server docs for Hermes integration
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) — Common issues and solutions

## 📌 Architecture (Jul 2026)

This kanban server is **fully self-contained** — no external cron jobs. The server-side scheduler replaces all cron jobs with asyncio background tasks running inside the FastAPI process:

| Loop | Interval (default) | Purpose |
|------|--------------------|---------|
| `task_dispatcher` | 5s | Keeps the worker pool filled (`min_workers`–`max_workers`) |
| `stale_watcher` | 120s | Releases `in_progress` tasks stuck past `STALE_MINUTES` |
| `dead_board_monitor` | 3600s | Detects a stalled board and auto-remediates |
| `metrics_collector` | 900s | Snapshot metrics + backlog triggers |
| `repo_scanner` | 1800s | Runs code-quality scanners, creates improvement tasks |
| `template_trigger` | 900s | Processes task templates |
| `worker_death_watcher` | 15s | Restarts crashed worker subprocesses |
| `zombie_cleaner` | 1800s | Blocks/archives tasks at `max_attempts` |
| `task_archiver` | 3600s | Archives completed/stale tasks |
| `blocked_remediator` | 3600s | Audits + archives un-actionable blocked tasks |
| `self_improver` | 3600s | Health checks, codebase audits, improvement tasks |
| `_task_fountain_loop` | 60s | Fast board-health check + generic seed tasks |

All intervals are configurable via environment variables (see `CONFIGURATION.md`).

See `server/.env.example` for configuration. Alerts fire via webhook to Discord.

This kanban coordinates **multiple AI agents** working on the same repo's roadmap simultaneously. Each agent claims tasks atomically via the REST API — no two agents can grab the same task.

## 🆕 Schema Migrations Page

A dedicated **Schema Migrations** page is available at `/schema-migrations` (nav item: "Migrations" with Database icon). It lists all recorded schema migrations with their applied status, description, and timestamps. Accessible via the sidebar.

**API Endpoint:**
```http
GET http://localhost:8727/api/schema-migrations
```

## 🆕 Shared Skeleton Components

The frontend uses a shared `Skeleton.tsx` component library for consistent loading states across all 14 pages:

| Skeleton | Usage |
|----------|-------|
| `CardSkeleton` | Placeholder for a single task card |
| `CompactCardSkeleton` | Placeholder for compact view cards |
| `TableRowSkeleton` | Placeholder for table/list rows |
| `ColumnSkeleton` | Column with N card skeletons (default 5) |
| `ListViewSkeleton` | Full-page list view loading state |
| `KanbanBoardSkeleton` | Full kanban board loading state (4 columns) |
| `PageSkeleton` | Generic page loading state with N rows (default 6) |

Pages like SchemaMigrationsPage, WebhooksPage, IssuesPage, AnalyticsPage, LabelsPage, LogsPage, AgentHealthPage, and others all use these skeletons for consistent loading UX.

## How to Use (for Agents)

### 1. Get Available Tasks
```http
GET http://localhost:8727/api/tasks?status=available&repo=my-repo
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
  "repo": "my-repo",
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

1. **Poll sparingly** — `GET /api/tasks?status=available` every 30s max
2. **Claim immediately** when you see a task you want — don't read the full description first
3. **Release promptly** if you claim something you can't handle — `POST /unclaim`
4. **Stay in your lane** — stick to tasks assigned to you; respect others' claims
5. **Update branch field** early so the other agent knows where you're working

## Scanner System

Improvement scanners run automatically every 1800s via the scheduler's `repo_scanner` loop.
They create kanban tasks for code quality issues. Key behaviors:

- **Per-repo batching** — findings are grouped per repo, not per file. Instead of 8 separate
  unwrap() tasks, you get 1 task listing all files.
- **Test-gap matching is smart** — `gaps.py` treats a module as covered if any test file
  matches `test_{module}.py`, `test_{parent}_{module}.py` (nested convention, e.g.
  `workers/llm.py` → `test_workers_llm.py`), or imports the module (grouped test files
  like `test_scanner_modules.py`). No more false-positive "untested" tasks for code that
  has tests.
- **Self-cleaning** — each scan pass also closes stale *available* tasks: if a task was
  never claimed but its originating scanner no longer reports the finding, it's blocked +
  archived automatically. Works in reverse of the regressed-done re-opener to keep the
  board free of junk.
- **Find-only scanners** — unwraps, bare excepts, stale TODOs, large files, missing
  `__init__.py`, test gaps, and dep review tasks have `skip_verify=True`. They're
  created once and never re-opened by the verifier, preventing infinite loops.
- **Auto-fix scanners** — unused imports (ruff), STDB indexes, and CI pipeline tasks
  do NOT have `skip_verify=True`. The mechanical worker actually fixes them, so
  re-verification checks that the fix persists.
- **Layer progression** — L0=stdb_index, L1=todos/deps/unused_code/test_gaps,
  L2=architecture, L3=docs_ci, L4=prod_readiness. L3+ scanners always run
  regardless of lower-layer completion.
- **Task fountain** (`_task_fountain.py`) runs every 60s as a fast board-health check.
  Only creates generic seed tasks when available tasks drop below 3.
  Dedup covers the WHOLE board: it fetches every task per-repo (`GET /api/tasks?repo=X&limit=100000`,
  all statuses at once) — the old per-status `limit=200` capped dedup at 800 titles and
  let old duplicates (16x "Review my-repo…") slip through. If any repo query fails
  the run aborts (an incomplete dedup set is what created duplicates). The health check
  is gated ONCE per run and emits at most ONE review task per run (not one per repo),
  and API timeouts are 60s (board queries take 30s+ under load; the scheduler's
  subprocess timeout is 120s).

### Scanner layers

| Layer | Scanners | skip_verify | Can auto-fix? |
|-------|----------|-------------|---------------|
| L0 | stdb_index | No | Yes (adds #[index(btree)]) |
| L1 | todos, deps, unused_code, test_gaps | Mostly Yes | No (report only) |
| L2 | architecture | Yes | No (report only) |
| L3 | docs_ci | Yes | Partially (file stubs) |
| L4 | prod_readiness | Yes | No (human judgment) |

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

The server-side scheduler's `stale_watcher` loop runs every **120 seconds** (default) and checks for tasks stuck `in_progress` for **>45 minutes** (`STALE_MINUTES`, default) with no heartbeat. It **auto-fixes silently**: it kills any lingering worker process (so it can't keep working on a re-claimed task) and releases the task back to `available`. It does **not** fire a webhook alert — stale workers are remediated automatically, with no operator notification.

A worker that is **alive and heartbeating is never released**, no matter how old the claim is — LLM workers legitimately run up to `KANBAN_LLM_TIMEOUT` (60 min default), and force-releasing a still-beating worker previously caused the dispatcher to spawn a duplicate worker on the same task.

## Dead Board Auto-Remediation

The `dead_board_monitor` loop runs every **60 minutes** (default `DEAD_BOARD_INTERVAL_SECONDS=3600`) and:
1. Checks if the board has 0 completions in the last hour while work exists
2. **Auto-remediates** by restarting the server (systemd auto-restart)
3. If restart fails to restore throughput, fires a `BOARD_DEAD` webhook alert

This replaces the old alert-only pattern — now alerts only fire when auto-remediation fails.

## Self-Improvement Agent

The `self_improver` loop runs every **1 hour** (default `IMPROVER_INTERVAL_SECONDS=3600`) and:
1. Checks server health → auto-restarts if down
2. Scans board health (blocked tasks, stale in_progress, cycling tasks)
3. Auto-fixes definitive-failure tasks (reduces max_attempts to 1)
4. Creates improvement tasks on the board for deeper issues
5. Reports findings to server logs

This runs inside the server process — no external cron jobs needed.

This means:
- If an agent claims a task and disappears, it gets reclaimed within ~35 minutes max
- If you're actively working on a long task, send heartbeats via `POST /api/agents/{agent_id}/heartbeat` to keep the task alive
- On server restart, `_recover_stale_tasks()` immediately unclaims any `in_progress` tasks from the previous lifecycle — no tasks get permanently stuck
- The watchdog is fully silent: stale workers are killed and their tasks released automatically, with no webhook alerts fired

## Worker Isolation & Verification

Workers are [self-improvement machine](README.md#-features) agents that scan, fix, verify,
test, and document — with two guards that keep the "machine" honest:

- **Worktree isolation (default on):** each task worker runs in its own git worktree
  (`~/<repo>-kanban-<task-id>`) on branch `kanban/<task-id>`, so concurrent elves never
  collide in the main clone. If worktrees are unavailable (non-git repo, no origin), the
  worker degrades to the main clone. Disable with `KANBAN_WORKTREE=0`.
- **Test verification gate (default on):** when an LLM worker reports completion
  (`WORKER_DONE`), the worker runs the repo's test suite (`make test`, `cargo test`,
  pytest, or vitest/jest) and only marks the task done if it passes. A completion that
  breaks the repo's tests is rejected as blocked — so "improvements" must actually work.
  Configure with `KANBAN_VERIFY_TESTS` (enable/disable) and `KANBAN_VERIFY_TESTS_TIMEOUT`.

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
  "repo_focus": "spacetime-kanban"
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
kanban register --capabilities=rust,typescript --repo=my-repo
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
| `kanban info` | Show agent status and connection info |
| `kanban watch` | Watch for work and claim automatically (supports `--daemon`) |
| `kanban dispatch` | Dispatch tasks to workers (supports `--auto`) |
| `kanban webhook list/add/remove` | Manage webhook subscriptions |
|

---

## ✅ Test Coverage (Jul 2026)

**1,600 tests passing** (21 skipped) across 59 test files. Tests cover:

### State Transition Edge Cases
- Complete unclaimed task → 409 Conflict
- Block already-blocked task → 409 Conflict
- Block available task → 409 Conflict
- Claim in-progress task → 409 Conflict
- Complete already-done task → 409 Conflict

### Empty/Invalid Input Handling
- Empty title string, very long title (5000 chars)
- Invalid priority type (string instead of int)
- Duplicate label name, non-existent label assignment

### Analytics with Empty Data
- Throughput (daily zeros when no done tasks)
- Burndown, cycle times, per-agent stats — all return clean zero structures

### Webhook CRUD Edge Cases
- Delete nonexistent webhook → 404
- Test nonexistent webhook → 404
- Webhook deliveries with real data

### Schema Migrations
- List schema migrations via `/api/schema-migrations` alias endpoint
- Record migration with all fields

### Auth Middleware
- PATCH task without API key → 401
- DELETE task without API key → 401
- Claim task without API key → 401

### MCP Error Handling (Fixed)

The MCP server (`server/mcp_server.py`) now uses proper Python exceptions instead of error dicts:

| Before | After |
|--------|-------|
| `try/except` wrapper in `call_tool` returns `{"error": ...}` | `KanbanAPIError(Exception)` propagates to MCP framework |
| MCP returns success with error dict inside | MCP returns `isError: true` responses |
| Silent failures on HTTP errors | Proper exception chains with status codes |

The `KanbanAPIError` class carries both an error message and HTTP status code, allowing the MCP framework to surface errors correctly to the client.

## Fragile Interface Registry

These string-name contracts break silently if renamed. Check both `server/` and `web/` before changing.

| Contract | Location | Type |
|----------|----------|------|
| `GET /api/tasks` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks` | `server/routes/ (see routes/ directory)` | API route |
| `GET /api/tasks/{task_id}` | `server/routes/ (see routes/ directory)` | API route |
| `PATCH /api/tasks/{task_id}` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks/{task_id}/claim` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks/{task_id}/complete` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks/{task_id}/block` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks/{task_id}/unclaim` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/tasks/{task_id}/dependency` | `server/routes/ (see routes/ directory)` | API route |
| `POST /api/webhook/github` | `server/routes/ (see routes/ directory)` | GitHub webhook |
| `status=available\|claimed\|blocked\|done` | `server/routes/ (see routes/ directory)` | Task state machine values |
| `repo` query param | `GET /api/tasks` | Filter parameter |
| `agent_id` | Claim/complete operations | Identity string |
| `hermes`, `claude-vscode`, `ciel` | Convention | Reserved agent IDs |
| `task_*` ID format | Task creation | ID prefix convention |

**Note:** All task-state strings (`available`, `claimed`, `blocked`, `done`) appear in both server code and frontend UI components. Renaming them breaks the state machine.
