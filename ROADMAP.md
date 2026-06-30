# spacetimedb-kanban Roadmap

## Phase 1 — Core Foundation ✅
- [x] SpacetimeDB module: `tasks` table + atomic claim reducers
- [x] FastAPI REST backend at :8727
- [x] React + shadcn web dashboard
- [x] AGENTS.md with complete API guide
- [x] Basic kanban board UI

## Phase 2 — Multi-Agent UX ✅
- [x] WebSocket live-updates for the board (no refresh needed) — via STDB native sub
- [x] Agent heartbeat — detects stuck tasks (claimed but no activity for 30min)
- [x] Auto-unclaim stale tasks back to available
- [x] Discord webhook notifications on task state changes
- [x] Task dependencies / ordering — task B blocked on task A, enforced at claim time

## Phase 3 — Workflow & Integration ✅
- [x] Git branch naming convention enforcement — `kanban check-branch` + pre-push hook
- [x] Webhook integration — Discord notifications on all task state changes
- [x] Roadmap import — bulk-create tasks from a repo's ROADMAP.md (`kanban roadmap-import`)
- [x] GitHub PR linking — auto-update tasks on PR creation/merge (webhook receiver)

## Phase 4 — Intelligence ✅
- [x] Priority scoring — auto-suggest highest-value task based on agent capabilities
- [x] Swarm mode — auto-discover agents on the network
- [x] Agent capability tags — tasks tagged by required skill, agents self-select

## Phase 5 — Detail & UX ✅
- [x] Task detail modal — click card to see full info, logs, dependencies
- [x] Create task dialog — skills field, responsive grid layout
- [x] Dependency graph visualization — full-screen SVG DAG with status colors

## Phase 6 — Agent Daemon ✅
- [x] `kanban watch` — foreground/daemon agent lifecycle manager
- [x] Graceful shutdown — sends offline status, cleans up PID file
- [x] Real-time status output — heartbeat ticks, suggestion picks

## Phase 7 — Native Hermes Integration ✅
- [x] MCP server — 18 tools covering full kanban API (list, create, claim, complete, block, suggest, swarm, logs)
- [x] `add_log` STDB reducer + `POST /api/tasks/{task_id}/log` endpoint
- [x] MCP tools registered in Hermes config — auto-discovered on every session
- [x] Hermes registered in swarm as agent `hermes` with full capability tags
- [x] Auto-heartbeat cron — keeps Hermes alive in the swarm (every 2m, silent)

## Phase 8 — Web Dashboard Evolution ✅
- [x] Search bar — filter tasks by title, description, skills, repo, or ID
- [x] Search-aware empty state — shows "No tasks match X" when filtering
- [x] Combined repo + search filtering

## Phase 9 — Analytics & Cycle Time ✅
- [x] Overview dashboard — total tasks, status distribution, completion rates
- [x] Throughput chart — tasks completed per day (14-day SVG bar chart)
- [x] Repo breakdown — stacked status bars per repository
- [x] Cycle times — average/min/max hours from created to done per repo
- [x] Agent performance — per-agent completed/blocked counts with capability tags
- [x] Server-side analytics endpoints (`GET /api/analytics/overview`, `/throughput`, `/cycle-times`, `/agents`)

## Phase 10 — Autonomous Workflow ✅
- [x] `kanban dispatch` CLI command — scans tasks, scores, auto-claims best match
- [x] Skill-filtered dispatch — matches tasks against agent capabilities
- [x] Auto-dispatch cron — runs every 30m, claims tasks with score >= 100
- [x] `--skills` flag on `kanban create` — set required skills at creation time
- [x] Fix: STDB SQL unsupported ORDER BY/LIMIT in create_task endpoint
- [x] Generic outbound webhook system — Discord, Slack, Telegram, generic JSON
- [x] Webhook CRUD API — `GET/POST/PATCH/DELETE /api/webhooks`
- [x] Webhook CLI — `kanban webhook list/add/remove` with event filtering
- [x] Backward-compatible: legacy `discord_webhook_url` still fires alongside new webhooks
- [x] GitHub issue sync — two-way sync between kanban tasks and GitHub issues

## Phase 11 — Web UI for GitHub Integration ✅
- [x] GitHub issue section in task detail modal — shows linked issue with status + link
- [x] "Create Issue" button in detail modal — creates GH issue from kanban task
- [x] Issues page — dedicated page listing all linked issues with repo filter, search, status
- [x] GitHub Issues nav item in sidebar
- [x] MCP issue tools — kanban_issue_link, kanban_issue_create, kanban_issue_status, kanban_issue_list
- [x] API client methods for issue operations in web frontend

## Phase 12 — STDB-Native Infrastructure ✅
- [x] Migrate webhook subscriptions from `~/.kanban/webhooks.json` → STDB `webhook_subscriptions` table
- [x] Migrate issue links from `~/.kanban/issue_map.json` → STDB `issue_links` table
- [x] STDB reducers: `add_webhook_subscription`, `remove_webhook_subscription`, `update_webhook_subscription`
- [x] STDB reducers: `link_issue`, `unlink_issue`, `update_issue_link_status`
- [x] SQL queries for reads, reducers for writes — consistent with existing architecture
- [x] No ad-hoc JSON files — all persistence in STDB

## Phase 13 — CI & Test Infrastructure ✅
- [x] GitHub Actions CI: Python syntax check, Rust wasm build, Vite frontend build
- [x] E2E test fixes: correct port (8725→8727), proper agents endpoint response format
- [x] All 9 E2E tests passing: health, tasks, atomic claim, claim→complete, block→unclaim, logs, agents, delete

## Phase 14 — Webhook Management UI ✅
- [x] Webhook test endpoint: POST /api/webhooks/{id}/test fires a test ping to verify configuration
- [x] Webhooks API client in frontend (list, get, create, update, delete, test)
- [x] Webhook management page: create form, event toggles, type selector, edit events/label, test button, delete
- [x] Sidebar nav item: Webhooks between GitHub Issues and Activity Log
- [x] Add webhook event definitions for "test" action in all formatters (discord, slack, telegram)

## Phase 15 — Agent Health Dashboard ✅
- [x] Server endpoint GET /api/agents/health: agents joined with current task details, staleness detection (>5min stale)
- [x] Agent Health page: stat cards (online/working/stale), agent grid with capability chips, heartbeat ages
- [x] Current task inline display with click-to-navigate to board
- [x] Auto-refresh every 15 seconds, manual refresh button
- [x] AgentHealth nav item between Webhooks and Activity Log

## Phase 16 — Drag & Drop Kanban Board ✅
- [x] Task cards are draggable between columns (Available, In Progress, Blocked, Done)
- [x] Drop zones with visual feedback: highlighted border + background on drag over
- [x] Smart transitions: drop on Available = unclaim, In Progress = claim, Blocked = block, Done = complete
- [x] Opacity dimming on dragged card, primary ring on drop zone
- [x] "Drag cards between columns" hint in board header

## Phase 17 — Task Export ✅
- [x] Server endpoint GET /api/tasks/export?format=csv|json with status/repo filters
- [x] CSV export: 15-column header, proper Content-Disposition headers
- [x] JSON export: full task objects as array
- [x] Export button with CSV/JSON dropdown on Board page
- [x] Export button with CSV/JSON dropdown on Analytics page

## Phase 18 — Bulk Operations ✅
- [x] Select mode toggle in board header (highlighted when active)
- [x] Checkbox on every task card in select mode
- [x] Fixed bottom action bar: Select all, count display, Clear
- [x] Bulk action buttons: Claim, Complete, Block, Release, Delete
- [x] Sequential batch processing with progress feedback
- [x] Select/deselect all, smart toggle per card

## Phase 19 — Compact Card View ✅
- [x] View toggle button (LayoutGrid/List icons) in board header
- [x] Compact cards: colored priority left border, condensed layout, inline action buttons
- [x] Detailed cards preserved as default view
- [x] Total task count badge next to Board title

## Phase 20 — Advanced Filters ✅
- [x] Collapsible filter bar with Priority multi-select (Urgent/High/Medium/Low)
- [x] Assignee filter with Unassigned option, extracted from task data
- [x] Filters button highlights when active, clear-all button when filters applied
- [x] Compound filtering: search + repo + priority + assignee all stack

## Phase 21 — Labels/Tag System ✅
- [x] STDB-native: `kanban_labels` + `task_label_assignments` tables with full reducers
- [x] Color-coded label management — create, edit, delete with preset color palette
- [x] Label badges on detailed task cards (color pills with name)
- [x] Label dot indicators on compact cards
- [x] Label assignment in task detail modal — click labels to toggle on/off
- [x] Label filter in advanced filters bar — color-highlighted toggle buttons
- [x] Labels management page at /labels with inline editing
- [x] Cascade cleanup — label assignments cleaned on task/label deletion
- [x] Nav item between Board and GitHub Issues
- [x] API: CRUD + task assignment + filter via `label=` query param

## Phase 22 — Enhanced Activity Log ✅
- [x] Server: action/agent/search/date-range/offset filters on GET /api/logs
- [x] Server: GET /api/logs/stats — total/today/agents/action-breakdown
- [x] Stats bar: total events, today count, active agents, top action
- [x] Action type multi-select dropdown with icons
- [x] Agent dropdown filter, search in notes/task IDs
- [x] Date range quick buttons (24h, 7d, 30d, All)
- [x] Load more pagination with offset-based fetching
- [x] Relative timestamps with absolute on hover
- [x] Event distribution breakdown with click-to-filter

## Phase 23 — Keyboard Shortcuts ✅
- [x] n → New task, s// → Search focus, c → Compact, f → Filters, b → Select
- [x] g → Dependency graph, e → Export CSV, 1-4 → Column tabs
- [x] ? → Help modal with all shortcuts listed
- [x] Esc → Progressive close (panel → filters → modals → graph → select)
- [x] Smart suppression when typing in inputs; Esc blurs focused inputs

## Phase 24 — Webhook Delivery Log ✅
- [x] STDB: `webhook_deliveries` table with full tracking (id, webhook_id, event, url, status_code, response_body, success, delivered_at)
- [x] Server: every webhook dispatch logs success/failure with HTTP status and response body
- [x] Server: `GET /api/webhooks/{id}/deliveries` endpoint with limit
- [x] Frontend: expandable delivery history per webhook — status badges, response preview, timestamps
- [x] Lazy-loaded delivery history (fetched on expand, not on page load)

## Phase 25 — Batch Label Assignment ✅
- [x] STDB reducers: `batch_assign_labels` / `batch_unassign_labels` (comma-separated task/label IDs)
- [x] Server: `POST /api/tasks/batch/labels` and `POST /api/tasks/batch/unlabels` endpoints
- [x] Frontend: Labels button in bulk operations bar with label picker popover
- [x] Color-highlighted label toggle with Assign/Remove actions
- [x] Proper route ordering — batch routes registered before `{task_id}` routes

## Phase 26 — Quick Add to Column ✅
- [x] "+" button on each column header (Available, In Progress, Blocked, Done)
- [x] Inline title input with Enter to create, Escape to cancel
- [x] STDB: `add_task` reducer accepts `initial_status` parameter (default "available")
- [x] Server: `POST /api/tasks` accepts optional `status` field
- [x] Frontend: auto-claim for In Progress column (create → claim)
- [x] Auto-focus on quick-add input when it appears
- [x] All existing callers updated to pass the new param

## Phase 27 — Saved Filter Views ✅
- [x] Save any filter combination (repo + search + priority + assignee + labels) as a named view
- [x] Saved views persist in localStorage across sessions
- [x] Clickable pills below header bar — one tap restores saved filter state
- [x] Hover-to-reveal delete button on each view
- [x] "Save" button next to "Filters" opens inline name dialog
- [x] Full state capture: search query, repo, priorities, assignees, label filters

## Phase 28 — Issue Badges on Task Cards ✅
- [x] Bulk-load all issue links alongside board data
- [x] Issue badge on compact cards — `#143` style with open/closed color
- [x] Issue badge on detailed cards — clickable `repo#123` with GitHub icon
- [x] Open issues: green, closed issues: purple
- [x] Click-through to GitHub issue from the badge on detailed cards
- [x] Auto-fetched every 30s to stay in sync with issue linking

## Bug Fixes & Polish ✅
- [x] PR webhook title overwrite — preserves original kanban task title on PR open/reopen
- [x] create_task race condition — pre-generated UUID IDs eliminate skills race
- [x] Vite dev proxy port 8725→8727 (was silently broken)
- [x] Seed endpoint missing — POST /api/tasks/seed now works
- [x] Throughput chart: real date labels (Jun 16) instead of "14d ago"
- [x] Auto-refresh: Analytics, Issues, Activity Log pages refresh every 30s
- [x] Activity log timestamps — each entry now shows HH:MM when it occurred
- [x] Live toast notifications — popups for claim/complete/block/release via STDB subscriptions
