# spacetime-kanban

**Atomic multi-agent kanban board** — a shared task coordination system built on SpacetimeDB.  
Multiple AI agents (or humans) can simultaneously discover, claim, complete, and manage tasks on a shared board without conflicts.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue?logo=python)](server/pyproject.toml)
[![TypeScript](https://img.shields.io/badge/typescript-5.6+-blue?logo=typescript)](web/tsconfig.json)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker)](docker-compose.yml)

---

## ✨ Features

| Capability | Description |
|---|---|
| **Atomic task claiming** | STDB sequential reducers guarantee no two agents claim the same task |
| **Full state machine** | `available → claimed → completed / blocked → unclaimed` with dependency enforcement |
| **Self-healing scheduler** | Built-in loops handle stale task recovery, dead board detection, metrics, and task dispatch — no cron jobs needed |
| **Web dashboard** | Full React + shadcn UI — board view, analytics, logs, labels, webhooks, agent health, and more |
| **Hermes MCP integration** | Expose the entire kanban as MCP tools — Hermes agents claim and complete tasks natively |
| **GitHub issue sync** | Link kanban tasks to GitHub issues, create issues from tasks, bidirectional status tracking |
| **Webhook alerts** | Discord, Slack, Telegram, or custom webhook notifications on state changes |
| **Branch validation** | Pre-push hooks enforce `feature/kanban-{task_id}` branch naming |
| **Audit logging** | Every claim, completion, block, and state change is recorded with agent attribution and timestamps |
| **REST API** | Full REST API for task CRUD, claiming, agent management, analytics, and more |
| **Docker support** | One-command `docker compose up` with health-chained services |

---

## 🚀 Quick Start (Docker — 2 minutes)

```bash
git clone https://github.com/omiinaya/spacetime-kanban.git
cd spacetime-kanban
cp server/.env.example server/.env   # review and edit
docker compose up -d                  # starts STDB + backend
```

Open [http://localhost:8727](http://localhost:8727) for the web dashboard.

See [INSTALL.md](INSTALL.md) for manual setup, production deployment, and detailed options.

---

## 🏗️ Architecture at a Glance

```
┌────────────────────────────────────────────────────────────┐
│                    Docker / Host                             │
│                                                              │
│  ┌──────────────────┐     ┌──────────────────────────────┐  │
│  │  SpacetimeDB      │     │  FastAPI Backend (:8727)      │  │
│  │  (v2.6.1)         │◄────│  ┌────────────────────────┐  │  │
│  │  HTTP :3001       │     │  │ Scheduler (asyncio)    │  │  │
│  │  WS   :3002       │     │  │ ├ stale_watcher (120s) │  │  │
│  │                   │     │  │ ├ dead_board_monitor   │  │  │
│  │  Tables:          │     │  │ ├ metrics_collector    │  │  │
│  │  ├ tasks          │     │  │ ├ task_dispatcher      │  │  │
│  │  ├ task_logs      │     │  │ ├ repo_scanner (1800s) │  │  │
│  │  ├ agents         │     │  │ ├ template_trigger     │  │  │
│  │  ├ webhooks       │     │  │ ├ zombie_cleaner       │  │  │
│  │  ├ labels         │     │  │ ├ self_improver        │  │  │
│  │  ├ comments       │     │  │ └ ... (12 loops total) │  │  │
│  │  ├ checklists     │     │  │ REST API (/api/*)      │  │  │
│  │  ├ issues         │     │  │ Static Frontend (/)    │  │  │
│  │  └ projects       │     │  │ MCP Server (stdio)     │  │  │
│  │                   │     │  └────────────────────────┘  │  │
│  └──────────────────┘     └──────────────────────────────┘  │
│                                                              │
│  ┌──────────────────┐     ┌──────────────────────────────┐  │
│  │  Hermes Agent     │     │  Web Browser (:8727)         │  │
│  │  (via MCP/API)    │────►│  React + shadcn UI          │  │
│  └──────────────────┘     └──────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed data flow, scheduler reference, and component design.

---

## 📚 Documentation

| Document | For | Covers |
|---|---|---|
| [INSTALL.md](INSTALL.md) | Everyone | Full install guide — Docker, manual, production |
| [CONFIGURATION.md](CONFIGURATION.md) | Operators | All environment variables, STDB config, scheduler tuning |
| [API.md](API.md) | Developers | Complete REST API reference with examples |
| [MCP.md](MCP.md) | Hermes Users | MCP server setup, tool reference, agent integration |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Contributors | System design, data flow, component reference |
| [AGENTS.md](AGENTS.md) | AI Agents | Agent onboarding — task lifecycle, claiming, conventions |
| [SETUP.md](SETUP.md) | CLI Users | Agent CLI setup, branch hooks, workflow |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Everyone | Common issues and solutions |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributors | Development setup, testing, PR workflow |

---

## 📦 Project Structure

```
spacetime-kanban/
├── server/               # Python FastAPI backend
│   ├── main.py           # App entry point, static file serving
│   ├── config.py         # Pydantic settings (all env vars)
│   ├── models.py         # Pydantic data models
│   ├── auth.py           # API key authentication
│   ├── shared.py         # STDB connection helpers
│   ├── scheduler.py      # All background scheduler loops
│   ├── mcp_server.py     # MCP stdio server (36 tools)
│   ├── issue_sync.py     # GitHub issue sync logic
│   ├── routes/           # FastAPI route modules
│   │   ├── __init__.py
│   │   ├── tasks.py      # Task CRUD + state machine
│   │   ├── agents.py     # Agent registration, heartbeat
│   │   ├── analytics.py  # Analytics endpoints
│   │   ├── apikeys.py    # API key management (auth-gated)
│   │   ├── github.py     # GitHub issue sync + webhook
│   │   ├── labels.py     # Label CRUD
│   │   ├── logs.py       # Activity logs
│   │   ├── projects.py   # Project/repo registry
│   │   ├── webhook_subs.py # Webhook subscription CRUD
│   │   └── ...           # health, ops, rules, scanner, dispatcher, templates
│   └── workers/          # Worker subprocess management
│       ├── base.py       # Base worker class
│       ├── llm.py        # LLM-driven workers
│       ├── run.py        # Worker entry point
│       └── mechanical/   # Regex-based mechanical workers
├── web/                  # React + Vite frontend
│   └── src/
│       ├── App.tsx       # Root component + routing
│       ├── pages/        # Page components (14 pages)
│       ├── components/   # Shared UI components
│       ├── hooks/        # Custom React hooks
│       └── api.ts        # API client
├── docker-compose.yml    # STDB + backend orchestration
├── Dockerfile            # Multi-stage build
├── docker-entrypoint.sh  # Container entrypoint
├── kanban                # kanban CLI (single-file, stdlib-only)
└── bin/                  # CLI utilities
    └── check-branch      # Branch name validator
```

---

## 🧪 Test Summary

| Layer | Tests | Status |
|---|---|---|
| Python backend | 1,600 + 21 skipped | ✅ |
| Frontend (Vitest) | 194 | ✅ |
| E2E (Playwright) | — | ⚪ Requires STDB |
| TypeScript (tsc) | Clean | ✅ |
| Ruff lint | All checks passed | ✅ |
| Pre-commit hooks | Ruff check + format | ✅ |

---

## 📄 License

MIT — see [LICENSE](LICENSE).

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow, testing, and PR guidelines.
