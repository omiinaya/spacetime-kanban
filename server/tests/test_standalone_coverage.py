"""Standalone targeted coverage tests — direct function calls without fixtures.

Tests specific error paths in ops.py and dispatcher.py that the fixture-based
tests are not covering due to shared-mock interactions.
"""
from unittest.mock import AsyncMock, patch

import pytest

# ── routes/ops.py line 71: dedup continue in roadmap import ──


@pytest.mark.asyncio
async def test_ops_roadmap_import_dedup():
    """Roadmap import dedup continues when existing task exists with same title."""
    from routes.ops import import_roadmap

    body = type("RoadmapImportRequest", (), {
        "content": "- [ ] TODO: fix this\n",
        "repo": "test-repo",
        "created_by": "tester",
    })()

    with patch("routes.ops._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [{"id": "existing", "status": "available"}]
        with patch("routes.ops._sql", new_callable=AsyncMock) as mock_sql:
            mock_sql.return_value = []
            with patch("routes.ops._call", new_callable=AsyncMock) as mock_call:
                result = await import_roadmap(body)
                # _call should NOT have been called since the task was dedup'd
                mock_call.assert_not_called()
                assert result["status"] == "imported"
                assert result["task_count"] == 1


# ── routes/ops.py line 146: schema migration alias ──


@pytest.mark.asyncio
async def test_ops_schema_migration_alias():
    """POST /api/schema-migrations alias calls record_migration."""
    from routes.ops import record_schema_migration

    body = type("MigrationCreate", (), {
        "version": "v2", "description": "Test",
        "applied_by": "tester", "checksum": "abc",
    })()

    with patch("routes.ops._call", new_callable=AsyncMock) as mock_call, \
         patch("routes.ops._sql", new_callable=AsyncMock):
        mock_call.return_value = {"status": "ok"}
        result = await record_schema_migration(body)
        assert result["status"] == "recorded"
        assert result["version"] == "v2"


# ── routes/projects.py lines 115-117: suggest_by_project except ──


@pytest.mark.asyncio
async def test_projects_suggest_exception():
    """suggest_by_project handles HTTPException from reducer."""
    from routes.projects import suggest_by_project

    with patch("routes.projects._call", new_callable=AsyncMock) as mock_call:
        from fastapi import HTTPException
        mock_call.side_effect = HTTPException(502, "Reducer failed")
        with patch("routes.projects._sql", new_callable=AsyncMock) as mock_sql:
            mock_sql.side_effect = [
                [],  # tasks
                [{"id": "proj_1", "priority": 1, "active": True}],  # projects
            ]
            result = await suggest_by_project(limit=5)
            assert isinstance(result, list)


# ── routes/dispatcher.py line 59: set_dispatcher_state exception ──


@pytest.mark.asyncio
async def test_dispatcher_set_state_exception():
    """set_dispatcher_state raises 502 on reducer failure."""
    from fastapi import HTTPException

    from routes.dispatcher import set_dispatcher_state

    body = type("DispatcherStateUpdate", (), {"key": "k", "value": "v"})()

    with patch("routes.dispatcher._call", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("Reducer crashed")
        with pytest.raises(HTTPException) as exc_info:
            await set_dispatcher_state(body)
        assert exc_info.value.status_code == 502


# ── routes/dispatcher.py: delete_dispatcher_state exception (line 59 pattern) ──


@pytest.mark.asyncio
async def test_dispatcher_delete_state_exception():
    """delete_dispatcher_state raises 502 on non-key-not-found error."""
    from fastapi import HTTPException

    from routes.dispatcher import delete_dispatcher_state

    with patch("routes.dispatcher._call", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = Exception("STDB unreachable")
        with pytest.raises(HTTPException) as exc_info:
            await delete_dispatcher_state("some_key")
        assert exc_info.value.status_code == 502


# ── routes/projects.py: create_project empty id raises 400 ──


@pytest.mark.asyncio
async def test_projects_create_empty_id():
    """create_project raises 400 when id is empty."""
    from fastapi import HTTPException

    from routes.projects import create_project

    body = type("ProjectCreate", (), {
        "id": "", "name": "", "description": "",
        "color": "#fff", "priority": 2, "active": True,
    })()

    with patch("routes.projects._call", new_callable=AsyncMock), \
         patch("routes.projects._sql", new_callable=AsyncMock), \
         patch("routes.projects._sql_param", new_callable=AsyncMock), \
         pytest.raises(HTTPException) as exc_info:
        await create_project(body)
        assert exc_info.value.status_code == 400


# ── routes/ops.py: calendar and cross-project endpoints ──


@pytest.mark.asyncio
async def test_ops_calendar():
    """calendar_tasks returns tasks with due_by dates."""
    from routes.ops import calendar_tasks

    with patch("routes.ops._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            {"id": "t1", "title": "T", "priority": 0, "status": "available",
             "repo": "r", "created_at": 1000, "updated_at": 1000,
             "due_by": 2000, "description": "", "assigned_to": None,
             "branch": None, "roadmap_item": "", "created_by": "",
             "depends_on": None, "required_skills": None, "score": 0,
             "position": None, "fail_count": 0, "max_attempts": 3,
             "fail_reason": None, "subtask_of": None, "subtasks": None,
             "sprint": None, "archived": False, "estimated_hours": None,
             "spent_hours": None},
        ]
        result = await calendar_tasks()
        assert len(result) == 1
        assert result[0].due_by == 2000


# ── routes/health.py lines 53-54: except ImportError ──


@pytest.mark.asyncio
async def test_health_no_scheduler():
    """system_health returns defaults when scheduler module unavailable."""
    # Mock sys.modules to remove scheduler symbols
    import sys

    from routes.health import system_health
    fake_scheduler = type("scheduler", (), {})()
    with patch.dict(sys.modules, {"scheduler": fake_scheduler}):
        result = await system_health()
        assert result["status"] == "ok"
        assert result["workers"]["active"] == 0


# ── routes/logs.py lines 35-36: multi-action filter pass ──


@pytest.mark.asyncio
async def test_logs_multi_action_filter():
    """list_logs handles multi-action filter (comma-separated) via Python-side pass."""
    from routes.logs import list_logs

    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            {"id": "l1", "task_id": "t1", "action": "created",
             "agent_id": None, "notes": None, "timestamp": 1000},
        ]
        result = await list_logs(action="created,claimed")
        assert len(result) == 1  # Python filter passes created
