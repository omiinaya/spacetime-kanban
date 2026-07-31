"""Targeted coverage tests for remaining uncovered lines in routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _absorb_coroutine(coro):
    """Consume a fire-and-forget coroutine without executing it.

    Endpoints use ``asyncio.create_task(_notify(...))`` for background
    notifications. In tests we patch create_task so the coroutine would
    otherwise be GC'd un-awaited (RuntimeWarning). Closing it keeps the
    test hermetic — the notify payload is mocked anyway.
    """
    coro.close()
    return None


# ── Local mock_all fixture (mirrors test_coverage_routes) ──


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
        for name in ("_sql",):
            stack.enter_context(patch(f"shared.{name}", mock_map[name]))
        yield {"sql": sql, "param": param, "call": call, "notify": notify}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── routes/projects.py lines 115-117: suggest_by_project dict result ──


@pytest.mark.asyncio
async def test_projects_suggest_by_project_dict_result(client, mock_all):
    """suggest_by_project returns notice when reducer returns ok status."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = []
    mock_all["param"].return_value = []
    resp = await client.get("/api/suggest-by-project?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data == [{"notice": "reducer returned ok — no data"}]


# ── routes/logs.py lines 35-36: agent_id filter ──


@pytest.mark.asyncio
async def test_logs_agent_id_filter(client, mock_all):
    """list_logs with agent_id param covers agent_id SQL substitution."""
    mock_all["sql"].return_value = [
        {
            "id": "l1",
            "task_id": "t1",
            "action": "created",
            "agent_id": "bot",
            "notes": None,
            "timestamp": 1000,
        },
    ]
    resp = await client.get("/api/logs", params={"agent_id": "bot"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


# ── routes/rules.py line 96: update_rule with non-existent id ──


@pytest.mark.asyncio
async def test_rules_update_not_found(client, mock_all):
    """update_rule raises 404 when rule_id doesn't exist."""
    mock_all["param"].return_value = []
    resp = await client.patch(
        "/api/rules/nonexistent-rule",
        json={"name": "test"},
        headers={"X-API-Key": "test-api-key-123"},
    )
    assert resp.status_code == 404


# ── routes/templates.py line 45: create template not found after creation ──


@pytest.mark.asyncio
async def test_templates_create_not_found_after_creation(client, mock_all):
    """create_task_template raises 500 when template not found after creation."""
    mock_all["call"].return_value = {"status": "ok"}

    mock_all["param"].return_value = []  # no rows returned after creation
    resp = await client.post(
        "/api/task-templates",
        json={
            "title": "Test Template",
            "description": "desc",
            "priority": 2,
            "repo": "test-repo",
            "created_by": "test",
            "cron_schedule": "0 * * * *",
        },
    )
    assert resp.status_code == 500


# ── routes/templates.py lines 95, 97: trigger_templates no log ──


@pytest.mark.asyncio
async def test_templates_trigger_no_log(client, mock_all):
    """trigger_templates returns success when no trigger log found."""
    mock_all["sql"].return_value = []
    resp = await client.post("/api/task-templates/trigger?repo=test-repo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "triggered"
    assert data["notes"] == "completed"


# ── routes/webhook_subs.py line 81: telegram webhook test ──


@pytest.mark.asyncio
async def test_webhook_subs_test_telegram(client, mock_all):
    """test_webhook sends POST to telegram-type webhook."""
    mock_all["param"].return_value = [{"id": "wh1", "url": "https://t.me/bot", "type": "telegram"}]
    mock_all["call"].return_value = {"status": "sent"}

    fake_httpx_client = AsyncMock()
    # post.return_value must be a plain MagicMock, NOT an AsyncMock child:
    # an AsyncMock's return_value is itself an AsyncMock, so resp would be
    # one too and resp.raise_for_status() would create an un-awaited
    # coroutine (RuntimeWarning). A MagicMock makes it a sync method.
    fake_httpx_client.post.return_value = MagicMock(status_code=200)
    fake_httpx_client.__aenter__.return_value = fake_httpx_client
    fake_httpx_client.__aexit__.return_value = None

    with (
        patch(
            "routes.webhook_subs.webhooks.get_webhook",
            return_value={"id": "wh1", "url": "https://t.me/bot", "type": "telegram"},
        ),
        patch("routes.webhook_subs.webhooks.remove_webhook"),
        patch("routes.webhook_subs.httpx.AsyncClient", return_value=fake_httpx_client),
    ):
        resp = await client.post(
            "/api/webhooks/wh1/test", headers={"X-API-Key": "test-api-key-123"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "sent"


# ── routes/webhook_subs.py lines 90-91: webhook test exception ──


@pytest.mark.asyncio
async def test_webhook_subs_test_exception(client, mock_all):
    """test_webhook raises 502 when webhook POST fails."""
    mock_all["param"].return_value = [
        {"id": "wh1", "url": "https://example.com/hook", "type": "generic"}
    ]
    mock_all["call"].return_value = {"status": "sent"}

    fake_httpx_client = AsyncMock()
    fake_httpx_client.post.side_effect = Exception("Connection refused")
    fake_httpx_client.__aenter__.return_value = fake_httpx_client
    fake_httpx_client.__aexit__.return_value = None

    with (
        patch(
            "routes.webhook_subs.webhooks.get_webhook",
            return_value={"id": "wh1", "url": "https://example.com/hook", "type": "generic"},
        ),
        patch("routes.webhook_subs.webhooks.remove_webhook"),
        patch("routes.webhook_subs.httpx.AsyncClient", return_value=fake_httpx_client),
    ):
        resp = await client.post(
            "/api/webhooks/wh1/test", headers={"X-API-Key": "test-api-key-123"}
        )
    assert resp.status_code == 502


# ── routes/tasks.py lines 468-490: _sync_to_github with token ──


@pytest.mark.asyncio
async def test_sync_to_github_with_token(client, mock_all):
    """_sync_to_github with token and valid link calls issue sync functions."""
    from routes.tasks import _sync_to_github

    mock_all["call"].return_value = {"status": "ok"}
    with (
        patch("issue_sync.get_link", return_value={"repo": "test/test", "issue_number": 42}),
        patch("config.settings.github_token", "fake-token"),
        patch("issue_sync.close_issue", new_callable=AsyncMock) as mock_close,
        patch("issue_sync.reopen_issue", new_callable=AsyncMock) as mock_reopen,
        patch("issue_sync.add_issue_comment", new_callable=AsyncMock),
    ):
        result = await _sync_to_github("task_1", "completed", "All done")
        assert result is None
        mock_close.assert_called_once_with("fake-token", "test/test", 42)

        result = await _sync_to_github("task_1", "unclaimed", "Reopened")
        assert result is None
        mock_reopen.assert_called_once_with("fake-token", "test/test", 42)


# ── routes/github.py line 264: non-matching event ignored ──


@pytest.mark.asyncio
async def test_github_webhook_ignored_event(client, mock_all):
    """handle_github_webhook returns ignored for non-issue/non-PR events."""
    resp = await client.post(
        "/api/webhook/github",
        json={"action": "created", "repository": {"full_name": "test/test"}},
        headers={"X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── routes/github.py lines 164-169: reopened issue with existing task id ──


@pytest.mark.asyncio
async def test_github_webhook_reopened_re_link(client, mock_all):
    """Reopened issue with task_id in body re-links existing task."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("issue_sync.link_issue"), patch("issue_sync.update_issue_status"):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "opened",
                "issue": {
                    "number": 1,
                    "title": "Fix bug",
                    "html_url": "https://github.com/test/test/issues/1",
                    "state": "open",
                    "body": "kanban task `task_12345_abc123`",
                },
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "re-linked"


# ── routes/github.py lines 216-233: closed issue ──


@pytest.mark.asyncio
async def test_github_webhook_closed_issue(client, mock_all):
    """Closed issue auto-completes linked task."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = [{"id": "task_1", "status": "inProgress"}]
    mock_all["param"].return_value = [{"id": "task_1", "status": "inProgress"}]
    with (
        patch("issue_sync.get_task_id_for_issue", return_value="task_1"),
        patch("issue_sync.update_issue_status"),
        patch("asyncio.create_task", side_effect=_absorb_coroutine),
    ):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "closed",
                "issue": {"number": 1, "title": "Fix bug", "html_url": "", "body": ""},
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


# ── routes/github.py lines 259-260: reopened with no linked task ──


@pytest.mark.asyncio
async def test_github_webhook_reopened_no_link(client, mock_all):
    """Reopened issue with no linked task returns ignored."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("issue_sync.get_task_id_for_issue", return_value=None):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "reopened",
                "issue": {"number": 2, "title": "Reopen", "html_url": "", "body": ""},
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── routes/github.py lines 225-229: closed issue with available status ──


@pytest.mark.asyncio
async def test_github_webhook_closed_available(client, mock_all):
    """Closed issue with available task claims then completes."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = [{"id": "task_1", "status": "available"}]
    mock_all["param"].return_value = [{"id": "task_1", "status": "available"}]
    with (
        patch("issue_sync.get_task_id_for_issue", return_value="task_1"),
        patch("issue_sync.update_issue_status"),
        patch("asyncio.create_task", side_effect=_absorb_coroutine),
    ):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "closed",
                "issue": {"number": 3, "title": "Fix", "html_url": "", "body": ""},
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_github_webhook_closed_else(client, mock_all):
    """Closed issue with blocked task completes directly."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = [{"id": "task_1", "status": "blocked"}]
    mock_all["param"].return_value = [{"id": "task_1", "status": "blocked"}]
    with (
        patch("issue_sync.get_task_id_for_issue", return_value="task_1"),
        patch("issue_sync.update_issue_status"),
        patch("asyncio.create_task", side_effect=_absorb_coroutine),
    ):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "closed",
                "issue": {"number": 4, "title": "Fix", "html_url": "", "body": ""},
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_github_webhook_closed_no_task(client, mock_all):
    """Closed issue with no linked task returns ignored."""
    mock_all["call"].return_value = {"status": "ok"}
    with patch("issue_sync.get_task_id_for_issue", return_value=None):
        resp = await client.post(
            "/api/webhook/github",
            json={
                "action": "closed",
                "issue": {"number": 3, "title": "Fix", "html_url": "", "body": ""},
                "repository": {"full_name": "test/test"},
                "sender": {"login": "bot"},
            },
            headers={"X-GitHub-Event": "issues"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


# ── routes/tasks.py line 471: early return when no repo/issue_number ──


@pytest.mark.asyncio
async def test_sync_to_github_no_link_data(client, mock_all):
    """_sync_to_github returns early when link lacks repo/issue_number."""
    from routes.tasks import _sync_to_github

    mock_all["call"].return_value = {"status": "ok"}
    with (
        patch("issue_sync.get_link", return_value={"repo": "", "issue_number": 0}),
        patch("config.settings.github_token", "fake-token"),
    ):
        result = await _sync_to_github("task_1", "completed", "Done")
        assert result is None


# ── routes/tasks.py lines 489-490: exception handler ──


@pytest.mark.asyncio
async def test_sync_to_github_exception(client, mock_all):
    """_sync_to_github handles exceptions gracefully."""
    from routes.tasks import _sync_to_github

    mock_all["call"].return_value = {"status": "ok"}
    with (
        patch("issue_sync.get_link", return_value={"repo": "test/test", "issue_number": 42}),
        patch("config.settings.github_token", "fake-token"),
        patch("issue_sync.close_issue", side_effect=Exception("API error")),
        patch("logging.getLogger"),
    ):
        result = await _sync_to_github("task_1", "completed", "Done")
        assert result is None


# ── routes/projects.py line 117: suggest_by_project regular return ──


@pytest.mark.asyncio
async def test_projects_suggest_by_project_return(client, mock_all):
    """suggest_by_project returns list when reducer returns non-dict."""
    mock_all["call"].return_value = [{"id": "t1", "title": "Task"}]
    mock_all["sql"].return_value = []
    mock_all["param"].return_value = []
    resp = await client.get("/api/suggest-by-project?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── main.py line 223: 404 catch-all handler ──


@pytest.mark.asyncio
async def test_main_404_api(client):
    """API catch-all returns 404 for unknown routes."""
    resp = await client.get("/api/unknown-endpoint")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Not found"


# ── routes/github.py line 260: unknown action ──


@pytest.mark.asyncio
async def test_github_webhook_assigned_action(client, mock_all):
    """Issue with unknown action (assigned) returns ignored."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/webhook/github",
        json={
            "action": "assigned",
            "issue": {"number": 5, "title": "Assigned", "html_url": "", "body": ""},
            "repository": {"full_name": "test/test"},
            "sender": {"login": "bot"},
        },
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert resp.json()["action"] == "assigned"


# ── routes/templates.py lines 96-97: trigger exception handler ──


@pytest.mark.asyncio
async def test_templates_trigger_exception(client, mock_all):
    """trigger_templates handles exceptions with 500."""
    mock_all["call"].side_effect = Exception("Reducer crash")
    mock_all["sql"].return_value = []
    resp = await client.post("/api/task-templates/trigger")
    assert resp.status_code == 500
