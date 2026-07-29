"""Tests for server/workers/run.py — worker entry point and task router."""

import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, ".")

from workers.run import route_task


class TestRouteTask:
    """route_task() routes to mechanical or LLM worker."""

    def test_mechanical_handler_matched(self):
        """When a mechanical handler matches the title, it gets used."""
        from workers.base import WorkerContext

        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "fix clippy warning", "repo": "test-repo"}

        def mock_handler(ctx):
            return (True, "Fixed clippy")

        with (
            patch("workers.run.match_handler", return_value=mock_handler),
            patch("workers.run.run_llm_worker") as mock_llm,
            patch("workers.base.WorkerContext.add_log"),
        ):
            success, message = route_task(ctx)

            assert success is True
            assert "Fixed clippy" in message
            mock_llm.assert_not_called()

    def test_llm_fallback_when_no_pattern_matches(self):
        """When no mechanical handler matches, LLM worker is used."""
        from workers.base import WorkerContext

        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "Research market trends", "repo": "test-repo"}

        with (
            patch("workers.run.match_handler", return_value=None),
            patch("workers.run.run_llm_worker", return_value=(True, "Research done")),
        ):
            success, message = route_task(ctx)

            assert success is True
            assert "Research done" in message

    def test_llm_blocked_propagates(self):
        """LLM worker blocked result propagates through route_task."""
        from workers.base import WorkerContext

        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "Complex refactor", "repo": "test-repo"}

        with (
            patch("workers.run.match_handler", return_value=None),
            patch("workers.run.run_llm_worker", return_value=(False, "Cannot refactor")),
        ):
            success, message = route_task(ctx)

            assert success is False
            assert "Cannot refactor" in message

    def test_mechanical_blocked_propagates(self):
        """Mechanical handler blocked result propagates."""
        from workers.base import WorkerContext

        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "fix clippy error in auth", "repo": "test-repo"}

        def mock_handler(ctx):
            return (False, "Rust not installed")

        with (
            patch("workers.run.match_handler", return_value=mock_handler),
            patch("workers.run.run_llm_worker") as mock_llm,
            patch("workers.base.WorkerContext.add_log"),
        ):
            success, message = route_task(ctx)

            assert success is False
            assert "Rust not installed" in message
            mock_llm.assert_not_called()


class TestMain:
    """main() parses args and calls run_worker."""

    def test_main_calls_run_worker(self):
        """main() should call run_worker with the task_id."""
        from workers.run import main

        with (
            patch("workers.run.run_worker", return_value=0) as mock_run,
            patch.object(sys, "argv", ["run.py", "task_123"]),
            patch.object(sys, "exit"),
        ):
            main()
            mock_run.assert_called_once_with("task_123", route_task)

    def test_main_exits_2_without_args(self):
        """main() should exit 2 when no task_id provided."""
        from workers.run import main

        with (
            patch.object(sys, "argv", ["run.py"]),
            patch.object(sys, "exit", side_effect=SystemExit) as mock_exit,
        ):
            with pytest.raises(SystemExit):
                main()
            mock_exit.assert_called_once_with(2)

    def test_main_exits_with_worker_code(self):
        """main() exits with the code from run_worker."""
        from workers.run import main

        with (
            patch("workers.run.run_worker", return_value=1),
            patch.object(sys, "argv", ["run.py", "task_123"]),
            patch.object(sys, "exit") as mock_exit,
        ):
            main()
            mock_exit.assert_called_once_with(1)
