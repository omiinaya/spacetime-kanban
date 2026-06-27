# spacetimedb-kanban Roadmap

## Phase 1 — Core Foundation ✅
- [x] SpacetimeDB module: `tasks` table + atomic claim reducers
- [x] FastAPI REST backend at :8725
- [x] React + shadcn web dashboard
- [x] AGENTS.md with complete API guide
- [x] Basic kanban board UI

## Phase 2 — Multi-Agent UX
- [ ] WebSocket live-updates for the board (no refresh needed)
- [ ] Agent heartbeat — detects stuck tasks (claimed but no activity for 30min)
- [ ] Auto-unclaim stale tasks back to available
- [ ] Task dependencies / ordering (task B blocked on task A)

## Phase 3 — Workflow & Integration
- [ ] GitHub PR linking — agents auto-update tasks on PR creation/merge
- [ ] Git branch naming convention enforcement
- [ ] Webhook integration — post task events to Discord channel
- [ ] Roadmap import — bulk-create tasks from a repo's ROADMAP.md

## Phase 4 — Intelligence
- [ ] Priority scoring — auto-suggest highest-value task based on agent capabilities
- [ ] Swarm mode — auto-discover agents on the network
- [ ] Agent capability tags — tasks tagged by required skill, agents self-select
