#!/bin/bash
set -euo pipefail

# If a command is passed, run it instead
if [ $# -gt 0 ]; then
    exec "$@"
fi

STDB_SERVER="http://${STDB_HOST:-localhost}:${STDB_PORT:-3001}"

# Wait for SpacetimeDB to be ready
echo "Waiting for SpacetimeDB at ${STDB_SERVER}..."
for i in $(seq 1 60); do
    if curl -sf "${STDB_SERVER}/health" >/dev/null 2>&1; then
        echo "SpacetimeDB is ready!"
        break
    fi
    echo "Attempt $i/60: STDB not ready yet..."
    sleep 2
done

# Publish the WASM module to SpacetimeDB
MODULE_WASM="/app/server/spacetimedb/module.wasm"
if [ -f "$MODULE_WASM" ]; then
    echo "Publishing module to SpacetimeDB..."
    spacetime publish -f "$MODULE_WASM" \
        -s "${STDB_SERVER}" \
        -d "${STDB_DB:-kanban}" \
        --yes 2>&1 || echo "Module publish skipped (may already exist or no changes)"
fi

# Start the Python server
cd /app/server
echo "Starting kanban server on port ${SERVER_PORT:-8727}..."
exec python main.py
