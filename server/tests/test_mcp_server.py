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
    kanban_claim,
    kanban_complete,
    kanban_create_task,
    kanban_list_tasks,
    kanban_split_task,
    kanban_update_task,
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


# ── Tool Registration ──────────────────────────────────────────────────


class TestToolRegistration:
    def test_app_exists(self):
        assert app is not None

    def test_app_name(self):
        assert app.name == "spacetimedb-kanban"

    def test_all_tools_registered(self):
        """Verify tool functions are registered via add_tool()."""
        # app.tools may vary by installed MCP SDK version
        assert len(app._tool_manager._tools) >= 33, "Not enough tools registered"
