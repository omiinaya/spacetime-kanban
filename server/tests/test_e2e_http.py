"""End-to-end HTTP integration tests for spacetime-kanban.

These tests hit the REAL server at http://localhost:8727 and require a
running backend + SpacetimeDB instance with the kanban module published.

Usage:
    python -m pytest tests/test_e2e_http.py -v --tb=short

    # Skip mutation tests (read-only health + list):
    python -m pytest tests/test_e2e_http.py -v --tb=short -k "health or list"

Run ALL tests (including e2e-marked):
    python -m pytest tests/test_e2e_http.py -v --tb=short -m e2e
"""

import contextlib
import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("KANBAN_API_BASE", "http://localhost:8727")
E2E_TAG = f"e2e-{uuid.uuid4().hex[:8]}"
RUN_ID = uuid.uuid4().hex[:8]

pytestmark = pytest.mark.e2e


# ── Skip guard ─────────────────────────────────────────────────────────


def _server_reachable() -> bool:
    """Return True iff the kanban server's health endpoint responds."""
    try:
        resp = httpx.get(f"{BASE_URL}/api/health", timeout=5)
        return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


_SERVER_UP = _server_reachable()


def _require_server():
    """Skip the entire module if the server is not reachable."""
    if not _SERVER_UP:
        pytest.skip(
            f"kanban server not reachable at {BASE_URL}/api/health — "
            "start the server and SpacetimeDB first"
        )


def _mutation_available() -> bool:
    """Quick probe: can we create a task?

    Returns True if the create endpoint accepts requests (auth disabled OR
    our API key works).  False if STDB is down, the database is missing,
    or auth blocks us.
    """
    import json as _json

    try:
        body = _json.dumps({"title": "e2e-probe", "repo": "e2e-test", "description": "probe"})
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get("KANBAN_API_KEY")
        if api_key:
            headers["X-API-Key"] = api_key
        resp = httpx.post(
            f"{BASE_URL}/api/tasks",
            content=body,
            headers=headers,
            timeout=10,
        )
        # 201 = created, 200 = created/exists, 401 = auth needed, 502 = STDB down
        return resp.status_code in (200, 201)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
        return False


_MUTATIONS_OK = _mutation_available() if _SERVER_UP else False


def _require_mutations():
    """Skip mutation-dependent tests if the server can't accept them."""
    if not _MUTATIONS_OK:
        pytest.skip(
            "mutation endpoints not available — STDB may be down, "
            "database missing, or auth required (set KANBAN_API_KEY)"
        )


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
async def client():
    """Async HTTP client pointed at the real kanban server."""
    api_key = os.environ.get("KANBAN_API_KEY")
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=15) as ac:
        yield ac


@pytest.fixture
async def created_task(client):
    """Create a test task, yield its id, then delete it on teardown."""
    _require_mutations()
    body = {
        "title": f"[{E2E_TAG}] E2E Test Task {uuid.uuid4().hex[:6]}",
        "repo": "test-e2e",
        "description": "Task created by the E2E HTTP integration test suite",
    }
    resp = await client.post("/api/tasks", json=body)
    # If the server is running but STDB isn't configured, this will fail
    if resp.status_code not in (200, 201):
        pytest.skip(f"cannot create test task (status {resp.status_code}): {resp.text[:200]}")
    data = resp.json()
    task_id = data.get("id")
    if not task_id:
        pytest.skip(f"no task id in response: {data}")
    yield task_id
    # Cleanup
    with contextlib.suppress(Exception):
        await client.delete(f"/api/tasks/{task_id}")


# ═══════════════════════════════════════════════════════════════════════
# 1. Health endpoint
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """Health endpoint returns status=ok with board/crashes/workers fields."""
    _require_server()
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "board" in data, f"board missing from health: {data.keys()}"
    assert "crashes" in data, f"crashes missing from health: {data.keys()}"
    assert "workers" in data, f"workers missing from health: {data.keys()}"
    # Type checks
    assert isinstance(data["board"], dict)
    assert isinstance(data["crashes"], dict)
    assert isinstance(data["workers"], dict)


# ═══════════════════════════════════════════════════════════════════════
# 2. List available tasks
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_available_tasks(client):
    """GET /api/tasks?status=available returns a list."""
    _require_server()
    resp = await client.get("/api/tasks", params={"status": "available", "limit": 10})
    assert resp.status_code in (200, 502), (
        f"unexpected status: {resp.status_code} {resp.text[:200]}"
    )
    if resp.status_code == 502:
        pytest.skip(f"STDB query failed: {resp.text[:200]}")
    data = resp.json()
    assert isinstance(data, list)
    # Should always return a list (empty or populated)
    for t in data:
        assert "id" in t
        assert "title" in t
        assert "status" in t


# ═══════════════════════════════════════════════════════════════════════
# 3. Create a task
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_task(client):
    """POST /api/tasks creates a task and returns its id."""
    _require_server()
    _require_mutations()
    title = f"[{E2E_TAG}] Create test {uuid.uuid4().hex[:6]}"
    body = {
        "title": title,
        "repo": "test-e2e",
        "description": "Testing task creation via E2E HTTP test",
    }
    resp = await client.post("/api/tasks", json=body)
    assert resp.status_code in (
        200,
        201,
    ), f"create failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()
    assert "id" in data, f"no id in create response: {data}"
    task_id = data["id"]
    assert len(task_id) > 0
    # Cleanup
    await client.delete(f"/api/tasks/{task_id}")


# ═══════════════════════════════════════════════════════════════════════
# 4. Created task appears in list
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_created_task_appears_in_list(client, created_task):
    """A newly created task shows up in the task list."""
    task_id = created_task
    # Try fetching directly
    resp = await client.get(f"/api/tasks/{task_id}")
    if resp.status_code == 502:
        pytest.skip(f"STDB query failed: {resp.text[:200]}")
    assert resp.status_code == 200, f"get task failed: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    assert data["id"] == task_id
    assert data["status"] in ("available", "inProgress")
    # Try listing with search
    list_resp = await client.get("/api/tasks", params={"search": task_id[:20], "limit": 50})
    if list_resp.status_code == 200:
        tasks = list_resp.json()
        ids = {t["id"] for t in tasks}
        assert task_id in ids, f"task {task_id} not found in list: {ids}"


# ═══════════════════════════════════════════════════════════════════════
# 5. Claim a task
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_claim_task(client, created_task):
    """POST /api/tasks/{id}/claim claims the task for an agent."""
    task_id = created_task
    agent_id = f"e2e-test-agent-{RUN_ID}"
    resp = await client.post(
        f"/api/tasks/{task_id}/claim",
        json={"agent_id": agent_id},
    )
    if resp.status_code in (502,):
        pytest.skip(f"STDB mutation failed: {resp.text[:200]}")
    assert resp.status_code in (
        200,
        409,
    ), f"claim failed: {resp.status_code} {resp.text[:300]}"
    if resp.status_code == 409:
        # Another agent may have claimed it — that's OK for this test
        return
    data = resp.json()
    assert data["status"] == "claimed"
    assert data["task_id"] == task_id
    assert data["assigned_to"] == agent_id
    # Verify the task is now in_progress
    t = await client.get(f"/api/tasks/{task_id}")
    if t.status_code == 200:
        assert t.json()["status"] == "inProgress"
        assert t.json()["assigned_to"] == agent_id


# ═══════════════════════════════════════════════════════════════════════
# 6. Double-claim returns 409
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_double_claim_returns_409(client, created_task):
    """Claiming an already-claimed task returns 409 Conflict."""
    task_id = created_task
    agent_a = f"e2e-agent-a-{RUN_ID}"
    agent_b = f"e2e-agent-b-{RUN_ID}"

    # First claim
    r1 = await client.post(f"/api/tasks/{task_id}/claim", json={"agent_id": agent_a})
    if r1.status_code in (502,):
        pytest.skip(f"STDB mutation failed: {r1.text[:200]}")
    if r1.status_code == 409:
        # Someone else already claimed it — skip the double-claim test
        pytest.skip("task was already claimed by another agent")
    assert r1.status_code == 200, f"first claim failed: {r1.status_code} {r1.text[:300]}"

    # Second claim by a different agent — must fail
    r2 = await client.post(f"/api/tasks/{task_id}/claim", json={"agent_id": agent_b})
    assert r2.status_code == 409, (
        f"expected 409 for double claim, got {r2.status_code}: {r2.text[:200]}"
    )

    # Verify the task still belongs to agent_a
    t = await client.get(f"/api/tasks/{task_id}")
    if t.status_code == 200:
        assert t.json()["assigned_to"] == agent_a


# ═══════════════════════════════════════════════════════════════════════
# 7. Complete a claimed task
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_complete_task(client, created_task):
    """POST /api/tasks/{id}/complete marks a claimed task as done."""
    task_id = created_task
    agent_id = f"e2e-completer-{RUN_ID}"

    # Claim
    claim_r = await client.post(f"/api/tasks/{task_id}/claim", json={"agent_id": agent_id})
    if claim_r.status_code in (502,):
        pytest.skip(f"STDB mutation failed: {claim_r.text[:200]}")
    if claim_r.status_code == 409:
        # Another agent claimed it — unclaim first, then re-claim
        await client.post(f"/api/tasks/{task_id}/unclaim")
        claim_r = await client.post(f"/api/tasks/{task_id}/claim", json={"agent_id": agent_id})
        if claim_r.status_code != 200:
            pytest.skip("could not claim task for complete test")
    assert claim_r.status_code == 200, f"claim for complete failed: {claim_r.status_code}"

    # Complete
    notes = f"E2E test completed at {uuid.uuid4().hex[:8]}"
    comp_r = await client.post(
        f"/api/tasks/{task_id}/complete",
        json={"result_notes": notes},
    )
    if comp_r.status_code in (502,):
        pytest.skip(f"STDB complete failed: {comp_r.text[:200]}")
    assert comp_r.status_code == 200, f"complete failed: {comp_r.status_code} {comp_r.text[:300]}"
    data = comp_r.json()
    assert data["status"] in ("completed",), f"unexpected complete status: {data}"

    # Verify the task is done
    t = await client.get(f"/api/tasks/{task_id}")
    if t.status_code == 200:
        assert t.json()["status"] == "done"


# ═══════════════════════════════════════════════════════════════════════
# 8. Analytics overview
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analytics_overview(client):
    """GET /api/analytics/overview returns valid analytics data."""
    _require_server()
    resp = await client.get("/api/analytics/overview")
    assert resp.status_code in (200, 502), f"unexpected: {resp.status_code} {resp.text[:200]}"
    if resp.status_code == 502:
        pytest.skip(f"STDB query failed: {resp.text[:200]}")
    data = resp.json()
    assert isinstance(data, dict)
    # Expected fields from the analytics overview endpoint
    expected_fields = {"total", "by_status", "repos"}
    optional_fields = {"claims_last_hour", "completions_last_hour", "claim_complete_ratio"}
    for field in expected_fields:
        assert field in data, (
            f"field {field!r} missing from analytics overview: {list(data.keys())}"
        )
    for field in optional_fields:
        if field in data:
            assert isinstance(data[field], (int, float, dict)), (
                f"field {field!r} has unexpected type: {type(data[field])}"
            )
    # Type checks for required fields
    assert isinstance(data["total"], (int, float))
    assert isinstance(data["by_status"], dict)
    assert isinstance(data["repos"], (dict, list))
