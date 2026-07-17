"""Integration tests against a LIVE kanban server + SpacetimeDB.

Unlike test_api.py (fully mocked STDB), these tests exercise the real reducer
chain: FastAPI → STDB HTTP API → Rust reducers → database. They verify the
two invariants that mocking cannot prove:

1. Claim atomicity — two concurrent claims on the same task yield exactly
   one winner (the claim_task reducer is transactional).
2. Dependency enforcement — a task whose dependency is not done cannot be
   claimed, and becomes claimable once the dependency completes.

Run with:  KANBAN_LIVE=1 venv/bin/python -m pytest tests/test_integration_stdb.py -v
Skipped by default so CI (no live STDB) stays green.

All test tasks use a unique run prefix and are deleted in teardown.
"""

import os
import time
import uuid

import httpx
import pytest

BASE = os.environ.get("KANBAN_API_BASE", "http://localhost:8727")
RUN_ID = uuid.uuid4().hex[:8]

pytestmark = pytest.mark.skipif(
    not os.environ.get("KANBAN_LIVE"),
    reason="live STDB integration tests — set KANBAN_LIVE=1 to run",
)


def _title(name: str) -> str:
    return f"[itest-{RUN_ID}] {name}"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=15) as c:
        resp = c.get("/api/health")
        assert resp.status_code == 200, f"kanban server not healthy at {BASE}"
        yield c


@pytest.fixture()
def task(client):
    """Create a live test task, delete it after the test."""
    created = []

    def _make(title: str, **kw):
        body = {"title": _title(title), "priority": 2, "repo": "integration-test", **kw}
        resp = client.post("/api/tasks", json=body)
        assert resp.status_code == 201, resp.text
        tid = resp.json()["id"]
        created.append(tid)
        return tid

    yield _make

    for tid in created:
        client.delete(f"/api/tasks/{tid}")


def force_claim(client: httpx.Client, tid: str, agent: str, attempts: int = 10):
    """Claim a task, beating the live dispatcher's competing claims.

    The real dispatcher and agent-swarm swarm poll for available tasks every few
    minutes and will happily claim integration-test tasks. unclaim works
    regardless of who holds the task, so: unclaim → claim, retry until ours.
    """
    last = None
    for _ in range(attempts):
        r = client.post(f"/api/tasks/{tid}/claim", json={"agent_id": agent})
        if r.status_code == 200:
            # Verify we actually own it (a 200 from an earlier state read could lie)
            t = client.get(f"/api/tasks/{tid}").json()
            if t.get("assigned_to") == agent:
                return
        client.post(f"/api/tasks/{tid}/unclaim")
        time.sleep(0.3)
        last = r
    raise AssertionError(f"could not claim {tid} as {agent} after {attempts} attempts (last: {last.status_code if last else '?'} {last.text[:120] if last else ''})")


# ── Claim atomicity ──────────────────────────────────────────────────


def test_claim_atomicity_sequential(client, task):
    """Second claim of an already-claimed task must fail."""
    tid = task("claim race")
    force_claim(client, tid, "agent-a")

    r2 = client.post(f"/api/tasks/{tid}/claim", json={"agent_id": "agent-b"})
    assert r2.status_code in (400, 409, 500), (
        f"second claim should fail, got {r2.status_code}: {r2.text}"
    )

    # Task must belong to the FIRST claimant
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["assigned_to"] == "agent-a"
    assert t["status"] == "in_progress"


def test_claim_atomicity_concurrent(client, task):
    """10 concurrent claims → at most 1 winner, and the final owner is unique.

    The live dispatcher may also race in — if it wins, all 10 racers fail,
    which is still correct atomicity (exactly one owner overall).
    """
    import concurrent.futures

    tid = task("concurrent claim race")

    def claim(i):
        return i, client.post(f"/api/tasks/{tid}/claim", json={"agent_id": f"racer-{i}"})

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(claim, range(10)))

    winners = [i for i, r in results if r.status_code == 200]
    assert len(winners) <= 1, f"expected at most 1 winner, got {len(winners)}: {winners}"

    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "in_progress"
    if winners:
        assert t["assigned_to"] == f"racer-{winners[0]}"
    else:
        # Dispatcher won the race — still proves a single owner
        assert t["assigned_to"] is not None


# ── Dependency enforcement ───────────────────────────────────────────


def test_dependency_blocks_claim_until_done(client, task):
    """B depends on A: claim(B) fails until A completes."""
    a = task("dependency parent")
    b = task("dependency child")

    r = client.post(f"/api/tasks/{b}/dependency", json={"depends_on": a})
    assert r.status_code == 200, r.text

    # Claim B while A is available → must fail
    r = client.post(f"/api/tasks/{b}/claim", json={"agent_id": "dep-test"})
    assert r.status_code in (400, 409, 500), (
        f"claim with unfinished dependency should fail, got {r.status_code}: {r.text}"
    )

    # Complete A: claim it first, then complete
    force_claim(client, a, "dep-test")
    assert client.post(f"/api/tasks/{a}/complete", json={"result_notes": "itest"}).status_code == 200

    # Now B must be claimable
    force_claim(client, b, "dep-test")

    t = client.get(f"/api/tasks/{b}").json()
    assert t["status"] == "in_progress"
    assert t["assigned_to"] == "dep-test"


def test_dependency_clear_allows_claim(client, task):
    """Clearing a dependency frees the task immediately."""
    a = task("dep parent clear")
    b = task("dep child clear")
    client.post(f"/api/tasks/{b}/dependency", json={"depends_on": a})

    r = client.post(f"/api/tasks/{b}/claim", json={"agent_id": "dep-test"})
    assert r.status_code in (400, 409, 500)

    # Clear dependency with empty string
    r = client.post(f"/api/tasks/{b}/dependency", json={"depends_on": ""})
    assert r.status_code == 200

    force_claim(client, b, "dep-test")


# ── State machine round-trips ────────────────────────────────────────


def block_to_limit(client: httpx.Client, tid: str, agent: str, reason: str = "itest block"):
    """Drive a task to genuinely-blocked state.

    block_task_with_reason only marks 'blocked' when fail_count reaches
    max_attempts (default 3); before that it returns the task to available
    for retry (intentional reducer semantics). So: claim → fail, 3 times.
    """
    for i in range(3):
        force_claim(client, tid, agent)
        r = client.post(f"/api/tasks/{tid}/block-with-reason", json={"reason": f"{reason} #{i + 1}"})
        assert r.status_code == 200, r.text
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "blocked", f"expected blocked after 3 fails, got {t['status']} (fc={t['fail_count']})"
    return t


def test_blocked_task_unclaims_to_available(client, task):
    """blocked --[unclaim]--> available (the path bulk-retry relies on)."""
    tid = task("block roundtrip")
    block_to_limit(client, tid, "sm-test")

    r = client.post(f"/api/tasks/{tid}/unclaim")
    assert r.status_code == 200, r.text
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "available"
    assert t["assigned_to"] is None


def test_bulk_retry_resets_and_releases(client, task):
    """bulk-retry: blocked task returns to available with fail_count = 0."""
    tid = task("bulk retry")
    block_to_limit(client, tid, "br-test", "itest bulk-retry")

    r = client.post("/api/tasks/bulk-retry", json={"task_ids": [tid], "reset_fails": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["retried"] == 1, data
    assert data["failed"] == [], data

    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "available"
    assert t["fail_count"] == 0

    # And it must be claimable again (circuit breaker gives a fresh budget)
    force_claim(client, tid, "br-test")


def test_archive_hides_and_unarchive_restores(client, task):
    """archive → task disappears from default lists; unarchive restores."""
    tid = task("archive roundtrip")

    r = client.post(f"/api/tasks/{tid}/archive")
    assert r.status_code == 200, r.text
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["archived"] is True

    r = client.post(f"/api/tasks/{tid}/unarchive")
    assert r.status_code == 200, r.text
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["archived"] is False


# ── Data integrity ───────────────────────────────────────────────────


def test_created_task_has_expected_defaults(client, task):
    """Reducer-assigned defaults: status available, fail_count 0, not archived."""
    tid = task("defaults check")
    t = client.get(f"/api/tasks/{tid}").json()
    assert t["status"] == "available"
    assert t["fail_count"] == 0
    assert t["archived"] is False
    assert t["assigned_to"] is None
    assert t["created_at"] > 0
