# Contributing to SpacetimedbKanban

Thank you for your interest! This is an atomic multi-agent kanban board built on SpacetimeDB.

## Getting Started

```bash
git clone https://github.com/omiinaya/spacetimedb-kanban.git
cd spacetimedb-kanban

# Backend
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Start server (port 8727)
python3 main.py
```

The frontend is pre-built as part of the backend serve — the server at `:8727` serves both the API and the static frontend files from `web/dist/`. For frontend development:

```bash
cd web
npm install
npm run dev     # Vite dev server at :5189
```

## AI Agent Contributors

This project is specifically designed for AI coding agents. Before starting work, read [AGENTS.md](./AGENTS.md) for the full API reference, task lifecycle, and claiming workflow. For Claude Code specifically, see [CLAUDE.md](./CLAUDE.md).

## Project Structure

- **server/** — FastAPI backend (port 8727), REST API for task CRUD and claiming
  - `server/main.py` — Application entrypoint
  - `server/routes/` — Route handlers (13 modules)
  - `server/tests/` — Test suite (387 tests)
  - `server/spacetimedb/` — Rust STDB module (WASM)
- **web/** — React + shadcn kanban board UI (Vite port 5189)
  - `web/src/` — Source code
  - `web/dist/` — Build output (served by backend)
- **bin/** — CLI tools (`kanban`, `check-branch`)

## Commit Messages

```
type: concise subject
```

Types: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`, `style:`, `perf:`

## Quality Gates (run before pushing)

```bash
# Backend
cd server
python3 -m pytest tests/ -x --tb=short
python3 -m ruff check .
python3 -m ruff format --check .

# STDB module
cd server/spacetimedb
cargo check
cargo clippy -- -D warnings

# Frontend
cd web
npx tsc --noEmit
npm run build
```

## AI Agent Guidelines

1. Always check the kanban before starting work
2. Claim a task atomically — 409 means another agent got it
3. Follow the branch convention: `{type}/kanban-{task_id}--{slug}`
4. Update task status as you progress
5. Release promptly if blocked
6. Run all quality gates before pushing
