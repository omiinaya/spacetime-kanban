"""Tests for server/scheduler_low_backlog.py — backlog detection and scanner triggering."""

from unittest.mock import patch

import pytest

from server.scheduler_low_backlog import (
    CRITICAL_BACKLOG_THRESHOLD,
    LOW_BACKLOG_THRESHOLD,
    _get_actionable_available_count,
    check_backlog_and_trigger,
)

# We must reset module-level state between tests
_module_globals = {}

# The module uses module-level variables _last_trigger_ms and _scanner_running


def _reset_state():
    """Reset module-level state between tests."""
    import server.scheduler_low_backlog as slb

    slb._last_trigger_ms = 0
    slb._scanner_running = False


@pytest.fixture(autouse=True)
def reset_state():
    _reset_state()
    yield
    _reset_state()


class TestSchedulerLowBacklog:
    """Test suite for scheduler_low_backlog.py — backlog detection and scanner triggering."""

    # ── _get_actionable_available_count ────────────────────────────────

    @patch("server.scheduler_low_backlog._api_get")
    async def test_actionable_count_returns_zero_when_no_tasks(self, mock_api_get):
        """No tasks returned from API should return 0."""
        mock_api_get.return_value = None
        count = await _get_actionable_available_count()
        assert count == 0

    @patch("server.scheduler_low_backlog._api_get")
    async def test_actionable_count_filters_zombies(self, mock_api_get):
        """Tasks with fail_count >= max_attempts should not be counted."""
        mock_api_get.return_value = [
            {"id": "t1", "fail_count": 0, "max_attempts": 3},
            {"id": "t2", "fail_count": 2, "max_attempts": 3},
            {"id": "t3", "fail_count": 3, "max_attempts": 3},  # zombie
            {"id": "t4", "fail_count": 5, "max_attempts": 3},  # zombie
        ]
        count = await _get_actionable_available_count()
        assert count == 2  # t1 and t2 are actionable

    @patch("server.scheduler_low_backlog._api_get")
    async def test_actionable_count_all_actionable(self, mock_api_get):
        """All tasks with fail_count < max_attempts should be counted."""
        mock_api_get.return_value = [
            {"id": "t1", "fail_count": 0, "max_attempts": 3},
            {"id": "t2", "fail_count": 1, "max_attempts": 5},
        ]
        count = await _get_actionable_available_count()
        assert count == 2

    @patch("server.scheduler_low_backlog._api_get")
    async def test_actionable_count_empty_list(self, mock_api_get):
        """Empty task list should return 0."""
        mock_api_get.return_value = []
        count = await _get_actionable_available_count()
        assert count == 0

    # ── check_backlog_and_trigger ──────────────────────────────────────

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("time.time")
    async def test_returns_false_when_backlog_above_threshold(
        self, mock_time, mock_trigger, mock_count
    ):
        """When actionable count is well above LOW_BACKLOG_THRESHOLD, return False."""
        mock_time.return_value = 1000000
        mock_count.return_value = LOW_BACKLOG_THRESHOLD + 10  # above threshold

        result = await check_backlog_and_trigger({"total_done": 50})

        assert result is False
        mock_trigger.assert_not_called()

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("time.time")
    async def test_triggers_scanner_when_critical(self, mock_time, mock_trigger, mock_count):
        """When actionable count is below CRITICAL_BACKLOG_THRESHOLD and done > 5, trigger."""
        mock_time.return_value = 1000000
        mock_count.return_value = CRITICAL_BACKLOG_THRESHOLD - 1  # 2 or less
        mock_trigger.return_value = {"scanner_repo1": {"created": 3}}

        import server.scheduler_low_backlog as slb

        slb._last_trigger_ms = 0

        result = await check_backlog_and_trigger({"total_done": 50})

        assert result is True
        mock_trigger.assert_called_once()

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("time.time")
    async def test_triggers_scanner_when_low(self, mock_time, mock_trigger, mock_count):
        """When actionable count is between critical and low threshold, trigger scanner."""
        mock_time.return_value = 1000000
        mock_count.return_value = LOW_BACKLOG_THRESHOLD  # exactly at threshold
        mock_trigger.return_value = {"scanner_repo1": {"created": 5}}

        import server.scheduler_low_backlog as slb

        slb._last_trigger_ms = 0

        result = await check_backlog_and_trigger({"total_done": 50})

        assert result is True
        mock_trigger.assert_called_once()

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("server.scheduler_low_backlog._generate_improvement_tasks")
    @patch("time.time")
    async def test_generates_improvement_tasks_when_scanner_finds_nothing(
        self, mock_time, mock_improve, mock_trigger, mock_count
    ):
        """When scanner returns no new tasks, improvement tasks should be generated."""
        mock_time.return_value = 1000000
        mock_count.return_value = 0  # critical
        mock_trigger.return_value = {"scanner_r1": {"created": 0}}
        mock_improve.return_value = 2

        import server.scheduler_low_backlog as slb

        slb._last_trigger_ms = 0

        result = await check_backlog_and_trigger({"total_done": 50})

        assert result is True
        mock_improve.assert_called_once()

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("time.time")
    async def test_respects_cooldown(self, mock_time, mock_count):
        """check_backlog_and_trigger should return False if called within cooldown."""
        mock_time.return_value = 1000000
        mock_count.return_value = 0

        import server.scheduler_low_backlog as slb

        # Set last trigger to just now
        slb._last_trigger_ms = int(1000000 * 1000) - 10  # 10ms ago

        result = await check_backlog_and_trigger({"total_done": 50})

        assert result is False

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._api_get")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("time.time")
    async def test_fetches_overview_when_none_provided(
        self, mock_time, mock_trigger, mock_api_get, mock_count
    ):
        """When overview is None, check_backlog_and_trigger should fetch it."""
        mock_time.return_value = 1000000
        mock_count.return_value = 0
        mock_api_get.return_value = {"total_done": 50}
        mock_trigger.return_value = {"r1": {"created": 2}}

        import server.scheduler_low_backlog as slb

        slb._last_trigger_ms = 0

        result = await check_backlog_and_trigger()  # No overview provided

        assert result is True
        mock_api_get.assert_called_once_with("/api/analytics/overview")

    @patch("server.scheduler_low_backlog._get_actionable_available_count")
    @patch("server.scheduler_low_backlog._trigger_scanner")
    @patch("time.time")
    async def test_does_not_trigger_when_done_too_low(self, mock_time, mock_trigger, mock_count):
        """Should not trigger when total_done <= 5 even if actionable is 0."""
        mock_time.return_value = 1000000
        mock_count.return_value = 0

        import server.scheduler_low_backlog as slb

        slb._last_trigger_ms = 0

        result = await check_backlog_and_trigger({"total_done": 3})

        assert result is False
        mock_trigger.assert_not_called()


# ═══════════════════════════════════════════════════════════════════
# _extract_actionable_headings — junk-task prevention
# ═══════════════════════════════════════════════════════════════════


class TestActionableHeadings:
    """Only genuinely doable headings become tasks; structural/status
    sections (Recently Completed, Deferred, Summary, etc.) are skipped."""

    def test_pending_items_are_actionable(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Status: PENDING

### Add --adults parameter to United CLI (P2)
### Fix search dedup race in gateway (P1)
### Migrate cache refresh to _proxy_upstream (P3)
"""
        titles = [h["title"] for h in _extract_actionable_headings(content)]
        assert len(titles) == 3
        assert any("--adults" in t for t in titles)
        assert any("dedup race" in t for t in titles)

    def test_recently_completed_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Recently Completed

### Alaska scaffold — COMPLETE
### Spirit investigation — RESOLVED
"""
        assert _extract_actionable_headings(content) == []

    def test_deferred_wont_do_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Deferred / Won't Do

### Add --adults parameter (deferred)
### AA normalizer enrichment (won't do)
"""
        assert _extract_actionable_headings(content) == []

    def test_status_all_implemented_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Status: ALL IMPLEMENTED (verified 2026-08-05)
### P0 — Customer portal web view ✅ Done
### P2 — Dashboard charts ✅ Done
"""
        assert _extract_actionable_headings(content) == []

    def test_section_headers_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Summary
## Reference Results (Full Suite)
## Retrieval Quality
## What We're Building
## Build Verification Results
"""
        assert _extract_actionable_headings(content) == []

    def test_done_marker_in_item_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Pending

### Add tests for module X (DONE)
### Add real work item (P1)
"""
        titles = [h["title"] for h in _extract_actionable_headings(content)]
        assert len(titles) == 1
        assert "real work item" in titles[0]

    def test_short_headings_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = "## Hi\n## Add more\n"
        assert _extract_actionable_headings(content) == []

    def test_priority_marker_without_verb_is_actionable(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = "## Pending\n### STDB: republish module to live DB (P0)\n"
        titles = [h["title"] for h in _extract_actionable_headings(content)]
        assert len(titles) == 1
        assert "republish" in titles[0]

    def test_research_log_skipped(self):
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Research Log

### 2026-08-05 PENDING reconciliation — verified complete
### 2026-07-01 Tick 7
"""
        assert _extract_actionable_headings(content) == []

    def test_realistic_full_doc(self):
        """Mixed doc: pending items kept, completed/deferred/research skipped."""
        from server.scheduler_low_backlog import _extract_actionable_headings

        content = """## Status: PENDING

### Add --adults parameter to United CLI (P2)
### Fix search dedup race in gateway (P1)

## Recently Completed

### Alaska scaffold — COMPLETE

## Research Log

### 2026-08-05 reconciliation

## Deferred / Won't Do

### AA normalizer enrichment (won't do)
"""
        titles = [h["title"] for h in _extract_actionable_headings(content)]
        assert len(titles) == 2
        assert all("United CLI" in t or "dedup" in t for t in titles)
