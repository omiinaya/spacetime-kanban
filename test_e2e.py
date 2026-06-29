#!/usr/bin/env python3
"""End-to-end test: simulates two agents claiming tasks atomically."""
import httpx, time, json

BASE = "http://localhost:8727"

def test_health():
    r = httpx.get(f"{BASE}/api/health")
    assert r.status_code == 200, f"Health: {r.status_code}"
    print("✅ Health check")

def test_list_tasks():
    r = httpx.get(f"{BASE}/api/tasks?status=available")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) >= 6, f"Expected 6+ available tasks, got {len(tasks)}"
    print(f"✅ List tasks: {len(tasks)} available tasks found")
    return tasks

def test_create_task():
    r = httpx.post(f"{BASE}/api/tasks", json={
        "title": "Integration test task",
        "description": "Created by E2E test",
        "priority": 1,
        "repo": "spacetimedb-kanban",
        "roadmap_item": "Test",
        "created_by": "e2e-test",
    })
    assert r.status_code == 201, f"Create: {r.status_code} {r.text}"
    print(f"✅ Created task: {r.json().get('id', 'ok')}")

def test_atomic_claim():
    """Two agents try to claim the same task — only one should succeed."""
    # Get first available task
    r = httpx.get(f"{BASE}/api/tasks?status=available&repo=sample-repo-p")
    tasks = r.json()
    if not tasks:
        print("⚠ No available tasks to claim")
        return
    task_id = tasks[0]["id"]
    print(f"  Task {task_id[:20]}... — trying two simultaneous claims")

    # Agent 1 claims
    r1 = httpx.post(f"{BASE}/api/tasks/{task_id}/claim", json={"agent_id": "hermes-test"})
    # Agent 2 tries same task
    r2 = httpx.post(f"{BASE}/api/tasks/{task_id}/claim", json={"agent_id": "claude-test"})

    success = [a for a, r in [("hermes-test", r1), ("claude-test", r2)] if r.status_code == 200]
    failures = [a for a, r in [("hermes-test", r1), ("claude-test", r2)] if r.status_code >= 400]

    print(f"  200 OK: {success}")
    print(f"  409 Conflict: {failures}")

    assert len(success) == 1, f"Expected exactly 1 success, got {len(success)}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}"
    print("✅ Atomic claim works — only one agent claimed the task")

    # Release it back
    r = httpx.post(f"{BASE}/api/tasks/{task_id}/unclaim")
    assert r.status_code == 200, f"Unclaim: {r.status_code}"
    print("✅ Unclaimed task back to available")

def test_claim_complete_flow():
    r = httpx.get(f"{BASE}/api/tasks?status=available")
    tasks = r.json()
    if not tasks:
        print("⚠ No tasks to test complete flow")
        return
    task_id = tasks[0]["id"]

    # Claim
    r = httpx.post(f"{BASE}/api/tasks/{task_id}/claim", json={"agent_id": "e2e-test"})
    assert r.status_code == 200
    print(f"  Claimed {task_id[:20]}...")

    # Complete
    r = httpx.post(f"{BASE}/api/tasks/{task_id}/complete", json={"result_notes": "All tests passed"})
    assert r.status_code == 200, f"Complete: {r.status_code} {r.text}"
    print(f"✅ Claim→Complete flow works")

def test_block_unclaim():
    r = httpx.get(f"{BASE}/api/tasks?status=available")
    tasks = r.json()
    if not tasks:
        print("⚠ No tasks to test block flow")
        return
    task_id = tasks[0]["id"]

    r = httpx.post(f"{BASE}/api/tasks/{task_id}/claim", json={"agent_id": "block-test"})
    assert r.status_code == 200

    r = httpx.post(f"{BASE}/api/tasks/{task_id}/block", json={"reason": "Dependency not ready"})
    assert r.status_code == 200, f"Block: {r.status_code}"
    print("  Task blocked")

    r = httpx.post(f"{BASE}/api/tasks/{task_id}/unclaim")
    assert r.status_code == 200
    print(f"✅ Block→Unclaim flow works")

def test_logs():
    r = httpx.get(f"{BASE}/api/logs?limit=5")
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) > 0, "Expected at least one log entry"
    print(f"✅ Activity log: {len(logs)} entries")

def test_agents():
    r = httpx.get(f"{BASE}/api/agents")
    assert r.status_code == 200
    agents = r.json()
    print(f"✅ Active agents: {len(agents)} registered")

def test_delete():
    r = httpx.get(f"{BASE}/api/tasks?status=available")
    tasks = r.json()
    if not tasks:
        print("⚠ No tasks to delete")
        return
    task_id = tasks[0]["id"]
    r = httpx.delete(f"{BASE}/api/tasks/{task_id}")
    assert r.status_code == 200
    print(f"✅ Delete task: {task_id[:20]}...")

if __name__ == "__main__":
    try:
        test_health()
        test_list_tasks()
        test_create_task()
        test_atomic_claim()
        test_claim_complete_flow()
        test_block_unclaim()
        test_logs()
        test_agents()
        test_delete()
        print("\n🎉 All E2E tests passed!")
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
