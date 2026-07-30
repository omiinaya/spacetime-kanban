"""Targeted coverage tests for analytics, github, and health routes."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from main import app


def _make_task(tid="t1", title="T", status="available", repo="my-repo",
               priority=0, created_at=1000, updated_at=1000, due_by=None,
               roadmap_item="", description="", assigned_to=None,
               branch=None, created_by="test", depends_on=None,
               required_skills=None, score=0, position=None,
               fail_count=0, max_attempts=3, fail_reason=None,
               subtask_of=None, subtasks=None, sprint=None,
               archived=False, estimated_hours=None, spent_hours=None):
    return {
        "id": tid, "title": title, "description": description,
        "priority": priority, "status": status, "assigned_to": assigned_to,
        "repo": repo, "branch": branch, "roadmap_item": roadmap_item,
        "created_by": created_by, "created_at": created_at,
        "updated_at": updated_at, "depends_on": depends_on,
        "required_skills": required_skills, "score": score,
        "position": position, "fail_count": fail_count,
        "max_attempts": max_attempts, "fail_reason": fail_reason,
        "subtask_of": subtask_of, "subtasks": subtasks,
        "due_by": due_by, "sprint": sprint, "archived": archived,
        "estimated_hours": estimated_hours, "spent_hours": spent_hours,
    }


# ── Fixtures ──


@pytest.fixture(autouse=True)
def mock_all():
    """Mock STDB helpers for all route tests."""
    route_modules = {
        "routes.agents": ["_sql", "_sql_param", "_call"],
        "routes.analytics": ["_sql", "_sql_param"],
        "routes.github": ["_sql_param", "_call", "_notify"],
        "routes.health": [],
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
    from contextlib import ExitStack
    with ExitStack() as stack:
        sql = AsyncMock(return_value=[])
        param = AsyncMock(return_value=[])
        call = AsyncMock(return_value={"status": "ok"})
        notify = AsyncMock(return_value=None)
        mock_map = {"_sql": sql, "_sql_param": param, "_call": call, "_notify": notify}
        for mod, names in route_modules.items():
            for name in names:
                stack.enter_context(patch(f"{mod}.{name}", mock_map[name]))
        # Patch shared for dynamic imports (health endpoint)
        for name in ("_sql",):
            stack.enter_context(patch(f"shared.{name}", mock_map[name]))
        yield {"sql": sql, "param": param, "call": call, "notify": notify}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Analytics: throughput (lines 125-134) ──


@pytest.mark.asyncio
async def test_analytics_throughput(client, mock_all):
    """Throughput groups completions by day."""
    import time as _time
    now = int(_time.time() * 1000)
    day_ms = 86_400_000
    yesterday = now - day_ms
    mock_all["sql"].return_value = [
        _make_task("t1", "Done yesterday", status="done", updated_at=yesterday),
        _make_task("t2", "Today task", status="available", updated_at=now),
    ]
    resp = await client.get("/api/analytics/throughput?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 8
    assert any(d["completed"] > 0 for d in data)


# ── Analytics: cycle times (lines 160-168, 172, 182-188, 192-193) ──


@pytest.mark.asyncio
async def test_analytics_cycle_times_basic(client, mock_all):
    """Cycle times computes duration from created to completed logs."""
    mock_all["sql"].side_effect = [
        [  # logs
            {"id": "l1", "task_id": "t1", "action": "created", "timestamp": 1000, "agent_id": None, "notes": None},
            {"id": "l2", "task_id": "t1", "action": "completed", "timestamp": 5000, "agent_id": None, "notes": None},
        ],
        [  # tasks for repo mapping
            {"id": "t1", "repo": "my-repo"},
        ],
    ]
    resp = await client.get("/api/analytics/cycle-times")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["repo"] == "my-repo"


@pytest.mark.asyncio
async def test_analytics_cycle_times_repo_filter(client, mock_all):
    """Cycle times filters by repo parameter."""
    mock_all["sql"].side_effect = [
        [  # logs
            {"id": "l1", "task_id": "t1", "action": "created", "timestamp": 1000, "agent_id": None, "notes": None},
            {"id": "l2", "task_id": "t1", "action": "completed", "timestamp": 5000, "agent_id": None, "notes": None},
        ],
    ]
    mock_all["param"].return_value = [{"id": "t1", "repo": "my-repo"}]
    resp = await client.get("/api/analytics/cycle-times", params={"repo": "my-repo"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ── Analytics: burndown (lines 214, 216) ──


@pytest.mark.asyncio
async def test_analytics_burndown_filters(client, mock_all):
    """Burndown applies sprint and repo filters."""
    import time as _time
    now = int(_time.time() * 1000)
    day_ms = 86_400_000
    recent = now - day_ms
    mock_all["sql"].return_value = [
        {"id": "t1", "status": "done", "repo": "my-repo", "roadmap_item": "S1",
         "created_at": recent, "updated_at": recent + 1000,
         "priority": 2, "title": "A", "description": "", "assigned_to": None,
         "branch": None, "created_by": "test", "depends_on": None,
         "required_skills": None, "score": 0, "position": None,
         "fail_count": 0, "max_attempts": 3, "fail_reason": None,
         "subtask_of": None, "subtasks": None, "due_by": None,
         "sprint": None, "archived": False, "estimated_hours": None,
         "spent_hours": None},
        {"id": "t2", "status": "available", "repo": "other-repo", "roadmap_item": "S1",
         "created_at": recent, "updated_at": recent,
         "priority": 2, "title": "B", "description": "", "assigned_to": None,
         "branch": None, "created_by": "test", "depends_on": None,
         "required_skills": None, "score": 0, "position": None,
         "fail_count": 0, "max_attempts": 3, "fail_reason": None,
         "subtask_of": None, "subtasks": None, "due_by": None,
         "sprint": None, "archived": False, "estimated_hours": None,
         "spent_hours": None},
        {"id": "t3", "status": "available", "repo": "my-repo", "roadmap_item": "S2",
         "created_at": recent, "updated_at": recent,
         "priority": 2, "title": "C", "description": "", "assigned_to": None,
         "branch": None, "created_by": "test", "depends_on": None,
         "required_skills": None, "score": 0, "position": None,
         "fail_count": 0, "max_attempts": 3, "fail_reason": None,
         "subtask_of": None, "subtasks": None, "due_by": None,
         "sprint": None, "archived": False, "estimated_hours": None,
         "spent_hours": None},
    ]
    resp = await client.get("/api/analytics/burndown?repo=my-repo&sprint=S1&days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert data["days_total"] == 7
    assert data["total_completed"] == 1  # Only t1 is done from my-repo + S1


# ── Analytics: agents with repo filter (lines 285, 299-305, 309-310) ──


@pytest.mark.asyncio
async def test_analytics_agents_repo_filter(client, mock_all):
    """Agent stats with repo filter."""
    mock_all["sql"].return_value = [
        {"id": "agent-1", "status": "online", "capabilities": None, "repo_focus": None, "last_heartbeat": 1000},
    ]
    mock_all["param"].return_value = [
        {"task_id": "t1", "agent_id": "agent-1", "action": "completed", "timestamp": 0, "id": "l1", "notes": None},
    ]
    resp = await client.get("/api/analytics/agents", params={"repo": "my-repo"})
    assert resp.status_code == 200
    assert resp.json()[0]["completed"] == 1


# ── Analytics: cross-project (lines 327-357) ──


@pytest.mark.asyncio
async def test_analytics_cross_project(client, mock_all):
    """Cross-project returns per-repo aggregations."""
    mock_all["sql"].side_effect = [
        [  # tasks
            {"id": "t1", "repo": "repo-a", "status": "done", "priority": 0, "roadmap_item": "S1",
             "sprint": "S1", "title": "T1", "description": "", "assigned_to": None,
             "branch": None, "created_by": "test", "created_at": 1000, "updated_at": 1000,
             "depends_on": None, "required_skills": None, "score": 0, "position": None,
             "fail_count": 0, "max_attempts": 3, "fail_reason": None,
             "subtask_of": None, "subtasks": None, "due_by": None,
             "archived": False, "estimated_hours": None, "spent_hours": None},
            {"id": "t2", "repo": "repo-a", "status": "available", "priority": 2,
             "roadmap_item": "", "sprint": "", "title": "T2", "description": "",
             "assigned_to": None, "branch": None, "created_by": "test",
             "created_at": 1000, "updated_at": 1000, "depends_on": None,
             "required_skills": None, "score": 0, "position": None,
             "fail_count": 0, "max_attempts": 3, "fail_reason": None,
             "subtask_of": None, "subtasks": None, "due_by": None,
             "archived": False, "estimated_hours": None, "spent_hours": None},
        ],
        [  # projects
            {"id": "repo-a", "name": "Repo A", "description": ""},
        ],
    ]
    resp = await client.get("/api/analytics/cross-project")
    assert resp.status_code == 200
    data = resp.json()
    assert "repo-a" in data
    assert data["repo-a"]["total"] == 2
    assert data["repo-a"]["by_status"]["done"] == 1
    assert data["repo-a"]["sprints"] == ["S1"]


# ── Analytics: calendar (lines 363-385) ──


@pytest.mark.asyncio
async def test_analytics_calendar_default(client, mock_all):
    """Calendar returns current month tasks with due dates."""
    mock_all["sql"].return_value = []
    resp = await client.get("/api/analytics/calendar")
    assert resp.status_code == 200
    assert resp.json()["tasks"] == []


@pytest.mark.asyncio
async def test_analytics_calendar_with_data(client, mock_all):
    """Calendar returns tasks in the specified month."""
    due = int(datetime(2026, 6, 15, tzinfo=UTC).timestamp() * 1000)
    mock_all["sql"].return_value = [
        _make_task("t1", "June task", status="available", due_by=due),
    ]
    resp = await client.get("/api/analytics/calendar", params={"year": 2026, "month": 6})
    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 1
    assert resp.json()["tasks"][0]["title"] == "June task"


# ── Github: issue opened -- lines 144-212 ──


@pytest.mark.asyncio
async def test_github_issue_opened_creates_task(client, mock_all):
    """Issue opened creates a task when no existing link."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("routes.github.issue_sync.get_link", return_value=None), \
         patch("routes.github.issue_sync.link_issue", return_value={}), \
         patch("routes.github.issue_sync.update_issue_status", return_value={}):
        resp = await client.post(
            "/api/webhook/github",
            json={"action": "opened", "issue": {"number": 50, "title": "New",
                  "html_url": "", "body": "", "state": "open", "url": ""},
                  "repository": {"full_name": "test/repo"}},
            headers={"X-GitHub-Event": "issues"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "created"


@pytest.mark.asyncio
async def test_github_issue_reopened_done(client, mock_all):
    """Issue reopened unclaims a done task."""
    mock_all["param"].return_value = [
        _make_task("t1", "Done task", status="done", repo="test/repo"),
    ]
    mock_all["call"].return_value = {"status": "ok"}
    with patch("routes.github.issue_sync.get_task_id_for_issue", return_value="t1"), \
         patch("routes.github.issue_sync.update_issue_status", return_value={}):
        resp = await client.post(
            "/api/webhook/github",
            json={"action": "reopened", "issue": {"number": 42, "title": "Reopen",
                  "html_url": "", "body": "", "state": "open"},
                  "repository": {"full_name": "test/repo"}},
            headers={"X-GitHub-Event": "issues"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "reopened"


@pytest.mark.asyncio
async def test_github_pr_opened_sql_fallback(client, mock_all):
    """PR opened falls back on SQL error."""
    mock_all["param"].side_effect = Exception("DB error")
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "opened", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "PR title"},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "linked"


@pytest.mark.asyncio
async def test_github_pr_merged_available(client, mock_all):
    """PR merged claims and completes an available task."""
    mock_all["param"].return_value = [
        _make_task("task_abc", "Task", status="available", repo="test/repo"),
    ]
    mock_all["call"].return_value = {"status": "ok"}
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "closed", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "", "merged": True},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_github_pr_closed_not_merged(client, mock_all):
    """PR closed without merge is ignored."""
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "closed", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "", "merged": False},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_github_pr_merged_http_exception(client, mock_all):
    """PR merged handles HTTPException gracefully."""
    mock_all["param"].return_value = [
        _make_task("task_abc", "Task", status="inProgress", repo="test/repo"),
    ]
    mock_all["call"].side_effect = HTTPException(502, "reducer failed")
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "closed", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "", "merged": True},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── Health: project endpoints ──


@pytest.mark.asyncio
async def test_health_projects(client, mock_all):
    """GET /api/health/projects returns data."""
    with patch("scanners.discover_repos", return_value=["repo1"]), \
         patch("scanners.health.compute_all_projects", return_value={"projects": []}):
        resp = await client.get("/api/health/projects")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_health_project_detail(client, mock_all):
    """GET /api/health/projects/{name} returns data."""
    with patch("scanners.health.compute_project_health", return_value={"name": "repo1"}):
        resp = await client.get("/api/health/projects/repo1")
    assert resp.status_code == 200


# ── Ops: roadmap import batch (lines 60-85) ──


@pytest.mark.asyncio
async def test_ops_roadmap_import(client, mock_all):
    """POST /api/roadmap/import processes tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["param"].return_value = []
    content = "## Phase 1\n" + "\n".join(f"- [ ] Task {i}" for i in range(8))
    resp = await client.post("/api/roadmap/import", json={"content": content, "repo": "test-repo"})
    assert resp.status_code == 200
    assert resp.json()["task_count"] == 8


# ── Webhook subs: edge cases (lines 48, 58-91) ──


@pytest.mark.asyncio
async def test_webhook_update_404(client, mock_all):
    """PATCH /api/webhooks/{id} for non-existent returns 404."""
    with patch("routes.webhook_subs.webhooks.update_webhook", return_value=None):
        resp = await client.patch(
            "/api/webhooks/nonexistent", json={"label": "test"},
            headers={"X-API-Key": "test-api-key-123"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_webhook_test_404(client, mock_all):
    """POST /api/webhooks/{id}/test for non-existent returns 404."""
    with patch("routes.webhook_subs.webhooks.get_webhook", return_value=None):
        resp = await client.post(
            "/api/webhooks/nonexistent/test",
            headers={"X-API-Key": "test-api-key-123"})
    assert resp.status_code == 404


# ── Health: uptime with scheduler loaded (lines 53-54) ──


@pytest.mark.asyncio
async def test_health_uptime_with_scheduler(client, mock_all):
    """Health endpoint shows uptime when scheduler has start_time."""
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


@pytest.mark.asyncio
async def test_health_board_with_data(client, mock_all):
    """Health shows board summary when tasks exist."""
    mock_all["sql"].return_value = [
        {"id": "t1", "status": "done"},
        {"id": "t2", "status": "available"},
    ]
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["board"]["total"] == 2
    assert resp.json()["board"]["by_status"]["done"] == 1
    assert resp.json()["board"]["by_status"]["available"] == 1


# ── Github: PR no branch / bad pattern (lines 164-169) ──


@pytest.mark.asyncio
async def test_github_pr_no_branch(client, mock_all):
    """PR event with no branch ref is ignored."""
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "opened", "pull_request": {"head": {},
              "html_url": "", "title": ""},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_github_pr_bad_pattern(client, mock_all):
    """PR event with non-conforming branch is ignored."""
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "opened", "pull_request": {"head": {"ref": "random-branch"},
              "html_url": "", "title": ""},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── Github: PR opened with task title (lines 216-233, 259-260) ──


@pytest.mark.asyncio
async def test_github_pr_opened_task_title(client, mock_all):
    """PR opened updates task title when task exists."""
    mock_all["param"].return_value = [
        {"title": "Existing task"},
    ]
    mock_all["call"].return_value = {"status": "ok"}
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "opened", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "PR title"},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "linked"


# ── Github: PR merged task not found (lines 264, 272, 277, 287) ──


@pytest.mark.asyncio
async def test_github_pr_merged_not_found(client, mock_all):
    """PR merged with no matching task is ignored."""
    mock_all["param"].return_value = []
    branch = "feature/kanban-task_abc--feature"
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "closed", "pull_request": {"head": {"ref": branch},
              "html_url": "", "title": "", "merged": True},
              "repository": {"full_name": "test/repo"}},
        headers={"X-GitHub-Event": "pull_request"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert "not found" in resp.json()["reason"]


# ── Ops: cross-project (line 146) ──


@pytest.mark.asyncio
async def test_ops_cross_project(client, mock_all):
    """GET /api/cross-project returns per-repo aggregation."""
    mock_all["sql"].return_value = [
        {"id": "t1", "repo": "repo-a", "status": "done", "priority": 0,
         "archived": True, "title": "", "description": "",
         "assigned_to": None, "branch": None, "created_by": "",
         "created_at": 1000, "updated_at": 1000, "depends_on": None,
         "required_skills": None, "score": 0, "position": None,
         "fail_count": 0, "max_attempts": 3, "fail_reason": None,
         "subtask_of": None, "subtasks": None, "due_by": None,
         "sprint": None, "roadmap_item": "",
         "estimated_hours": None, "spent_hours": None},
    ]
    resp = await client.get("/api/cross-project")
    assert resp.status_code == 200
    assert len(resp.json()) > 0


# ── Webhook: test success (lines 58-91) ──


@pytest.mark.asyncio
async def test_webhook_test_success(client, mock_all):
    """POST /api/webhooks/{id}/test sends a test ping."""
    with patch("routes.webhook_subs.webhooks.get_webhook", return_value={
        "id": "wh1", "url": "https://hooks.example.com/hook",
        "type": "generic", "events": "created", "label": "test",
    }), patch("webhooks._format_payload", return_value={"text": "ping"}), \
        patch("httpx.AsyncClient") as mc:
        mclient = AsyncMock()
        mc.return_value.__aenter__.return_value = mclient
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mclient.post = AsyncMock(return_value=mock_resp)
        resp = await client.post(
            "/api/webhooks/wh1/test",
            headers={"X-API-Key": "test-api-key-123"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


# ── Health: board query exception (lines 71-77) ──


@pytest.mark.asyncio
async def test_health_board_query_exception(client, mock_all):
    """Health handles board query failure gracefully."""
    mock_all["sql"].side_effect = Exception("DB timeout")
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("board") == {}  # board stays empty on error


# ── Health: board query import error (line 71-72) ──


@pytest.mark.asyncio
async def test_health_board_import_error(client):
    """Health handles when shared module import fails."""
    import sys
    old_shared = sys.modules.get("shared")
    sys.modules["shared"] = None  # Make shared unimportable
    try:
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("board") == {}
    finally:
        if old_shared:
            sys.modules["shared"] = old_shared
        else:
            sys.modules.pop("shared", None)


# ── Tasks: batch assign/unassign labels (lines 292-314) ──

@pytest.mark.asyncio
async def test_tasks_batch_assign_labels(client, mock_all):
    """POST /api/tasks/batch/labels should assign labels to tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/batch/labels",
            json={"task_ids": ["t1", "t2"], "label_ids": ["l1", "l2"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "assigned"


@pytest.mark.asyncio
async def test_tasks_batch_assign_empty(client, mock_all):
    """batch/labels with empty lists returns 400."""
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/batch/labels",
            json={"task_ids": [], "label_ids": []},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_tasks_batch_unassign_labels(client, mock_all):
    """POST /api/tasks/batch/unlabels should remove labels."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/batch/unlabels",
            json={"task_ids": ["t1"], "label_ids": ["l1"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "removed"


@pytest.mark.asyncio
async def test_tasks_batch_unassign_empty(client, mock_all):
    """batch/unlabels with empty lists returns 400."""
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/batch/unlabels",
            json={"task_ids": [], "label_ids": []},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 400


# ── Tasks: seed (line 168-169) ──

@pytest.mark.asyncio
async def test_tasks_seed(client, mock_all):
    """POST /api/tasks/seed should seed sample tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post("/api/tasks/seed")
    assert resp.status_code == 200
    assert resp.json()["status"] == "seeded"


# ── Tasks: set skills (line 368, 719-720) ──

@pytest.mark.asyncio
async def test_tasks_set_skills(client, mock_all):
    """POST /api/tasks/{id}/skills should set task skills."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/task_1/skills", json={"skills": "python, rust"},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"


# ── Tasks: unarchive (line 411, 734-737) ──

@pytest.mark.asyncio
async def test_tasks_unarchive(client, mock_all):
    """POST /api/tasks/{id}/unarchive should unarchive a task."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/task_1/unarchive",
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "unarchived"


# ── Tasks: list with archived filter (lines 125-126) ──

@pytest.mark.asyncio
async def test_tasks_list_archived_filter(client, mock_all):
    """GET /api/tasks?archived=true should pass archived filter."""
    mock_all["param"].return_value = []
    resp = await client.get("/api/tasks", params={"status": "available", "archived": True})
    assert resp.status_code == 200


# ── Tasks: list with repo filter (lines 195-206) ──

@pytest.mark.asyncio
async def test_tasks_list_repo_filter(client, mock_all):
    """GET /api/tasks?repo=xxx should pass repo filter."""
    mock_all["param"].return_value = []
    resp = await client.get("/api/tasks", params={"repo": "sample-repo-q"})
    assert resp.status_code == 200



# ── Tasks: reorder (lines 274-275) ──

@pytest.mark.asyncio
async def test_tasks_reorder(client, mock_all):
    """POST /api/tasks/reorder should call reorder_task."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/reorder", json={"task_id": "t1", "position": 1},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reordered"


@pytest.mark.asyncio
async def test_tasks_bulk_reorder(client, mock_all):
    """POST /api/tasks/bulk-reorder should call bulk_reorder_tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-reorder",
            json={"items": [{"task_id": "t1", "position": 0}]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reordered"



# ── Tasks: suggest with agent capabilities (lines 79-80, 86-87) ──

@pytest.mark.asyncio
async def test_tasks_suggest_with_agent_caps(client, mock_all):
    """GET /api/tasks/suggest handles agent errors gracefully."""
    mock_all["sql"].side_effect = [
        [{"id": "t1", "title": "Test", "status": "available",
          "repo": "r", "priority": 128, "created_at": 9999999999999,
          "required_skills": "", "description": "", "assigned_to": None,
          "branch": None, "created_by": "test", "updated_at": 9999999999999,
          "depends_on": None, "score": 0, "position": None,
          "fail_count": 0, "max_attempts": 3, "fail_reason": None,
          "subtask_of": None, "subtasks": None, "due_by": None,
          "sprint": None, "archived": False, "estimated_hours": None,
          "spent_hours": None}],  # tasks
        [{"id": "agent-1", "capabilities": None}],  # agent
        [],  # blockers
    ]
    resp = await client.get("/api/tasks/suggest", params={"agent_caps": "python, rust"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


# ── Tasks: pagination edge cases (lines 156, 158) ──

@pytest.mark.asyncio
async def test_tasks_list_with_offset_limit(client, mock_all):
    """GET /api/tasks with offset and limit pagination."""
    mock_all["param"].return_value = [
        {"id": "t1", "title": "T1", "status": "available",
         "repo": "r", "priority": 0, "created_at": 1000, "updated_at": 1000,
         "description": "", "assigned_to": None, "branch": None,
         "created_by": "test", "depends_on": None, "required_skills": None,
         "score": 0, "position": None, "fail_count": 0, "max_attempts": 3,
         "fail_reason": None, "subtask_of": None, "subtasks": None,
         "due_by": None, "sprint": None, "archived": False,
         "estimated_hours": None, "spent_hours": None, "roadmap_item": ""},
        {"id": "t2", "title": "T2", "status": "available",
         "repo": "r", "priority": 0, "created_at": 1000, "updated_at": 1000,
         "description": "", "assigned_to": None, "branch": None,
         "created_by": "test", "depends_on": None, "required_skills": None,
         "score": 0, "position": None, "fail_count": 0, "max_attempts": 3,
         "fail_reason": None, "subtask_of": None, "subtasks": None,
         "due_by": None, "sprint": None, "archived": False,
         "estimated_hours": None, "spent_hours": None, "roadmap_item": ""},
    ]
    resp = await client.get("/api/tasks", params={"offset": 0, "limit": 1})
    assert resp.status_code == 200


# ── Tasks: task not found (line 387) ──

@pytest.mark.asyncio
async def test_tasks_get_not_found(client, mock_all):
    """GET /api/tasks/{id} returns 404 for unknown task."""
    mock_all["param"].return_value = []
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.get("/api/tasks/nonexistent")
    assert resp.status_code == 404


# ── Tasks: bulk archive (lines 622-623) ──

@pytest.mark.asyncio
async def test_tasks_bulk_archive(client, mock_all):
    """POST /api/tasks/bulk-archive archives tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-archive", json={"task_ids": ["t1", "t2"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200


# ── Tasks: bulk retry (lines 697-698) ──

@pytest.mark.asyncio
async def test_tasks_bulk_retry(client, mock_all):
    """POST /api/tasks/bulk-retry retries failed tasks."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-retry", json={"task_ids": ["t1"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200


# ── Dispatcher: state parsing errors and call failures ──


@pytest.mark.asyncio
async def test_dispatcher_state_json_decode_error(client, mock_all):
    """Dispatcher handles non-JSON value in dispatcher_state."""
    mock_all["sql"].return_value = [
        {"key": "test_key", "value": "not-json{"},
    ]
    resp = await client.get("/api/dispatcher/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("test_key") == "not-json{"


@pytest.mark.asyncio
async def test_dispatcher_state_call_failure(client, mock_all):
    """Dispatcher returns 502 when set_dispatcher_state reducer fails."""
    mock_all["call"].side_effect = Exception("Reducer crashed")
    resp = await client.post(
        "/api/dispatcher/state",
        json={"key": "test_key", "value": "test_val"},
    )
    assert resp.status_code == 502
    assert "Reducer crashed" in resp.text


@pytest.mark.asyncio
async def test_dispatcher_state_delete_not_found(client, mock_all):
    """Dispatcher returns 404 when deleting non-existent key."""
    mock_all["call"].side_effect = Exception("Key not found: ghost")
    resp = await client.delete("/api/dispatcher/state/ghost")
    assert resp.status_code == 404


# ── Labels: fallback responses after create/update ──


@pytest.mark.asyncio
async def test_create_label_fallback(client, mock_all):
    """create_label returns fallback when label not found after insert."""
    mock_all["param"].return_value = []  # SELECT after create returns nothing
    resp = await client.post("/api/labels", json={
        "id": "new_label", "name": "new", "color": "#ff0", "description": "",
    })
    assert resp.status_code == 201
    assert resp.json() == {"status": "created"}


@pytest.mark.asyncio
async def test_update_label_fallback(client, mock_all):
    """update_label returns fallback when label not found after update."""
    mock_all["param"].return_value = []  # SELECT after update returns nothing
    resp = await client.patch("/api/labels/label_42", json={
        "name": "renamed", "color": "#00f", "description": "",
    })
    assert resp.status_code == 200
    assert resp.json() == {"status": "updated"}


# ── Ops: roadmap import dedup and migration alias ──


@pytest.mark.asyncio
async def test_roadmap_import_dedup_existing(client, mock_all):
    """Roadmap import skips tasks that already exist (same title+repo, not done)."""
    mock_all["param"].return_value = [{"id": "existing_1", "status": "available"}]
    resp = await client.post("/api/roadmap/import", json={
        "content": "- [ ] Existing title\n",
        "repo": "test-repo",
        "created_by": "test",
    })
    assert resp.status_code == 200
    mock_all["call"].assert_not_called()
    data = resp.json()
    assert data["status"] == "imported"
    assert data["task_count"] == 1


@pytest.mark.asyncio
async def test_schema_migration_alias(client, mock_all):
    """POST /api/schema-migrations alias returns 201."""
    resp = await client.post("/api/schema-migrations", json={
        "version": "v2", "description": "Test migration",
        "applied_by": "tester", "checksum": "abc123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "recorded"
    assert data["version"] == "v2"


# ── Projects: suggest_by_project fallback ──


@pytest.mark.asyncio
async def test_suggest_by_project_reducer_fail_fallback(client, mock_all):
    """suggest_by_project falls back to API computation when reducer fails."""
    mock_all["call"].side_effect = HTTPException(502, "Reducer failed")
    call_count = [0]

    async def sql_side(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return []  # tasks
        return [{"id": "proj_1", "priority": 1, "active": True}]

    mock_all["sql"].side_effect = sql_side
    resp = await client.get("/api/suggest-by-project?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── Main: 404 catch-all (line 223) ──


@pytest.mark.asyncio
async def test_main_404_catch_all(client, mock_all):
    """GET on non-existent API path returns 404."""
    resp = await client.get("/api/nonexistent/route")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Not found"


# ── Analytics: old-task throughput filtering (line 130) ──


@pytest.mark.asyncio
async def test_analytics_throughput_old_done_task_filtered(client, mock_all):
    """Throughput filters out tasks older than requested days."""
    old_done = _make_task("old_done", status="done", updated_at=1000)
    mock_all["sql"].return_value = [old_done]
    resp = await client.get("/api/analytics/throughput?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert all(d["completed"] == 0 for d in data)


# ── Analytics: agents endpoint with blocked actions (lines 304-305) ──


@pytest.mark.asyncio
async def test_analytics_agents_blocked_counted(client, mock_all):
    """Agents endpoint counts blocked logs separately."""
    calls = []

    async def sql_side(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return [{"id": "agent_1", "status": "online"}]
        return [
            {"agent_id": "agent_1", "action": "completed", "task_id": "t1"},
            {"agent_id": "agent_1", "action": "blocked", "task_id": "t2"},
        ]

    mock_all["sql"].side_effect = sql_side
    resp = await client.get("/api/analytics/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["completed"] == 1
    assert data[0]["blocked"] == 1


# ── Logs: multi-action filter pass (lines 35-36) ──


@pytest.mark.asyncio
async def test_logs_multi_action_filter(client, mock_all):
    """list_logs with multiple comma-separated actions enters pass block."""
    mock_all["sql"].return_value = [
        {"id": "l1", "task_id": "t1", "action": "created", "agent_id": None, "notes": None, "timestamp": 1000},
    ]
    resp = await client.get("/api/logs", params={"action": "created,claimed"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


# ── Projects: suggest by project exception path (lines 115-117) ──


@pytest.mark.asyncio
async def test_suggest_by_project_exception(client, mock_all):
    """suggest_by_project handles reducer exception via fallback."""
    mock_all["call"].side_effect = HTTPException(502, "Reducer failed")
    mock_all["sql"].side_effect = [
        [],  # tasks for fallback query
        [{"id": "proj_1", "priority": 1, "active": True}],  # projects
    ]
    resp = await client.get("/api/suggest-by-project?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)

