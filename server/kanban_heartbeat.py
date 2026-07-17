#!/usr/bin/env python3
"""Heartbeat for the kanban swarm — keeps Hermes marked as online.

Runs every 2 minutes via cron. Sends a heartbeat to the kanban API.
Silent when successful (no_agent mode — only output on error).
"""

import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8728")
AGENT_ID = os.environ.get("KANBAN_AGENT_ID", "hermes")


def main():
    url = f"{API_BASE}/api/agents/{AGENT_ID}/heartbeat"
    data = json.dumps({"agent_id": AGENT_ID, "status": "online"}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode()
        if resp.status >= 400:
            print(f"ERROR: Heartbeat failed ({resp.status}): {body[:200]}")
            sys.exit(1)
        # Success = silent (no output = no notification in no_agent mode)
    except Exception as e:
        print(f"ERROR: Heartbeat exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
