"""Cover remaining scheduler.py lines: repo_scanner (604-619) and shutdown (1253-1254)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRepoScanner:
    """Cover lines 604-619: repo_scanner async loop."""

    @pytest.mark.asyncio
    @patch("scheduler.asyncio.sleep")
    async def test_repo_scanner_cancelled_on_first_sleep(self, mock_sleep):
        """CancelledError on first sleep exits immediately."""
        mock_sleep.side_effect = asyncio.CancelledError()

        from scheduler import repo_scanner

        await repo_scanner(interval=1)

    @pytest.mark.asyncio
    @patch("scheduler.asyncio.sleep")
    @patch("scheduler.asyncio.get_event_loop")
    async def test_repo_scanner_runs_one_iteration(self, mock_get_loop, mock_sleep):
        """repo_scanner runs one full scan iteration and exits on CancelledError."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        # mock the event loop's run_in_executor
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(
            return_value={"scanner1": {"created": 3, "finding_count": 5}}
        )
        mock_get_loop.return_value = mock_loop

        from scheduler import repo_scanner

        await repo_scanner(interval=1)

        # Verify run_in_executor was called
        mock_loop.run_in_executor.assert_called_once()

    @pytest.mark.asyncio
    @patch("scheduler.asyncio.sleep")
    @patch("scheduler.asyncio.get_event_loop")
    async def test_repo_scanner_exception_handling(self, mock_get_loop, mock_sleep):
        """Exception in scanned is caught at lines 615-619."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(side_effect=RuntimeError("scanner failed"))
        mock_get_loop.return_value = mock_loop

        from scheduler import repo_scanner

        # Exception should be caught and printed, then CancelledError on next sleep
        await repo_scanner(interval=1)
        mock_loop.run_in_executor.assert_called_once()


class TestSchedulerShutdown:
    """Cover lines 1253-1254: scheduler cleanup."""

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self):
        """Scheduler stop_scheduler closes the httpx client."""
        import scheduler

        # Set up a mock client on the module
        mock_client = AsyncMock()
        scheduler._client = mock_client

        # Create a fake scheduler task that cancels immediately
        async def dummy_task():
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy_task())
        scheduler._scheduler_tasks = [task]

        await scheduler.stop_scheduler()

        # Client should have been closed
        mock_client.aclose.assert_called_once()
        assert scheduler._client is None
        assert len(scheduler._scheduler_tasks) == 0

    @pytest.mark.asyncio
    async def test_shutdown_no_client(self):
        """stope_scheduler handles None client gracefully."""
        import scheduler

        scheduler._client = None
        scheduler._scheduler_tasks = []

        await scheduler.stop_scheduler()
        # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_shutdown_client_close_error(self):
        """stop_scheduler propagates aclose errors."""
        import scheduler

        mock_client = AsyncMock()
        mock_client.aclose.side_effect = RuntimeError("close failed")
        scheduler._client = mock_client
        scheduler._scheduler_tasks = []

        with pytest.raises(RuntimeError, match="close failed"):
            await scheduler.stop_scheduler()


class TestStartScheduler:
    """Test start_scheduler's core logic."""

    @pytest.mark.asyncio
    @patch("scheduler._get_client")
    @patch("scheduler.settings")
    @patch("scheduler._recover_stale_tasks")
    @patch("scheduler._seed_initial_workers")
    async def test_start_scheduler_creates_loops(
        self, mock_seed, mock_recover, mock_settings, mock_get_client
    ):
        """start_scheduler creates the expected background tasks."""
        import scheduler

        # Reset global state
        scheduler._client = None
        scheduler._scheduler_tasks = []
        scheduler.scheduler_start_time = None

        # Enable all scheduler intervals
        mock_settings.scheduler_enabled = True
        mock_settings.dispatcher_interval_seconds = 5
        mock_settings.stale_check_interval_seconds = 120
        mock_settings.dead_board_interval_seconds = 3600
        mock_settings.template_interval_seconds = 900
        mock_settings.metrics_interval_seconds = 900
        mock_settings.scanner_interval_seconds = 1800
        mock_settings.improver_interval_seconds = 3600
        mock_settings.worker_script = None  # skip seed workers
        mock_get_client.return_value = AsyncMock()
        mock_recover.return_value = 0

        await scheduler.start_scheduler()

        # Should have created tasks
        assert len(scheduler._scheduler_tasks) >= 8  # 8+ loops

        # Cancel all tasks
        await scheduler.stop_scheduler()
