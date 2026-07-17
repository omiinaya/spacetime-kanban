"""Shared pytest fixtures for spacetimedb-kanban server tests.

These fixtures mock the SpacetimeDB backend so tests can run without
a running STDB instance.  The ASGITransport-based client avoids needing
a live uvicorn process.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── Route modules that import STDB helpers from shared ─────────────────
# Each entry: (module_name, [helper names it imports])
_ROUTE_HELPER_MAP = {
    "routes.agents": ["_sql", "_sql_param", "_call"],
    "routes.analytics": ["_sql"],
    "routes.github": ["_sql_param", "_call", "_notify"],
    "routes.labels": ["_sql", "_sql_param", "_call"],
    "routes.logs": ["_sql"],
    "routes.projects": ["_sql", "_sql_param", "_call"],
    "routes.tasks": ["_sql", "_sql_param", "_call", "_notify"],
    "routes.templates": ["_sql", "_sql_param", "_call"],
}


def _patch_route_modules(stack: ExitStack):
    """Patch STDB helpers in all route modules so tests can mock them."""
    for mod, names in _ROUTE_HELPER_MAP.items():
        for name in names:
            stack.enter_context(patch(f"{mod}.{name}", new_callable=AsyncMock))


@pytest.fixture
def mock_stdb():
    """Mock STDB calls (_sql, _sql_param, _call) to avoid needing a running
    SpacetimeDB instance.  Each test can override the return values on the
    yielded dict to control what the route handlers "see" in the database.

    Usage::

        def test_list_tasks(mock_stdb):
            mock_stdb["sql"].return_value = [...]   # rows returned by _sql()
            mock_stdb["call"].return_value = {...}   # value returned by _call()

    The dict keys are: ``sql``, ``param``, ``call``, ``notify``.
    """
    with ExitStack() as stack:
        sql = stack.enter_context(patch("main._sql", new_callable=AsyncMock))
        param = stack.enter_context(patch("main._sql_param", new_callable=AsyncMock))
        call = stack.enter_context(patch("main._call", new_callable=AsyncMock))
        notify = stack.enter_context(patch("main._notify", new_callable=AsyncMock))
        _patch_route_modules(stack)

        # Set default return values on ALL mocks (both main and route modules)
        sql.return_value = []
        param.return_value = []
        call.return_value = {"status": "ok"}
        notify.return_value = None

        yield {
            "sql": sql,
            "param": param,
            "call": call,
            "notify": notify,
        }


@pytest.fixture
async def client():
    """Create an async HTTP client against the real FastAPI ``app`` via
    ``ASGITransport`` -- no uvicorn process needed.

    The ``lifespan`` handler (which waits for STDB) is NOT triggered because
    ``ASGITransport`` defaults to ``lifespan="off"``.
    """
    # pylint: disable=import-outside-toplevel
    from main import app  # noqa: E402

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
