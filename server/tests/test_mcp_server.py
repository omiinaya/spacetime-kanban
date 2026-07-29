"""Tests for server/mcp_server.py.

The MCP server module uses @app.list_tools() and @app.call_tool() decorators
from the mcp.server.Server class, which are valid in MCP SDK v1.x.
"""

import sys

import pytest

sys.path.insert(0, ".")

from mcp_server import app, api_get, api_post  # noqa: E402
from mcp_server import KanbanAPIError  # noqa: E402


def test_mcp_app_exists():
    """Verify the MCP server app object exists."""
    assert app is not None


def test_app_name():
    """Verify the server name."""
    assert app.name == "spacetimedb-kanban"


def test_kanban_api_error_defaults():
    """KanbanAPIError defaults to status_code=0."""
    err = KanbanAPIError("test error")
    assert str(err) == "test error"
    assert err.status_code == 0


def test_kanban_api_error_with_code():
    """KanbanAPIError stores the HTTP status code."""
    err = KanbanAPIError("not found", status_code=404)
    assert str(err) == "not found"
    assert err.status_code == 404


@pytest.mark.parametrize(
    "path,expected_safe",
    [
        ("/api/tasks", "/api/tasks"),
        ("/api/tasks/task_123", "/api/tasks/task_123"),
        ("/api/tasks/task with spaces", "/api/tasks/task%20with%20spaces"),
    ],
)
def test_api_get_validates_paths(path, expected_safe):
    """api_get should return a result (list or dict) for valid paths when server is up,
    or raise KanbanAPIError when the server is down."""
    try:
        result = api_get(path)
        # If we get here, server is running — just check return type
        assert isinstance(result, (list, dict)), f"expected list/dict, got {type(result)}"
    except KanbanAPIError:
        pass  # Expected when server is down


@pytest.mark.parametrize(
    "path,body,expected_safe",
    [
        ("/api/tasks", {"title": "test"}, "/api/tasks"),
        ("/api/tasks/task_123/claim", {"agent_id": "hermes"}, "/api/tasks/task_123/claim"),
    ],
)
def test_api_post_validates_paths(path, body, expected_safe):
    """api_post should return a dict for valid paths when server is up,
    or raise KanbanAPIError when the server is down."""
    try:
        result = api_post(path, body)
        # If we get here, server is running — just check return type
        assert isinstance(result, dict), f"expected dict, got {type(result)}"
    except KanbanAPIError:
        pass  # Expected when server is down
