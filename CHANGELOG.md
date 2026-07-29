# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Improved
- CHANGELOG.md, LICENSE, .coveragerc added
- Dockerfile STDB version corrected to v2.6.1
- Stale planning files removed
- Scanner tests discovered in test collection
- CI/CD workflows: branch triggers corrected, removed stale deps, consistent working-directory
- ROADMAP.md updated: test count 387, Round 8 section

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
