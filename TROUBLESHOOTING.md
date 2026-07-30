# Troubleshooting

Common issues and fixes for SpacetimeDB Kanban.

---

## STDB Connection Issues

### "Connection refused" on startup
STDB (SpacetimeDB) is not running. Start it:

```bash
spacetime start
```
or
```bash
docker compose up -d spacetime
```

### STDB retries exhausted
The server waits for STDB to become available, retrying periodically. If it gives up:

- Increase `KANBAN_STDB_RETRIES` env var (default: 60, each retry is ~1 second)
- Ensure STDB actually starts within that window

### Module not found errors
The server module hasn't been published to STDB yet. Run `spacetime publish` from the `server/` directory:

```bash
cd server && spacetime publish
```

---

## Auth Issues

### 401 Unauthorized
The `API_KEY` env var is set but the request is missing the `X-API-Key` header.

- Every API request must include `X-API-Key: <your-api-key>`
- Check that the client is sending the header

### Generate an API key
```bash
openssl rand -hex 32
```
Set the output as `API_KEY` in your `.env` file.

### Disable auth (not recommended for public deployments)
Leave `API_KEY` empty in your `.env` file. Auth is skipped when no key is configured.

---

## Claim Fails

### 409 Conflict — "already claimed"
Another agent grabbed the task first. List available tasks again and pick another:

```bash
curl http://localhost:8727/api/tasks?status=available
```

### 409 Conflict — "dependency not done"
The task has a dependency that is still open (not in `done` status). Complete the dependency first.

### 404 Not Found
The task ID doesn't exist. Verify the task exists:

```bash
curl http://localhost:8727/api/tasks
```

---

## Scheduler Not Starting

### Check that the scheduler is enabled
Ensure `SCHEDULER_ENABLED=true` in your `.env` file.

### Check server logs
Look for the "Starting scheduler" message in the server logs:

```bash
# Local
tail -f server/logs/app.log | grep scheduler

# Docker
docker compose logs backend | grep scheduler
```

### Scheduler loops log their interval on startup
Each background loop announces itself on start, e.g.:

```
stale_watcher loop every 120s
dead_board_monitor loop every 900s
```

If you don't see these lines, the scheduler isn't running.

---

## Webhooks Not Firing

### Set a default webhook URL
```bash
WEBHOOK_DEFAULT_URL=https://discord.com/api/webhooks/...
```

### Test a webhook
```bash
curl -X POST http://localhost:8727/api/webhooks/<id>/test
```

### Check delivery logs
```bash
curl http://localhost:8727/api/webhooks/<id>/deliveries
```

### Increase timeout (default: 10s)
If your webhook endpoint is slow, increase `WEBHOOK_TIMEOUT_SECONDS`.

### Increase max retries (default: 3)
Set `WEBHOOK_MAX_RETRIES` to a higher value.

---

## Docker Issues

### "Port already in use"
Change the host port mapping in `docker-compose.yml`:

```yaml
# Example: map host 8728 → container 8727
ports:
  - "8728:8727"
  - "3003:3001"
```

### Container keeps restarting
Check the logs:

```bash
docker compose logs backend
```

### Frontend shows blank page
Static build artifacts may be stale. Rebuild:

```bash
docker compose build --no-cache backend
```

### STDB data persistence
Use `docker compose down` (without `-v`) to keep your data volumes intact.

### Full reset
Destroys **all data**:

```bash
docker compose down -v && docker compose up -d
```

---

## MCP Server Issues

### ModuleNotFoundError: mcp.server.mcpserver
The `mcp` package version is too old. Install a compatible version:

```bash
pip install "mcp>=2.0.0"
```

### Changes to mcp_server.py not reflected
Kill the MCP process; the gateway respawns it automatically:

```bash
pkill -f mcp_server.py
```

### Tools not appearing in Hermes
Verify the MCP server starts cleanly:

```bash
python server/mcp_server.py
```

It will hang on stdio (that's correct — press Ctrl+C to exit). If it errors, fix the error before trying to use it from Hermes.

---

## Frontend Issues

### Blank page on :8727
Rebuild static assets:

```bash
cd web && npm run build
```

### Vite dev server not connecting to API
Check the proxy config in `vite.config.ts`. The API proxy target should point to port 8727.

### TypeScript errors in tests
Vitest handles types differently from `tsc`. Tests are excluded from `tsc` via the `exclude` field in `tsconfig.json` — errors in test files during `tsc` are expected and can be ignored.

---

## Performance

### Slow task listing with many tasks
STDB queries support pagination. Use `limit` and `offset` params:

```bash
curl "http://localhost:8727/api/tasks?limit=50&offset=0"
```

### Worker subprocess memory
Adjust `MAX_MEMORY_PCT` to throttle workers at a lower percentage of available memory.

### Many agents polling
Increase `STALE_CHECK_INTERVAL_SECONDS` to reduce load on the database.

---

## Getting Help

- **System design:** Read [ARCHITECTURE.md](./ARCHITECTURE.md)
- **All logs:** `docker compose logs -f`
- **Health check:** `curl http://localhost:8727/api/health`
- **File an issue:** Open a GitHub issue on the repository
