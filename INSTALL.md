# Installation Guide

This document covers all three installation methods for **spacetimedb-kanban** — a multi-agent kanban board on SpacetimeDB.

- [Option 1: Docker (Recommended)](#option-1-docker-recommended)
- [Option 2: Manual (Development)](#option-2-manual-development)
- [Option 3: Production Deployment](#option-3-production-deployment)
- [Post-Install Verification](#post-install-verification)
- [Troubleshooting](#troubleshooting)

---

## Option 1: Docker (Recommended)

The fastest way to get running. A single `docker compose up` starts both SpacetimeDB and the kanban backend.

### Prerequisites

- **Docker** — [Install Docker](https://docs.docker.com/engine/install/) (version 24+ recommended)
- **Docker Compose** — included with Docker Desktop; on Linux install the plugin separately:
  ```bash
  sudo apt install docker-compose-plugin   # Debian / Ubuntu
  sudo dnf install docker-compose-plugin   # Fedora
  ```

### Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/omiinaya/spacetimedb-kanban.git
   cd spacetimedb-kanban
   ```

2. **Configure environment**

   ```bash
   cp server/.env.example server/.env
   ```

   Edit `server/.env` to set your preferences (see [CONFIGURATION.md](CONFIGURATION.md) for all options).

3. **Start all services**

   ```bash
   docker compose up -d
   ```

   This starts two containers:
   - `spacetimedb-kanban-db` — SpacetimeDB (ports `3001` / `3002`)
   - `spacetimedb-kanban-backend` — FastAPI server (port `8727`)

   The backend waits for STDB to become healthy before starting.

4. **Verify the installation**

   ```bash
   curl http://localhost:8727/api/health
   ```

   A successful response looks like:
   ```json
   {
     "status": "ok",
     "now_ms": 1748397912000,
     "workers_alive": 0,
     "scheduler_enabled": true
   }
   ```

5. **Open the web UI**

   Point your browser to **[http://localhost:8727](http://localhost:8727)**.

### Managing the Containers

| Action | Command |
|--------|---------|
| **Stop** | `docker compose down` |
| **View backend logs** | `docker compose logs -f backend` |
| **View STDB logs** | `docker compose logs -f spacetime` |
| **Rebuild after code changes** | `docker compose build backend && docker compose up -d` |
| **Reset everything** (deletes volumes) | `docker compose down -v` |

> **Note:** The Docker image is built locally from the multi-stage Dockerfile. It compiles the frontend, builds the SpacetimeDB WASM module, and packages the Python server. The first build may take several minutes.

---

## Option 2: Manual (Development)

For contributors, custom deployments, or when you need hot-reload during development.

### Prerequisites

- **Python** ≥ 3.11 (check with `python3 --version`)
- **Node.js** ≥ 20 (check with `node --version`)
- **npm** ≥ 10 (check with `npm --version`)
- **SpacetimeDB CLI** — install the CLI tool:
  ```bash
  curl -fsSL https://github.com/spacetimedb/spacetimedb/releases/download/v2.6.1/spacetime-linux-x86_64.tar.gz \
    | tar xz -C /usr/local/bin/
  chmod +x /usr/local/bin/spacetime
  ```
- **Rust toolchain** — for compiling the STDB WASM module:
  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  rustup target add wasm32-unknown-unknown
  ```

### Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/omiinaya/spacetimedb-kanban.git
   cd spacetimedb-kanban
   ```

2. **Set up the Python backend environment**

   ```bash
   cd server

   # Create and activate a virtual environment
   python3 -m venv .venv
   source .venv/bin/activate

   # Install dependencies (either method works)
   pip install -e .              # editable install from pyproject.toml
   # OR
   pip install -r requirements.txt
   ```

   Dependencies installed:
   | Package | Version |
   |---------|---------|
   | `fastapi` | ≥ 0.115.0 |
   | `uvicorn` | ≥ 0.30.0 |
   | `httpx` | ≥ 0.27.0 |
   | `pydantic` | ≥ 2.0.0 |
   | `pydantic-settings` | ≥ 2.0.0 |
   | `python-dotenv` | ≥ 1.0.0 |

   Copy and customize the environment file:

   ```bash
   cp .env.example .env
   # Edit .env as needed
   ```

   Return to the project root:

   ```bash
   cd ..
   ```

3. **Build the frontend**

   ```bash
   cd web
   npm install      # install Node dependencies
   npm run build    # production build (outputs to web/dist/)
   cd ..
   ```

   For **active frontend development** with hot-reload:

   ```bash
   cd web
   npm install
   npm run dev      # starts Vite dev server on port 4444
   # Keep this running in a separate terminal
   ```

4. **Set up SpacetimeDB**

   Start a local SpacetimeDB instance:

   ```bash
   spacetime start &
   # Wait for it to be ready (usually 10–15 seconds)
   ```

   Or run STDB via Docker (useful if you don't want to manage two runtimes):

   ```bash
   docker run -d --name stdb \
     -p 3001:3001 -p 3002:3002 \
     spacetimedb/spacetimedb:latest
   ```

5. **Publish the STDB module**

   ```bash
   cd server/spacetimedb

   # Build the WASM module
   cargo build --release --target wasm32-unknown-unknown

   # Publish to the local STDB instance
   spacetime publish \
     -b target/wasm32-unknown-unknown/release/spacetimedb_kanban.wasm \
     -s http://localhost:3001 \
     --yes kanban

   cd ../..
   ```

6. **Start the backend server**

   ```bash
   cd server
   python main.py
   ```

   The server starts on **http://localhost:8727** and waits for STDB before accepting requests.

   For development with automatic reload:

   ```bash
   uvicorn main:app --reload --port 8727
   ```

### Development Workflow Summary

| Component | Production Mode | Dev Mode (Hot-Reload) |
|-----------|----------------|----------------------|
| **Backend** | `python main.py` | `uvicorn main:app --reload --port 8727` |
| **Frontend** | `npm run build` + served by backend | `npm run dev` (port 4444, proxy to :8727) |
| **STDB** | `spacetime start` or Docker | Same |

### Running Tests

```bash
# Backend tests (from server/)
cd server
python -m pytest -q

# Frontend tests (from web/)
cd web
npm test

# Rust module tests
cd server/spacetimedb && cargo test

# All tests at once
make test-all
```

---

## Option 3: Production Deployment

For a long-running, secure production instance.

### Docker (Production-Ready)

The `docker-compose.yml` already includes `restart: unless-stopped` on the backend service. For production:

1. **Set a strong API key** for authentication:

   ```bash
   echo "API_KEY=$(openssl rand -hex 32)" >> server/.env
   ```

   This enables auth on all mutation endpoints. Clients provide the key via the `X-API-Key` header.

2. **Configure webhook alerts** for state changes:

   ```bash
   echo "WEBHOOK_DEFAULT_URL=https://discord.com/api/webhooks/..." >> server/.env
   ```

3. **Tune scheduler intervals** for your workload:

   | Variable | Production Suggestion | Notes |
   |----------|----------------------|-------|
   | `DISPATCHER_INTERVAL_SECONDS` | `30` | How often the task dispatcher runs |
   | `STALE_CHECK_INTERVAL_SECONDS` | `120` | Stale task recovery frequency |
   | `DEAD_BOARD_INTERVAL_SECONDS` | `900` | Board auto-remediation check |
   | `METRICS_INTERVAL_SECONDS` | `900` | Metrics snapshot interval |

4. **Use a reverse proxy** for SSL termination and domain binding:

   **nginx example:**
   ```nginx
   server {
       listen 443 ssl;
       server_name kanban.example.com;

       ssl_certificate /etc/letsencrypt/live/kanban.example.com/fullchain.pem;
       ssl_certificate_key /etc/letsencrypt/live/kanban.example.com/privkey.pem;

       location / {
           proxy_pass http://127.0.0.1:8727;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   **Caddy example** (auto HTTPS):
   ```
   kanban.example.com {
       reverse_proxy localhost:8727
   }
   ```

5. **Mount STDB data volume for persistence** — already configured in `docker-compose.yml`:

   ```yaml
   volumes:
     - stdb-data:/var/spacetime
   ```

   This volume persists all kanban data across container restarts.

6. **Start with production compose**:

   ```bash
   docker compose up -d
   ```

### Non-Docker Production

If running without Docker on a server:

- Use **systemd** or **supervisord** to manage the `python main.py` process
- Set up log rotation for `uvicorn` logs
- Use **nginx** or **Caddy** as a reverse proxy
- Run SpacetimeDB as a systemd service or in a Docker container with persistent volumes

---

## Post-Install Verification

After installation, run through these checks:

1. **Health endpoint**

   ```bash
   curl http://localhost:8727/api/health
   ```

   Expect: `{"status": "ok", ...}`

2. **Web UI loads**

   Open [http://localhost:8727](http://localhost:8727) in a browser. You should see the kanban dashboard.

3. **Test task creation via API**

   ```bash
   curl -X POST http://localhost:8727/api/tasks \
     -H "Content-Type: application/json" \
     -d '{"title": "Hello, kanban!", "description": "Test task", "priority": 0}'
   ```

   If `API_KEY` is set, add the header: `-H "X-API-Key: your-key"`. Expect a 200 response with the created task.

4. **Verify MCP server imports** (if using MCP integration)

   ```bash
   cd server && python -c "import mcp_server; print('MCP server imports OK')"
   ```

5. **Check all containers are running** (Docker only)

   ```bash
   docker compose ps
   ```

   Both `spacetimedb-kanban-db` and `spacetimedb-kanban-backend` should show `Up`.

---

## Troubleshooting

| Issue | Likely Cause | Fix |
|-------|-------------|-----|
| Backend fails to start | STDB not running | Ensure `spacetime start` or Docker STDB is running on port 3001 |
| `curl: Connection refused` on :8727 | Backend starting | Wait for the startup sequence (STDB retry loop, ~30s) |
| Web UI shows "Dashboard not built" | Frontend not compiled | Run `cd web && npm install && npm run build` |
| `Module publish failed` (manual setup) | WASM not built | Run `cargo build --release --target wasm32-unknown-unknown` in `server/spacetimedb/` |
| 409 Conflict on claim | Task already claimed or dependency not done | List available tasks: `GET /api/tasks?status=available` |
| `spacetime: command not found` | STDB CLI not installed | Download from [GitHub releases](https://github.com/spacetimedb/spacetimedb/releases) |

For more detailed help, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) and [CONFIGURATION.md](CONFIGURATION.md).

---

## Quick Reference

```bash
# ── Docker ──
cp server/.env.example server/.env
docker compose up -d
curl http://localhost:8727/api/health
docker compose logs -f backend
docker compose down

# ── Manual ──
cd server && python3 -m venv .venv && source .venv/bin/activate && pip install -e .
cd web && npm install && npm run build
spacetime start
cd server/spacetimedb && cargo build --release --target wasm32-unknown-unknown && \
  spacetime publish -b target/wasm32-unknown-unknown/release/spacetimedb_kanban.wasm -s http://localhost:3001 --yes kanban
cd server && python main.py
```
