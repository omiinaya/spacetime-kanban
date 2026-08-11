#!/usr/bin/env bash
# kanban-profile-worker.sh — guardrail #1 + #2 for spacetime-kanban workers.
#
# #1 PROFILE SCOPING: each task runs under the Hermes profile that matches its
#    repo scope, so it inherits exactly the right skills/guardrails:
#      repo~proxmox*        -> -p proxmox
#      repo~truenas*|nas*   -> -p truenas
#      repo~nodeterm*       -> -p nodeterm
#      repo~kanban|spacetime -> default (this kanban itself)
#      else                 -> -p dev
# #2 VAULT INJECTION: the worker is launched through vault-exec, so every
#    secret the task needs (TRUENAS_API_KEY, etc.) is injected from LightBWS
#    at runtime — never committed, never in plain env files.
#
# Usage: kanban-profile-worker.sh <task_id>
set -euo pipefail

TASK_ID="${1:?usage: kanban-profile-worker.sh <task_id>}"
KANBAN_API="${KANBAN_API:-http://localhost:8727}"
AGENT_ID="${AGENT_ID:-hermes}"
VAULT_EXEC="${VAULT_EXEC:-/root/.hermes/bin/vault-exec}"
HERMES_BIN="${HERMES_BIN:-hermes}"

# Fetch the task to learn its repo scope (read-only).
TASK_JSON=$(curl -s -m 10 "${KANBAN_API}/api/tasks/${TASK_ID}" 2>/dev/null || echo "{}")
REPO=$(echo "$TASK_JSON" | python3 -c "import sys,json;print((json.load(sys.stdin).get('repo') or ''))" 2>/dev/null || echo "")
TITLE=$(echo "$TASK_JSON" | python3 -c "import sys,json;print((json.load(sys.stdin).get('title') or ''))" 2>/dev/null || echo "")

# Pick profile by scope.
PROFILE="dev"
case "$REPO" in
  *proxmox*|*pve*)   PROFILE="proxmox" ;;
  *truenas*|*nas*)   PROFILE="truenas" ;;
  *nodeterm*)        PROFILE="nodeterm" ;;
  *kanban*|*spacetime*) PROFILE="default" ;;
esac

# Build the task prompt: title + description + explicit guardrails.
DESC=$(echo "$TASK_JSON" | python3 -c "import sys,json;print((json.load(sys.stdin).get('description') or ''))" 2>/dev/null || echo "")
PROMPT="You are a kanban worker (agent: ${AGENT_ID}). Complete this task:
TITLE: ${TITLE}
DESCRIPTION: ${DESC}
Rules: verify against the live system read-only first; never mutate without
explicit task instruction; if blocked, say WORKER_BLOCKED with the reason.
When done, reply WORKER_DONE: <one-line summary>."

# Run under the chosen profile with vault secrets injected.
exec "${VAULT_EXEC}" -- "${HERMES_BIN}" -p "${PROFILE}" chat -q "${PROMPT}"