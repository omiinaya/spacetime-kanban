#!/usr/bin/env python3
"""Clear all kanban tasks via the API's delete_task reducer."""

import httpx

API = "http://localhost:8728"


def main():
    resp = httpx.get(f"{API}/api/tasks", timeout=60)
    resp.raise_for_status()
    tasks = resp.json()
    total = len(tasks)
    print(f"Total tasks: {total}")

    for i, task in enumerate(tasks):
        tid = task["id"]
        try:
            r = httpx.delete(f"{API}/api/tasks/{tid}", timeout=10)
            if r.status_code == 200:
                print(f"[{i + 1}/{total}] Deleted {tid}", flush=True)
            else:
                print(f"[{i + 1}/{total}] FAIL {tid}: {r.status_code} {r.text[:100]}", flush=True)
        except Exception as e:
            print(f"[{i + 1}/{total}] ERROR {tid}: {e}", flush=True)

    print(f"\nDone. Deleted {total} tasks.")


if __name__ == "__main__":
    main()
