# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed
- Worker dispatch now excludes archived tasks: every scheduler fetch of available tasks (`task_dispatcher`, `_seed_initial_workers`, `zombie_cleaner`, `self_improver`) passes `archived=false`. Archived tasks are removed from the active board and must never be re-dispatched — previously they stayed status=available and workers burned turns on them. STDB `claim_task` reducer also rejects archived tasks (defense in depth; deploys on next module republish).
- `scanner/gaps.py` test-gap matcher no longer produces false positives: a module is covered if any test file matches `test_{module}.py`, `test_{parent}_{module}.py` (this repo's nested convention, e.g. `workers/llm.py` → `test_workers_llm.py`), or imports the module (grouped test files like `test_scanner_modules.py`). Previously modules that WERE tested got flagged as untested, creating junk tasks workers would burn turns on.
- Scanner runner now self-cleans: available scanner tasks whose finding no longer exists are blocked + archived automatically (complement to the regressed-done re-opener). Stops stale junk tasks from lingering on the board indefinitely.
- `stale_watcher` now auto-fixes stale workers silently: kills the lingering worker process before unclaiming (prevents duplicate workers on re-claimed tasks) and never fires a webhook alert — stale worker remediation is fully automatic with no operator notification
- `stale_watcher` never releases a worker that is alive AND heartbeating — LLM workers legitimately run up to `KANBAN_LLM_TIMEOUT` (60 min default); the old 60-min force-release spawned duplicate workers on the same task
- Removed the `worker.stale` webhook event + alert-dedup machinery (`_should_alert_stale`, `_stale_alerted_tasks`) from `scheduler.py` and `webhook_dispatcher.py`

### Added
- Auto-star on first install: when `GITHUB_TOKEN` is configured, the server stars the project's GitHub repo once on startup (best-effort, opt-out via `AUTO_STAR_ENABLED=false`). Skips if already starred or if the authenticated user is the repo owner. Repo taken from `GITHUB_DEFAULT_REPO` or detected from git origin. Covered by `tests/test_auto_star.py` (28 tests).
- Python test count: 299→449 (+150 tests across 8 sessions)
  - 35 scheduler helper tests (API wrappers, worker lifecycle, crash detection)
  - 27 issue_sync tests (sanitize, parse, SQL generation, link/unlink)
  - MCP server test fix: rewritten for MCP SDK v2.0.0 (MCPServer + Tool.from_function API)
  - 8 Worker run CLI routing/parsing tests
  - 6 Analytics endpoint structure tests
- Frontend test coverage expanded: 90→188 tests (13 files)
  - AgentHealthPage: 27 tests (formatDuration, loading, error, empty, stat bar, refresh, navigation)
  - LogsPage: 18 tests (relativeTime, filters, pagination, stats, event distribution, clear, load more)
  - WebhooksPage: 13 tests (CRUD, delete confirmation, create form, deliveries)
  - LabelsPage: 16 tests (CRUD, edit, delete with confirm, create form, toast errors)
  - SchemaMigrationsPage: 12 tests (CRUD, form validation, success/error messages, table rendering)
  - IssuesPage: 12 tests (loading, rendering, filtering by repo/issue number, error/empty states)

### Fixed
- **Junk-task generator** (`scheduler_low_backlog._generate_improvement_tasks`): now only creates tasks from *actionable* headings. Previously every `## ` heading in IMPROVEMENTS.md/PERFORMANCE.md/SCHEMA_EVOLUTION_POLICY.md became a task — so structural sections ("Recently Completed", "Deferred / Blocked", "Status: PENDING", "Summary", "Research Log") and done/deferred items were seeded as kanban tasks that workers burned LLM turns on. New `_extract_actionable_headings()` filters by priority markers (P0-P3), action verbs, strong action signals, and section context; skips status/emoji/completed/deferred headings. Covered by 12 new tests.
- **Worker verification gate** (`workers/llm.py`): an LLM worker that reports `WORKER_DONE` must now pass the repo's test suite before the task is marked done (`_verify_repo_tests`). A completion whose change breaks the tests is rejected as blocked. Configurable via `KANBAN_VERIFY_TESTS` / `KANBAN_VERIFY_TESTS_TIMEOUT`. Detectable harnesses: Makefile `test`, Cargo.toml, pytest, vitest/jest. Covered by 13 new tests.
- **Worker worktree isolation** (`workers/base.py`): each task worker now runs in its own git worktree (`~/<repo>-kanban-<task-id>` on branch `kanban/<task-id>`) instead of the main clone, so concurrent agents never collide on the same files. Graceful fallback to the main clone when worktrees aren't possible; teardown (push + remove + prune) on completion. Configurable via `KANBAN_WORKTREE`. Covered by 7 new tests.
- Docker entrypoint: STDB v2.6.1 CLI flags (`-b` instead of `-f`), health endpoint `/v1/health`
- Bare `except: pass` replaced with proper error logging in all route handlers
- CI/CD branch triggers: `develop`→`main` in all workflow files
- Duplicate health endpoints removal, dead section header cleanup
- MCP server: rewritten for SDK v2.0.0 (`@app.list_tools()` removed)
- Scanner `test_gaps.py` renamed to `gaps.py` to prevent pytest misidentification

### Changed
- **Project renamed `spacetimedb-kanban` → `spacetime-kanban`** (repo, Python package,
  FastAPI title, MCP server name, Cargo crate, WASM artifact `spacetime_kanban.wasm`,
  Docker container names, docs, tests). GitHub remote is now
  `github.com/omiinaya/spacetime-kanban`.
- Task fountain / seed repos now configurable via `KANBAN_REPOS` (comma-separated;
  default: just `spacetime-kanban`) instead of a hardcoded repo list.
- `GET /api/api-keys` gated behind the same `verify_auth` check as mutations
  (open in demo mode, requires `X-API-Key` when `API_KEY` is set).
- Docs refreshed to match the current codebase: env defaults, scheduler loop
  inventory (12 loops), route modules, CLI commands, test counts.
- Backend test count: 449 → **1,600** passing (+21 skipped); frontend 188 → **194**.
- ROADMAP.md: updated test count to 449+, expanded Round 8 section
- CHANGELOG.md: structured format, added Round 8 entries
- `requirements.txt` minimums synced to `pyproject.toml` (fastapi≥0.115.0, uvicorn≥0.30.0, httpx≥0.27.0)
- tsconfig.json: exclude `src/__tests__` from tsc (vitest handles test file types)
- 72 files reformatted with `ruff format` for consistent style
- Dockerfile: pinned STDB to `v2.6.1`

## Phase 1 — Core Foundation
- SpacetimeDB module: `tasks` table + atomic claim reducers
- FastAPI REST backend at :8727
- React + shadcn web dashboard
- AGENTS.md with complete API guide
- Basic kanban board UI

## Phase 2 — Multi-Agent UX
- WebSocket live-updates for the board (via STDB native sub)
- Agent heartbeat — detects stuck tasks (>30min no activity)
- Auto-unclaim stale tasks back to available
- Discord webhook notifications on task state changes
- Task dependencies / ordering

## Phase 3 — Workflow & Integration
- Git branch naming convention enforcement
- Webhook integration — Discord notifications
- Roadmap import — bulk-create tasks from ROADMAP.md
- GitHub PR linking — auto-update tasks

## Phase 4 — Intelligence
- Priority scoring engine
- Swarm mode — auto-discover agents
- Agent capability tags with skill matching

## Phase 5 — Detail & UX
- Task detail modal with logs, dependencies
- Create task dialog with skills field
- Dependency graph visualization (SVG DAG)

## Phase 6 — Agent Daemon
- `kanban watch` foreground/daemon lifecycle manager
- Graceful shutdown with PID file cleanup
- Real-time status output

## Phase 7 — Native Hermes Integration
- MCP server: 36 tools covering full kanban API
- `add_log` STDB reducer + POST /api/tasks/{id}/log endpoint
- Hermes swarm registration with capability tags
- Auto-heartbeat cron

## Phase 8 — Web Dashboard Evolution
- Search bar with multi-field filtering
- Search-aware empty state
- Combined repo + search filtering

## Phase 9 — Analytics & Cycle Time
- Overview dashboard with status distribution
- Throughput chart (14-day SVG bar chart)
- Repo breakdown with stacked status bars
- Cycle time metrics (average/min/max hours)
- Agent performance per-agent completed/blocked

## Phase 10 — Autonomous Workflow
- `kanban dispatch` CLI command
- Skill-filtered auto-claim dispatch cron
- Generic outbound webhook system (Discord, Slack, Telegram, generic JSON)
- Webhook CRUD API + CLI
- GitHub issue sync

## Phase 11 — Web UI for GitHub Integration
- GitHub issue section in task detail modal
- Issues page with repo filter, search, status
- MCP issue tools

## Phase 12 — STDB-Native Infrastructure
- Migrate webhooks + issue links from JSON files to STDB tables
- Full STDB reducers for webhook + issue CRUD

## Phase 13 — CI & Test Infrastructure
- GitHub Actions CI pipeline
- E2E test fixes
- All 9 E2E tests passing

## Phase 14 — Webhook Management UI
- Webhook CRUD UI with test endpoint
- Sidebar nav item for webhooks

## Phase 15 — Agent Health Dashboard
- Agent health endpoint + UI page
- Auto-refresh every 15s

## Phase 16 — Drag & Drop Kanban Board
- DnD between columns with smart transitions
- Visual feedback on drag over

## Phase 17 — Task Export
- CSV/JSON export with Content-Disposition headers
- Export buttons on board + analytics pages

## Phase 18 — Bulk Operations
- Select mode with checkboxes
- Action bar for bulk claim/complete/block/release/reassign/delete

## Phase 19 — Compact Card View
- Priority-colored left border cards
- Layout toggle between compact/detailed

## Phase 20 — Advanced Filters
- Priority, assignee, label filter multi-select
- Compound filtering with search + repo

## Phase 21 — Labels/Tag System
- STDB-native labels with color palette
- Label assignment in detail modal
- Label filter with color-highlighted toggles
- Labels management page

## Phase 22 — Enhanced Activity Log
- Multi-filter activity log (action, agent, date)
- Stats bar with active agent counts
- Click-to-filter from breakdown

## Phase 23 — Keyboard Shortcuts
- n, s, c, f, b, g, e, 1-4, ?
- Esc progressive close
- Smart suppression in inputs

## Phase 24 — Webhook Delivery Log
- STDB webhook_deliveries tracking table
- Expandable delivery history per webhook

## Phase 25 — Batch Label Assignment
- STDB reducers for batch assign/unassign
- Label picker popover in bulk bar

## Phase 26 — Quick Add to Column
- + button per column header
- Inline title input with Enter to confirm
- Auto-claim for In Progress column

## Phase 27 — Saved Filter Views
- Save/restore filter combinations in localStorage
- Clickable filter view pills

## Phase 28 — Issue Badges on Task Cards
- Issue number badges on compact + detail cards
- Color-coded open/closed status
- Click-through to GitHub

## Phase 29 — Task Templates
- 7 built-in templates (Bug, Feature, Refactor, Chore, Docs, Perf, Security)
- Template picker with pre-fill and icon

## Phase 30 — Task Comments
- STDB task_comments table
- Comment section in TaskDetailDialog
- MCP comment tools

## Phase 31 — Task Checklists / Subtasks
- STDB task_checklists table with position/completed
- Checklist section with progress counter
- Cascade cleanup on task delete

## Phase 32 — Custom Task Order
- position field with optional ordering
- Within-column drag reorder
- Sequential positions (100 spacing)

## Bug Fixes & Polish
- PR webhook title overwrite fix
- create_task race condition fix (pre-generated UUIDs)
- Vite dev proxy port fix (8725→8727)
- Seed endpoint added
- Throughput chart real date labels
- Auto-refresh on analytics/issues/logs pages
- Activity log HH:MM timestamps
- Live toast notifications for state changes
- Analytics SQL aggregation fix (STDB v2.6.1 compat)
- Board snapshot webhook completions field added
- Worker test coverage (0% → ~85%)
- MCP server test unskipped (1→9 passing)
- Import path consistency fix
