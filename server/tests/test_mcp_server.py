"""Tests for server/mcp_server.py.

The MCP server wraps the kanban REST API as MCP tools.
We mock urllib.request to test the HTTP wrappers and tool functions
without needing a running kanban server.
"""

import json
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

import pytest

from mcp_server import (
    KanbanAPIError,
    api_delete,
    api_get,
    api_patch,
    api_post,
    api_put,
    app,
    kanban_add_checklist_item,
    kanban_add_comment,
    kanban_add_log,
    kanban_add_project,
    kanban_block,
    kanban_block_with_reason,
    kanban_claim,
    kanban_complete,
    kanban_create_task,
    kanban_delete_comment,
    kanban_delete_project,
    kanban_delete_task,
    kanban_get_logs,
    kanban_get_task,
    kanban_heartbeat,
    kanban_issue_create,
    kanban_issue_link,
    kanban_issue_list,
    kanban_issue_status,
    kanban_list_agents,
    kanban_list_checklist,
    kanban_list_comments,
    kanban_list_projects,
    kanban_list_tasks,
    kanban_register_agent,
    kanban_remove_checklist_item,
    kanban_set_capabilities,
    kanban_set_dependency,
    kanban_set_skills,
    kanban_split_task,
    kanban_suggest,
    kanban_suggest_by_project,
    kanban_toggle_checklist_item,
    kanban_unclaim,
    kanban_update_project,
    kanban_update_task,
    main,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _mock_response(data, status=200):
    """Create a mock urllib.response object."""
    encoded = json.dumps(data).encode()
    resp = MagicMock()
    resp.read.return_value = encoded
    resp.status = status
    resp.__enter__.return_value = resp
    return resp


def _mock_http_error(status_code, body="Error"):
    """Create an HTTPError that can be raised."""
    err = HTTPError(
        url="http://test",
        code=status_code,
        msg="Error",
        hdrs={},
        fp=None,
    )
    # mock the read() method on HTTPError
    err.read = Mock(return_value=body.encode())
    return err


# ── KanbanAPIError ────────────────────────────────────────────────────


class TestKanbanAPIError:
    def test_default_status_code(self):
        err = KanbanAPIError("test error")
        assert str(err) == "test error"
        assert err.status_code == 0

    def test_with_status_code(self):
        err = KanbanAPIError("not found", status_code=404)
        assert str(err) == "not found"
        assert err.status_code == 404


# ── HTTP Wrappers ──────────────────────────────────────────────────────


class TestAPIGet:
    def test_success_returns_list(self):
        with patch("mcp_server.urllib.request.urlopen", return_value=_mock_response([1, 2, 3])):
            result = api_get("/api/tasks")
            assert result == [1, 2, 3]

    def test_success_returns_dict(self):
        with patch(
            "mcp_server.urllib.request.urlopen", return_value=_mock_response({"status": "ok"})
        ):
            result = api_get("/api/health")
            assert result == {"status": "ok"}

    def test_http_error_raises_kanban_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=_mock_http_error(404, "Not found")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_get("/api/tasks/nonexistent")
            assert exc.value.status_code == 404

    def test_connection_error_raises_kanban_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=ConnectionError("Connection refused")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_get("/api/tasks")
            assert "Connection refused" in str(exc.value)


class TestAPIPost:
    def test_success_with_body(self):
        mock_resp = _mock_response({"status": "created", "id": "task_1"})
        with patch("mcp_server.urllib.request.urlopen", return_value=mock_resp):
            result = api_post("/api/tasks", {"title": "Test"})
            assert result["status"] == "created"

    def test_success_empty_body(self):
        empty_resp = MagicMock()
        empty_resp.read.return_value = b""
        empty_resp.__enter__.return_value = empty_resp
        with patch("mcp_server.urllib.request.urlopen", return_value=empty_resp):
            result = api_post("/api/tasks/claim", {"agent_id": "test"})
            assert result == {"status": "ok"}

    def test_http_error_raises_kanban_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=_mock_http_error(409, "Conflict")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_post("/api/tasks/task_1/claim", {"agent_id": "test"})
            assert exc.value.status_code == 409

    def test_generic_error(self):
        with (
            patch("mcp_server.urllib.request.urlopen", side_effect=TimeoutError("timed out")),
            pytest.raises(KanbanAPIError),
        ):
            api_post("/api/tasks", {"title": "Test"})


class TestAPIPatch:
    def test_success(self):
        mock_resp = _mock_response({"status": "updated"})
        with patch("mcp_server.urllib.request.urlopen", return_value=mock_resp):
            result = api_patch("/api/tasks/task_1", {"title": "Updated"})
            assert result["status"] == "updated"

    def test_http_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=_mock_http_error(404, "Not found")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_patch("/api/tasks/task_1", {"title": "Updated"})
            assert exc.value.status_code == 404

    def test_generic_error(self):
        """Cover lines 76-77: generic exception handler in api_patch."""
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=ConnectionError("connection lost")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_patch("/api/tasks/task_1", {"title": "Updated"})
            assert "connection lost" in str(exc.value)


class TestAPIPut:
    def test_success(self):
        mock_resp = _mock_response({"status": "updated"})
        with patch("mcp_server.urllib.request.urlopen", return_value=mock_resp):
            result = api_put("/api/agents/agent-1/capabilities", {"capabilities": "python"})
            assert result["status"] == "updated"

    def test_http_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=_mock_http_error(500, "Server error")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_put("/api/agents/agent-1/capabilities", {"capabilities": "python"})
            assert exc.value.status_code == 500

    def test_generic_error(self):
        """Cover lines 92-93: generic exception handler in api_put."""
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=ConnectionError("connection lost")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_put("/api/agents/agent-1/capabilities", {"capabilities": "python"})
            assert "connection lost" in str(exc.value)


class TestAPIDelete:
    def test_success(self):
        mock_resp = _mock_response({"status": "deleted"})
        with patch("mcp_server.urllib.request.urlopen", return_value=mock_resp):
            result = api_delete("/api/tasks/task_1")
            assert result["status"] == "deleted"

    def test_http_error(self):
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=_mock_http_error(404, "Not found")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_delete("/api/tasks/nonexistent")
            assert exc.value.status_code == 404

    def test_generic_error(self):
        """Cover lines 106-107: generic exception handler in api_delete."""
        with patch(
            "mcp_server.urllib.request.urlopen", side_effect=ConnectionError("connection lost")
        ):
            with pytest.raises(KanbanAPIError) as exc:
                api_delete("/api/tasks/task_1")
            assert "connection lost" in str(exc.value)


# ── Tool Functions ─────────────────────────────────────────────────────


class TestListTasks:
    @pytest.mark.asyncio
    async def test_no_filters(self):
        with patch("mcp_server.api_get", return_value=[{"id": "t1"}, {"id": "t2"}]):
            result = json.loads(await kanban_list_tasks())
            assert result["count"] == 2
            assert len(result["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_with_status_filter(self):
        with patch("mcp_server.api_get", return_value=[{"id": "t1", "status": "available"}]):
            result = json.loads(await kanban_list_tasks(status="available"))
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_empty_response(self):
        with patch("mcp_server.api_get", return_value=[]):
            result = json.loads(await kanban_list_tasks())
            assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_with_repo_filter(self):
        """Cover line 121: repo parameter in kanban_list_tasks."""
        with patch("mcp_server.api_get", return_value=[{"id": "t1", "repo": "my-repo"}]):
            result = json.loads(await kanban_list_tasks(status="available", repo="my-repo"))
            assert result["count"] == 1
            assert result["tasks"][0]["repo"] == "my-repo"


class TestGetTask:
    @pytest.mark.asyncio
    async def test_with_downstream_blockers(self):
        """Cover lines 129-137: downstream blocker detection."""
        with (
            patch("mcp_server.api_get") as mock_get,
        ):

            def side_effect(path, *args, **kwargs):
                if "logs" in path:
                    return [{"action": "created", "agent_id": "hermes"}]
                if path == "/api/tasks":
                    return [
                        {"id": "child_1", "depends_on": "task_main", "title": "Child 1"},
                        {"id": "child_2", "depends_on": "task_main", "title": "Child 2"},
                        {"id": "unrelated", "depends_on": "other", "title": "Unrelated"},
                    ]
                return {"id": "task_main", "title": "Main task"}

            mock_get.side_effect = side_effect
            result = json.loads(await kanban_get_task(task_id="task_main"))
            assert result["task"]["id"] == "task_main"
            assert result["blocker_count"] == 2
            assert len(result["downstream_blockers"]) == 2
            assert result["downstream_blockers"][0]["id"] == "child_1"
            assert result["downstream_blockers"][1]["id"] == "child_2"
            assert result["logs"] == [{"action": "created", "agent_id": "hermes"}]

    @pytest.mark.asyncio
    async def test_no_downstream_blockers(self):
        """Cover lines 129-137 with no downstream tasks."""
        with (
            patch("mcp_server.api_get") as mock_get,
        ):

            def side_effect(path, *args, **kwargs):
                if "logs" in path:
                    return []
                if path == "/api/tasks":
                    return [
                        {"id": "other", "depends_on": "different", "title": "Other"},
                    ]
                return {"id": "task_main", "title": "Main task"}

            mock_get.side_effect = side_effect
            result = json.loads(await kanban_get_task(task_id="task_main"))
            assert result["blocker_count"] == 0
            assert result["downstream_blockers"] == []

    @pytest.mark.asyncio
    async def test_logs_not_list_returns_empty(self):
        """Cover edge case where logs API returns non-list."""
        with (
            patch("mcp_server.api_get") as mock_get,
        ):

            def side_effect(path, *args, **kwargs):
                if "logs" in path:
                    return {"error": "not found"}
                if path == "/api/tasks":
                    return []
                return {"id": "task_main"}

            mock_get.side_effect = side_effect
            result = json.loads(await kanban_get_task(task_id="task_main"))
            assert result["logs"] == []


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_basic_creation(self):
        with (
            patch("mcp_server.api_post", return_value={"status": "created", "id": "task_1"}),
            patch("mcp_server.api_get", return_value=[{"id": "task_1", "created_at": 1000}]),
        ):
            result = json.loads(await kanban_create_task(title="Test task", repo="test"))
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_with_skills(self):
        with (
            patch(
                "mcp_server.api_post", return_value={"status": "created", "id": "task_1"}
            ) as mock_post,
            patch("mcp_server.api_get", return_value=[{"id": "task_1", "created_at": 1000}]),
        ):
            result = json.loads(
                await kanban_create_task(title="Test task", repo="test", required_skills="python")
            )
            assert result["status"] == "created"
            assert result["skills_set"] == "python"
            # Should have called skills POST
            skills_calls = [c for c in mock_post.call_args_list if "skills" in str(c)]
            assert len(skills_calls) >= 1

    @pytest.mark.asyncio
    async def test_with_skills_empty_tasks_list(self):
        """Cover edge case: tasks list is empty when setting skills."""
        with (
            patch("mcp_server.api_post", return_value={"status": "created", "id": "task_1"}),
            patch("mcp_server.api_get", return_value=[]),
        ):
            result = json.loads(
                await kanban_create_task(title="Test task", repo="test", required_skills="python")
            )
            assert result["status"] == "created"
            # Skills path shouldn't crash on empty list
            assert "skills_set" not in result


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_update_title(self):
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(await kanban_update_task(task_id="task_1", title="New title"))
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_no_fields_raises_error(self):
        with pytest.raises(KanbanAPIError):
            await kanban_update_task(task_id="task_1")

    @pytest.mark.asyncio
    async def test_update_with_branch(self):
        """Cover lines 188, 190, 192: branch field handling."""
        with patch(
            "mcp_server.api_patch", return_value={"status": "updated", "branch": "feature/test"}
        ):
            result = json.loads(await kanban_update_task(task_id="task_1", branch="feature/test"))
            assert result["status"] == "updated"
            assert result["branch"] == "feature/test"

    @pytest.mark.asyncio
    async def test_update_all_fields(self):
        """Cover all body-building branches in kanban_update_task."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(
                await kanban_update_task(
                    task_id="task_1",
                    title="New title",
                    description="New description",
                    priority=1,
                    branch="feature/test",
                )
            )
            assert result["status"] == "updated"


class TestClaim:
    @pytest.mark.asyncio
    async def test_claim_task(self):
        with patch("mcp_server.api_post", return_value={"status": "claimed", "task_id": "task_1"}):
            result = json.loads(await kanban_claim(task_id="task_1", agent_id="test-agent"))
            assert result["status"] == "claimed"


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_task(self):
        with patch("mcp_server.api_post", return_value={"status": "completed"}):
            result = json.loads(await kanban_complete(task_id="task_1", notes="Done!"))
            assert result["status"] == "completed"


class TestBlock:
    @pytest.mark.asyncio
    async def test_block_task(self):
        """Cover line 210: kanban_block."""
        with patch("mcp_server.api_post", return_value={"status": "blocked"}):
            result = json.loads(await kanban_block(task_id="task_1", reason="Blocked on deps"))
            assert result["status"] == "blocked"

    @pytest.mark.asyncio
    async def test_block_task_default_reason(self):
        """Cover line 210 with default reason."""
        with patch("mcp_server.api_post", return_value={"status": "blocked"}):
            result = json.loads(await kanban_block(task_id="task_1"))
            assert result["status"] == "blocked"


class TestBlockWithReason:
    @pytest.mark.asyncio
    async def test_block_with_reason(self):
        """Cover line 215: kanban_block_with_reason."""
        with patch(
            "mcp_server.api_post", return_value={"status": "blocked", "fail_reason": "API limit"}
        ):
            result = json.loads(
                await kanban_block_with_reason(task_id="task_1", reason="API limit")
            )
            assert result["status"] == "blocked"
            assert result["fail_reason"] == "API limit"


class TestSplitTask:
    @pytest.mark.asyncio
    async def test_split_with_titles(self):
        with patch("mcp_server.api_post", return_value={"status": "split", "child_count": 2}):
            result = json.loads(await kanban_split_task(task_id="task_1", child_titles=["A", "B"]))
            assert result["status"] == "split"

    @pytest.mark.asyncio
    async def test_split_empty_titles_raises_error(self):
        with pytest.raises(KanbanAPIError):
            await kanban_split_task(task_id="task_1", child_titles=[])


class TestUnclaim:
    @pytest.mark.asyncio
    async def test_unclaim_task(self):
        """Cover line 227: kanban_unclaim."""
        with patch("mcp_server.api_post", return_value={"status": "available"}):
            result = json.loads(await kanban_unclaim(task_id="task_1"))
            assert result["status"] == "available"


class TestDeleteTask:
    @pytest.mark.asyncio
    async def test_delete_task(self):
        """Cover line 232: kanban_delete_task."""
        with patch("mcp_server.api_delete", return_value={"status": "deleted"}):
            result = json.loads(await kanban_delete_task(task_id="task_1"))
            assert result["status"] == "deleted"


class TestSetDependency:
    @pytest.mark.asyncio
    async def test_set_dependency(self):
        """Cover line 237: kanban_set_dependency."""
        with patch(
            "mcp_server.api_post", return_value={"status": "updated", "depends_on": "task_0"}
        ):
            result = json.loads(await kanban_set_dependency(task_id="task_1", depends_on="task_0"))
            assert result["status"] == "updated"
            assert result["depends_on"] == "task_0"

    @pytest.mark.asyncio
    async def test_clear_dependency(self):
        """Cover line 237 with empty depends_on."""
        with patch("mcp_server.api_post", return_value={"status": "updated", "depends_on": ""}):
            result = json.loads(await kanban_set_dependency(task_id="task_1", depends_on=""))
            assert result["status"] == "updated"
            assert result["depends_on"] == ""


class TestSetSkills:
    @pytest.mark.asyncio
    async def test_set_skills(self):
        """Cover line 242: kanban_set_skills."""
        with patch("mcp_server.api_post", return_value={"status": "updated"}):
            result = json.loads(await kanban_set_skills(task_id="task_1", skills="python,fastapi"))
            assert result["status"] == "updated"


class TestSuggest:
    @pytest.mark.asyncio
    async def test_suggest_default(self):
        """Cover lines 247-250: kanban_suggest with default params."""
        with patch("mcp_server.api_get", return_value=[{"id": "t1", "score": 0.95}]):
            result = json.loads(await kanban_suggest())
            assert len(result) == 1
            assert result[0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_suggest_with_agent(self):
        """Cover lines 247-250: kanban_suggest with agent_id."""
        with patch("mcp_server.api_get", return_value=[{"id": "t1", "score": 0.95}]):
            result = json.loads(await kanban_suggest(agent_id="hermes", limit=10))
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_suggest_with_limit(self):
        """Cover lines 247-250: kanban_suggest with custom limit."""
        with patch("mcp_server.api_get", return_value=[{"id": "t1"}, {"id": "t2"}]):
            result = json.loads(await kanban_suggest(limit=2))
            assert len(result) == 2


class TestListAgents:
    @pytest.mark.asyncio
    async def test_list_agents(self):
        """Cover lines 255-256: kanban_list_agents."""
        with patch("mcp_server.api_get", return_value=[{"id": "agent_1"}, {"id": "agent_2"}]):
            result = json.loads(await kanban_list_agents())
            assert result["count"] == 2
            assert len(result["agents"]) == 2

    @pytest.mark.asyncio
    async def test_list_agents_non_list(self):
        """Cover lines 255-256: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_list_agents())
            assert result["count"] == 0
            assert result["agents"] == []


class TestRegisterAgent:
    @pytest.mark.asyncio
    async def test_register_agent(self):
        """Cover line 271: kanban_register_agent."""
        with patch(
            "mcp_server.api_post", return_value={"status": "registered", "agent_id": "my-agent"}
        ):
            result = json.loads(
                await kanban_register_agent(
                    agent_id="my-agent",
                    host="localhost",
                    capabilities="python",
                    repo_focus="test-repo",
                )
            )
            assert result["status"] == "registered"
            assert result["agent_id"] == "my-agent"

    @pytest.mark.asyncio
    async def test_register_agent_minimal(self):
        """Cover line 271: minimal registration."""
        with patch("mcp_server.api_post", return_value={"status": "registered"}):
            result = json.loads(await kanban_register_agent(agent_id="my-agent"))
            assert result["status"] == "registered"


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat(self):
        """Cover line 290: kanban_heartbeat."""
        with patch("mcp_server.api_post", return_value={"status": "online"}):
            result = json.loads(
                await kanban_heartbeat(
                    agent_id="my-agent", status="online", current_task_id="task_1"
                )
            )
            assert result["status"] == "online"

    @pytest.mark.asyncio
    async def test_heartbeat_defaults(self):
        """Cover line 290: heartbeat with defaults."""
        with patch("mcp_server.api_post", return_value={"status": "online"}):
            result = json.loads(await kanban_heartbeat(agent_id="my-agent"))
            assert result["status"] == "online"


class TestSetCapabilities:
    @pytest.mark.asyncio
    async def test_set_capabilities(self):
        """Cover line 304: kanban_set_capabilities."""
        with patch("mcp_server.api_put", return_value={"status": "updated"}):
            result = json.loads(
                await kanban_set_capabilities(
                    agent_id="my-agent",
                    capabilities="python,go",
                    repo_focus="backend",
                )
            )
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_set_capabilities_no_repo_focus(self):
        """Cover line 304: capabilities without repo_focus."""
        with patch("mcp_server.api_put", return_value={"status": "updated"}):
            result = json.loads(
                await kanban_set_capabilities(agent_id="my-agent", capabilities="python")
            )
            assert result["status"] == "updated"


class TestListProjects:
    @pytest.mark.asyncio
    async def test_list_projects(self):
        """Cover lines 317-318: kanban_list_projects."""
        with patch("mcp_server.api_get", return_value=[{"id": "proj_1"}, {"id": "proj_2"}]):
            result = json.loads(await kanban_list_projects())
            assert result["count"] == 2
            assert len(result["projects"]) == 2

    @pytest.mark.asyncio
    async def test_list_projects_non_list(self):
        """Cover lines 317-318: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_list_projects())
            assert result["count"] == 0
            assert result["projects"] == []


class TestAddProject:
    @pytest.mark.asyncio
    async def test_add_project(self):
        """Cover line 335: kanban_add_project."""
        with patch("mcp_server.api_post", return_value={"status": "created", "id": "my-project"}):
            result = json.loads(
                await kanban_add_project(
                    id="my-project",
                    name="My Project",
                    description="A test project",
                    color="#ff0000",
                    priority=1,
                    active=True,
                )
            )
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_add_project_defaults(self):
        """Cover line 335: kanban_add_project with defaults."""
        with patch("mcp_server.api_post", return_value={"status": "created"}):
            result = json.loads(await kanban_add_project(id="my-project"))
            assert result["status"] == "created"


class TestUpdateProject:
    @pytest.mark.asyncio
    async def test_update_project_all_fields(self):
        """Cover lines 359-369: kanban_update_project body building."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(
                await kanban_update_project(
                    project_id="proj_1",
                    name="New Name",
                    description="New desc",
                    color="#00ff00",
                    priority=1,
                    active=False,
                )
            )
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_project_name_only(self):
        """Cover lines 359-369: name only."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(await kanban_update_project(project_id="proj_1", name="New Name"))
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_project_description_only(self):
        """Cover lines 359-369: description only."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(
                await kanban_update_project(project_id="proj_1", description="New desc")
            )
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_project_color_only(self):
        """Cover lines 359-369: color only."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(await kanban_update_project(project_id="proj_1", color="#0000ff"))
            assert result["status"] == "updated"

    @pytest.mark.asyncio
    async def test_update_project_defaults(self):
        """Cover lines 359-369: defaults (priority=3, active=True)."""
        with patch("mcp_server.api_patch", return_value={"status": "updated"}):
            result = json.loads(await kanban_update_project(project_id="proj_1"))
            assert result["status"] == "updated"


class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_delete_project(self):
        """Cover line 374: kanban_delete_project."""
        with patch("mcp_server.api_delete", return_value={"status": "deleted"}):
            result = json.loads(await kanban_delete_project(project_id="proj_1"))
            assert result["status"] == "deleted"


class TestSuggestByProject:
    @pytest.mark.asyncio
    async def test_suggest_by_project(self):
        """Cover line 379: kanban_suggest_by_project."""
        with patch("mcp_server.api_get", return_value=[{"id": "t1", "project": "proj_1"}]):
            result = json.loads(await kanban_suggest_by_project(limit=5))
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_suggest_by_project_default(self):
        """Cover line 379: default limit."""
        with patch("mcp_server.api_get", return_value=[]):
            result = json.loads(await kanban_suggest_by_project())
            assert result == []


class TestAddLog:
    @pytest.mark.asyncio
    async def test_add_log(self):
        """Cover line 389: kanban_add_log."""
        with patch("mcp_server.api_post", return_value={"status": "logged"}):
            result = json.loads(
                await kanban_add_log(
                    task_id="task_1", action="started", agent_id="hermes", notes="Working"
                )
            )
            assert result["status"] == "logged"

    @pytest.mark.asyncio
    async def test_add_log_defaults(self):
        """Cover line 389: kanban_add_log with defaults."""
        with patch("mcp_server.api_post", return_value={"status": "logged"}):
            result = json.loads(await kanban_add_log(task_id="task_1", action="completed"))
            assert result["status"] == "logged"


class TestGetLogs:
    @pytest.mark.asyncio
    async def test_get_logs(self):
        """Cover lines 404-405: kanban_get_logs."""
        with patch(
            "mcp_server.api_get", return_value=[{"action": "created"}, {"action": "claimed"}]
        ):
            result = json.loads(await kanban_get_logs(task_id="task_1"))
            assert result["count"] == 2
            assert len(result["logs"]) == 2
            assert result["task_id"] == "task_1"

    @pytest.mark.asyncio
    async def test_get_logs_non_list(self):
        """Cover lines 404-405: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_get_logs(task_id="task_1"))
            assert result["count"] == 0
            assert result["logs"] == []


class TestIssueLink:
    @pytest.mark.asyncio
    async def test_issue_link(self):
        """Cover line 416: kanban_issue_link."""
        with patch("mcp_server.api_post", return_value={"status": "linked"}):
            result = json.loads(
                await kanban_issue_link(task_id="task_1", repo="my-repo", issue_number=42)
            )
            assert result["status"] == "linked"


class TestIssueCreate:
    @pytest.mark.asyncio
    async def test_issue_create(self):
        """Cover line 432: kanban_issue_create."""
        with patch(
            "mcp_server.api_post", return_value={"status": "created", "issue_url": "http://..."}
        ):
            result = json.loads(
                await kanban_issue_create(
                    task_id="task_1", repo="my-repo", labels="bug", assignee="hermes"
                )
            )
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_issue_create_defaults(self):
        """Cover line 432: kanban_issue_create with defaults."""
        with patch("mcp_server.api_post", return_value={"status": "created"}):
            result = json.loads(await kanban_issue_create(task_id="task_1"))
            assert result["status"] == "created"


class TestIssueStatus:
    @pytest.mark.asyncio
    async def test_issue_status(self):
        """Cover line 447: kanban_issue_status."""
        with patch("mcp_server.api_get", return_value={"task_id": "task_1", "issue_number": 42}):
            result = json.loads(await kanban_issue_status(task_id="task_1"))
            assert result["issue_number"] == 42


class TestIssueList:
    @pytest.mark.asyncio
    async def test_issue_list(self):
        """Cover lines 452-454: kanban_issue_list."""
        with patch("mcp_server.api_get", return_value=[{"task_id": "t1"}, {"task_id": "t2"}]):
            result = json.loads(await kanban_issue_list())
            assert result["count"] == 2
            assert len(result["links"]) == 2

    @pytest.mark.asyncio
    async def test_issue_list_with_repo(self):
        """Cover lines 452-454: kanban_issue_list with repo filter."""
        with patch("mcp_server.api_get", return_value=[{"task_id": "t1"}]):
            result = json.loads(await kanban_issue_list(repo="my-repo"))
            assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_issue_list_non_list(self):
        """Cover lines 452-454: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_issue_list())
            assert result["count"] == 0
            assert result["links"] == []


class TestAddComment:
    @pytest.mark.asyncio
    async def test_add_comment(self):
        """Cover line 464: kanban_add_comment."""
        with patch("mcp_server.api_post", return_value={"status": "created"}):
            result = json.loads(
                await kanban_add_comment(
                    task_id="task_1", body="This is a comment", author="hermes"
                )
            )
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_add_comment_default_author(self):
        """Cover line 464: kanban_add_comment with default author."""
        with patch("mcp_server.api_post", return_value={"status": "created"}):
            result = json.loads(await kanban_add_comment(task_id="task_1", body="Comment text"))
            assert result["status"] == "created"


class TestListComments:
    @pytest.mark.asyncio
    async def test_list_comments(self):
        """Cover lines 477-478: kanban_list_comments."""
        with patch(
            "mcp_server.api_get", return_value=[{"body": "comment 1"}, {"body": "comment 2"}]
        ):
            result = json.loads(await kanban_list_comments(task_id="task_1"))
            assert result["count"] == 2
            assert len(result["comments"]) == 2
            assert result["task_id"] == "task_1"

    @pytest.mark.asyncio
    async def test_list_comments_non_list(self):
        """Cover lines 477-478: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_list_comments(task_id="task_1"))
            assert result["count"] == 0
            assert result["comments"] == []


class TestDeleteComment:
    @pytest.mark.asyncio
    async def test_delete_comment(self):
        """Cover line 489: kanban_delete_comment."""
        with patch("mcp_server.api_delete", return_value={"status": "deleted"}):
            result = json.loads(
                await kanban_delete_comment(task_id="task_1", comment_id="comment_1")
            )
            assert result["status"] == "deleted"


class TestAddChecklistItem:
    @pytest.mark.asyncio
    async def test_add_checklist_item(self):
        """Cover line 494: kanban_add_checklist_item."""
        with patch("mcp_server.api_post", return_value={"status": "created", "id": "item_1"}):
            result = json.loads(
                await kanban_add_checklist_item(task_id="task_1", text="Check this")
            )
            assert result["status"] == "created"

    @pytest.mark.asyncio
    async def test_add_checklist_item_defaults(self):
        """Cover line 494: with different text."""
        with patch("mcp_server.api_post", return_value={"status": "created"}):
            result = json.loads(
                await kanban_add_checklist_item(task_id="task_1", text="Do the thing")
            )
            assert result["status"] == "created"


class TestListChecklist:
    @pytest.mark.asyncio
    async def test_list_checklist(self):
        """Cover lines 499-501: kanban_list_checklist."""
        items = [
            {"id": "item_1", "text": "Task 1", "completed": False},
            {"id": "item_2", "text": "Task 2", "completed": True},
        ]
        with patch("mcp_server.api_get", return_value=items):
            result = json.loads(await kanban_list_checklist(task_id="task_1"))
            assert result["count"] == 2
            assert result["completed"] == 1
            assert result["remaining"] == 1
            assert result["task_id"] == "task_1"

    @pytest.mark.asyncio
    async def test_list_checklist_all_completed(self):
        """Cover lines 499-501: all completed."""
        items = [
            {"id": "item_1", "text": "Task 1", "completed": True},
            {"id": "item_2", "text": "Task 2", "completed": True},
        ]
        with patch("mcp_server.api_get", return_value=items):
            result = json.loads(await kanban_list_checklist(task_id="task_1"))
            assert result["completed"] == 2
            assert result["remaining"] == 0

    @pytest.mark.asyncio
    async def test_list_checklist_non_list(self):
        """Cover lines 499-501: non-list response."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_list_checklist(task_id="task_1"))
            assert result["count"] == 0
            assert result["completed"] == 0


class TestToggleChecklistItem:
    @pytest.mark.asyncio
    async def test_toggle_checklist_item(self):
        """Cover line 514: kanban_toggle_checklist_item."""
        with patch("mcp_server.api_post", return_value={"status": "toggled", "completed": True}):
            result = json.loads(
                await kanban_toggle_checklist_item(task_id="task_1", item_id="item_1")
            )
            assert result["status"] == "toggled"
            assert result["completed"] is True


class TestRemoveChecklistItem:
    @pytest.mark.asyncio
    async def test_remove_checklist_item(self):
        """Cover line 519: kanban_remove_checklist_item."""
        with patch("mcp_server.api_delete", return_value={"status": "deleted"}):
            result = json.loads(
                await kanban_remove_checklist_item(task_id="task_1", item_id="item_1")
            )
            assert result["status"] == "deleted"


# ── Tool Registration ──────────────────────────────────────────────────


class TestToolRegistration:
    def test_app_exists(self):
        assert app is not None

    def test_app_name(self):
        assert app.name == "spacetime-kanban"

    def test_all_tools_registered(self):
        """Verify tool functions are registered via add_tool()."""
        # app.tools may vary by installed MCP SDK version
        assert len(app._tool_manager._tools) >= 33, "Not enough tools registered"


# ── Main entry point ──────────────────────────────────────────────────


class TestMain:
    @pytest.mark.asyncio
    async def test_main_function(self):
        """Cover line 573: main() function runs the app over stdio."""
        with patch("mcp_server.app.run") as mock_run:
            main()
            mock_run.assert_called_once_with(transport="stdio")


class TestListTasksNonList:
    @pytest.mark.asyncio
    async def test_list_tasks_non_list_response(self):
        """Cover edge case where API returns non-list for tasks."""
        with patch("mcp_server.api_get", return_value={"error": "not found"}):
            result = json.loads(await kanban_list_tasks())
            assert result["count"] == 0
            # When API returns a non-list, it's passed through as-is
            assert result["tasks"] == {"error": "not found"}
