"""Tests for server/scheduler.py — task lifecycle, stale detection, worker spawning."""

import time
from unittest.mock import MagicMock, patch

from server.scheduler import (
    _check_crashed_workers,
    _get_client,
    _get_worker_count,
    _kill_worker,
    _now_ms,
    _reset_worker_crash_count,
    _spawn_worker,
    _worker_crash_counts,
    _worker_processes,
    _worker_spawn_times,
)


class TestScheduler:
    """Test suite for scheduler.py — worker management, crash detection, lifecycle."""

    def teardown_method(self):
        """Clean up module-level state between tests."""
        _worker_processes.clear()
        _worker_spawn_times.clear()
        _worker_crash_counts.clear()

    # ── task_dispatcher: archived filter ──────────────────────────────

    @patch("server.scheduler.settings")
    async def test_dispatcher_excludes_archived_tasks(self, mock_settings):
        """task_dispatcher must fetch available tasks with archived=false.

        Regression: the dispatcher previously fetched
        ``/api/tasks?status=available&limit=200`` WITHOUT the archived
        filter. Tasks archived by the scanner's stale-closer (or the
        archiver) stayed status=available and got re-dispatched to
        workers — burning turns on tasks removed from the active board.
        """
        import asyncio

        import server.scheduler as sched_mod

        mock_settings.worker_script = "python3 run.py"
        mock_settings.max_workers = 10
        mock_settings.max_memory_pct = 99.0
        mock_settings.agent_id = "hermes"

        calls = []

        async def fake_get(path):
            calls.append(path)
            if "archived=false" in path:
                return []  # no available (non-archived) tasks → no spawn
            return None

        with (
            patch.object(sched_mod, "_api_get", side_effect=fake_get),
            patch.object(sched_mod, "_get_worker_count", return_value=0),
        ):
            task = asyncio.create_task(sched_mod.task_dispatcher(0.01))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        assert calls, "dispatcher never fetched available tasks"
        assert all("archived=false" in c for c in calls), (
            f"dispatcher fetched without archived filter: {calls}"
        )

    # ── _now_ms ────────────────────────────────────────────────────────

    def test_now_ms_returns_integer(self):
        """_now_ms() should return a reasonable integer timestamp."""
        result = _now_ms()
        assert isinstance(result, int)
        # Should be roughly current epoch in ms
        now = int(time.time() * 1000)
        assert abs(result - now) < 5000  # Within 5 seconds

    # ── _spawn_worker ──────────────────────────────────────────────────

    @patch("server.scheduler.settings")
    @patch("server.scheduler.subprocess.Popen")
    def test_spawn_worker_returns_false_when_no_script_or_args(self, mock_popen, mock_settings):
        """_spawn_worker returns False when neither worker_script nor worker_args is set."""
        mock_settings.worker_script = ""
        mock_settings.worker_args = ""
        result = _spawn_worker("task_123", "Test Task", "test-repo")
        assert result is False
        mock_popen.assert_not_called()

    @patch("server.scheduler.settings")
    @patch("server.scheduler.subprocess.Popen")
    def test_spawn_worker_with_py_script(self, mock_popen, mock_settings):
        """_spawn_worker with a .py script should invoke python3 <script> <task_id>."""
        mock_settings.worker_script = "worker.py"
        mock_settings.worker_args = ""
        mock_settings.worker_command = "python3"
        mock_settings.agent_id = "test-agent"
        mock_settings.server_port = 8727
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        result = _spawn_worker("task_abc123", "Fix bug", "spacetime-kanban")

        assert result is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "python3" in args
        assert "task_abc123" in args
        assert _worker_processes["task_abc123"] == mock_proc
        assert "task_abc123" in _worker_spawn_times

    @patch("server.scheduler.settings")
    @patch("server.scheduler.subprocess.Popen")
    def test_spawn_worker_with_args_mode(self, mock_popen, mock_settings):
        """_spawn_worker with worker_args should invoke python3 <args> <task_id>."""
        mock_settings.worker_script = ""
        mock_settings.worker_args = "-m server.workers.run"
        mock_settings.worker_command = "python3"
        mock_settings.agent_id = "test-agent"
        mock_settings.server_port = 8727
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        result = _spawn_worker("task_xyz", "Deploy", "repo1")

        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert "python3" in cmd[0]
        assert "-m" in cmd
        assert "server.workers.run" in cmd
        assert "task_xyz" in cmd

    @patch("server.scheduler.settings")
    @patch("server.scheduler.subprocess.Popen")
    def test_spawn_worker_env_includes_kv_params(self, mock_popen, mock_settings):
        """Environment passed to subprocess should include KANBAN_API and AGENT_ID."""
        mock_settings.worker_script = "worker.py"
        mock_settings.worker_args = ""
        mock_settings.worker_command = "python3"
        mock_settings.agent_id = "hermes-test"
        mock_settings.server_port = 9876

        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        _spawn_worker("task_001", "Test", "my-repo")

        env = mock_popen.call_args[1]["env"]
        assert env["KANBAN_API"] == "http://localhost:9876"
        assert env["AGENT_ID"] == "hermes-test"
        # Verify Hermes gateway vars are stripped
        assert env.get("_HERMES_GATEWAY") == ""
        assert env.get("HERMES_SESSION_ID") == ""

    # ── _get_worker_count ──────────────────────────────────────────────

    def test_get_worker_count_empty(self):
        """No workers registered returns 0."""
        _worker_processes.clear()
        assert _get_worker_count() == 0

    def test_get_worker_count_alive_only(self):
        """Only processes with poll() returning None should be counted."""
        alive = MagicMock()
        alive.poll.return_value = None
        dead = MagicMock()
        dead.poll.return_value = 0

        _worker_processes["task_a"] = alive
        _worker_processes["task_b"] = dead

        assert _get_worker_count() == 1

    # ── _check_crashed_workers ────────────────────────────────────────

    def test_check_crashed_workers_empty(self):
        """No workers => no crashes."""
        _worker_processes.clear()
        assert _check_crashed_workers() == []

    def test_check_crashed_workers_detects_dead(self):
        """A worker with non-None poll() should appear in crashed list."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 2  # non-zero exit = crash

        _worker_processes["task_crash"] = mock_proc
        _worker_spawn_times["task_crash"] = time.monotonic() - 10  # 10s ago

        crashed = _check_crashed_workers()
        assert len(crashed) == 1
        tid, exit_code, spawn_time = crashed[0]
        assert tid == "task_crash"
        assert exit_code == 2
        assert spawn_time > 0

    def test_check_crashed_workers_increments_crash_count_on_immediate_death(self):
        """A worker dying within _IMMEDIATE_CRASH_THRESHOLD (3s) should increment crash count."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1

        _worker_processes["task_immediate"] = mock_proc
        _worker_spawn_times["task_immediate"] = time.monotonic()  # just spawned
        _worker_crash_counts.clear()

        _check_crashed_workers()

        assert _worker_crash_counts.get("task_immediate", 0) == 1

    def test_check_crashed_workers_resets_crash_count_on_late_death(self):
        """A worker dying after the threshold should have crash count cleared."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1

        _worker_processes["task_late"] = mock_proc
        _worker_spawn_times["task_late"] = time.monotonic() - 10  # 10s ago (> 3s threshold)
        _worker_crash_counts["task_late"] = 2  # previously had 2 crashes

        _check_crashed_workers()

        # crash count should be popped (not 2)
        assert _worker_crash_counts.get("task_late") is None

    def test_check_crashed_workers_skips_alive(self):
        """Alive workers should not be in crashed list."""
        alive = MagicMock()
        alive.poll.return_value = None  # still running

        _worker_processes["task_alive"] = alive
        _worker_spawn_times["task_alive"] = time.monotonic()

        assert _check_crashed_workers() == []

    # ── _kill_worker ───────────────────────────────────────────────────

    def test_kill_worker_nonexistent(self):
        """Killing a non-existent worker returns False."""
        assert _kill_worker("no_such_task") is False

    def test_kill_worker_alive(self):
        """Killing an alive worker should call kill() and return True."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive

        _worker_processes["task_kill"] = mock_proc
        _worker_spawn_times["task_kill"] = time.monotonic()

        result = _kill_worker("task_kill")
        assert result is True
        mock_proc.kill.assert_called_once()
        assert "task_kill" not in _worker_processes
        assert "task_kill" not in _worker_spawn_times

    def test_kill_worker_already_dead(self):
        """Killing a worker that already exited should not call kill() and return False."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already dead

        _worker_processes["task_dead"] = mock_proc
        _worker_spawn_times["task_dead"] = time.monotonic()

        result = _kill_worker("task_dead")
        assert result is False
        mock_proc.kill.assert_not_called()
        assert "task_dead" not in _worker_processes

    # ── _reset_worker_crash_count ──────────────────────────────────────

    def test_reset_worker_crash_count(self):
        """Resetting crash count should remove the entry."""
        _worker_crash_counts["task_retry"] = 3
        _reset_worker_crash_count("task_retry")
        assert _worker_crash_counts.get("task_retry") is None

    def test_reset_worker_crash_count_nonexistent(self):
        """Resetting a non-existent crash count should not raise."""
        _worker_crash_counts.clear()
        _reset_worker_crash_count("no_such_task")  # Should not raise

    # ── _get_client ────────────────────────────────────────────────────

    def test_get_client_creates_singleton(self):
        """_get_client should return the same client instance on repeated calls."""
        import server.scheduler as sched_mod

        # Save original and force None
        orig = sched_mod._client
        sched_mod._client = None
        try:
            client1 = _get_client()
            client2 = _get_client()
            assert client1 is client2
        finally:
            # Clean up to avoid warnings
            if sched_mod._client is not None:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                loop.run_until_complete(sched_mod._client.aclose())
            sched_mod._client = orig
