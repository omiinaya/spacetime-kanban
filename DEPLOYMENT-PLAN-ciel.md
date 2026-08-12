# Spacetime-x deployment plan — testing + production variants
(Ciel draft, 2026-08-11 — for Omar's green-light)

## Omar's vision (verbatim intent)
> "If we deploy spacetime-x projects, set up SpacetimeDB on Coolify (if compatible)
> and all the spacetime-x projects too. TWO variants: testing and production —
> so we can run the projects AND work on them easily."

## Compatibility verdict (verified tonight)
**SpacetimeDB + Coolify = COMPATIBLE ✅**
- SpacetimeDB ships an official Docker image: `spacetimedb/spacetimedb:latest`
  (ports 3001 HTTP / 3002 WS, volume /var/spacetime).
- spacetime-kanban provides docker-compose.yml (STDB + backend, health-chained)
  and a multi-stage Dockerfile — both are first-class citizens for Coolify's
  "Docker Compose" / "Dockerfile" app types.
- Coolify on CT 104 is RUNNING, API healthy on :8000 (health 200).

## Architecture: two variants per project

```
Coolify (CT 104)
├── kanban-testing
│   ├── spacetime (stdb, testing volume)   :3001
│   └── backend    (8727, testing env)     :8721
└── kanban-production
    ├── spacetime (stdb, prod volume)      :3101
    └── backend    (8727, prod env)        :8722
```

Pattern per project (applied to all spacetime-x repos):
- **testing**: dev-friendly env vars, low auth friction, hot code path, own STDB volume
- **production**: strong API_KEY from vault, webhook alerts, tuned scheduler
  intervals, persistent STDB volume, backup cron

## Steps
1. Get Coolify API token from LightBWS vault (`COOLIFY_API_KEY`) — single source.
2. Seed the pattern with **spacetime-kanban** (it's the reference project, already
   reviewed + test suite verified: 1685 pass, 2 known failures to fix).
3. Fix before deploy (from REVIEW-ciel.md):
   - pin `mcp>=1.0,<2` in server/requirements.txt
   - add test deps as dev group (pytest, pytest-asyncio, pytest-timeout)
   - fix dead `mock_run` fixture in test_scanner_modules.py
   - pin compose STDB version (not `:latest`) to match CLI (2.6.x)
   - make auto_star.py opt-in
4. Per project: duplicate the compose, remap ports/volumes/env per variant,
   create both Coolify apps, wire domains via Coolify proxy.
5. Verify: STDB health, publish WASM (entrypoint does it), backend /api/health,
   claim-contention test on testing, then prod.

## Repos to roll out (spacetime-x fleet, from gh listing)
spacetime-api, -browser, -cars, -drivers, -air, -jobs, -mods, -swarm,
-hardware-test, -wiki, -ab, -rpm, -tv, -llm, -memory, -kanban (reference)

## Guardrails
- Secrets ONLY from vault (never in compose/env committed).
- Production variants get API keys; testing variants stay open on LAN.
- STDB prod volume gets backup (TrueNAS snapshot or rsync) — we already have
  mrx-thunder/mrx-cloud mounts for this.
- Roll out incrementally: kanban first as the pattern-prover, then by priority.

## Open questions for Omar
1. Coolify API token — confirm we pull it from LightBWS vault (my assumption: yes).
2. Which spacetime-x projects are priority after kanban?
3. Domain names per variant (e.g. kanban.mrxlab.net / kanban-test.mrxlab.net)?
