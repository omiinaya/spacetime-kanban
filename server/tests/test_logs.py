"""Comprehensive tests for routes/logs.py with mocked STDB backend.

Uses the ``mock_stdb`` fixture from ``conftest.py`` which patches helpers in
route modules via ``_patch_route_modules``.

**Important:** ``mock_stdb["sql"]`` controls ``routes.tasks._sql``, NOT
``routes.logs._sql``.  The conftest fixture creates a separate hidden mock
for each route module.  For tests that need to control what ``routes.logs._sql``
returns, patch it explicitly:

    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [...]

For ``_sql_param`` (used by task_id/agent_id filters, all ``batch_logs`` calls,
and ``logs_stats``), patch it the same way:

    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [...]
"""

from unittest.mock import AsyncMock, patch

import pytest

# ── Helper: build a minimal log dict as returned by STDB rows ──────────


def _make_log(
    lid="log_1",
    task_id="task_1",
    action="created",
    agent_id="hermes",
    notes="Some notes",
    timestamp=1000,
):
    """Build a minimal task_logs row dict."""
    return {
        "id": lid,
        "task_id": task_id,
        "action": action,
        "agent_id": agent_id,
        "notes": notes,
        "timestamp": timestamp,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /api/logs  —  list_logs
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_logs_empty(client, mock_stdb):
    """No logs in the database returns an empty list.

    This test passes because the default AsyncMock from conftest's
    _patch_route_modules is iterable and yields no items.
    """
    resp = await client.get("/api/logs")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_logs_task_id_filter(client, mock_stdb):
    """task_id parameter routes through _sql_param and returns matching logs.

    The SQL already filters; _sql_param returns only the matching row.
    """
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [
            _make_log(lid="log_1", task_id="task_42", action="claimed"),
        ]

        resp = await client.get("/api/logs", params={"task_id": "task_42"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["task_id"] == "task_42"
        assert data[0]["action"] == "claimed"
        # Verify _sql_param was called with the right template
        call_sql = mock_param.call_args[0][0]
        assert "WHERE" in call_sql
        assert "task_id" in call_sql


@pytest.mark.asyncio
async def test_list_logs_task_id_filter_no_match(client, mock_stdb):
    """task_id filter that yields no results."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = []

        resp = await client.get("/api/logs", params={"task_id": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_list_logs_action_filter_single(client, mock_stdb):
    """Single action filter is applied Python-side after the DB query."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_1", action="created"),
            _make_log(lid="log_2", action="completed"),
            _make_log(lid="log_3", action="blocked"),
        ]

        resp = await client.get("/api/logs", params={"action": "completed"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "completed"
        assert data[0]["id"] == "log_2"


@pytest.mark.asyncio
async def test_list_logs_action_filter_multi(client, mock_stdb):
    """Comma-separated actions filter multiple values."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_1", action="created"),
            _make_log(lid="log_2", action="completed"),
            _make_log(lid="log_3", action="blocked"),
            _make_log(lid="log_4", action="claimed"),
        ]

        resp = await client.get("/api/logs", params={"action": "created,blocked"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        actions = {d["action"] for d in data}
        assert actions == {"created", "blocked"}


@pytest.mark.asyncio
async def test_list_logs_action_filter_no_match(client, mock_stdb):
    """Action filter that does not match any log."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_1", action="created"),
            _make_log(lid="log_2", action="completed"),
        ]

        resp = await client.get("/api/logs", params={"action": "heartbeat"})
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_list_logs_search_filter(client, mock_stdb):
    """Search filter matches across notes, task_id, and action (case-insensitive)."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(
                lid="log_1", task_id="task_auth", notes="Fixed login bug", action="completed"
            ),
            _make_log(lid="log_2", task_id="task_ui", notes="Added button", action="created"),
            _make_log(lid="log_3", task_id="task_auth2", notes="More auth work", action="claimed"),
            _make_log(lid="log_4", task_id="task_build", notes="CI fix", action="completed"),
        ]

        resp = await client.get("/api/logs", params={"search": "auth"})
        assert resp.status_code == 200
        data = resp.json()
        # Should match task_auth (by task_id) and task_auth2 (by both task_id and notes)
        assert len(data) == 2
        task_ids = {d["task_id"] for d in data}
        assert task_ids == {"task_auth", "task_auth2"}


@pytest.mark.asyncio
async def test_list_logs_search_filter_no_match(client, mock_stdb):
    """Search that does not match any log returns empty list."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_1", notes="Alpha release"),
            _make_log(lid="log_2", notes="Beta testing"),
        ]

        resp = await client.get("/api/logs", params={"search": "gamma"})
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_list_logs_since_filter(client, mock_stdb):
    """since filter restricts to logs after a timestamp."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_2", timestamp=200),
            _make_log(lid="log_3", timestamp=300),
        ]

        resp = await client.get("/api/logs", params={"since": "150"})
        assert resp.status_code == 200
        data = resp.json()
        # SQL already filters; all returned rows have timestamp > 150
        assert len(data) == 2
        timestamps = {d["timestamp"] for d in data}
        assert timestamps == {200, 300}
        # Verify the SQL contained the since clause
        call_sql = mock_sql.call_args[0][0]
        assert "timestamp > 150" in call_sql


@pytest.mark.asyncio
async def test_list_logs_until_filter(client, mock_stdb):
    """until filter restricts to logs before a timestamp."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_1", timestamp=100),
        ]

        resp = await client.get("/api/logs", params={"until": "150"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["timestamp"] == 100
        call_sql = mock_sql.call_args[0][0]
        assert "timestamp < 150" in call_sql


@pytest.mark.asyncio
async def test_list_logs_since_and_until(client, mock_stdb):
    """Both since and until filters narrow the time range."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid="log_2", timestamp=200),
        ]

        resp = await client.get("/api/logs", params={"since": "150", "until": "250"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["timestamp"] == 200
        call_sql = mock_sql.call_args[0][0]
        assert "timestamp > 150" in call_sql
        assert "timestamp < 250" in call_sql


@pytest.mark.asyncio
async def test_list_logs_offset_limit(client, mock_stdb):
    """offset and limit params correctly paginate results."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid=f"log_{i}", task_id=f"task_{i}", timestamp=i * 100) for i in range(1, 11)
        ]  # 10 logs, timestamps 100, 200, ..., 1000
        # Sorted by -timestamp: log_10(1000), log_9(900), ..., log_1(100)

        resp = await client.get("/api/logs", params={"offset": 2, "limit": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        # offset 2 → skip log_10(1000), log_9(900) → start at log_8(800)
        assert data[0]["timestamp"] == 800  # log_8
        assert data[1]["timestamp"] == 700  # log_7
        assert data[2]["timestamp"] == 600  # log_6


@pytest.mark.asyncio
async def test_list_logs_default_limit(client, mock_stdb):
    """No limit param defaults to 50."""
    with patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql:
        mock_sql.return_value = [
            _make_log(lid=f"log_{i}", task_id=f"task_{i}", timestamp=i) for i in range(60)
        ]

        resp = await client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.json()
        # 60 rows returned from DB, default limit is 50
        assert len(data) == 50


@pytest.mark.asyncio
async def test_list_logs_combined_filters(client, mock_stdb):
    """Combined task_id + action + since filters work together."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        # _sql_param with task_id + since returns a subset
        mock_param.return_value = [
            _make_log(lid="log_a", task_id="task_5", action="completed", timestamp=500),
            _make_log(lid="log_b", task_id="task_5", action="claimed", timestamp=400),
            _make_log(lid="log_c", task_id="task_5", action="completed", timestamp=300),
        ]

        resp = await client.get(
            "/api/logs",
            params={"task_id": "task_5", "action": "completed", "since": "250"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # SQL filter: task_id="task_5", since=250 → log_a (500), log_b (400), log_c (300)
        # Python action filter: "completed" → log_a (500), log_c (300)
        assert len(data) == 2
        assert all(d["action"] == "completed" for d in data)
        assert all(d["timestamp"] > 250 for d in data)

        # Verify _sql_param was called with task_id
        assert mock_param.call_count >= 1
        call_sql = mock_param.call_args[0][0]
        assert "task_id" in call_sql
        assert "timestamp > 250" in call_sql


# ══════════════════════════════════════════════════════════════════════
# GET /api/logs/batch  —  batch_logs
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_batch_logs_empty_task_ids(client, mock_stdb):
    """Empty task_ids string returns an empty dict."""
    resp = await client.get("/api/logs/batch", params={"task_ids": ""})
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_batch_logs_whitespace_task_ids(client, mock_stdb):
    """Whitespace-only task_ids returns an empty dict."""
    resp = await client.get("/api/logs/batch", params={"task_ids": "   ,  , "})
    assert resp.status_code == 200
    assert resp.json() == {}


@pytest.mark.asyncio
async def test_batch_logs_single_task(client, mock_stdb):
    """Single task ID returns its latest log."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [
            _make_log(lid="log_a", task_id="task_1", action="heartbeat", timestamp=300),
            _make_log(lid="log_b", task_id="task_1", action="heartbeat", timestamp=200),
        ]

        resp = await client.get("/api/logs/batch", params={"task_ids": "task_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_1" in data
        assert data["task_1"] is not None
        # latest by timestamp
        assert data["task_1"]["id"] == "log_a"
        assert data["task_1"]["timestamp"] == 300


@pytest.mark.asyncio
async def test_batch_logs_multiple_tasks(client, mock_stdb):
    """Multiple task IDs return latest log per task."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [
            _make_log(lid="log_1a", task_id="task_1", action="heartbeat", timestamp=300),
            _make_log(lid="log_1b", task_id="task_1", action="heartbeat", timestamp=200),
            _make_log(lid="log_2a", task_id="task_2", action="heartbeat", timestamp=500),
            _make_log(lid="log_3a", task_id="task_3", action="heartbeat", timestamp=100),
        ]

        resp = await client.get(
            "/api/logs/batch",
            params={"task_ids": "task_1,task_2,task_3"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data["task_1"]["id"] == "log_1a"
        assert data["task_2"]["id"] == "log_2a"
        assert data["task_3"]["id"] == "log_3a"


@pytest.mark.asyncio
async def test_batch_logs_missing_tasks_return_none(client, mock_stdb):
    """Task IDs with no log entries appear as None in the result."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        # Only one task has logs
        mock_param.return_value = [
            _make_log(lid="log_a", task_id="task_1", action="heartbeat", timestamp=100),
        ]

        resp = await client.get(
            "/api/logs/batch",
            params={"task_ids": "task_1,task_missing,task_ghost"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data["task_1"] is not None
        assert data["task_missing"] is None
        assert data["task_ghost"] is None


@pytest.mark.asyncio
async def test_batch_logs_default_action(client, mock_stdb):
    """Default action filter is 'heartbeat'."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [
            _make_log(lid="log_hb", task_id="task_1", action="heartbeat", timestamp=200),
        ]

        resp = await client.get("/api/logs/batch", params={"task_ids": "task_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_1"]["id"] == "log_hb"
        # Verify SQL included action filter and indexed task_id OR conditions
        call_sql = mock_param.call_args[0][0]
        assert "action" in call_sql
        assert "task_id" in call_sql


@pytest.mark.asyncio
async def test_batch_logs_custom_action(client, mock_stdb):
    """Custom action filter restricts results."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        mock_param.return_value = [
            _make_log(lid="log_comp", task_id="task_1", action="completed", timestamp=300),
        ]

        resp = await client.get(
            "/api/logs/batch",
            params={"task_ids": "task_1", "action": "completed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_1"]["action"] == "completed"


@pytest.mark.asyncio
async def test_batch_logs_multi_action(client, mock_stdb):
    """Multi-action filter (comma-separated) returns logs matching any of them.

    The SQL filters by the first action; remaining actions are applied
    Python-side.
    """
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        # _sql_param only filters by the first action in SQL
        mock_param.return_value = [
            _make_log(lid="log_1", task_id="task_1", action="completed", timestamp=300),
            _make_log(lid="log_2", task_id="task_1", action="claimed", timestamp=200),
            _make_log(lid="log_3", task_id="task_1", action="blocked", timestamp=100),
        ]

        resp = await client.get(
            "/api/logs/batch",
            params={"task_ids": "task_1", "action": "completed,claimed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Python-side filter removes "blocked" — latest remaining is "completed" (ts=300)
        assert data["task_1"] is not None
        assert data["task_1"]["action"] == "completed"


@pytest.mark.asyncio
async def test_batch_logs_truncates_at_100(client, mock_stdb):
    """More than 100 task IDs are truncated to 100."""
    with patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param:
        # Return some logs
        mock_param.return_value = [
            _make_log(lid=f"log_{i}", task_id=f"task_{i}", action="heartbeat", timestamp=100)
            for i in range(50)
        ]

        many_ids = ",".join(f"task_{i}" for i in range(150))
        resp = await client.get(
            "/api/logs/batch",
            params={"task_ids": many_ids},
        )
        assert resp.status_code == 200
        data = resp.json()
        # At most 100 entries in the result
        assert len(data) <= 100
        # task_0 through task_99 are present (first 100)
        assert "task_0" in data
        assert "task_99" in data
        # task_100 is the 101st — excluded
        assert "task_100" not in data


# ══════════════════════════════════════════════════════════════════════
# GET /api/logs/stats  —  logs_stats
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_logs_stats_success(client, mock_stdb):
    """Full stats aggregation returns all five sections with data."""
    with (
        patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql,
        patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param,
    ):
        # Call order: _sql → _sql_param → _sql → _sql_param → _sql_param
        mock_sql.side_effect = [
            [{"cnt": 10}],  # 1st: total COUNT(*)
            [  # 3rd: GROUP BY action
                {"action": "created", "cnt": 3},
                {"action": "completed", "cnt": 5},
                {"action": "blocked", "cnt": 2},
            ],
        ]
        mock_param.side_effect = [
            [{"cnt": 2}],  # 2nd: today events
            [{"cnt": 1}],  # 4th: active agents today
            [  # 5th: top agents
                {"agent_id": "hermes", "cnt": 2},
            ],
        ]

        resp = await client.get("/api/logs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 10
        assert data["today_events"] == 2
        assert data["active_agents_today"] == 1
        assert data["action_breakdown"] == {"created": 3, "completed": 5, "blocked": 2}
        assert data["top_agents"] == {"hermes": 2}


@pytest.mark.asyncio
async def test_logs_stats_empty_db(client, mock_stdb):
    """Empty database returns zeroes for all counters."""
    with (
        patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql,
        patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param,
    ):
        mock_sql.side_effect = [
            [{"cnt": 0}],  # total
            [],  # action GROUP BY (no rows)
        ]
        mock_param.side_effect = [
            [{"cnt": 0}],  # today
            [{"cnt": 0}],  # active agents today
            [],  # top agents (no rows)
        ]

        resp = await client.get("/api/logs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["today_events"] == 0
        assert data["active_agents_today"] == 0
        assert data["action_breakdown"] == {}
        assert data["top_agents"] == {}


@pytest.mark.asyncio
async def test_logs_stats_no_today_events(client, mock_stdb):
    """No events today — today counters are zero, total is non-zero."""
    with (
        patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql,
        patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param,
    ):
        mock_sql.side_effect = [
            [{"cnt": 25}],  # total
            [  # action GROUP BY
                {"action": "claimed", "cnt": 10},
                {"action": "heartbeat", "cnt": 15},
            ],
        ]
        mock_param.side_effect = [
            [{"cnt": 0}],  # today events
            [{"cnt": 0}],  # active agents today
            [],  # top agents today
        ]

        resp = await client.get("/api/logs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 25
        assert data["today_events"] == 0
        assert data["active_agents_today"] == 0
        assert data["action_breakdown"] == {"claimed": 10, "heartbeat": 15}
        assert data["top_agents"] == {}


@pytest.mark.asyncio
async def test_logs_stats_single_action_type(client, mock_stdb):
    """Only one action type in the database."""
    with (
        patch("routes.logs._sql", new_callable=AsyncMock) as mock_sql,
        patch("routes.logs._sql_param", new_callable=AsyncMock) as mock_param,
    ):
        mock_sql.side_effect = [
            [{"cnt": 7}],  # total
            [  # action GROUP BY — single action
                {"action": "heartbeat", "cnt": 7},
            ],
        ]
        mock_param.side_effect = [
            [{"cnt": 3}],  # today events
            [{"cnt": 2}],  # active agents today
            [  # top agents today
                {"agent_id": "agent_a", "cnt": 2},
                {"agent_id": "agent_b", "cnt": 1},
            ],
        ]

        resp = await client.get("/api/logs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 7
        assert data["action_breakdown"] == {"heartbeat": 7}
        assert data["top_agents"] == {"agent_a": 2, "agent_b": 1}
