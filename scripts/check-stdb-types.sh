#!/usr/bin/env bash
# check-stdb-types.sh — STDB generated-type drift guard.
#
# Regenerates the TypeScript client bindings from the Rust module source and
# diffs them against the checked-in web/src/stdb/. If they differ, the WebSocket
# deserializer can silently crash at runtime (this exact bug blanked the board:
# 91 deserializer exceptions, 0 tasks rendered — see commit a9e4f72).
#
# Usage:
#   scripts/check-stdb-types.sh          # check only (CI mode, exit 1 on drift)
#   scripts/check-stdb-types.sh --fix    # regenerate and overwrite web/src/stdb
#
# Requires: spacetime CLI on PATH, cargo toolchain (first run compiles the module).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE_PATH="$REPO_ROOT/server/spacetimedb"
CHECKED_IN="$REPO_ROOT/web/src/stdb"
TMP_DIR="$(mktemp -d /tmp/stdb-gen-XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "▸ Regenerating types from $MODULE_PATH ..."
spacetime generate --lang typescript \
  --module-path "$MODULE_PATH" \
  --out-dir "$TMP_DIR/gen" > /dev/null

if [[ "${1:-}" == "--fix" ]]; then
  rm -rf "$CHECKED_IN"
  cp -r "$TMP_DIR/gen" "$CHECKED_IN"
  echo "✔ web/src/stdb regenerated from module source."
  exit 0
fi

if diff -rq "$TMP_DIR/gen" "$CHECKED_IN" > /dev/null 2>&1; then
  echo "✔ STDB types are in sync with the module."
  exit 0
else
  echo "✘ STDB TYPE DRIFT DETECTED — checked-in web/src/stdb is stale:"
  diff -rq "$TMP_DIR/gen" "$CHECKED_IN" | head -30
  echo
  echo "Run: scripts/check-stdb-types.sh --fix"
  exit 1
fi
