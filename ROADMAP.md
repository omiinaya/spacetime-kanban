# spacetimedb-kanban Roadmap

## Phase 1 — Core Foundation ✅
- [x] SpacetimeDB module: `tasks` table + atomic claim reducers
- [x] FastAPI REST backend at :8727
- [x] React + shadcn web dashboard
- [x] AGENTS.md with complete API guide
- [x] Basic kanban board UI

## Phase 2 — Multi-Agent UX
- [x] WebSocket live-updates for the board (no refresh needed) — via STDB native sub
- [x] Agent heartbeat — detects stuck tasks (claimed but no activity for 30min)
- [x] Auto-unclaim stale tasks back to available
- [x] Discord webhook notifications on task state changes
- [x] Task dependencies / ordering — task B blocked on task A, enforced at claim time

## Phase 3 — Workflow & Integration
- [x] Git branch naming convention enforcement — `kanban check-branch` + pre-push hook
- [x] Webhook integration — Discord notifications on all task state changes
- [x] Roadmap import — bulk-create tasks from a repo's ROADMAP.md (`kanban roadmap-import`)
- [x] GitHub PR linking — auto-update tasks on PR creation/merge (webhook receiver)

## Phase 4 — Intelligence
- [ ] Priority scoring — auto-suggest highest-value task based on agent capabilities
- [ ] Swarm mode — auto-discover agents on the network
- [ ] Agent capability tags — tasks tagged by required skill, agents self-select
