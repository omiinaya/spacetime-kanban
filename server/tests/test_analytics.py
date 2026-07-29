"""Tests for server/routes/analytics.py — analytics endpoints.

These tests mock the STDB _sql and _sql_param helpers to avoid needing
a running STDB instance.  The mock_stdb fixture is in tests/conftest.py.

Note: The old GROUP BY version of this endpoint used SQL-level aggregation
for performance. STDB v2.6.1 doesn't support GROUP BY, so we fetch all
tasks and aggregate in Python. These tests validate the fallback logic.
"""

import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, "..")

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_sql():
    """Mock _sql to return fake task data."""
    fake_tasks = [
        {"id": "t1", "status": "done", "repo": "test-repo", "updated_at": 9999999999999},
        {"id": "t2", "status": "done", "repo": "test-repo", "updated_at": 9999999999999},
        {"id": "t3", "status": "done", "repo": "other-repo", "updated_at": 9999999999999},
        {"id": "t4", "status": "available", "repo": "test-repo", "updated_at": 1000000},
        {"id": "t5", "status": "blocked", "repo": "test-repo", "updated_at": 2000000},
        {"id": "t6", "status": "inProgress", "repo": "other-repo", "updated_at": 3000000},
    ]
    with patch("routes.analytics._sql", new_callable=AsyncMock) as mock:
        # Default: SELECT * FROM tasks returns fake_tasks
        mock.return_value = fake_tasks
        yield mock


@pytest.fixture
def mock_sql_param():
    """Mock _sql_param — used for claim churn query."""
    with patch("routes.analytics._sql_param", new_callable=AsyncMock) as mock:
        mock.return_value = []
        yield mock


# ═══════════════════════════════════════════════════════════════════════
# analytics_overview
# ═══════════════════════════════════════════════════════════════════════


class TestAnalyticsOverview:
    """analytics_overview() returns correctly structured data."""

    async def test_returns_expected_fields(self, mock_sql, mock_sql_param):
        """All required fields are present in the response."""
        from routes.analytics import analytics_overview

        result = await analytics_overview()
        expected = {
            "total",
            "by_status",
            "repos",
            "completed_today",
            "completed_week",
            "total_done",
            "claims_last_hour",
            "completions_last_hour",
            "claim_complete_ratio",
        }
        for field in expected:
            assert field in result, f"missing field: {field}"

    async def test_counts_by_status(self, mock_sql, mock_sql_param):
        """by_status reflects task status distribution."""
        from routes.analytics import analytics_overview

        result = await analytics_overview()
        assert result["total"] == 6
        assert result["by_status"]["done"] == 3
        assert result["by_status"]["available"] == 1
        assert result["by_status"]["blocked"] == 1
        assert result["by_status"]["inProgress"] == 1

    async def test_repo_breakdown(self, mock_sql, mock_sql_param):
        """Repos are split correctly with per-status counts."""
        from routes.analytics import analytics_overview

        result = await analytics_overview()
        repos = result["repos"]
        assert "test-repo" in repos
        assert "other-repo" in repos
        assert repos["test-repo"]["total"] == 4
        assert repos["test-repo"]["done"] == 2
        assert repos["test-repo"]["available"] == 1
        assert repos["test-repo"]["blocked"] == 1
        assert repos["other-repo"]["total"] == 2
        assert repos["other-repo"]["done"] == 1
        assert repos["other-repo"]["inProgress"] == 1

    async def test_completions_counted(self, mock_sql, mock_sql_param):
        """Tasks with updated_at within last hour are counted as completions_last_hour."""
        import time

        now = int(time.time() * 1000)
        hour_ago = now - 3_600_000

        # Override mock to return tasks within the hour
        recent_tasks = [
            {"id": "t1", "status": "done", "repo": "test", "updated_at": now - 1000},
            {"id": "t2", "status": "done", "repo": "test", "updated_at": now - 2000},
            {"id": "t3", "status": "done", "repo": "test", "updated_at": hour_ago + 5000},
            {"id": "t4", "status": "done", "repo": "test", "updated_at": hour_ago - 10000},
        ]
        mock_sql.return_value = recent_tasks

        from routes.analytics import analytics_overview

        result = await analytics_overview()
        assert result["completions_last_hour"] == 3  # t1, t2, t3
        assert result["total"] == 4

    async def test_empty_board(self, mock_sql, mock_sql_param):
        """Empty task list should still return valid structure."""
        mock_sql.return_value = []
        from routes.analytics import analytics_overview

        result = await analytics_overview()
        assert result["total"] == 0
        assert result["by_status"] == {}
        assert result["total_done"] == 0
        assert result["completions_last_hour"] == 0
        assert result["claims_last_hour"] == 0
        assert result["claim_complete_ratio"] == 0.0

    async def test_sql_failure_returns_graceful_error(self):
        """If _sql raises, the exception propagates as HTTP 502."""
        from fastapi import HTTPException

        from routes.analytics import analytics_overview

        with patch("routes.analytics._sql", new_callable=AsyncMock) as mock:
            mock.side_effect = HTTPException(502, "SQL query failed: timeout")

            with pytest.raises(HTTPException) as excinfo:
                await analytics_overview()
            assert excinfo.value.status_code == 502
