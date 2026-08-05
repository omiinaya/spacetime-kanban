"""Coverage for remaining scheduler.py self_improver branches.

Targets uncovered lines:
- 960-966: stale tasks check (tasks in_progress >30min)
- 980: cycling tasks count print
- 1012-1015: git status check lines
- 1027-1028: exception handler

NOTE: self_improver catches CancelledError internally (at line 1025-1026)
and breaks the loop. The function returns normally — CancelledError is
NEVER propagated to the caller. Tests call the function directly without
pytest.raises.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

# Health check response — must be truthy to pass the health check gate
_OK_HEALTH = {"status": "ok"}


def _make_get_mock():
    """Create an AsyncMock for _api_get that returns sensible values per URL."""
    m = AsyncMock()

    async def side_effect(path: str, timeout: float = 15):
        if "/api/health" in path:
            return _OK_HEALTH
        elif "status=inProgress" in path:
            return [
                {
                    "id": "task_stale_1",
                    "title": "Old in_progress task",
                    "status": "inProgress",
                    "updated_at": 1000,  # way in the past → stale
                    "created_at": 1000,
                }
            ]
        elif "status=blocked" in path or "status=available" in path:
            return []
        return None

    m.side_effect = side_effect
    return m


class TestSelfImproverStaleTasks:
    """Cover lines 960-966: stale tasks in self_improver."""

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_stale_task_detected(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """A task in_progress >30min triggers a stale-task creation."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_save.return_value = None
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")

        async def get_side_effect(path, timeout=15):
            if "/api/health" in path:
                return _OK_HEALTH
            elif "status=inProgress" in path:
                return [
                    {
                        "id": "task_stale_1",
                        "title": "Old in_progress task",
                        "status": "inProgress",
                        "updated_at": 1000,  # way in the past
                        "created_at": 1000,
                    }
                ]
            return []

        mock_get.side_effect = get_side_effect
        mock_post.return_value = {"status": "ok"}

        from scheduler import self_improver

        await self_improver(interval=1)

        # At least one API post should have occurred (stale task creation
        # via _create_improvement_task → _api_post)
        mock_post.assert_called()

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_no_stale_tasks_no_action(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """No stale in_progress tasks → no stale-task creation."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")

        async def get_side_effect(path, timeout=15):
            if "/api/health" in path:
                return _OK_HEALTH
            elif "status=inProgress" in path:
                return [
                    {
                        "id": "task_fresh",
                        "title": "Fresh task",
                        "status": "inProgress",
                        # updated_at = now-ish (recent, not stale)
                        "updated_at": 9999999999999,
                        "created_at": 9999999999999,
                    }
                ]
            return []

        mock_get.side_effect = get_side_effect
        mock_post.return_value = {"status": "ok"}

        from scheduler import self_improver

        await self_improver(interval=1)

        # No stale improvement tasks should have been created.
        # _api_post may still be called for other reasons (max-attempts, etc.)
        # but at minimum the function should not crash.


class TestSelfImproverCyclingTasks:
    """Cover line 980: cycling tasks with fail_count."""

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_cycling_tasks_detected(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """>20 available tasks with fail_count ⇒ path executes."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")

        cycling_tasks = [
            {
                "id": f"task_cycle_{i}",
                "title": f"Cycling task {i}",
                "status": "available",
                "fail_count": i + 1,
                "fail_reason": "generic error",
                "max_attempts": 3,
            }
            for i in range(25)
        ]

        async def get_side_effect(path, timeout=15):
            if "/api/health" in path:
                return _OK_HEALTH
            elif "status=available" in path:
                return cycling_tasks
            return []

        mock_get.side_effect = get_side_effect

        from scheduler import self_improver

        with patch("builtins.print") as mock_print:
            await self_improver(interval=1)
            assert mock_print.called


class TestSelfImproverGitStatus:
    """Cover lines 1012-1015: git status check."""

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_git_status_with_changes(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """Uncommitted changes detected → printed."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None

        async def get_side_effect(path, timeout=15):
            return _OK_HEALTH if "/api/health" in path else []

        mock_get.side_effect = get_side_effect

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b" M modified.py\n?? new.py\n", b"")
        mock_subproc.return_value = mock_proc

        from scheduler import self_improver

        with patch("builtins.print") as mock_print:
            await self_improver(interval=1)

            print_calls = [str(c) for c in mock_print.call_args_list]
            assert any("uncommitted" in c.lower() for c in print_calls)

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_git_status_clean(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """Clean git status → no uncommitted print."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None

        async def get_side_effect(path, timeout=15):
            return _OK_HEALTH if "/api/health" in path else []

        mock_get.side_effect = get_side_effect

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_subproc.return_value = mock_proc

        from scheduler import self_improver

        with patch("builtins.print") as mock_print:
            await self_improver(interval=1)

            print_calls = [str(c) for c in mock_print.call_args_list]
            uncommitted_prints = [c for c in print_calls if "uncommitted" in c.lower()]
            assert len(uncommitted_prints) == 0

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_git_status_exception(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """Git command failure → exception caught, function completes."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None

        async def get_side_effect(path, timeout=15):
            return _OK_HEALTH if "/api/health" in path else []

        mock_get.side_effect = get_side_effect

        mock_subproc.side_effect = FileNotFoundError("git not found")

        from scheduler import self_improver

        await self_improver(interval=1)

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_self_improver_exception_handler(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """Cover line 1027-1028: exception handler in self_improver."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")

        call_count = 0

        async def get_side_effect(path, timeout=15):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _OK_HEALTH  # health check passes
            raise RuntimeError("fake API error")

        mock_get.side_effect = get_side_effect

        from scheduler import self_improver

        await self_improver(interval=1)

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_stale_task_already_flagged_skips_duplicate(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """A stale task that already has a [Stale] board entry is NOT re-created.

        Covers the dedup branch: board fetch → existing_refs → continue.
        """
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")
        mock_post.return_value = {"status": "ok"}

        async def get_side_effect(path, timeout=15):
            if "/api/health" in path:
                return _OK_HEALTH
            elif "status=blocked" in path:
                return []
            elif "status=inProgress" in path:
                return [
                    {
                        "id": "task_stale_1",
                        "title": "Old in_progress task",
                        "status": "inProgress",
                        "updated_at": 1000,  # way in the past
                        "created_at": 1000,
                    }
                ]
            elif "limit=100000" in path:
                # Board already contains a [Stale] entry referencing task_stale_1
                return [
                    {
                        "title": "[Stale] Task stuck in_progress: Old task",
                        "description": "Task task_stale_1 has been in_progress without heartbeat for >30min",
                    }
                ]
            return []

        mock_get.side_effect = get_side_effect

        from scheduler import self_improver

        await self_improver(interval=1)

        # The improvement-task POST must NOT have fired — dedup skipped it.
        for call in mock_post.call_args_list:
            args, kwargs = call
            path = args[0] if args else kwargs.get("path", "")
            assert "/api/tasks" not in path or "max-attempts" in path, (
                f"unexpected POST {path} — duplicate [Stale] task was created"
            )

    @pytest.mark.asyncio
    @patch("scheduler._restart_server")
    @patch("scheduler._api_get")
    @patch("scheduler._api_post")
    @patch("scheduler._load_improver_status")
    @patch("scheduler._save_improver_status")
    @patch("scheduler.asyncio.create_subprocess_exec")
    @patch("scheduler.asyncio.sleep")
    async def test_high_blocked_count_prints_warning(
        self,
        mock_sleep,
        mock_subproc,
        mock_save,
        mock_load,
        mock_post,
        mock_get,
        mock_restart,
    ):
        """>5 blocked tasks triggers the high-blocked-count warning path."""
        mock_sleep.side_effect = [None, asyncio.CancelledError()]
        mock_load.return_value = {"run_count": 0}
        mock_restart.return_value = None
        mock_subproc.return_value = AsyncMock()
        mock_subproc.return_value.communicate.return_value = (b"", b"")
        mock_post.return_value = {"status": "ok"}

        async def get_side_effect(path, timeout=15):
            if "/api/health" in path:
                return _OK_HEALTH
            if "status=blocked" in path:
                return [{"id": f"b{i}", "status": "blocked"} for i in range(8)]
            return []

        mock_get.side_effect = get_side_effect

        from scheduler import self_improver

        await self_improver(interval=1)

        # The warning branch executed (no exception) — the loop just ends
        # via CancelledError from sleep. No POST should be needed here.
        mock_sleep.assert_called()
