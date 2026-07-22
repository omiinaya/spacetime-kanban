"""Unit tests for spacetimedb-kanban API with mocked STDB backend."""

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
        "routes.analytics": ["_sql"],
        "routes.github": ["_sql_param", "_call", "_notify"],
        "routes.labels": ["_sql", "_sql_param", "_call"],
        "routes.logs": ["_sql"],
        "routes.projects": ["_sql", "_sql_param", "_call"],
        "routes.tasks": ["_sql", "_sql_param", "_call", "_notify"],
        "routes.templates": ["_sql", "_sql_param", "_call"],
        "routes.ops": ["_sql", "_call"],
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
    with patch("routes.analytics._sql", new_callable=AsyncMock) as mock_sql:
        # Endpoint filters in SQL; emulate by returning only in-window rows
        mock_sql.return_value = [l for l in logs if l["timestamp"] > now_ms - 3_600_000]
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
    mock_all["param"].return_value = [
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
