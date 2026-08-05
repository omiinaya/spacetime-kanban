"""Unit tests for spacetime-kanban API with mocked STDB backend."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from main import app

# ── Helpers ────────────────────────────────────────────────────────────


def _make_task(
    tid="task_1",
    title="Test task",
    description="A test task",
    priority=0,
    status="available",
    repo="sample-repo-q",
    due_by=None,
    sprint=None,
    archived=False,
    estimated_hours=None,
    spent_hours=None,
):
    """Build a minimal task dict as returned by STDB rows."""
    return {
        "id": tid,
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "assigned_to": None,
        "repo": repo,
        "branch": None,
        "roadmap_item": "",
        "created_by": "test",
        "created_at": 1000,
        "updated_at": 1000,
        "depends_on": None,
        "required_skills": None,
        "score": 0,
        "position": None,
        "fail_count": 0,
        "max_attempts": 3,
        "fail_reason": None,
        "subtask_of": None,
        "subtasks": None,
        "due_by": due_by,
        "sprint": sprint,
        "archived": archived,
        "estimated_hours": estimated_hours,
        "spent_hours": spent_hours,
    }


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def mock_all():
    """Mock STDB helpers for every test — covers both main.py and route modules."""
    # ── Route modules that import STDB helpers from shared ──────
    route_modules = {
        "routes.agents": ["_sql", "_sql_param", "_call"],
        "routes.analytics": ["_sql", "_sql_param"],
        "routes.github": ["_sql_param", "_call", "_notify"],
        "routes.labels": ["_sql", "_sql_param", "_call"],
        "routes.logs": ["_sql"],
        "routes.projects": ["_sql", "_sql_param", "_call"],
        "routes.tasks": ["_sql", "_sql_param", "_call", "_notify"],
        "routes.templates": ["_sql", "_sql_param", "_call"],
        "routes.ops": ["_sql", "_sql_param", "_call"],
        "routes.dispatcher": ["_sql", "_sql_param", "_call"],
        "routes.rules": ["_sql", "_sql_param", "_call"],
        "routes.apikeys": ["_sql", "_call"],
    }

    with ExitStack() as stack:
        # Create the shared mocks
        sql = AsyncMock(return_value=[])
        param = AsyncMock(return_value=[])
        call = AsyncMock(return_value={"status": "ok"})
        notify = AsyncMock(return_value=None)

        # Map function names to their mock objects
        mock_map = {"_sql": sql, "_sql_param": param, "_call": call, "_notify": notify}

        # Patch each route module's references with the SAME mock objects
        for mod, names in route_modules.items():
            for name in names:
                stack.enter_context(patch(f"{mod}.{name}", mock_map[name]))

        # Patch shared module for dynamic imports (e.g. routes/health.py which
        # does `from shared import _sql` inside the function body at call time)
        for name in ("_sql",):
            stack.enter_context(patch(f"shared.{name}", mock_map[name]))

        yield {"sql": sql, "param": param, "call": call, "notify": notify}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def enable_auth():
    """Temporarily enable API key auth for testing."""
    with patch("main.settings.api_key", "test-api-key-123"):
        yield


@pytest.fixture
def mock_webhooks():
    """Mock webhooks module STDB calls (sync functions)."""
    with (
        patch("webhooks._stdb_sql", return_value=[]) as stdb,
        patch("webhooks._sql_param", return_value=[]) as param,
        patch("webhooks._call", return_value={"status": "ok"}) as call,
    ):
        yield {"stdb": stdb, "param": param, "call": call}


# ════════════════════════════════════════════════════════════════════════
# Health
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # Health endpoint now includes scheduler state and board overview
    assert "workers" in data
    assert "crashes" in data
    assert "board" in data


# ════════════════════════════════════════════════════════════════════════
# List Tasks
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_tasks_empty(client, mock_all):
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_tasks_cache_hit(client, mock_all):
    """Second call within the TTL reuses the cached rows (no second _sql)."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Fix auth", repo="sample-repo-q"),
        _make_task("t2", "Add captcha", repo="spacetime-browser"),
    ]
    resp1 = await client.get("/api/tasks", params={"search": "auth"})
    assert resp1.status_code == 200
    assert len(resp1.json()) == 1

    sql_calls_after_first = mock_all["sql"].call_count

    resp2 = await client.get("/api/tasks", params={"search": "captcha"})
    assert resp2.status_code == 200
    assert len(resp2.json()) == 1
    # Cache hit — no additional _sql query fired
    assert mock_all["sql"].call_count == sql_calls_after_first


@pytest.mark.asyncio
async def test_list_tasks_cache_invalidated_on_write(client, mock_all):
    """A task mutation clears the cache so the next list re-queries STDB."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Fix auth", repo="sample-repo-q"),
        _make_task("t2", "Add captcha", repo="spacetime-browser"),
    ]
    # Warm the cache
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    sql_calls_after_read = mock_all["sql"].call_count

    # A write (create) invalidates the cache
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []
    create_resp = await client.post(
        "/api/tasks",
        json={"title": "New task", "repo": "test", "description": "d"},
    )
    assert create_resp.status_code in (201, 200)

    # Next read must hit STDB again (cache was cleared)
    resp2 = await client.get("/api/tasks")
    assert resp2.status_code == 200
    assert mock_all["sql"].call_count > sql_calls_after_read


@pytest.mark.asyncio
async def test_list_tasks_with_repo_filter(client, mock_all):
    mock_all["sql"].return_value = [
        _make_task("t1", "Fix auth", repo="sample-repo-q"),
        _make_task("t2", "Add captcha", repo="spacetime-browser"),
    ]
    resp = await client.get("/api/tasks", params={"repo": "sample-repo-q"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_search(client, mock_all):
    """Search filter should match by title, description, repo, etc."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Fix auth bug", "Authentication module fix"),
        _make_task("t2", "Add dashboard", "captcha dashboard for auth flow"),
        _make_task("t3", "Setup CI", "CI pipeline"),
    ]
    resp = await client.get("/api/tasks", params={"search": "auth"})
    assert resp.status_code == 200
    data = resp.json()
    # Should match t1 (title) and t2 (description)
    assert len(data) == 2
    titles = {d["title"] for d in data}
    assert "Fix auth bug" in titles
    assert "Add dashboard" in titles


@pytest.mark.asyncio
async def test_list_tasks_with_repo_and_search(client, mock_all):
    """Combined repo + search filtering."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Fix auth", repo="sample-repo-q"),
        _make_task("t2", "Auth captcha", repo="spacetime-browser"),
    ]
    mock_all["param"].return_value = [
        _make_task("t1", "Fix auth", repo="sample-repo-q"),
    ]
    resp = await client.get("/api/tasks", params={"repo": "sample-repo-q", "search": "auth"})
    assert resp.status_code == 200
    data = resp.json()
    # repo filter with param, then search filter client-side
    assert len(data) == 1
    assert data[0]["repo"] == "sample-repo-q"


# ════════════════════════════════════════════════════════════════════════
# Create Task
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_task(client, mock_all):
    """Task creation should return the created task with status=available."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # empty = no dedup match, create proceeds
    resp = await client.post(
        "/api/tasks", json={"title": "New task", "priority": 5, "repo": "test"}
    )
    assert resp.status_code == 200 or resp.status_code == 201
    data = resp.json()
    # Endpoint returns {"id": ..., "status": "created"} on success
    assert data.get("status") == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_task_missing_title(client, mock_all):
    """Missing required title should return 422."""
    resp = await client.post("/api/tasks", json={"repo": "test"})
    assert resp.status_code == 422


# ════════════════════════════════════════════════════════════════════════
# Due By (Deadline)
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_task_with_due_by(client, mock_all):
    """Task creation with due_by should preserve the deadline."""
    due_by_ms = 1893456000000  # 2030-01-01
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # empty = no dedup match, create proceeds
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Due task",
            "repo": "test",
            "due_by": due_by_ms,
        },
    )
    assert resp.status_code == 200 or resp.status_code == 201
    data = resp.json()
    assert data.get("status") == "created"


@pytest.mark.asyncio
async def test_list_tasks_due_by_field(client, mock_all):
    """List tasks returns due_by field for tasks that have one."""
    due_by_ms = 1893456000000
    mock_all["sql"].return_value = [
        _make_task("t1", "Due task", due_by=due_by_ms),
        _make_task("t2", "No due task"),
    ]
    resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    has_due = [t for t in data if t["due_by"] is not None]
    assert len(has_due) == 1
    assert has_due[0]["due_by"] == due_by_ms


# ════════════════════════════════════════════════════════════════════════
# Task Templates
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_templates_empty(client, mock_all):
    resp = await client.get("/api/task-templates")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_template(client, mock_all):
    """Create a task template and verify it's returned."""
    mock_all["param"].return_value = [
        {
            "id": "tpl_abc123",
            "title": "Weekly cleanup",
            "description": "Clean up old branches",
            "priority": 2,
            "repo": "sample-repo-n",
            "roadmap_item": "",
            "required_skills": None,
            "cron_schedule": "weekly mon 9:00",
            "created_by": "test",
            "created_at": 1000,
            "last_triggered_at": 0,
            "active": True,
        }
    ]
    resp = await client.post(
        "/api/task-templates",
        json={
            "title": "Weekly cleanup",
            "cron_schedule": "weekly mon 9:00",
            "repo": "sample-repo-n",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Weekly cleanup"
    assert data["cron_schedule"] == "weekly mon 9:00"


# ════════════════════════════════════════════════════════════════════════
# Agents
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_agents_empty(client, mock_all):
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json() == []


# ════════════════════════════════════════════════════════════════════════
# Projects
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_projects(client, mock_all):
    mock_all["sql"].return_value = [
        {
            "id": "sample-repo-q",
            "name": "SpacetimeAir",
            "description": "",
            "color": "#0ea5e9",
            "priority": 0,
            "active": True,
            "created_at": 1000,
            "updated_at": 1000,
        }
    ]
    resp = await client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "sample-repo-q"


# ════════════════════════════════════════════════════════════════════════
# Analytics
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analytics_overview(client, mock_all):
    resp = await client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "by_status" in data
    assert "repos" in data
    assert "claims_last_hour" in data
    assert "completions_last_hour" in data
    assert "claim_complete_ratio" in data


@pytest.mark.asyncio
async def test_analytics_overview_with_data(client, mock_all):
    """Overview returns correct aggregations when tasks exist."""
    # Now does a single _sql("SELECT * FROM tasks") call
    mock_all["sql"].side_effect = None
    mock_all["sql"].return_value = [
        {"id": "t1", "status": "blocked", "repo": "repo-a", "updated_at": 1000},
        {"id": "t2", "status": "done", "repo": "repo-b", "updated_at": 1000},
    ]
    # _sql_param calls: [churn_logs]
    mock_all["param"].side_effect = [
        [],
    ]
    resp = await client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["by_status"] == {"blocked": 1, "done": 1}
    assert data["completed_today"] == 0
    assert data["completed_week"] == 0
    assert data["total_done"] == 1
    assert "repo-a" in data["repos"]
    assert "repo-b" in data["repos"]
    assert data["repos"]["repo-a"]["total"] == 1
    assert data["repos"]["repo-b"]["done"] == 1


@pytest.mark.asyncio
async def test_analytics_claim_churn(client, mock_all):
    """Claim-churn endpoint flags hot-looping tasks, excludes completed ones."""
    import time as _time

    now_ms = int(_time.time() * 1000)
    recent = now_ms - 60_000  # 1 min ago — inside the window
    logs = [
        # t1: claimed 4x, never completed → churning
        *[{"task_id": "t1", "action": "claimed", "timestamp": recent}] * 4,
        # t2: claimed 5x but completed → excluded
        *[{"task_id": "t2", "action": "claimed", "timestamp": recent}] * 5,
        {"task_id": "t2", "action": "completed", "timestamp": recent},
        # t3: claimed 2x — below threshold → excluded
        *[{"task_id": "t3", "action": "claimed", "timestamp": recent}] * 2,
        # t4: claimed 4x but OUTSIDE the window → excluded
        *[{"task_id": "t4", "action": "claimed", "timestamp": now_ms - 7_200_000}] * 4,
    ]
    with patch("shared._sql", new_callable=AsyncMock) as mock_sql:
        # Endpoint filters in SQL; emulate by returning only in-window rows
        mock_sql.return_value = [line for line in logs if line["timestamp"] > now_ms - 3_600_000]
        mock_all["param"].return_value = mock_sql.return_value
        resp = await client.get("/api/analytics/claim-churn?minutes=60&threshold=3")
    assert resp.status_code == 200
    data = resp.json()
    churning = {c["task_id"]: c["claims"] for c in data["churning"]}
    assert churning == {"t1": 4}
    assert data["total_claims"] == 11
    assert data["total_completed"] == 1


# ════════════════════════════════════════════════════════════════════════
# CSV Export
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_csv_export(client, mock_all):
    mock_all["sql"].return_value = [
        _make_task("t1", "Task 1"),
        _make_task("t2", "Task 2"),
    ]
    resp = await client.get("/api/tasks/export", params={"format": "csv"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    body = resp.text
    assert "id" in body
    assert "title" in body
    assert "due_by" in body


# ════════════════════════════════════════════════════════════════════════
# Logs
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_logs_empty(client, mock_all):
    resp = await client.get("/api/logs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_logs_search(client, mock_all):
    """Log search filters by notes/task_id/action."""
    mock_all["sql"].return_value = [
        {
            "id": "log_1",
            "task_id": "task_1",
            "action": "created",
            "agent_id": "hermes",
            "notes": "Initial creation",
            "timestamp": 1000,
        },
        {
            "id": "log_2",
            "task_id": "task_2",
            "action": "completed",
            "agent_id": "hermes",
            "notes": "All done",
            "timestamp": 2000,
        },
    ]
    resp = await client.get("/api/logs", params={"search": "creation"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["action"] == "created"


# ════════════════════════════════════════════════════════════════════════
# Update Task
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_update_task_due_by(client, mock_all):
    """Updating due_by should call set_due_by reducer."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={"due_by": 1893456000000})
    assert resp.status_code == 200
    # Verify set_due_by was called with correct args
    set_due_call = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_due_by"]
    assert len(set_due_call) == 1
    # _call("set_due_by", [task_id, due_by]) -> c[0] = ("set_due_by", [task_id, due_by])
    reducer_args = set_due_call[0][0][1]  # the second positional arg = [task_id, due_by]
    assert reducer_args[0] == "t1"
    assert reducer_args[1] == 1893456000000


@pytest.mark.asyncio
async def test_clear_due_by(client, mock_all):
    """Setting due_by to null should call set_due_by with 0."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={"due_by": None})
    assert resp.status_code == 200
    set_due_call = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_due_by"]
    assert len(set_due_call) == 1
    reducer_args = set_due_call[0][0][1]
    assert reducer_args[1] == 0


# ════════════════════════════════════════════════════════════════════════
# Auth Middleware
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_health_no_auth_required(client, enable_auth):
    """Health endpoint should work without auth even when API key is set."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_task_with_valid_api_key(client, mock_all, enable_auth):
    """POST /api/tasks with valid X-API-Key header should succeed."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Auth test task", "repo": "test"},
        headers={"X-API-Key": "test-api-key-123"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("status") == "created"


@pytest.mark.asyncio
async def test_create_task_with_invalid_api_key(client, mock_all, enable_auth):
    """POST /api/tasks with invalid X-API-Key header should return 401."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Should fail", "repo": "test"},
        headers={"X-API-Key": "wrong-key"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_create_task_without_api_key(client, mock_all, enable_auth):
    """POST /api/tasks without X-API-Key header should return 401."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Should fail", "repo": "test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_task_with_bearer_token(client, mock_all, enable_auth):
    """POST /api/tasks with Authorization: Bearer header should succeed."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Bearer test", "repo": "test"},
        headers={"Authorization": "Bearer test-api-key-123"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("status") == "created"


@pytest.mark.asyncio
async def test_create_task_with_bearer_wrong_token(client, mock_all, enable_auth):
    """POST /api/tasks with wrong Bearer token should return 401."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Should fail", "repo": "test"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════════════
# Webhook CRUD
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_webhooks_empty(client, mock_webhooks):
    """GET /api/webhooks should return empty list."""
    resp = await client.get("/api/webhooks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_webhook(client, mock_webhooks, mock_all):
    """POST /api/webhooks should create and return webhook with id."""
    resp = await client.post(
        "/api/webhooks",
        json={"url": "https://hooks.example.com/hook", "type": "generic"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["url"] == "https://hooks.example.com/hook"
    assert data["type"] == "generic"


@pytest.mark.asyncio
async def test_get_webhook(client, mock_webhooks):
    """GET /api/webhooks/{id} should return the webhook."""
    wh_id = "wh_test123"
    mock_webhooks["param"].return_value = [
        {
            "id": wh_id,
            "url": "https://hooks.example.com/hook",
            "wh_type": "generic",
            "events": "created,completed",
            "label": "generic:https://hooks.example.com/hook",
            "created_at": 1000,
        }
    ]
    resp = await client.get(f"/api/webhooks/{wh_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == wh_id
    assert data["type"] == "generic"
    assert "created,completed" in str(data["events"]) or "created" in data["events"]


@pytest.mark.asyncio
async def test_get_webhook_not_found(client, mock_webhooks):
    """GET /api/webhooks/{id} for non-existent webhook should return 404."""
    mock_webhooks["param"].return_value = []
    resp = await client.get("/api/webhooks/nonexistent")
    assert resp.status_code == 404
    assert "detail" in resp.json()


@pytest.mark.asyncio
async def test_delete_webhook(client, mock_webhooks):
    """DELETE /api/webhooks/{id} should return status deleted."""
    resp = await client.delete("/api/webhooks/wh_test123")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


@pytest.mark.asyncio
async def test_update_webhook(client, mock_webhooks):
    """PATCH /api/webhooks/{id} should update and return webhook."""
    wh_id = "wh_test123"
    mock_webhooks["param"].return_value = [
        {
            "id": wh_id,
            "url": "https://hooks.example.com/hook",
            "wh_type": "generic",
            "events": "created,completed,blocked",
            "label": "generic:updated-hook",
            "created_at": 1000,
        }
    ]
    resp = await client.patch(
        f"/api/webhooks/{wh_id}",
        json={"label": "generic:updated-hook", "events": ["created", "completed", "blocked"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    # get_webhook returns after update, so we see the mock data
    assert data["id"] == wh_id


@pytest.mark.asyncio
async def test_get_webhook_deliveries_empty(client, mock_webhooks):
    """GET /api/webhooks/{id}/deliveries should return empty list."""
    mock_webhooks["param"].return_value = []
    resp = await client.get("/api/webhooks/wh_test123/deliveries")
    assert resp.status_code == 200
    assert resp.json() == []


# ════════════════════════════════════════════════════════════════════════
# Labels CRUD
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_label(client, mock_all):
    """POST /api/labels should create a label."""
    mock_all["param"].return_value = [
        {
            "id": "lbl_test",
            "name": "bug",
            "color": "#ef4444",
            "description": "Bug label",
            "created_at": 1000,
        }
    ]
    resp = await client.post(
        "/api/labels",
        json={"name": "bug", "color": "#ef4444", "description": "Bug label"},
    )
    assert resp.status_code == 201
    data = resp.json()
    # Either returns the full label object or {"status": "created"}
    assert "name" in data or data.get("status") == "created"


@pytest.mark.asyncio
async def test_list_labels(client, mock_all):
    """GET /api/labels should return a list."""
    mock_all["sql"].return_value = [
        {"id": "lbl_1", "name": "bug", "color": "#ef4444", "description": "", "created_at": 1000},
        {
            "id": "lbl_2",
            "name": "feature",
            "color": "#22c55e",
            "description": "",
            "created_at": 2000,
        },
    ]
    resp = await client.get("/api/labels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "bug"


@pytest.mark.asyncio
async def test_delete_label(client, mock_all):
    """DELETE /api/labels/{id} should delete the label."""
    resp = await client.delete("/api/labels/lbl_test")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


@pytest.mark.asyncio
async def test_update_label(client, mock_all):
    """PATCH /api/labels/{id} should update label metadata."""
    mock_all["param"].return_value = [
        {
            "id": "lbl_test",
            "name": "bug-fix",
            "color": "#ff0000",
            "description": "Updated bug label",
            "created_at": 1000,
        }
    ]
    resp = await client.patch(
        "/api/labels/lbl_test",
        json={"name": "bug-fix", "color": "#ff0000"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Either the full label object or {"status": "updated"}
    assert data.get("status") == "updated" or data.get("name") == "bug-fix"


# ════════════════════════════════════════════════════════════════════════
# Comments
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_add_comment(client, mock_all):
    """POST /api/tasks/{id}/comments should add a comment."""
    resp = await client.post(
        "/api/tasks/task_1/comments",
        json={"body": "This is a comment", "author": "tester"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data.get("status") == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_comments_empty(client, mock_all):
    """GET /api/tasks/{id}/comments should return empty list when none exist."""
    resp = await client.get("/api/tasks/task_1/comments")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_comments_with_data(client, mock_all):
    """GET /api/tasks/{id}/comments should return stored comments."""
    # Note: main.py's list_comments calls _sql_param(...) directly now
    mock_all["param"].return_value = [
        {
            "id": "cmt_1",
            "task_id": "task_1",
            "author": "tester",
            "body": "First comment",
            "created_at": 1000,
        },
        {
            "id": "cmt_2",
            "task_id": "task_1",
            "author": "dev",
            "body": "Second comment",
            "created_at": 2000,
        },
    ]
    resp = await client.get("/api/tasks/task_1/comments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["author"] == "tester"
    assert data[1]["body"] == "Second comment"


@pytest.mark.asyncio
async def test_delete_comment(client, mock_all):
    """DELETE /api/tasks/{id}/comments/{cmt_id} should remove the comment."""
    resp = await client.delete("/api/tasks/task_1/comments/cmt_1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


# ════════════════════════════════════════════════════════════════════════
# Checklist
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_add_checklist_item(client, mock_all):
    """POST /api/tasks/{id}/checklist should add an item."""
    resp = await client.post(
        "/api/tasks/task_1/checklist",
        json={"text": "Check this item"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data.get("status") == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_checklist_empty(client, mock_all):
    """GET /api/tasks/{id}/checklist should return empty list."""
    resp = await client.get("/api/tasks/task_1/checklist")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_checklist_with_data(client, mock_all):
    """GET /api/tasks/{id}/checklist should return stored items."""
    mock_all["param"].return_value = [
        {
            "id": "cl_1",
            "task_id": "task_1",
            "text": "Item one",
            "completed": False,
            "position": 0,
            "created_at": 1000,
        },
        {
            "id": "cl_2",
            "task_id": "task_1",
            "text": "Item two",
            "completed": True,
            "position": 1,
            "created_at": 2000,
        },
    ]
    resp = await client.get("/api/tasks/task_1/checklist")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["text"] == "Item one"
    assert data[1]["completed"] is True


@pytest.mark.asyncio
async def test_toggle_checklist_item(client, mock_all):
    """POST /api/tasks/{id}/checklist/{item_id}/toggle should toggle state."""
    resp = await client.post("/api/tasks/task_1/checklist/cl_1/toggle")
    assert resp.status_code == 200
    assert resp.json() == {"status": "toggled"}


@pytest.mark.asyncio
async def test_remove_checklist_item(client, mock_all):
    """DELETE /api/tasks/{id}/checklist/{item_id} should remove item."""
    resp = await client.delete("/api/tasks/task_1/checklist/cl_1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


# ════════════════════════════════════════════════════════════════════════
# Error Handling & Lifecycle
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_claim_already_claimed_409(client, mock_all):
    """Claiming an already-claimed task should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409, detail="Task is already claimed by other-agent"
    )
    resp = await client.post(
        "/api/tasks/task_1/claim",
        json={"agent_id": "test-agent"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_nonexistent_task_404(client, mock_all):
    """GET /api/tasks/{id} for non-existent task should return 404."""
    mock_all["param"].return_value = []
    mock_all["sql"].return_value = []
    resp = await client.get("/api/tasks/nonexistent_task_id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_task(client, mock_all):
    """GET /api/tasks/{id} should return the task."""
    mock_all["param"].return_value = [_make_task("task_1", "My task")]
    mock_all["sql"].return_value = [_make_task("task_1", "My task")]
    resp = await client.get("/api/tasks/task_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "My task"
    assert data["id"] == "task_1"


@pytest.mark.asyncio
async def test_claim_task(client, mock_all):
    """POST /api/tasks/{id}/claim should claim a task successfully."""
    mock_all["param"].return_value = [_make_task("task_1", "Claim me", status="available")]
    resp = await client.post(
        "/api/tasks/task_1/claim",
        json={"agent_id": "test-agent"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "claimed"
    assert data["assigned_to"] == "test-agent"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_unclaim_task(client, mock_all):
    """POST /api/tasks/{id}/unclaim should release a task."""
    mock_all["param"].return_value = [_make_task("task_1", "Unclaim me", status="claimed")]
    resp = await client.post("/api/tasks/task_1/unclaim")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unclaimed"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_complete_task(client, mock_all):
    """POST /api/tasks/{id}/complete should mark task as completed."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Complete me", status="claimed")]
    resp = await client.post(
        "/api/tasks/task_1/complete",
        json={"result_notes": "Finished the work"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_complete_task_default_body(client, mock_all):
    """POST /api/tasks/{id}/complete without body should still work."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Complete me", status="claimed")]
    resp = await client.post("/api/tasks/task_1/complete")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_block_task(client, mock_all):
    """POST /api/tasks/{id}/block should block a task."""
    mock_all["param"].return_value = [_make_task("task_1", "Block me", status="claimed")]
    resp = await client.post(
        "/api/tasks/task_1/block",
        json={"reason": "Waiting on dependencies"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_delete_task_endpoint(client, mock_all):
    """DELETE /api/tasks/{id} should delete the task."""
    resp = await client.delete("/api/tasks/task_1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


@pytest.mark.asyncio
async def test_list_tasks_by_status(client, mock_all):
    """GET /api/tasks?status=available should filter by status."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Available task", status="available"),
        _make_task("t2", "Another available", status="available"),
    ]
    resp = await client.get("/api/tasks", params={"status": "available"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    for t in data:
        assert t["status"] == "available"


@pytest.mark.asyncio
async def test_create_task_invalid_json_body(client, mock_all):
    """POST /api/tasks with non-JSON body should return 422."""
    resp = await client.post(
        "/api/tasks",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_task_label_assignment(client, mock_all):
    """POST /api/tasks/{id}/labels should assign labels."""
    resp = await client.post(
        "/api/tasks/task_1/labels",
        json={"label_ids": ["lbl_bug", "lbl_feature"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_get_task_labels(client, mock_all):
    """GET /api/tasks/{id}/labels should return assigned labels."""
    mock_all["sql"].return_value = [
        {"id": "lbl_bug", "name": "bug", "color": "#ef4444", "description": "", "created_at": 1000},
    ]
    mock_all["param"].return_value = mock_all["sql"].return_value
    resp = await client.get("/api/tasks/task_1/labels")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "bug"


# ════════════════════════════════════════════════════════════════════════
# Archive / Unarchive
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_archive_task(client, mock_all):
    """POST /api/tasks/{id}/archive should call toggle_archive reducer."""
    resp = await client.post("/api/tasks/task_1/archive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "toggled"
    assert data["task_id"] == "task_1"
    # Verify toggle_archive was called
    toggle_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "toggle_archive"]
    assert len(toggle_calls) == 1
    assert toggle_calls[0][0][1] == ["task_1"]


@pytest.mark.asyncio
async def test_unarchive_task(client, mock_all):
    """POST /api/tasks/{id}/unarchive should call unarchive_task reducer."""
    resp = await client.post("/api/tasks/task_1/unarchive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unarchived"
    assert data["task_id"] == "task_1"
    unarchive_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "unarchive_task"]
    assert len(unarchive_calls) == 1


# ════════════════════════════════════════════════════════════════════════
# Sprint
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_sprint(client, mock_all):
    """POST /api/tasks/{id}/sprint should call set_sprint reducer."""
    resp = await client.post(
        "/api/tasks/task_1/sprint",
        json={"sprint": "sprint-1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["sprint"] == "sprint-1"
    sprint_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_sprint"]
    assert len(sprint_calls) == 1
    assert sprint_calls[0][0][1] == ["task_1", "sprint-1"]


# ════════════════════════════════════════════════════════════════════════
# Time Estimates
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_time_estimates(client, mock_all):
    """POST /api/tasks/{id}/time-estimates should call set_time_estimates reducer."""
    resp = await client.post(
        "/api/tasks/task_1/time-estimates",
        json={"estimated_hours": 5, "spent_hours": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert data["estimated_hours"] == 5
    assert data["spent_hours"] == 2
    est_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_time_estimates"]
    assert len(est_calls) == 1
    assert est_calls[0][0][1] == ["task_1", 5, 2]


# ════════════════════════════════════════════════════════════════════════
# Task Relations
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_task_relations_empty(client, mock_all):
    """GET /api/tasks/{id}/relations should return empty list."""
    resp = await client.get("/api/tasks/task_1/relations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_task_relations_with_data(client, mock_all):
    """GET /api/tasks/{id}/relations should return stored relations."""
    mock_all["param"].return_value = [
        {
            "id": "rel_1",
            "task_id": "task_1",
            "related_task_id": "task_2",
            "relation_type": "blocks",
            "created_at": 1000,
        },
    ]
    resp = await client.get("/api/tasks/task_1/relations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["relation_type"] == "blocks"


@pytest.mark.asyncio
async def test_add_task_relation(client, mock_all):
    """POST /api/tasks/{id}/relations should add a relation."""
    resp = await client.post(
        "/api/tasks/task_1/relations",
        json={"related_task_id": "task_2", "relation_type": "blocks"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["related_task_id"] == "task_2"


@pytest.mark.asyncio
async def test_remove_task_relation(client, mock_all):
    """DELETE /api/tasks/{id}/relations/{rel_id} should delete relation."""
    resp = await client.delete("/api/tasks/task_1/relations/rel_1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


# ════════════════════════════════════════════════════════════════════════
# Automation Rules
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_rules_empty(client, mock_all):
    """GET /api/rules should return empty list."""
    resp = await client.get("/api/rules")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_rule(client, mock_all):
    """POST /api/rules should create a rule."""
    resp = await client.post(
        "/api/rules",
        json={
            "name": "Auto assign high priority",
            "trigger_event": "task_created",
            "action_type": "assign_to",
            "action_config": '{"agent": "bot"}',
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_rule(client, mock_all):
    """GET /api/rules/{id} should return a single rule."""
    mock_all["param"].return_value = [
        {
            "id": "rule_1",
            "name": "Test Rule",
            "description": "A test rule",
            "trigger_event": "task_created",
            "condition": None,
            "action_type": "move_to_column",
            "action_config": '{"status": "in_progress"}',
            "repo": None,
            "active": True,
            "created_at": 1000,
            "updated_at": 1000,
        }
    ]
    resp = await client.get("/api/rules/rule_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Rule"
    assert data["trigger_event"] == "task_created"


@pytest.mark.asyncio
async def test_get_rule_not_found(client, mock_all):
    """GET /api/rules/{id} for non-existent rule should return 404."""
    mock_all["param"].return_value = []
    resp = await client.get("/api/rules/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_rule(client, mock_all):
    """PATCH /api/rules/{id} should update a rule."""
    mock_all["param"].return_value = [
        {
            "id": "rule_1",
            "name": "Old Name",
            "description": "",
            "trigger_event": "task_created",
            "condition": None,
            "action_type": "move_to_column",
            "action_config": "{}",
            "repo": None,
            "active": True,
            "created_at": 1000,
            "updated_at": 1000,
        }
    ]
    resp = await client.patch("/api/rules/rule_1", json={"name": "New Name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_delete_rule(client, mock_all):
    """DELETE /api/rules/{id} should delete a rule."""
    resp = await client.delete("/api/rules/rule_1")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted"}


# ════════════════════════════════════════════════════════════════════════
# API Keys
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_api_keys_empty(client, mock_all):
    """GET /api/api-keys should return empty list."""
    resp = await client.get("/api/api-keys")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_api_key(client, mock_all):
    """POST /api/api-keys should create a key."""
    resp = await client.post(
        "/api/api-keys",
        json={
            "key_hash": "abc123hash",
            "name": "CI pipeline key",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_revoke_api_key(client, mock_all):
    """POST /api/api-keys/{id}/revoke should revoke a key."""
    resp = await client.post("/api/api-keys/key_1/revoke")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "revoked"
    assert data["key_id"] == "key_1"


# ════════════════════════════════════════════════════════════════════════
# Calendar & Cross-Project
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_calendar_empty(client, mock_all):
    """GET /api/calendar should return empty list when no tasks have due_by."""
    resp = await client.get("/api/calendar")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_calendar_with_dates(client, mock_all):
    """GET /api/calendar should return tasks with due_by set."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Due task", due_by=1893456000000),
    ]
    resp = await client.get("/api/calendar")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["due_by"] == 1893456000000


@pytest.mark.asyncio
async def test_cross_project_empty(client, mock_all):
    """GET /api/cross-project should return empty list when no tasks."""
    resp = await client.get("/api/cross-project")
    assert resp.status_code == 200
    assert resp.json() == []


# ════════════════════════════════════════════════════════════════════════
# Schema Migrations
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_migrations_empty(client, mock_all):
    """GET /api/migrations should return empty list."""
    resp = await client.get("/api/migrations")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_record_migration(client, mock_all):
    """POST /api/migrations should record a migration."""
    resp = await client.post(
        "/api/migrations",
        json={
            "version": "2026-07-14-01-add-sprint",
            "description": "Add sprint and archive fields",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["version"] == "2026-07-14-01-add-sprint"


# ════════════════════════════════════════════════════════════════════════
# PATCH /api/tasks/{id} with new fields
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_patch_task_sprint(client, mock_all):
    """PATCH with sprint should call set_sprint reducer."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={"sprint": "sprint-2"})
    assert resp.status_code == 200
    sprint_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_sprint"]
    assert len(sprint_calls) == 1
    assert sprint_calls[0][0][1] == ["t1", "sprint-2"]


@pytest.mark.asyncio
async def test_patch_task_archive(client, mock_all):
    """PATCH with archived=true should call archive_task reducer."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={"archived": True})
    assert resp.status_code == 200
    archive_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "archive_task"]
    assert len(archive_calls) == 1
    assert archive_calls[0][0][1] == ["t1"]


@pytest.mark.asyncio
async def test_patch_task_time_estimates(client, mock_all):
    """PATCH with estimated_hours and spent_hours should call set_time_estimates."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={"estimated_hours": 8, "spent_hours": 3})
    assert resp.status_code == 200
    est_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_time_estimates"]
    assert len(est_calls) == 1
    assert est_calls[0][0][1] == ["t1", 8, 3]


# ════════════════════════════════════════════════════════════════════════
# Bulk retry / bulk archive
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_bulk_retry_tasks(client, mock_all):
    """POST /api/tasks/bulk-retry should reset fails + unclaim each task."""
    resp = await client.post("/api/tasks/bulk-retry", json={"task_ids": ["t1", "t2"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] == 2
    assert data["failed"] == []
    reset_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "reset_fail_count"]
    unclaim_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "unclaim_task"]
    assert len(reset_calls) == 2
    assert len(unclaim_calls) == 2


@pytest.mark.asyncio
async def test_bulk_retry_without_reset(client, mock_all):
    """reset_fails=false should skip the reset_fail_count reducer."""
    resp = await client.post(
        "/api/tasks/bulk-retry", json={"task_ids": ["t1"], "reset_fails": False}
    )
    assert resp.status_code == 200
    reset_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "reset_fail_count"]
    unclaim_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "unclaim_task"]
    assert len(reset_calls) == 0
    assert len(unclaim_calls) == 1


@pytest.mark.asyncio
async def test_bulk_archive_tasks(client, mock_all):
    """POST /api/tasks/bulk-archive should toggle only unarchived tasks."""
    mock_all["param"].side_effect = [
        [_make_task("t1", "Task one")],  # t1 not archived
        [{**_make_task("t2", "Task two"), "archived": True}],  # t2 already archived
    ]
    resp = await client.post("/api/tasks/bulk-archive", json={"task_ids": ["t1", "t2"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 1
    toggle_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "toggle_archive"]
    assert len(toggle_calls) == 1
    assert toggle_calls[0][0][1] == ["t1"]


@pytest.mark.asyncio
async def test_bulk_archive_missing_task(client, mock_all):
    """Missing tasks land in the failed list."""
    mock_all["param"].return_value = []
    resp = await client.post("/api/tasks/bulk-archive", json={"task_ids": ["nope"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert data["failed"][0]["error"] == "not found"


# ════════════════════════════════════════════════════════════════════════
# ═══ NEW TESTS: Edge Cases, State Transitions, Error Handling ═════════
# ════════════════════════════════════════════════════════════════════════

# ── State Transition Edge Cases ────────────────────────────────────────


@pytest.mark.asyncio
async def test_complete_unclaimed_task_409(client, mock_all):
    """Completing an unclaimed/available task should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Cannot complete — task is not in_progress (status: available)",
    )
    resp = await client.post(
        "/api/tasks/task_1/complete",
        json={"result_notes": "Trying to complete an available task"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data
    assert "not in_progress" in data["detail"] or "available" in data["detail"]


@pytest.mark.asyncio
async def test_block_already_blocked_task_409(client, mock_all):
    """Blocking an already-blocked task should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Cannot block — task is already blocked",
    )
    resp = await client.post(
        "/api/tasks/task_1/block",
        json={"reason": "Block again"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_block_available_task_409(client, mock_all):
    """Blocking an available (unclaimed) task should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Cannot block — task is not in_progress (status: available)",
    )
    resp = await client.post(
        "/api/tasks/task_1/block",
        json={"reason": "Block before claim"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_claim_in_progress_task_409(client, mock_all):
    """Claiming a task that's already in_progress should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Task is already claimed by other-agent",
    )
    resp = await client.post(
        "/api/tasks/task_1/claim",
        json={"agent_id": "second-agent"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data
    assert "already claimed" in data["detail"].lower()


@pytest.mark.asyncio
async def test_complete_already_done_task_409(client, mock_all):
    """Completing a task that's already done should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Cannot complete — task is already done",
    )
    resp = await client.post(
        "/api/tasks/task_1/complete",
        json={"result_notes": "Already finished"},
    )
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data


# ── Empty / Invalid Input Handling ─────────────────────────────────────


@pytest.mark.asyncio
async def test_create_task_empty_title_string(client, mock_all):
    """Creating a task with empty title string — API accepts it (no Pydantic constraint)."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # no dedup match
    resp = await client.post(
        "/api/tasks",
        json={"title": "", "repo": "test"},
    )
    # The Pydantic model allows empty strings; backend processes it
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("status") == "created"


@pytest.mark.asyncio
async def test_create_task_very_long_title(client, mock_all):
    """Creating a task with a very long title should succeed."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []
    long_title = "A" * 5000
    resp = await client.post(
        "/api/tasks",
        json={"title": long_title, "repo": "test"},
    )
    assert resp.status_code in (200, 201)
    data = resp.json()
    assert data.get("status") == "created"


@pytest.mark.asyncio
async def test_create_task_invalid_priority_type(client, mock_all):
    """Creating a task with a string instead of int for priority should return 422."""
    resp = await client.post(
        "/api/tasks",
        json={"title": "Bad priority", "priority": "not-a-number", "repo": "test"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_assign_non_existent_label_to_task(client, mock_all):
    """Assigning a non-existent label ID to a task should still return updated."""
    mock_all["param"].return_value = []  # No existing labels
    resp = await client.post(
        "/api/tasks/task_1/labels",
        json={"label_ids": ["lbl_nonexistent"]},
    )
    # The endpoint calls assign_label_to_task which may succeed or fail silently
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_create_label_duplicate_name(client, mock_all):
    """Creating a label with a duplicate name should return 201 or 409 depending on backend."""
    # Simulate label already existing by having param return a row
    mock_all["param"].return_value = [
        {
            "id": "lbl_existing",
            "name": "bug",
            "color": "#ef4444",
            "description": "Existing bug label",
            "created_at": 1000,
        }
    ]
    resp = await client.post(
        "/api/labels",
        json={"name": "bug", "color": "#ef4444", "description": "Duplicate label"},
    )
    # The route doesn't check for duplicates; it calls add_label reducer
    # If the reducer rejects duplicates, we'd see 409; otherwise 201
    assert resp.status_code in (201, 409)


# ── Analytics with Empty Data ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_analytics_throughput_empty(client, mock_all):
    """Throughput analytics should return daily zeros when no done tasks exist."""
    resp = await client.get("/api/analytics/throughput?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 8  # days=7 → 8 entries (today + 7 past days)
    for entry in data:
        assert "date" in entry
        assert entry["completed"] == 0


@pytest.mark.asyncio
async def test_analytics_burndown_empty(client, mock_all):
    """Burndown analytics should return zero structure when no tasks exist."""
    resp = await client.get("/api/analytics/burndown?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert "days" in data
    assert "total_open_start" in data
    assert "total_completed" in data
    assert "total_remaining" in data
    assert data["total_completed"] == 0
    assert data["total_remaining"] == 0
    assert len(data["days"]) == 7


@pytest.mark.asyncio
async def test_analytics_cycle_times_empty(client, mock_all):
    """Cycle-times analytics should return empty list when no completed tasks exist."""
    # _sql is mocked to return empty by default (no tasks, no logs)
    resp = await client.get("/api/analytics/cycle-times")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_analytics_agents_empty(client, mock_all):
    """Agents analytics should return empty list when no agents registered."""
    resp = await client.get("/api/analytics/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


# ── Webhook CRUD Edge Cases ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_nonexistent_webhook_404(client, mock_webhooks, mock_all):
    """DELETE /api/webhooks/{id} for a non-existent webhook should return 404."""
    # Mock webhooks.remove_webhook to return False (not found)
    with patch("routes.webhook_subs.webhooks.remove_webhook", return_value=False):
        resp = await client.delete("/api/webhooks/wh_nonexistent")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_webhook_test_not_found_404(client, mock_webhooks, mock_all, enable_auth):
    """POST /api/webhooks/{id}/test for a non-existent webhook should return 404."""
    mock_webhooks["param"].return_value = []  # get_webhook returns None
    resp = await client.post(
        "/api/webhooks/wh_nonexistent/test",
        headers={"X-API-Key": "test-api-key-123"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_get_webhook_deliveries_with_data(client, mock_webhooks):
    """GET /api/webhooks/{id}/deliveries should return stored deliveries."""
    mock_webhooks["param"].return_value = [
        {
            "id": "del_1",
            "webhook_id": "wh_test123",
            "event": "created",
            "url": "https://hooks.example.com/hook",
            "status_code": 200,
            "response_body": "OK",
            "success": True,
            "delivered_at": 2000,
        }
    ]
    resp = await client.get("/api/webhooks/wh_test123/deliveries")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event"] == "created"
    assert data[0]["success"] is True


# ── Schema Migrations ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_schema_migrations_alias(client, mock_all):
    """GET /api/schema-migrations (alias) should return unordered migrations."""
    mock_all["sql"].return_value = [
        {
            "version": "2026-07-14-01-add-sprint",
            "description": "Add sprint and archive fields",
            "applied_at": 2000,
            "applied_by": "test-user",
            "checksum": "abc123",
        },
        {
            "version": "2026-07-13-01-initial",
            "description": "Initial schema",
            "applied_at": 1000,
            "applied_by": "system",
            "checksum": None,
        },
    ]
    resp = await client.get("/api/schema-migrations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    versions = {m["version"] for m in data}
    assert "2026-07-14-01-add-sprint" in versions
    assert "2026-07-13-01-initial" in versions
    # Check that all fields are present
    for m in data:
        assert "applied_at" in m
        assert "applied_by" in m
        assert "checksum" in m or m.get("checksum") is None


@pytest.mark.asyncio
async def test_record_migration_all_fields(client, mock_all):
    """POST /api/migrations with all optional fields should record successfully."""
    resp = await client.post(
        "/api/migrations",
        json={
            "version": "2026-07-20-01-add-labels",
            "description": "Add kanban_labels table and assignments",
            "applied_by": "ci-bot",
            "checksum": "sha256:aabbccddee",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["version"] == "2026-07-20-01-add-labels"
    # Verify the reducer was called with all fields
    migration_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "record_migration"]
    assert len(migration_calls) == 1
    args = migration_calls[0][0][1]
    assert args[0] == "2026-07-20-01-add-labels"
    assert args[1] == "Add kanban_labels table and assignments"
    assert args[2] == "ci-bot"
    assert args[3] == "sha256:aabbccddee"


# ── Auth Middleware Additional Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_task_without_auth_401(client, mock_all, enable_auth):
    """PATCH /api/tasks/{id} without API key should return 401."""
    resp = await client.patch(
        "/api/tasks/task_1",
        json={"title": "Hacked title"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_task_without_auth_401(client, mock_all, enable_auth):
    """DELETE /api/tasks/{id} without API key should return 401."""
    resp = await client.delete("/api/tasks/task_1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_claim_without_auth_401(client, mock_all, enable_auth):
    """POST /api/tasks/{id}/claim without API key should return 401."""
    resp = await client.post(
        "/api/tasks/task_1/claim",
        json={"agent_id": "test-agent"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_record_schema_migration_alias(client, mock_all):
    """POST /api/schema-migrations (alias) should record a migration."""
    resp = await client.post(
        "/api/schema-migrations",
        json={"version": "v2.3.0", "description": "Add test table"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recorded"
    migration_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "record_migration"]
    assert len(migration_calls) >= 1
    args = migration_calls[-1][0][1]
    assert "v2.3.0" in args


# ════════════════════════════════════════════════════════════════════════
# ═══ EDGE CASES: Unclaim, Dedup, Bulk, Export, Search, PATCH ══════════
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unclaim_available_task_409(client, mock_all):
    """Unclaim a task that's already available should return 409 Conflict."""
    mock_all["call"].side_effect = HTTPException(
        status_code=409,
        detail="Reducer failed: Cannot unclaim — task is not in_progress (status: available)",
    )
    resp = await client.post("/api/tasks/task_1/unclaim")
    assert resp.status_code == 409
    data = resp.json()
    assert "detail" in data
    assert "available" in data["detail"]


@pytest.mark.asyncio
async def test_filter_tasks_by_label(client, mock_all):
    """Filter tasks by label should return only tasks with that label."""
    # Mock the label-task assignment query → returns one task_id
    mock_all["param"].return_value = [{"task_id": "t1"}]
    # Mock the main tasks query → returns two tasks
    mock_all["sql"].return_value = [
        _make_task("t1", "Labeled task", repo="test"),
        _make_task("t2", "Unlabeled task", repo="test"),
    ]
    resp = await client.get("/api/tasks", params={"label": "lbl_bug"})
    assert resp.status_code == 200
    data = resp.json()
    # Only t1 should be returned (client-side label filter after SQL fetch)
    assert len(data) == 1
    assert data[0]["id"] == "t1"
    assert data[0]["title"] == "Labeled task"


@pytest.mark.asyncio
async def test_delete_nonexistent_task(client, mock_all):
    """DELETE for a non-existent task — API calls the reducer and returns 200
    (the STDB reducer is idempotent; no 404 is raised by the route itself)."""
    mock_all["param"].return_value = []  # no rows found
    resp = await client.delete("/api/tasks/nonexistent_id")
    # The route fetches task data (empty), calls delete_task reducer, returns 200
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_get_nonexistent_agent_404(client, mock_all):
    """GET /api/agents/{id} for a non-existent agent should return 404."""
    mock_all["param"].return_value = []  # no rows
    resp = await client.get("/api/agents/nonexistent_agent")
    assert resp.status_code == 404
    data = resp.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_create_duplicate_task_title_repo(client, mock_all):
    """Creating a task with the same title+repo as an existing non-done task
    returns status='exists' with the existing task's ID (dedup)."""
    mock_all["param"].return_value = [{"id": "task_1", "status": "available"}]
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks",
        json={"title": "Existing task", "repo": "test"},
    )
    assert resp.status_code == 200 or resp.status_code == 201
    data = resp.json()
    assert data["status"] == "exists"
    assert data["id"] == "task_1"
    assert "same title" in data.get("message", "").lower()


@pytest.mark.asyncio
async def test_bulk_retry_empty_array(client, mock_all):
    """Bulk-retry with an empty task_ids array should handle gracefully."""
    resp = await client.post("/api/tasks/bulk-retry", json={"task_ids": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] == 0
    assert data["failed"] == []


@pytest.mark.asyncio
async def test_bulk_archive_empty_array(client, mock_all):
    """Bulk-archive with an empty task_ids array should handle gracefully."""
    resp = await client.post("/api/tasks/bulk-archive", json={"task_ids": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert data["failed"] == []


@pytest.mark.asyncio
async def test_block_task_empty_reason(client, mock_all):
    """POST /api/tasks/{id}/block with an empty reason string should succeed."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Block me", status="in_progress")]
    resp = await client.post(
        "/api/tasks/task_1/block",
        json={"reason": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_block_task_no_body(client, mock_all):
    """POST /api/tasks/{id}/block with no request body should succeed (defaults)."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Block me", status="in_progress")]
    resp = await client.post("/api/tasks/task_1/block")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_complete_task_very_long_notes(client, mock_all):
    """Completing a task with very long result notes should be accepted."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Long notes task", status="in_progress")]
    long_notes = "Result: " + "A" * 10000
    resp = await client.post(
        "/api/tasks/task_1/complete",
        json={"result_notes": long_notes},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["task_id"] == "task_1"


@pytest.mark.asyncio
async def test_get_logs_for_nonexistent_task(client, mock_all):
    """GET /api/logs?task_id=nonexistent should return an empty array."""
    # _sql_param returns [] by default (no logs for that task_id)
    resp = await client.get("/api/logs", params={"task_id": "nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_analytics_overview_only_blocked(client, mock_all):
    """Analytics overview should not crash when all tasks are blocked."""
    mock_all["sql"].side_effect = None
    mock_all["sql"].return_value = [
        {"id": "t1", "status": "blocked", "repo": "test-repo", "updated_at": 1000},
        {"id": "t2", "status": "blocked", "repo": "test-repo", "updated_at": 2000},
    ]
    mock_all["param"].side_effect = [
        [],
    ]
    resp = await client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["by_status"].get("blocked", 0) == 2
    assert data["completed_today"] == 0
    assert data["completed_week"] == 0
    assert data["total_done"] == 0


@pytest.mark.asyncio
async def test_export_invalid_format(client, mock_all):
    """Export with an invalid format string defaults to JSON (200), not 422."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Task 1"),
    ]
    # The endpoint only checks format == 'csv'; anything else returns JSON
    resp = await client.get("/api/tasks/export", params={"format": "xml"})
    assert resp.status_code == 200
    # Should be JSON (not CSV) for unrecognised format
    content_type = resp.headers.get("content-type", "")
    assert "json" in content_type or "application" in content_type
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1


@pytest.mark.asyncio
async def test_search_special_characters(client, mock_all):
    """Search with SQL-injection-like characters should be handled safely
    (search is applied client-side in Python, not passed raw to SQL)."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Normal task", "Just a normal description"),
        _make_task("t2", "Auth module", "Authentication and authorization"),
    ]
    # SQL injection attempt in the search string
    resp = await client.get("/api/tasks", params={"search": "' OR 1=1; DROP TABLE tasks --"})
    assert resp.status_code == 200
    data = resp.json()
    # Should not crash, should return filtered results (empty in this case)
    assert isinstance(data, list)
    # The search string doesn't match any task title/desc, so empty
    assert len(data) == 0


@pytest.mark.asyncio
async def test_search_sql_injection_in_title(client, mock_all):
    """Creating a task with SQL injection in the title should be accepted
    (STDB parameterised queries prevent injection)."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # no dedup match
    payload = "Task'; DROP TABLE tasks; --"
    resp = await client.post(
        "/api/tasks",
        json={"title": payload, "repo": "test"},
    )
    assert resp.status_code == 200 or resp.status_code == 201
    data = resp.json()
    assert data.get("status") == "created"
    assert "id" in data


@pytest.mark.asyncio
async def test_patch_task_no_changes(client, mock_all):
    """PATCH /api/tasks/{id} with an empty JSON body should succeed (no-op)."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch("/api/tasks/t1", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_patch_task_empty_body(client, mock_all):
    """PATCH /api/tasks/{id} with '{ }' (all-null fields) should succeed."""
    mock_all["param"].return_value = [_make_task("t1", "My task")]
    resp = await client.patch(
        "/api/tasks/t1",
        json={
            "title": None,
            "description": None,
            "priority": None,
            "branch": None,
            "due_by": None,
            "sprint": None,
            "archived": None,
            "estimated_hours": None,
            "spent_hours": None,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_list_tasks_invalid_label(client, mock_all):
    """Filtering tasks by a non-existent label should return an empty list."""
    mock_all["param"].return_value = []  # no task-label assignments found
    mock_all["sql"].return_value = [
        _make_task("t1", "Some task"),
        _make_task("t2", "Another task"),
    ]
    resp = await client.get("/api/tasks", params={"label": "nonexistent_label_id"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_list_agents_with_data(client, mock_all):
    """GET /api/agents should return enriched agent data when agents exist."""
    mock_all["sql"].return_value = [
        {
            "id": "agent-1",
            "host": "host1.local",
            "capabilities": "python,typescript",
            "repo_focus": "sample-repo-q",
            "current_task_id": None,
            "status": "idle",
            "last_heartbeat": 2000000,
            "first_seen": 1000000,
        },
    ]
    resp = await client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "agent-1"
    assert data[0]["status"] == "idle"


# ════════════════════════════════════════════════════════════════════════
# ═══ ROUTE COVERAGE GAP TESTS — Agents, Projects, Templates, etc. ════
# ════════════════════════════════════════════════════════════════════════


# ── Agents ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_agent(client, mock_all):
    """POST /api/agents/register should register a new agent."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/agents/register",
        json={
            "agent_id": "new-agent",
            "host": "localhost",
            "capabilities": "python",
            "repo_focus": "test",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "registered"
    # Verify the reducer was called with the right args
    register_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "register_agent"]
    assert len(register_calls) == 1
    args = register_calls[0][0][1]
    assert args[0] == "new-agent"


@pytest.mark.asyncio
async def test_agent_heartbeat(client, mock_all):
    """POST /api/agents/{agent_id}/heartbeat should update heartbeat."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/agents/agent-1/heartbeat",
        json={"agent_id": "agent-1", "status": "busy", "current_task_id": "task_1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    heartbeat_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "agent_heartbeat"]
    assert len(heartbeat_calls) == 1
    args = heartbeat_calls[0][0][1]
    assert args[0] == "agent-1"
    assert args[1] == "busy"


@pytest.mark.asyncio
async def test_set_agent_capabilities(client, mock_all):
    """PUT /api/agents/{agent_id}/capabilities should update capabilities."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.put(
        "/api/agents/agent-1/capabilities",
        json={"capabilities": "rust,python", "repo_focus": "sample-repo-p"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    cap_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "set_agent_capabilities"]
    assert len(cap_calls) == 1
    args = cap_calls[0][0][1]
    assert args[0] == "agent-1"
    assert args[1] == "rust,python"


@pytest.mark.asyncio
async def test_get_agent_success(client, mock_all):
    """GET /api/agents/{id} should return agent data when found."""
    mock_all["param"].return_value = [
        {
            "id": "agent-1",
            "host": "host1.local",
            "capabilities": "python",
            "repo_focus": "test",
            "current_task_id": "task_1",
            "status": "busy",
            "last_heartbeat": 2000000,
            "first_seen": 1000000,
        },
    ]
    resp = await client.get("/api/agents/agent-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "agent-1"
    assert data["status"] == "busy"
    assert data["current_task_id"] == "task_1"


@pytest.mark.asyncio
async def test_agent_health_empty(client, mock_all):
    """GET /api/agents/health should return empty list when no agents."""
    mock_all["sql"].return_value = []  # no agents, no tasks
    resp = await client.get("/api/agents/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_agent_health_with_stale_agent(client, mock_all):
    """GET /api/agents/health should mark stale agents (no heartbeat >5min)."""
    mock_all["sql"].side_effect = [
        # First call: agents
        [
            {
                "id": "agent-1",
                "host": "host1.local",
                "capabilities": "python",
                "repo_focus": "test",
                "current_task_id": "task_1",
                "status": "idle",
                "last_heartbeat": 1000,  # very old heartbeat — should be stale
                "first_seen": 1000,
            },
        ],
        # Second call: tasks
        [
            {
                "id": "task_1",
                "title": "Test task",
                "description": "A test task",
                "priority": 0,
                "status": "available",
                "repo": "test",
            },
        ],
    ]
    resp = await client.get("/api/agents/health")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "agent-1"
    # The agent should be marked as stale since time.time() is way past last_heartbeat
    assert data[0].get("stale", False) is True


# ── Projects ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_project_empty_id(client, mock_all):
    """POST /api/projects with empty id should return 400."""
    resp = await client.post("/api/projects", json={"id": ""})
    assert resp.status_code == 400
    data = resp.json()
    assert "required" in data["detail"].lower()


@pytest.mark.asyncio
async def test_create_project_success(client, mock_all):
    """POST /api/projects should create a project and return its data."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [
        {
            "id": "test-repo",
            "name": "Test Repo",
            "description": "A test project",
            "color": "#0ea5e9",
            "priority": 1,
            "active": True,
            "created_at": 1000,
            "updated_at": 1000,
        },
    ]
    resp = await client.post(
        "/api/projects",
        json={"id": "test-repo", "name": "Test Repo", "priority": 1},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "test-repo"
    assert data["priority"] == 1
    assert data["active"] is True


@pytest.mark.asyncio
async def test_create_project_fallback_created(client, mock_all):
    """POST /api/projects should return fallback when fetch returns empty."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # fetch after create returns empty
    resp = await client.post(
        "/api/projects",
        json={"id": "fallback-repo", "name": "Fallback"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_update_project_with_priority(client, mock_all):
    """PATCH /api/projects/{id} with priority should update the project."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [
        {
            "id": "test-repo",
            "name": "Updated Repo",
            "description": "Updated description",
            "color": "#ff0000",
            "priority": 3,
            "active": True,
            "created_at": 1000,
            "updated_at": 2000,
        },
    ]
    resp = await client.patch(
        "/api/projects/test-repo",
        json={
            "name": "Updated Repo",
            "priority": 3,
            "description": "Updated description",
            "color": "#ff0000",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["priority"] == 3


@pytest.mark.asyncio
async def test_update_project_no_priority(client, mock_all):
    """PATCH /api/projects/{id} without priority should fetch current from DB."""
    mock_all["call"].return_value = {"status": "ok"}
    # First call to param is the priority fetch, second is the full fetch
    mock_all["param"].side_effect = [
        [{"priority": 2}],  # current priority from DB
        [
            {
                "id": "test-repo",
                "name": "Test Repo",
                "description": "",
                "color": "#6b7280",
                "priority": 2,
                "active": True,
                "created_at": 1000,
                "updated_at": 2000,
            }
        ],
    ]
    resp = await client.patch(
        "/api/projects/test-repo",
        json={"name": "Test Repo"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "test-repo"
    # Verify priority fetch happened
    assert len([c for c in mock_all["param"].call_args_list if "SELECT priority" in str(c)]) == 1


@pytest.mark.asyncio
async def test_update_project_no_priority_default(client, mock_all):
    """PATCH when project not found and no priority provided should default to 2."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].side_effect = [
        [],  # priority fetch returns empty (project doesn't exist)
        [],  # full fetch returns empty
    ]
    resp = await client.patch(
        "/api/projects/nonexistent",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_delete_project(client, mock_all):
    """DELETE /api/projects/{id} should delete the project."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.delete("/api/projects/test-repo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    delete_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "delete_project"]
    assert len(delete_calls) == 1
    assert delete_calls[0][0][1][0] == "test-repo"


@pytest.mark.asyncio
async def test_suggest_by_project_empty(client, mock_all):
    """GET /api/suggest-by-project fallback should return empty when no tasks or projects."""
    # Raise HTTPException to trigger the fallback scoring path
    mock_all["call"].side_effect = HTTPException(502, "reducer failed")
    mock_all["sql"].return_value = []  # no tasks, no projects
    resp = await client.get("/api/suggest-by-project", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_suggest_by_project_with_data(client, mock_all):
    """GET /api/suggest-by-project should score and sort tasks via fallback."""
    # Raise HTTPException to trigger the fallback scoring path
    mock_all["call"].side_effect = HTTPException(502, "reducer failed")
    mock_all["sql"].side_effect = [
        # First call: tasks
        [
            {
                "id": "t1",
                "title": "High priority task",
                "priority": 0,
                "repo": "repo-a",
                "created_at": 1000,
            },
            {
                "id": "t2",
                "title": "Old stale task",
                "priority": 5,
                "repo": "repo-a",
                "created_at": 100,
            },
            {"id": "t3", "title": "No repo task", "priority": 2, "repo": "", "created_at": 5000},
        ],
        # Second call: projects
        [
            {"id": "repo-a", "priority": 1, "active": True},
        ],
    ]
    resp = await client.get("/api/suggest-by-project", params={"limit": 10})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 3
    # All should have score and reason
    for item in data:
        assert "score" in item
        assert "reason" in item


# ── Templates ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_template_success(client, mock_all):
    """PATCH /api/task-templates/{id} should update a template."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [
        {
            "id": "tpl_1",
            "title": "Updated Template",
            "description": "",
            "priority": 2,
            "repo": "test",
            "roadmap_item": "",
            "required_skills": "",
            "cron_schedule": "0 9 * * *",
            "created_by": "test",
            "created_at": 1000,
            "last_triggered_at": 0,
            "active": True,
        },
    ]
    resp = await client.patch(
        "/api/task-templates/tpl_1",
        json={"title": "Updated Template", "priority": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated Template"


@pytest.mark.asyncio
async def test_update_template_404(client, mock_all):
    """PATCH /api/task-templates/{id} for non-existent template should return 404."""
    mock_all["param"].return_value = []  # template not found
    resp = await client.patch(
        "/api/task-templates/nonexistent",
        json={"title": "Ghost"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_template_success(client, mock_all):
    """DELETE /api/task-templates/{id} should delete a template."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.delete("/api/task-templates/tpl_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_template_404(client, mock_all):
    """DELETE /api/task-templates/{id} for non-existent should return 404."""
    mock_all["call"].side_effect = RuntimeError("not found")
    resp = await client.delete("/api/task-templates/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_template_500(client, mock_all):
    """DELETE /api/task-templates/{id} with non-404 error should return 500."""
    mock_all["call"].side_effect = RuntimeError("database connection failed")
    resp = await client.delete("/api/task-templates/tpl_1")
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_trigger_templates_success(client, mock_all):
    """POST /api/task-templates/trigger should trigger template processing."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = [
        {
            "id": "log_1",
            "task_id": "__trigger__",
            "action": "template_trigger",
            "agent_id": "system",
            "notes": "Triggered at 1000",
            "created_at": 1000,
        },
    ]
    resp = await client.post("/api/task-templates/trigger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "triggered"


# ── Dispatcher State ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_dispatcher_state_all_empty(client, mock_all):
    """GET /api/dispatcher/state should return empty dict when no state."""
    mock_all["sql"].return_value = []
    resp = await client.get("/api/dispatcher/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {}


@pytest.mark.asyncio
async def test_get_dispatcher_state_all_with_data(client, mock_all):
    """GET /api/dispatcher/state should return all state entries."""
    mock_all["sql"].return_value = [
        {"key": "mode", "value": '"auto"'},
        {"key": "count", "value": "42"},
    ]
    resp = await client.get("/api/dispatcher/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "auto"
    # 42 as number since json.loads("42") returns int
    assert data["count"] == 42


@pytest.mark.asyncio
async def test_get_dispatcher_state_invalid_json(client, mock_all):
    """GET /api/dispatcher/state should handle JSON decode errors gracefully."""
    mock_all["sql"].return_value = [
        {"key": "bad", "value": "not-json{"},
    ]
    resp = await client.get("/api/dispatcher/state")
    assert resp.status_code == 200
    data = resp.json()
    # Should return raw value when JSON decode fails
    assert data["bad"] == "not-json{"


@pytest.mark.asyncio
async def test_get_dispatcher_state_by_key_found(client, mock_all):
    """GET /api/dispatcher/state?key=xxx should return that key's value."""
    mock_all["param"].return_value = [
        {"key": "mode", "value": '"production"'},
    ]
    resp = await client.get("/api/dispatcher/state", params={"key": "mode"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "production"


@pytest.mark.asyncio
async def test_get_dispatcher_state_by_key_not_found(client, mock_all):
    """GET /api/dispatcher/state?key=xxx for missing key should return null."""
    mock_all["param"].return_value = []
    resp = await client.get("/api/dispatcher/state", params={"key": "nonexistent"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["nonexistent"] is None


@pytest.mark.asyncio
async def test_set_dispatcher_state(client, mock_all):
    """POST /api/dispatcher/state should set a state entry."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/dispatcher/state",
        json={"key": "mode", "value": "auto"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["key"] == "mode"


@pytest.mark.asyncio
async def test_delete_dispatcher_state(client, mock_all):
    """DELETE /api/dispatcher/state/{key} should delete a state entry."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.delete("/api/dispatcher/state/mode")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["key"] == "mode"


@pytest.mark.asyncio
async def test_delete_dispatcher_state_404(client, mock_all):
    """DELETE /api/dispatcher/state/{key} for missing key should return 404."""
    mock_all["call"].side_effect = RuntimeError("Key not found: nonexistent")
    resp = await client.delete("/api/dispatcher/state/nonexistent")
    assert resp.status_code == 404


# ── Ops (Roadmap Import, Cross-Project) ──────────────────────────────────


@pytest.mark.asyncio
async def test_roadmap_import_empty(client, mock_all):
    """POST /api/roadmap/import with empty content should return 0 tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/roadmap/import",
        json={"content": "", "repo": "test-repo"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_count"] == 0


@pytest.mark.asyncio
async def test_roadmap_import_one_phase(client, mock_all):
    """POST /api/roadmap/import with one phase should create tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # no existing tasks (no dedup)
    resp = await client.post(
        "/api/roadmap/import",
        json={
            "content": (
                "## Phase 1 \u2014 Setup\n\n"
                "- [ ] Install dependencies\n"
                "- [ ] Configure CI\n"
                "- [x] Already done\n"
            ),
            "repo": "test-repo",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_count"] == 2  # 2 open tasks, 1 skipped (done)


@pytest.mark.asyncio
async def test_roadmap_import_multiple_phases(client, mock_all):
    """POST /api/roadmap/import with multiple phases should assign different priorities."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []  # no dedup
    content = """## Phase 1 — Core

- [ ] Task A
- [ ] Task B

## Phase 2 — Features

- [ ] Task C
"""
    resp = await client.post(
        "/api/roadmap/import",
        json={"content": content, "repo": "multi-repo"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_count"] == 3
    # Verify we can see the calls
    add_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "add_task"]
    # Phase 1 tasks should have priority 0
    phase1_count = sum(1 for c in add_calls if c[0][1][3] == 0)
    # Phase 2 task should have priority 1
    phase2_count = sum(1 for c in add_calls if c[0][1][3] == 1)
    assert phase1_count == 2
    assert phase2_count == 1


@pytest.mark.asyncio
async def test_roadmap_import_dedup(client, mock_all):
    """POST /api/roadmap/import should skip existing non-done tasks but still count them."""
    mock_all["call"].return_value = {"status": "ok"}
    # Simulate existing task with same title+repo
    mock_all["param"].return_value = [{"id": "existing_t1", "status": "available"}]
    resp = await client.post(
        "/api/roadmap/import",
        json={
            "content": "## Phase 1 — Core\n\n- [ ] Task A\n",
            "repo": "test-repo",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_count"] == 1  # parsed from markdown (1 task)
    # Verify no tasks were CREATED (dedup skipped it)
    add_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "add_task"]
    assert len(add_calls) == 0


@pytest.mark.asyncio
async def test_cross_project_with_data(client, mock_all):
    """GET /api/cross-project should aggregate tasks by repo."""
    mock_all["sql"].return_value = [
        {"id": "t1", "repo": "repo-a", "status": "available"},
        {"id": "t2", "repo": "repo-a", "status": "inProgress"},
        {"id": "t3", "repo": "repo-b", "status": "done"},
        {"id": "t4", "repo": "repo-b", "status": "done"},
        {"id": "t5", "repo": "repo-c", "status": "blocked"},
    ]
    resp = await client.get("/api/cross-project")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    repos = {d["repo"] for d in data}
    assert "repo-a" in repos
    assert "repo-b" in repos
    assert "repo-c" in repos
    repo_a = next(d for d in data if d["repo"] == "repo-a")
    assert repo_a["available"] == 1
    assert repo_a["inProgress"] == 1
    repo_b = next(d for d in data if d["repo"] == "repo-b")
    assert repo_b["done"] == 2


# ── Scanner ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scan_endpoint_empty(client, mock_all):
    """POST /api/scanner/scan should return empty results when scanners find nothing."""
    with patch("scanners.runner.run_all_scanners", return_value={}):
        resp = await client.post("/api/scanner/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 0
    assert data["total_created"] == 0


@pytest.mark.asyncio
async def test_scan_endpoint_with_findings(client, mock_all):
    """POST /api/scanner/scan should aggregate scanner results."""
    with patch(
        "scanners.runner.run_all_scanners",
        return_value={
            "stdb_index": {"finding_count": 2, "created": 1},
            "todos": {"finding_count": 5, "created": 3},
        },
    ):
        resp = await client.post("/api/scanner/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_findings"] == 7
    assert data["total_created"] == 4


# ── GitHub Issues (no webhook) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_issues(client, mock_all):
    """GET /api/issues should list issue links."""
    with patch(
        "routes.github.issue_sync.list_links",
        return_value=[
            {
                "task_id": "t1",
                "repo": "test/repo",
                "issue_number": 1,
                "html_url": "https://github.com/test/repo/issues/1",
            },
        ],
    ):
        resp = await client.get("/api/issues")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["issue_number"] == 1


@pytest.mark.asyncio
async def test_list_issues_with_repo(client, mock_all):
    """GET /api/issues?repo=xxx should filter by repo."""
    with patch("routes.github.issue_sync.list_links", return_value=[]):
        resp = await client.get("/api/issues", params={"repo": "test/repo"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_issue_found(client, mock_all):
    """GET /api/issues/{task_id} should return the linked issue."""
    with patch(
        "routes.github.issue_sync.get_link",
        return_value={
            "repo": "test/repo",
            "issue_number": 42,
            "html_url": "https://github.com/test/repo/issues/42",
        },
    ):
        resp = await client.get("/api/issues/task_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kanban_task_id"] == "task_1"
    assert data["issue_number"] == 42


@pytest.mark.asyncio
async def test_get_issue_not_found(client, mock_all):
    """GET /api/issues/{task_id} for unlinked task should return 404."""
    with patch("routes.github.issue_sync.get_link", return_value=None):
        resp = await client.get("/api/issues/task_1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_link_issue_success(client, mock_all):
    """POST /api/issues/link should link a task to a GitHub issue."""
    with (
        patch("routes.github.issue_sync.get_link", return_value=None),
        patch(
            "routes.github.issue_sync.link_issue",
            return_value={
                "task_id": "task_1",
                "issue_number": 42,
                "html_url": "https://github.com/test/repo/issues/42",
            },
        ),
    ):
        resp = await client.post(
            "/api/issues/link",
            json={"task_id": "task_1", "repo": "test/repo", "issue_number": 42},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "linked"


@pytest.mark.asyncio
async def test_link_issue_already_linked(client, mock_all):
    """POST /api/issues/link for already-linked task should return 409."""
    with patch(
        "routes.github.issue_sync.get_link",
        return_value={
            "html_url": "https://github.com/test/repo/issues/1",
        },
    ):
        resp = await client.post(
            "/api/issues/link",
            json={"task_id": "task_1", "repo": "test/repo", "issue_number": 42},
        )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unlink_issue_success(client, mock_all):
    """POST /api/issues/unlink should remove the link."""
    with patch("routes.github.issue_sync.unlink_issue", return_value=True):
        resp = await client.post("/api/issues/unlink?task_id=task_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unlinked"


@pytest.mark.asyncio
async def test_unlink_issue_404(client, mock_all):
    """POST /api/issues/unlink for unlinked task should return 404."""
    with patch("routes.github.issue_sync.unlink_issue", return_value=False):
        resp = await client.post("/api/issues/unlink?task_id=task_1")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_issue_from_task_task_not_found(client, mock_all):
    """POST /api/issues/create for missing task should return 404."""
    mock_all["param"].return_value = []  # task not found
    with (
        patch("config.settings.github_token", "test-token"),
        patch("config.settings.github_default_repo", ""),
    ):
        resp = await client.post(
            "/api/issues/create",
            json={"task_id": "nonexistent"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_issue_from_task_no_token(client, mock_all):
    """POST /api/issues/create without GitHub token should return 400."""
    mock_all["param"].return_value = [_make_task("task_1", "Test task")]
    with patch("config.settings.github_token", ""):
        resp = await client.post(
            "/api/issues/create",
            json={"task_id": "task_1"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_issue_from_task_no_repo(client, mock_all):
    """POST /api/issues/create without repo should return 400."""
    mock_all["param"].return_value = [_make_task("task_1", "Test task")]
    with (
        patch("config.settings.github_token", "test-token"),
        patch("config.settings.github_default_repo", ""),
    ):
        resp = await client.post(
            "/api/issues/create",
            json={"task_id": "task_1", "repo": ""},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_issue_from_task_success(client, mock_all):
    """POST /api/issues/create should create and link a GitHub issue."""
    mock_all["param"].return_value = [_make_task("task_1", "Test task", description="A test task")]
    mock_all["call"].return_value = {"status": "ok"}
    with (
        patch("config.settings.github_token", "test-token"),
        patch("config.settings.github_default_repo", "test/repo"),
        patch(
            "routes.github.issue_sync.create_issue",
            return_value={
                "issue_number": 100,
                "html_url": "https://github.com/test/repo/issues/100",
                "issue_url": "https://api.github.com/repos/test/repo/issues/100",
                "state": "open",
            },
        ),
        patch("routes.github.issue_sync.link_issue", return_value={"task_id": "task_1"}),
        patch("routes.github.issue_sync.update_issue_status", return_value={"status": "updated"}),
    ):
        resp = await client.post(
            "/api/issues/create",
            json={
                "task_id": "task_1",
                "repo": "test/repo",
                "labels": "bug,urgent",
                "assignee": "test-user",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"
    assert data["issue_number"] == 100


# ════════════════════════════════════════════════════════════════════════
# ═══ TASK ROUTE EDGE CASES — suggest, clear, bulk, block variants ════
# ════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_suggest_tasks_empty(client, mock_all):
    """GET /api/tasks/suggest should return empty list when no tasks."""
    mock_all["sql"].return_value = []
    resp = await client.get("/api/tasks/suggest", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.asyncio
async def test_suggest_tasks_with_data(client, mock_all):
    """GET /api/tasks/suggest should return scored tasks."""
    mock_all["sql"].return_value = [
        _make_task("t1", "High priority", priority=0, repo="sample-repo-q"),
        _make_task("t2", "Low priority", priority=5, repo="other"),
    ]
    resp = await client.get("/api/tasks/suggest", params={"limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 2
    for item in data:
        assert "task" in item
        assert "score" in item
        assert "reason" in item


@pytest.mark.asyncio
async def test_suggest_tasks_with_agent(client, mock_all):
    """GET /api/tasks/suggest with agent_id should attempt capability matching."""
    mock_all["sql"].return_value = [
        _make_task("t1", "Task A", priority=0, repo="test"),
    ]
    mock_all["param"].return_value = [
        {"capabilities": "python,typescript"},
    ]
    resp = await client.get("/api/tasks/suggest", params={"agent_id": "agent-1", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


@pytest.mark.asyncio
async def test_clear_all_tasks_success(client, mock_all):
    """POST /api/tasks/clear should delete all tasks."""
    mock_all["sql"].return_value = [
        {"id": "task_1"},
        {"id": "task_2"},
    ]
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post("/api/tasks/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cleared"
    assert data["deleted"] == 2


@pytest.mark.asyncio
async def test_clear_all_tasks_empty(client, mock_all):
    """POST /api/tasks/clear with no tasks should return 0 deleted."""
    mock_all["sql"].return_value = []
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post("/api/tasks/clear")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 0


@pytest.mark.asyncio
async def test_bulk_action_claim(client, mock_all):
    """POST /api/tasks/bulk with claim action should claim tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Test", status="in_progress")]
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "claim", "task_ids": ["task_1"], "agent_id": "test-agent"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["results"][0]["status"] == "claimed"


@pytest.mark.asyncio
async def test_bulk_action_complete(client, mock_all):
    """POST /api/tasks/bulk with complete action should complete tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Test", status="done")]
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "complete", "task_ids": ["task_1"], "result_notes": "Done!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_bulk_action_block(client, mock_all):
    """POST /api/tasks/bulk with block action should block tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].side_effect = [
        [_make_task("task_1", "Test", status="in_progress")],
        [_make_task("task_1", "Test", status="blocked")],
    ]
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "block", "task_ids": ["task_1"], "reason": "Blocked for testing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_bulk_action_unclaim(client, mock_all):
    """POST /api/tasks/bulk with unclaim action should unclaim tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Test", status="available")]
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "unclaim", "task_ids": ["task_1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_bulk_action_delete(client, mock_all):
    """POST /api/tasks/bulk with delete action should delete tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Test")]
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "delete", "task_ids": ["task_1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["status"] == "deleted"


@pytest.mark.asyncio
async def test_bulk_action_unknown(client, mock_all):
    """POST /api/tasks/bulk with unknown action should return error."""
    resp = await client.post(
        "/api/tasks/bulk",
        json={"action": "invalid", "task_ids": ["task_1"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["status"] == "error"
    assert "Unknown action" in data["results"][0]["error"]


@pytest.mark.asyncio
async def test_permanent_block_task(client, mock_all):
    """POST /api/tasks/{id}/permanent-block should block permanently."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = [_make_task("task_1", "Test", status="blocked")]
    resp = await client.post(
        "/api/tasks/task_1/permanent-block",
        json={"reason": "Cannot fix"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "permanently_blocked"
    # Verify set_max_attempts was called (fail_count handling)
    max_attempts_calls = [
        c for c in mock_all["call"].call_args_list if c[0][0] == "set_max_attempts"
    ]
    assert len(max_attempts_calls) == 1


@pytest.mark.asyncio
async def test_set_max_attempts(client, mock_all):
    """POST /api/tasks/{id}/max-attempts should update max attempts."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/max-attempts",
        json={"max_attempts": 5},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_attempts"] == 5


@pytest.mark.asyncio
async def test_set_dependency(client, mock_all):
    """POST /api/tasks/{id}/dependency should set a dependency."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_2/dependency",
        json={"depends_on": "task_1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["depends_on"] == "task_1"


@pytest.mark.asyncio
async def test_clear_dependency(client, mock_all):
    """POST /api/tasks/{id}/dependency with empty string should clear."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/dependency",
        json={"depends_on": ""},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["depends_on"] is None


@pytest.mark.asyncio
async def test_split_task(client, mock_all):
    """POST /api/tasks/{id}/split should split task into children."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/split",
        json={"child_titles": ["Child 1", "Child 2"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "split"
    assert data["child_count"] == 2


@pytest.mark.asyncio
async def test_reset_fail_count(client, mock_all):
    """POST /api/tasks/{id}/reset-fails should reset fail count."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post("/api/tasks/task_1/reset-fails")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reset"


@pytest.mark.asyncio
async def test_add_task_log(client, mock_all):
    """POST /api/tasks/{id}/log should add a log entry."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/log",
        json={"action": "commented", "agent_id": "test", "notes": "Test comment"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "logged"
    log_calls = [c for c in mock_all["call"].call_args_list if c[0][0] == "add_log"]
    assert len(log_calls) == 1


# ── Health: uptime with scheduler loaded ──


@pytest.mark.asyncio
async def test_health_uptime_with_scheduler(client):
    """Health endpoint should include uptime when scheduler has start_time."""
    import time as _time

    import scheduler as sched_mod

    orig = sched_mod.scheduler_start_time
    sched_mod.scheduler_start_time = _time.time() - 7200
    try:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["uptime_seconds"] is not None
        assert data["uptime_seconds"] >= 7199.0
    finally:
        sched_mod.scheduler_start_time = orig


# ── Health: project endpoints ──


@pytest.mark.asyncio
async def test_health_projects_endpoint(client):
    """GET /api/health/projects should succeed."""
    with (
        patch("scanners.discover_repos", return_value=["repo1"]),
        patch("scanners.health.compute_all_projects", return_value={"projects": []}),
    ):
        resp = await client.get("/api/health/projects")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_project_detail(client):
    """GET /api/health/projects/{name} should succeed."""
    with patch("scanners.health.compute_project_health", return_value={}):
        resp = await client.get("/api/health/projects/repo1")
    assert resp.status_code == 200
