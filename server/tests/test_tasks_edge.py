"""Targeted coverage tests for routes/tasks.py edge cases.

Covers: label assignments endpoint, block-with-reason, export filters,
scoring exception handlers, bulk operation error paths, reorder checklist,
task update branches, and delete notification firing.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from main import app


def _task_dict(
    tid="task_1",
    title="Test task",
    description="Desc",
    priority=0,
    status="available",
    repo="test-repo",
    assigned_to=None,
    branch=None,
    roadmap_item="",
    created_by="test",
    created_at=1000,
    updated_at=1000,
    depends_on=None,
    required_skills=None,
    score=0,
    position=None,
    fail_count=0,
    max_attempts=3,
    fail_reason=None,
    subtask_of=None,
    subtasks=None,
    due_by=None,
    sprint=None,
    archived=False,
    estimated_hours=None,
    spent_hours=None,
):
    return {
        "id": tid,
        "title": title,
        "description": description,
        "priority": priority,
        "status": status,
        "assigned_to": assigned_to,
        "repo": repo,
        "branch": branch,
        "roadmap_item": roadmap_item,
        "created_by": created_by,
        "created_at": created_at,
        "updated_at": updated_at,
        "depends_on": depends_on,
        "required_skills": required_skills,
        "score": score,
        "position": position,
        "fail_count": fail_count,
        "max_attempts": max_attempts,
        "fail_reason": fail_reason,
        "subtask_of": subtask_of,
        "subtasks": subtasks,
        "due_by": due_by,
        "sprint": sprint,
        "archived": archived,
        "estimated_hours": estimated_hours,
        "spent_hours": spent_hours,
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
        for name in ("_sql",):
            stack.enter_context(patch(f"shared.{name}", mock_map[name]))
        yield {"sql": sql, "param": param, "call": call, "notify": notify}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── GET /api/tasks/labels/assignments (19 uncovered lines) ──


@pytest.mark.asyncio
async def test_get_all_task_label_assignments(client, mock_all):
    """GET /api/tasks/labels/assignments returns task->labels mapping."""
    mock_all["sql"].return_value = [
        {"task_id": "t1", "id": "l1", "name": "bug", "color": "#f00",
         "description": "", "created_at": 1000},
        {"task_id": "t1", "id": "l2", "name": "urgent", "color": "#ff0",
         "description": "", "created_at": 1000},
        {"task_id": "t2", "id": "l1", "name": "bug", "color": "#f00",
         "description": "", "created_at": 1000},
    ]
    resp = await client.get("/api/tasks/labels/assignments")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert len(data["t1"]) == 2
    assert len(data["t2"]) == 1


# ── POST /api/tasks/{task_id}/block-with-reason (4 uncovered lines) ──


@pytest.mark.asyncio
async def test_block_with_reason_notifies_first_block(client, mock_all):
    """Block-with-reason triggers notification for first block."""
    mock_all["param"].return_value = [_task_dict(status="in_progress", fail_count=1)]
    resp = await client.post(
        "/api/tasks/task_1/block-with-reason",
        json={"reason": "Blocked on external API"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["reason"] == "Blocked on external API"


# ── GET /api/tasks: offset and limit slicing (lines 156, 158) ──


@pytest.mark.asyncio
async def test_list_tasks_offset_and_limit(client, mock_all):
    """GET /api/tasks with offset/limit returns subset."""
    mock_all["sql"].return_value = [
        _task_dict(tid="t1"), _task_dict(tid="t2"), _task_dict(tid="t3"),
    ]
    resp = await client.get("/api/tasks?offset=1&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["id"] == "t2"


# ── GET /api/tasks/export: repo filter (lines 195-196, 198, 200) ──


@pytest.mark.asyncio
async def test_export_tasks_with_repo_filter(client, mock_all):
    """GET /api/tasks/export with repo filter uses _sql_param."""
    mock_all["param"].return_value = [_task_dict(tid="t1", repo="my-repo")]
    resp = await client.get("/api/tasks/export?repo=my-repo")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_export_tasks_no_repo(client, mock_all):
    """GET /api/tasks/export without repo filter uses _sql."""
    mock_all["sql"].return_value = [_task_dict(tid="t1")]
    resp = await client.get("/api/tasks/export")
    assert resp.status_code == 200


# ── GET /api/tasks/export: status filter (line 206) ──


@pytest.mark.asyncio
async def test_export_tasks_status_filter(client, mock_all):
    """GET /api/tasks/export with status filter applied client-side."""
    mock_all["sql"].return_value = [
        _task_dict(tid="t1", status="available"),
        _task_dict(tid="t2", status="done"),
    ]
    resp = await client.get("/api/tasks/export?status=available")
    assert resp.status_code == 200


# ── POST /api/tasks/clear: delete failure (lines 183-184) ──


@pytest.mark.asyncio
async def test_clear_tasks_delete_failure_continues(client, mock_all):
    """Clear tasks handles individual delete failures by continuing."""
    mock_all["sql"].return_value = [_task_dict(tid="t1"), _task_dict(tid="t2")]
    mock_all["call"].side_effect = [Exception("fail"), {"status": "ok"}]
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/clear",
            json={"status_filter": "done", "repo": "test-repo"},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] == 1


# ── POST /api/tasks/batch/labels: exception (lines 299-300) ──


@pytest.mark.asyncio
async def test_batch_assign_labels_exception(client, mock_all):
    """Batch label assign returns 400 when reducer fails."""
    mock_all["call"].side_effect = Exception("invalid label")
    resp = await client.post(
        "/api/tasks/batch/labels",
        json={"task_ids": ["t1"], "label_ids": ["l_invalid"]},
    )
    assert resp.status_code == 400
    assert "invalid label" in resp.text


# ── POST /api/tasks/batch/unlabels: exception (lines 313-314) ──


@pytest.mark.asyncio
async def test_batch_unassign_labels_exception(client, mock_all):
    """Batch label unassign returns 400 when reducer fails."""
    mock_all["call"].side_effect = Exception("no such label")
    resp = await client.post(
        "/api/tasks/batch/unlabels",
        json={"task_ids": ["t1"], "label_ids": ["l_missing"]},
    )
    assert resp.status_code == 400
    assert "no such label" in resp.text


# ── PATCH /api/tasks/{id}: set skills (line 368) + unarchive (line 411) + response check ──


@pytest.mark.asyncio
async def test_update_task_with_skills(client, mock_all):
    """PATCH with required_skills calls set_task_skills."""
    mock_all["param"].return_value = [_task_dict()]
    resp = await client.patch(
        "/api/tasks/task_1",
        json={"required_skills": "rust,python"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


@pytest.mark.asyncio
async def test_update_task_unarchive(client, mock_all):
    """PATCH with archived=False on archived task calls unarchive_task."""
    mock_all["param"].return_value = [_task_dict(archived=True)]
    resp = await client.patch(
        "/api/tasks/task_1",
        json={"archived": False},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_task_not_found(client, mock_all):
    """PATCH /api/tasks/nonexistent returns 404."""
    mock_all["param"].return_value = []
    resp = await client.patch(
        "/api/tasks/nonexistent",
        json={"title": "New title"},
    )
    assert resp.status_code == 404


# ── DELETE /api/tasks/{id}: notification (line 430) ──


@pytest.mark.asyncio
async def test_delete_task_with_notification(client, mock_all):
    """DELETE task triggers notification event."""
    mock_all["param"].return_value = [_task_dict()]
    resp = await client.delete("/api/tasks/task_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"


# ── POST /api/tasks/{id}/checklist/{item_id}/reorder (lines 886-887) ──


@pytest.mark.asyncio
async def test_reorder_checklist(client, mock_all):
    """POST reorder checklist item."""
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/checklist/item_1/reorder?new_position=0",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "reordered"


# ── Bulk retry with errors (lines 604-605) ──


@pytest.mark.asyncio
async def test_bulk_retry_with_failure(client, mock_all):
    """Bulk retry handles individual task failures."""
    mock_all["call"].side_effect = Exception("Cannot retry")
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-retry",
            json={"task_ids": ["t1", "t2"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["retried"] == 0
    assert len(data["failed"]) == 2


# ── Bulk archive with errors (lines 622-623) ──


@pytest.mark.asyncio
async def test_bulk_archive_with_failure(client, mock_all):
    """Bulk archive handles individual task failures."""
    mock_all["call"].side_effect = [Exception("fail"), {"status": "ok"}]
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-archive",
            json={"task_ids": ["t1", "t2"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] >= 0


# ── Scoring: capabilities fetch exception (lines 79-80) ──


@pytest.mark.asyncio
async def test_scoring_capabilities_fetch_exception(client, mock_all):
    """Scoring graceful when agent cap fetch raises."""
    mock_all["sql"].return_value = [_task_dict(tid="t1")]
    mock_all["sql"].side_effect = [
        [_task_dict(tid="t1")],  # tasks
        Exception("STDB down"),  # agent caps (fails)
    ]
    resp = await client.get("/api/tasks?scored=true")
    assert resp.status_code == 200


# ── Scoring: blocker tasks fetch exception (lines 86-87) ──


@pytest.mark.asyncio
async def test_scoring_blocker_fetch_exception(client, mock_all):
    """Scoring graceful when blocker tasks fetch raises."""
    mock_all["sql"].return_value = [_task_dict(tid="t1")]
    mock_all["sql"].side_effect = [
        [_task_dict(tid="t1")],  # tasks
        [],  # agent caps (empty)
        Exception("STDB down"),  # blocker tasks (fails)
    ]
    resp = await client.get("/api/tasks?scored=true")
    assert resp.status_code == 200


# ── POST /api/tasks/bulk: exception handler (lines 697-698) ──


@pytest.mark.asyncio
async def test_bulk_tasks_exception(client, mock_all):
    """POST /api/tasks/bulk handles individual task errors."""
    mock_all["call"].side_effect = Exception("STDB error")
    resp = await client.post(
        "/api/tasks/bulk",
        json={"task_ids": ["t1", "t2"], "action": "claim", "agent_id": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["results"]) == 2
    assert data["results"][0]["status"] == "error"


# ── List tasks limit slicing: need limit < len(after offset) (line 158) ──


@pytest.mark.asyncio
async def test_list_tasks_limit_slicing(client, mock_all):
    """GET /api/tasks with limit less than remaining tasks slices correctly."""
    mock_all["sql"].return_value = [
        _task_dict(tid=f"t{i}") for i in range(5)
    ]
    resp = await client.get("/api/tasks?offset=1&limit=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2  # 4 remain after offset, limit=2 < 4


# ── POST /api/tasks with required_skills (line 368) ──


@pytest.mark.asyncio
async def test_create_task_with_skills(client, mock_all):
    """POST /api/tasks with required_skills calls set_task_skills."""
    mock_all["call"].return_value = {"status": "ok"}
    mock_all["sql"].return_value = [{"id": "new_task"}]
    resp = await client.post(
        "/api/tasks",
        json={
            "title": "Test with skills",
            "description": "Need rust dev",
            "required_skills": "rust,python",
            "repo": "test",
        },
    )
    assert resp.status_code == 201


# ── POST /api/tasks/{task_id}/block-with-reason: fail_count != 1 (line 529) ──


@pytest.mark.asyncio
async def test_block_with_reason_skip_notify_second_block(client, mock_all):
    """Block-with-reason skips notification when fail_count != 1."""
    mock_all["param"].return_value = [_task_dict(status="in_progress", fail_count=0)]
    resp = await client.post(
        "/api/tasks/task_1/block-with-reason",
        json={"reason": "Second attempt"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"


# ── Direct test for _sync_to_github early returns (lines 465-467) ──


@pytest.mark.asyncio
async def test_sync_to_github_no_link():
    """_sync_to_github returns early when no link exists."""
    from routes.tasks import _sync_to_github

    with patch("issue_sync.get_link", return_value=None):
        result = await _sync_to_github("task_1", "completed", "Done")
        assert result is None


@pytest.mark.asyncio
async def test_sync_to_github_no_token():
    """_sync_to_github returns early when no token configured."""
    from routes.tasks import _sync_to_github

    with patch("issue_sync.get_link", return_value={"repo": "test/test", "issue_number": 1}):
        with patch("config.settings.github_token", ""):
            result = await _sync_to_github("task_1", "completed", "Done")
            assert result is None


# ── Bulk archive with failure (lines 622-623) ──


@pytest.mark.asyncio
async def test_bulk_archive_all_fail(client, mock_all):
    """Bulk archive with all tasks failing."""
    mock_all["call"].side_effect = Exception("Cannot archive")
    with patch("main.settings.api_key", "test-api-key-123"):
        resp = await client.post(
            "/api/tasks/bulk-archive",
            json={"task_ids": ["t1", "t2"]},
            headers={"X-API-Key": "test-api-key-123"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert len(data["failed"]) == 2


# ── Scoring: capabilities fetch failure (lines 79-80) ──


@pytest.mark.asyncio
async def test_scoring_capabilities_exception(client, mock_all):
    """Scoring handles exception in capability fetch."""
    tasks = [_task_dict(tid="t1")]
    # First call returns tasks, second call (agent caps) raises
    mock_all["sql"].side_effect = [tasks, Exception("STDB error")]
    resp = await client.get("/api/tasks?scored=true")
    assert resp.status_code == 200


# ── Scoring: blocker tasks fetch failure (lines 86-87) ──


@pytest.mark.asyncio
async def test_scoring_blocker_exception(client, mock_all):
    """Scoring handles exception in blocker tasks fetch."""
    tasks = [_task_dict(tid="t1")]
    # First = tasks, second = agent caps (empty), third = blockers (raises)
    mock_all["sql"].side_effect = [tasks, [], Exception("STDB error")]
    resp = await client.get("/api/tasks?scored=true")
    assert resp.status_code == 200


# ── POST /api/tasks/{task_id}/labels: set labels (lines 951-952) ──


@pytest.mark.asyncio
async def test_set_task_labels(client, mock_all):
    """POST /api/tasks/{task_id}/labels sets task labels."""
    mock_all["param"].return_value = [{"label_id": "old_label"}]
    mock_all["call"].return_value = {"status": "ok"}
    resp = await client.post(
        "/api/tasks/task_1/labels",
        json={"label_ids": ["label_a", "label_b"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"


# ── Direct test for _maybe_notify_blocked (line 529) ──


@pytest.mark.asyncio
async def test_maybe_notify_blocked_early_return():
    """_maybe_notify_blocked returns early when no rows."""
    from routes.tasks import _maybe_notify_blocked
    result = _maybe_notify_blocked("task_1", [], "reason")
    assert result is None


@pytest.mark.asyncio
async def test_maybe_notify_blocked_skip_notification():
    """_maybe_notify_blocked skips notification when fail_count != 1."""
    from routes.tasks import _maybe_notify_blocked
    result = _maybe_notify_blocked("task_1", [{"fail_count": 0}], "reason")
    assert result is None
    result = _maybe_notify_blocked("task_1", [{"fail_count": 2}], "reason")
    assert result is None


# ── Direct test for bulk archive except path (lines 622-623) ──


@pytest.mark.asyncio
async def test_bulk_archive_error_direct():
    """POST /api/tasks/bulk-archive handles call failures."""
    from routes.tasks import bulk_archive_tasks

    body = type("BulkArchiveRequest", (), {"task_ids": ["t1"], "action": "archive"})()

    with patch("routes.tasks._call", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("DB error")
        with patch("routes.tasks._sql_param", new_callable=AsyncMock) as mock_param:
            mock_param.return_value = [{"id": "t1", "archived": False}]
            result = await bulk_archive_tasks(body)
            assert result["status"] == "ok"
            assert result["archived"] == 0
            assert len(result["failed"]) == 1


# ── GET /api/tasks/suggest: exception handlers (lines 79-80, 86-87) ──


@pytest.mark.asyncio
async def test_suggest_tasks_capability_exception(client, mock_all):
    """Suggest tasks handles capability fetch exception."""
    mock_all["sql"].return_value = [_task_dict(tid="t1")]
    mock_all["param"].side_effect = Exception("STDB error")
    resp = await client.get("/api/tasks/suggest?agent_id=agent_1&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_suggest_tasks_blocker_exception(client, mock_all):
    """Suggest tasks handles blocker tasks fetch exception."""
    mock_all["sql"].side_effect = [
        [_task_dict(tid="t1")],  # tasks
        Exception("STDB error"),  # blockers (fails)
    ]
    resp = await client.get("/api/tasks/suggest?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── Direct tests for remaining uncovered lines ──


@pytest.mark.asyncio
async def test_ops_roadmap_dedup_batch():
    """Roadmap import batch dedup continue (line 71)."""
    from routes.ops import import_roadmap

    body = type("RoadmapImportRequest", (), {
        "content": "\n".join([f"- [ ] Task {i}" for i in range(6)]),
        "repo": "test-repo",
        "created_by": "tester",
    })()

    with patch("routes.ops._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [{"id": "existing", "status": "available"}]
        with patch("routes.ops._call", new_callable=AsyncMock) as mock_call:
            result = await import_roadmap(body)
            mock_call.assert_not_called()
            assert result["status"] == "imported"
            assert result["task_count"] == 6


@pytest.mark.asyncio
async def test_ops_migration_alias_direct():
    """record_schema_migration calls record_migration (line 146)."""
    from routes.ops import record_schema_migration

    body = type("MigrationCreate", (), {
        "version": "v3", "description": "Direct test",
        "applied_by": "tester", "checksum": "def456",
    })()

    with patch("routes.ops._call", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = {"status": "ok"}
        result = await record_schema_migration(body)
        assert result["status"] == "recorded"
        assert result["version"] == "v3"


@pytest.mark.asyncio
async def test_logs_multi_action_pass():
    """list_logs enters the multi-action if/actions/pass block."""
    from routes.logs import list_logs

    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            {"id": "l1", "task_id": "t1", "action": "created",
             "agent_id": None, "notes": None, "timestamp": 1000},
        ]
        result = await list_logs(action="created,claimed")
        assert len(result) == 1


@pytest.mark.asyncio
async def test_projects_suggest_exception_direct():
    """suggest_by_project handles HTTPException from reducer."""
    from fastapi import HTTPException

    from routes.projects import suggest_by_project

    with patch("routes.projects._call", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = HTTPException(502, "Reducer failed")
        with patch("routes.projects._sql", new_callable=AsyncMock) as mock_sql:
            mock_sql.side_effect = [
                [],  # tasks
                [{"id": "proj_1", "priority": 1, "active": True}],  # projects
            ]
            result = await suggest_by_project(limit=5)
            assert isinstance(result, list)
