# Contributing to spacetimedb-kanban

Thank you for your interest! This is an atomic multi-agent kanban board built on SpacetimeDB — a shared task coordination system for AI coding agents.

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 20+
- Docker & Docker Compose (for SpacetimeDB)
- Rust toolchain with `wasm32-unknown-unknown` target (for STDB module builds)
- SpacetimeDB CLI v2.6.1

### Development Setup

```bash
git clone https://github.com/omiinaya/spacetimedb-kanban.git
cd spacetimedb-kanban

# ── Backend ──
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -e .           # installs dev dependencies too
cp .env.example .env       # review and edit
python3 main.py            # starts FastAPI on :8727

# ── Frontend (development mode) ──
cd web
npm install
npm run dev                 # Vite dev server on :4444 (hot-reload)

# ── SpacetimeDB (Docker) ──
cd ..                      # project root
docker compose up -d spacetime   # start STDB only
spacetime publish spacetimedb-kanban -y  # publish WASM module from server/
```

For full Docker setup (STDB + backend):
```bash
docker compose up -d        # starts both services
```

## Project Structure

```
spacetimedb-kanban/
├── server/               # Python FastAPI backend
│   ├── main.py           # App entry point, static file serving
│   ├── config.py         # Pydantic settings (all env vars)
│   ├── scheduler.py      # Background scheduler loops (12 loops)
│   ├── routes/           # REST API route modules (15 files)
│   ├── workers/          # Worker subprocess management
│   ├── mcp_server.py     # MCP stdio server (36 tools)
│   ├── issue_sync.py     # GitHub issue sync logic
│   ├── sessions/         # Session management
│   ├── scanners/         # Repo improvement scanners
│   └── tests/            # Test suite (449 tests)
├── web/                  # React + Vite + shadcn frontend
│   ├── src/pages/        # Page components (14 pages)
│   ├── src/components/   # Shared UI components (skeletons, columns, etc.)
│   └── src/__tests__/    # Vitest test suite (188 tests)
├── docker-compose.yml    # STDB + backend orchestration
├── Dockerfile            # Multi-stage build (frontend + backend)
└── bin/                  # CLI tools
```

## Development Workflow

### Backend

```bash
cd server
source .venv/bin/activate

# Run tests
python -m pytest -q                             # all non-e2e tests
python -m pytest tests/test_api.py -x --tb=long  # API tests with debug

# Type checking
python -m ruff check .
python -m ruff format --check .
python -m mypy .                                 # if configured

# Run server
python main.py                                   # :8727
```

### Frontend

```bash
cd web
npm run dev            # Vite dev :4444 (hot-reload, proxy to :8727)
npm run test           # Vitest (188 tests)
npx tsc --noEmit       # Type check
npm run build          # Production build -> dist/
```

### STDB Module (Rust WASM)

```bash
cd server/spacetimedb
cargo check
cargo clippy -- -D warnings
spacetime publish spacetimedb-kanban -y   # publish module
```

### Quality Gates (run before pushing)

```bash
# ── Python ──
cd server && source .venv/bin/activate
python -m pytest -q --tb=short -k "not test_api and not e2e"
python -m ruff check .
python -m ruff format --check .

# ── Frontend ──
cd web
npx tsc --noEmit
npm run build
npm run test

# ── STDB Module ──
cd server/spacetimedb
cargo check
cargo clippy -- -D warnings

# ── Push ──
cd ../..
git push
```

### Code Conventions

- Python: follows ruff rules (E,F,W,I,N,UP,B,SIM,S), line length 100, double quotes
- TypeScript: strict mode, no unchecked index access
- Git identity: `omiinaya <omiinaya@gmail.com>`
- Commit format: `type: concise subject` (types: feat, fix, docs, refactor, chore, test, style, perf)
- Branch format: `{type}/kanban-{task_id}--{slug}`

## For AI Agent Contributors

This project is specifically designed for AI coding agents to coordinate work on a shared roadmap.

1. **Read [AGENTS.md](./AGENTS.md)** first — complete agent onboarding with API reference, state machine, and conventions
2. **Read [CLAUDE.md](./CLAUDE.md)** if you're Claude Code
3. **Always check the kanban** before starting work
4. **Claim a task atomically** — `POST /api/tasks/{id}/claim` returns 409 if another agent took it
5. **Follow branch convention** — `{type}/kanban-{task_id}--{slug}`
6. **Update task status** as you progress
7. **Release promptly** if blocked

## Documentation Index

| Document | Purpose |
|---|---|
| [README.md](./README.md) | Project overview, features, quick start |
| [INSTALL.md](./INSTALL.md) | Full installation guide (Docker, manual, production) |
| [CONFIGURATION.md](./CONFIGURATION.md) | All environment variables explained |
| [API.md](./API.md) | Complete REST API reference |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | System architecture, data flow, design decisions |
| [MCP.md](./MCP.md) | MCP server docs for Hermes integration |
| [AGENTS.md](./AGENTS.md) | AI agent onboarding and workflow |
| [SETUP.md](./SETUP.md) | Agent CLI setup and branch hooks |
| [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) | Common issues and solutions |
| [ROADMAP.md](./ROADMAP.md) | Development roadmap and phase tracking |

## License

MIT — see [LICENSE](./LICENSE).
