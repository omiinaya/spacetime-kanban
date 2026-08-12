# spacetime-kanban — DEPLOYMENT NOTES (verified 2026-08-11)

## What works now (TESTING variant live on CT 104)
- Stack: `kanban-testing` compose (STDB + backend) — both containers healthy
- API: http://192.168.1.104:8721/api/health -> {"status":"ok"}
- Create/read/claim tasks against real SpacetimeDB reducers: VERIFIED
- STDB: clockworklabs/spacetime:v2.7.1, `start --listen-addr=0.0.0.0:3001`,
  host port 3003 (HTTP), 3004 (WS)

## The critical wiring: STDB_DB must be the DATABASE IDENTITY, not a name
The backend queries `http://stdb:3001/v1/database/{STDB_DB}/sql`. STDB
standalone resolves databases **by identity hash**, NOT by friendly name:
- `GET /v1/database/kanban` -> 404
- `GET /v1/database/<identity>` -> 200

So after publishing the module, set `STDB_DB=<database_identity>` from the
publish response. The repo's default `STDB_DB=kanban` only works if the DB is
published as a NAMED database under an authenticated CLI identity — which does
not work against a bare `spacetime start` standalone (CLI publish 401s with
"Invalid token: InvalidSignature" unless the server runs with matching JWT keys).

## How to publish the module (proven, no CLI auth needed)
```bash
# 1. Copy module.wasm into the STDB container
docker cp kanban-testing-backend:/app/server/spacetimedb/module.wasm /tmp/km.wasm
docker cp /tmp/km.wasm kanban-testing-stdb:/tmp/module.wasm
# 2. Publish via HTTP (delete_data=always replaces existing)
docker exec kanban-testing-stdb sh -c 'curl -s -X POST \
  "http://localhost:3001/v1/database?host_type=Wasm&delete_data=always" \
  -H "Content-Type: application/octet-stream" --data-binary @/tmp/module.wasm'
# 3. Response gives {"Success":{"database_identity":"c200d4..."}} -> use as STDB_DB
# 4. Recreate backend with STDB_DB=<identity> (restart is NOT enough — env only
#    applies on recreate: docker compose up -d --force-recreate backend)
```

## Build-blocking bugs fixed in the repo (commits be0752b, 3e1f8e7, 7c85d8c)
1. `.dockerignore` excluded `.env.example` but Dockerfile COPYs it -> build fails
   on fresh checkout. Fixed: copy from server/.env.example.
2. `.gitignore` had `*.lock` which also ignored web/package-lock.json -> npm ci
   always failed. Fixed: `!package-lock.json` + generated the lockfile.
3. `eslint@^10.8.0` incompatible with eslint-plugin-react-hooks@5 (needs <=9).
   Fixed: pin eslint ^9.0.0.
4. STDB references outdated: compose used `spacetimedb/spacetimedb:2.6.1`
   (image does NOT exist on Docker Hub) and Dockerfile downloaded a CLI release
   URL that 404s. Fixed: `clockworklabs/spacetime:v2.7.1` + best-effort CLI.
5. STDB healthcheck hit `/` (404); the image health endpoint is
   `/v1/health` (200). Fixed.
6. STDB container command needed `start --listen-addr=0.0.0.0:3001`
   (bare image prints help and exits). Fixed.

## Auth notes
- Auth is a single shared API_KEY (mutation endpoints) — fine for self-hosted.
- auto_star.py defaults ON; for our fleet we keep it off (AUTO_STAR_ENABLED=false).
- JWT keypair approach: STDB `start --jwt-*` needs PKCS8 EC P-256 keys; my
  initial SEC1 key failed to parse ("Unable to read private key"). Not needed
  for the HTTP-publish path above.

## Production variant (next)
- Same flow; own STDB identity (fresh publish), own ports (3011/3012, backend
  8722), KANBAN_PROD_API_KEY from vault (already stored), AUTO_STAR off.
