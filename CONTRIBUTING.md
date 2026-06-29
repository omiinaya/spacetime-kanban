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

## AI Agent Contributors

This project is specifically designed for AI coding agents. Before starting work, read [AGENTS.md](./AGENTS.md) for the full API reference, task lifecycle, and claiming workflow. For Claude Code specifically, see [CLAUDE.md](./CLAUDE.md).

## Project Structure

- **server/** — FastAPI backend (port 8727), REST API for task CRUD and claiming
- **web/** — React + shadcn kanban board UI (Vite port 5189)
- **kanban/** — CLI tool for agents (install.sh, kanban script)
- SpacetimeDB on localhost:3001 for persistence

## Commit Messages

```
type: concise subject
```

Types: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`

## AI Agent Guidelines

1. Always check the kanban before starting work
2. Claim a task atomically — 409 means another agent got it
3. Follow the branch convention: `{type}/kanban-{task_id}--{slug}`
4. Update task status as you progress
5. Release promptly if blocked
