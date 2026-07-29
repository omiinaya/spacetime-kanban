"""Tests for scheduler.py — helpers, worker management, API wrappers.

Focuses on the testable components: HTTP helpers, worker lifecycle,
crash detection. Scheduler infinite loops are tested via integration/E2E.
"""

import subprocess
import time
from unittest.mock import AsyncMock, MagicMock, patch

# ── _get_client ────────────────────────────────────────────────────────


class TestGetClient:
    def test_singleton(self):
        """_get_client() returns same instance on repeated calls."""
        import scheduler

        scheduler._client = None
        c1 = scheduler._get_client()
        c2 = scheduler._get_client()
        assert c1 is c2

    def test_reset_between_tests(self):
        """Clear module state so each test starts fresh."""
        import scheduler

        scheduler._client = None


# ── _api_get ───────────────────────────────────────────────────────────


class TestApiGet:
    @patch("scheduler._get_client")
    async def test_successful_get(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": "ok"}
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_get

        result = await _api_get("/api/health")
        assert result == {"data": "ok"}

    @patch("scheduler._get_client")
    async def test_non_200_returns_none(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_get

        result = await _api_get("/api/nonexistent")
        assert result is None

    @patch("scheduler._get_client")
    async def test_exception_returns_none(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Connection refused")
        mock_get_client.return_value = mock_client

        from scheduler import _api_get

        result = await _api_get("/api/health")
        assert result is None

    @patch("scheduler._get_client")
    async def test_quotes_unencoded_path(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        mock_client.get.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_get

        await _api_get("/api/tasks?status=in progress")
        call_url = mock_client.get.call_args[0][0]
        assert "%20" in call_url


# ── _api_post ──────────────────────────────────────────────────────────


class TestApiPost:
    @patch("scheduler._get_client")
    async def test_successful_post(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b'{"status": "ok"}'
        mock_resp.json.return_value = {"status": "ok"}
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_post

        result = await _api_post("/api/tasks", {"title": "test"})
        assert result == {"status": "ok"}

    @patch("scheduler._get_client")
    async def test_500_returns_none(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.content = b"error"
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_post

        result = await _api_post("/api/tasks", {"title": "test"})
        assert result is None

    @patch("scheduler._get_client")
    async def test_empty_content_returns_default(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.content = b""
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_post

        result = await _api_post("/api/tasks", {"title": "test"})
        assert result == {"status": "ok"}

    @patch("scheduler._get_client")
    async def test_exception_returns_none(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("Timeout")
        mock_get_client.return_value = mock_client

        from scheduler import _api_post

        result = await _api_post("/api/tasks", {})
        assert result is None


# ── _api_delete ────────────────────────────────────────────────────────


class TestApiDelete:
    @patch("scheduler._get_client")
    async def test_successful_delete(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.delete.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_delete

        result = await _api_delete("/api/tasks/task_1")
        assert result is True

    @patch("scheduler._get_client")
    async def test_non_200_returns_false(self, mock_get_client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_client.delete.return_value = mock_resp
        mock_get_client.return_value = mock_client

        from scheduler import _api_delete

        result = await _api_delete("/api/tasks/task_1")
        assert result is False

    @patch("scheduler._get_client")
    async def test_exception_returns_false(self, mock_get_client):
        mock_client = AsyncMock()
        mock_client.delete.side_effect = Exception("Error")
        mock_get_client.return_value = mock_client

        from scheduler import _api_delete

        result = await _api_delete("/api/tasks/task_1")
        assert result is False


# ── _now_ms ────────────────────────────────────────────────────────────


class TestNowMs:
    def test_returns_recent_timestamp(self):
        from scheduler import _now_ms

        now = _now_ms()
        # Should be close to current time
        import time as tm

        assert abs(now - int(tm.time() * 1000)) < 5000


# ── _get_worker_count ──────────────────────────────────────────────────


class TestGetWorkerCount:
    def test_no_workers(self):
        import scheduler

        scheduler._worker_processes = {}
        assert scheduler._get_worker_count() == 0

    def test_one_alive_worker(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # None = still running
        scheduler._worker_processes = {"task_1": mock_proc}
        assert scheduler._get_worker_count() == 1

    def test_dead_worker_not_counted(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 0  # exited cleanly
        scheduler._worker_processes = {"task_1": mock_proc}
        assert scheduler._get_worker_count() == 0

    def test_mixed_workers(self):
        import scheduler

        alive = MagicMock(spec=subprocess.Popen)
        alive.poll.return_value = None
        dead = MagicMock(spec=subprocess.Popen)
        dead.poll.return_value = 1
        scheduler._worker_processes = {"task_1": alive, "task_2": dead}
        assert scheduler._get_worker_count() == 1

    def test_none_process_not_counted(self):
        import scheduler

        scheduler._worker_processes = {"task_1": None}
        assert scheduler._get_worker_count() == 0


# ── _check_crashed_workers ─────────────────────────────────────────────


class TestCheckCrashedWorkers:
    def test_no_crashed(self):
        import scheduler

        scheduler._worker_processes = {}
        scheduler._worker_spawn_times = {}
        assert scheduler._check_crashed_workers() == []

    def test_detects_crashed_worker(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 1  # exited with error
        now = time.monotonic()
        scheduler._worker_processes = {"task_1": mock_proc}
        scheduler._worker_spawn_times = {"task_1": now - 5.0}  # 5s ago
        scheduler._worker_crash_counts = {}

        result = scheduler._check_crashed_workers()
        assert len(result) == 1
        assert result[0][0] == "task_1"
        assert result[0][1] == 1  # exit code

    def test_immediate_crash_increments_counter(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 1
        now = time.monotonic()
        scheduler._worker_processes = {"task_1": mock_proc}
        # Spawned just 0.5s ago — within immediate crash threshold
        scheduler._worker_spawn_times = {"task_1": now - 0.5}
        scheduler._worker_crash_counts = {}

        scheduler._check_crashed_workers()
        assert scheduler._worker_crash_counts.get("task_1") == 1

    def test_late_crash_resets_counter(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 1
        now = time.monotonic()
        scheduler._worker_processes = {"task_1": mock_proc}
        # Spawned 30s ago — not an immediate crash
        scheduler._worker_spawn_times = {"task_1": now - 30}
        scheduler._worker_crash_counts = {"task_1": 3}

        scheduler._check_crashed_workers()
        # Counter should be reset (popped)
        assert "task_1" not in scheduler._worker_crash_counts

    def test_running_process_not_crashed(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # still running
        scheduler._worker_processes = {"task_1": mock_proc}
        scheduler._worker_spawn_times = {"task_1": time.monotonic()}

        result = scheduler._check_crashed_workers()
        assert result == []


# ── _reset_worker_crash_count ──────────────────────────────────────────


class TestResetWorkerCrashCount:
    def test_resets_existing_counter(self):
        import scheduler

        scheduler._worker_crash_counts = {"task_1": 5}
        scheduler._reset_worker_crash_count("task_1")
        assert "task_1" not in scheduler._worker_crash_counts

    def test_handles_missing_key(self):
        import scheduler

        scheduler._worker_crash_counts = {}
        scheduler._reset_worker_crash_count("nonexistent")
        assert scheduler._worker_crash_counts == {}


# ── _kill_worker ───────────────────────────────────────────────────────


class TestKillWorker:
    def test_kills_running_worker(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # still running
        scheduler._worker_processes = {"task_1": mock_proc}
        scheduler._worker_spawn_times = {"task_1": 1000.0}

        assert scheduler._kill_worker("task_1") is True
        mock_proc.kill.assert_called_once()
        assert "task_1" not in scheduler._worker_processes

    def test_handles_already_dead(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 0  # already dead
        scheduler._worker_processes = {"task_1": mock_proc}

        assert scheduler._kill_worker("task_1") is False
        mock_proc.kill.assert_not_called()

    def test_handles_missing_task(self):
        import scheduler

        scheduler._worker_processes = {}
        assert scheduler._kill_worker("nonexistent") is False

    def test_kill_exception(self):
        import scheduler

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.kill.side_effect = Exception("Kill failed")
        scheduler._worker_processes = {"task_1": mock_proc}

        # Should not raise — exception is caught
        assert scheduler._kill_worker("task_1") is False


# ── _spawn_worker ──────────────────────────────────────────────────────


class TestSpawnWorker:
    @patch("scheduler.settings")
    def test_no_script_no_args_returns_false(self, mock_settings):
        mock_settings.worker_script = ""
        mock_settings.worker_args = ""

        from scheduler import _spawn_worker

        assert _spawn_worker("task_1", "title", "repo") is False

    @patch("scheduler.settings")
    @patch("scheduler.subprocess.Popen")
    def test_script_path_used(self, mock_popen, mock_settings):
        mock_settings.worker_script = "worker.py"
        mock_settings.worker_args = ""
        mock_settings.worker_command = "python3"
        mock_settings.server_port = 8727
        mock_settings.agent_id = "test-agent"
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        from scheduler import _spawn_worker

        result = _spawn_worker("task_1", "My Task", "my-repo")
        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "python3"
        assert cmd[1].endswith("worker.py")
        assert cmd[2] == "task_1"

    @patch("scheduler.settings")
    @patch("scheduler.subprocess.Popen")
    def test_args_mode(self, mock_popen, mock_settings):
        mock_settings.worker_script = ""
        mock_settings.worker_args = "-m workers.run"
        mock_settings.worker_command = "python3"
        mock_settings.server_port = 8727
        mock_settings.agent_id = "test-agent"
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        from scheduler import _spawn_worker

        result = _spawn_worker("task_1", "title", "repo")
        assert result is True
        cmd = mock_popen.call_args[0][0]
        assert "-m" in cmd
        assert "workers.run" in cmd
        assert "task_1" in cmd

    @patch("scheduler.settings")
    @patch("scheduler.subprocess.Popen")
    def test_env_vars_included(self, mock_popen, mock_settings):
        mock_settings.worker_script = "worker.py"
        mock_settings.worker_args = ""
        mock_settings.worker_command = "python3"
        mock_settings.server_port = 8727
        mock_settings.agent_id = "test-agent"
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        from scheduler import _spawn_worker

        _spawn_worker("task_1", "title", "repo")
        env = mock_popen.call_args[1]["env"]
        assert env["KANBAN_API"] == "http://localhost:8727"
        assert env["AGENT_ID"] == "test-agent"
        assert env["KANBAN_LLM_TIMEOUT"] == "3600"

    @patch("scheduler.settings")
    @patch("scheduler.subprocess.Popen")
    def test_spawn_exception_returns_false(self, mock_popen, mock_settings):
        mock_settings.worker_script = "worker.py"
        mock_settings.worker_args = ""
        mock_settings.worker_command = "python3"
        mock_settings.server_port = 8727
        mock_settings.agent_id = "test-agent"
        mock_popen.side_effect = Exception("No such file")

        from scheduler import _spawn_worker

        assert _spawn_worker("task_1", "title", "repo") is False
