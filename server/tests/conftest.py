"""Shared pytest fixtures for spacetimedb-kanban server tests.

These fixtures mock the SpacetimeDB backend so tests can run without
a running STDB instance.  The ASGITransport-based client avoids needing
a live uvicorn process.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, AsyncMock


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
    with patch("main._sql", new_callable=AsyncMock) as mock_sql:
        with patch("main._sql_param", new_callable=AsyncMock) as mock_sql_param:
            with patch("main._call", new_callable=AsyncMock) as mock_call:
                with patch("main._notify", new_callable=AsyncMock) as mock_notify:
                    # Default return values – override per test
                    mock_sql.return_value = []
                    mock_sql_param.return_value = []
                    mock_call.return_value = {"status": "ok"}
                    mock_notify.return_value = None
                    yield {
                        "sql": mock_sql,
                        "param": mock_sql_param,
                        "call": mock_call,
                        "notify": mock_notify,
                    }


@pytest.fixture
async def client():
    """Create an async HTTP client against the real FastAPI ``app`` via
    ``ASGITransport`` – no uvicorn process needed.

    The ``lifespan`` handler (which waits for STDB) is NOT triggered because
    ``ASGITransport`` defaults to ``lifespan="off"``.
    """
    # pylint: disable=import-outside-toplevel
    from main import app  # noqa: E402

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
