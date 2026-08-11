#!/usr/bin/env bash
# kanban-worker-exec.sh — runs the kanban task through the HOST's Hermes.
#
# Architecture: hermes, the profiles, and the vault all live on the PVE host
# (192.168.1.68). The worker CT (104) orchestrates but must not carry its own
# Hermes. This executor scp-s the prompt to the host, runs `hermes -p
# <profile> chat -q "$(cat <remote>)` (single arg, no shell mangling), cleans
# up the remote file, and returns the result.
#
# Args: <profile> <prompt-file>
set -euo pipefail

PROFILE="${1:?profile}"
PROMPT_FILE="${2:?prompt-file}"
SSH_KEY="${KANBAN_SSH_KEY:-/root/.ssh/kanban_worker}"
HOST="${KANBAN_HOST:-root@192.168.1.68}"
REMOTE="/tmp/kanban-worker-prompt.$$"

# Copy the prompt to the host, run hermes, then remove the remote file.
scp -q -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$PROMPT_FILE" "$HOST:$REMOTE"
trap 'ssh -q -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$HOST" "rm -f $REMOTE" 2>/dev/null || true' EXIT
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new \
  -o ConnectTimeout=10 "$HOST" \
  "/usr/local/bin/hermes -p $(printf '%q' "$PROFILE") chat -q \"\$(cat $REMOTE)\"" 2>/dev/null