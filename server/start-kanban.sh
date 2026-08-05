#!/bin/bash
# Start the kanban backend from the server/ directory.
# Uses relative paths so it works from any checkout location.
cd "$(dirname "$0")"
if [ -d venv ]; then
    source venv/bin/activate
fi
exec python main.py
