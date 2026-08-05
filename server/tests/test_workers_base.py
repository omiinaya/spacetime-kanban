"""Tests for server/workers/base.py — WorkerContext and shared lifecycle."""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.base import WorkerContext, _url, api_get, api_post, heartbeat_loop, run_worker


class TestUrlHelper:
    """_url() builds correct API URLs."""

    def test_simple_path(self):
        url = _url("/api/tasks")
        assert url == "http://localhost:8727/api/tasks"

    def test_path_with_encoding(self):
        url = _url("/api/tasks/task with spaces")
        assert "%20" in url

    def test_path_already_encoded(self):
        url = _url("/api/tasks/task%20id")
        assert url == "http://localhost:8727/api/tasks/task%20id"

    def test_strips_base_trailing_slash(self):
        url = _url("api/tasks")
        assert "//localhost:8727/api" in url


class TestApiGet:
    """api_get() handles server responses."""

    @patch("workers.base.urllib.request.urlopen")
    def test_success_dict(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_urlopen.return_value = mock_resp
        result = api_get("/api/health")
        assert result == {"status": "ok"}

    @patch("workers.base.urllib.request.urlopen")
    def test_success_list(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'[{"id": "1"}]'
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_urlopen.return_value = mock_resp
        result = api_get("/api/tasks")
        assert result == [{"id": "1"}]

    @patch("workers.base.urllib.request.urlopen")
    def test_http_error_returns_none(self, mock_urlopen):
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError("http://test", 503, "Service Unavailable", {}, None)
        result = api_get("/api/tasks")
        assert result is None

    @patch("workers.base.urllib.request.urlopen")
    def test_connection_error_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = ConnectionError("Connection refused")
        result = api_get("/api/nonexistent")
        assert result is None


class TestApiPost:
    """api_post() sends data and returns results."""

    @patch("workers.base.urllib.request.urlopen")
    def test_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value = mock_resp
        result = api_post("/api/tasks", {"title": "test"})
        assert result == {"status": "ok"}

    @patch("workers.base.urllib.request.urlopen")
    def test_empty_response_returns_default(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_urlopen.return_value = mock_resp
        result = api_post("/api/tasks/123/complete", {"result_notes": "done"})
        assert result == {"status": "ok"}

    @patch("workers.base.urllib.request.urlopen")
    def test_http_error_returns_none(self, mock_urlopen):
        from urllib.error import HTTPError

        # Create a proper mock HTTPError with bytes read()
        try:
            raise HTTPError("http://test", 400, "Bad Request", {}, None)
        except HTTPError as e:
            # The error object's read() needs to return bytes
            e.read = MagicMock(return_value=b"bad request")
            mock_urlopen.side_effect = e

        result = api_post("/api/tasks", {"title": "test"})
        assert result is None

    @patch("workers.base.urllib.request.urlopen")
    def test_generic_exception_returns_none(self, mock_urlopen):
        """Non-HTTP errors (connection refused, DNS, timeout) return None."""
        mock_urlopen.side_effect = ConnectionError("Connection refused")
        result = api_post("/api/tasks", {"title": "test"})
        assert result is None

    @patch("workers.base.urllib.request.Request")
    @patch("workers.base.urllib.request.urlopen")
    def test_request_has_content_type(self, mock_urlopen, mock_request):
        mock_request_instance = MagicMock()
        mock_request.return_value = mock_request_instance
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value = mock_resp

        api_post("/api/tasks", {"title": "test"})

        # Verify Content-Type header was set on the Request
        mock_request.assert_called_once()
        call_args, call_kwargs = mock_request.call_args
        assert call_kwargs.get("data") is not None
        # Check that add_header was called for Content-Type
        mock_request_instance.add_header.assert_any_call("Content-Type", "application/json")


class TestWorkerContext:
    """WorkerContext state management."""

    def test_init(self):
        ctx = WorkerContext("task_123")
        assert ctx.task_id == "task_123"
        assert ctx.task is None
        assert ctx._heartbeat_count == 0
        assert ctx._running is True

    def test_title_default(self):
        ctx = WorkerContext("task_123")
        assert ctx.title == "?"

    def test_title_from_task(self):
        ctx = WorkerContext("task_123")
        ctx.task = {"title": "My Task"}
        assert ctx.title == "My Task"

    def test_repo_default(self):
        ctx = WorkerContext("task_123")
        assert ctx.repo == ""

    def test_repo_path_none_when_no_repo(self):
        ctx = WorkerContext("task_123")
        assert ctx.repo_path is None

    @patch("workers.base.api_get")
    def test_load_task_success(self, mock_api_get):
        mock_api_get.return_value = {"id": "task_123", "title": "Test", "repo": "test-repo"}
        ctx = WorkerContext("task_123")
        result = ctx.load_task()
        assert result is True
        assert ctx.task["id"] == "task_123"
        assert ctx.title == "Test"

    @patch("workers.base.api_get")
    def test_load_task_failure(self, mock_api_get):
        mock_api_get.return_value = None
        ctx = WorkerContext("task_123")
        result = ctx.load_task()
        assert result is False
        assert ctx.task is None

    @patch("workers.base.api_get")
    @patch("workers.base.os.path.isdir", return_value=True)
    @patch("workers.base.os.path.expanduser", return_value="/home/test/tmp")
    def test_repo_path_with_existing_dir(
        self,
        mock_expanduser,
        mock_isdir,
        mock_api_get,
    ):
        """repo_path returns the path when the repo directory exists."""
        mock_api_get.return_value = {"id": "task_123", "title": "Test", "repo": "test-project"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "Test", "repo": "test-project"}
        path = ctx.repo_path
        assert path is not None
        assert "tmp" in path

    @patch("workers.base.api_post")
    def test_heartbeat(self, mock_api_post):
        mock_api_post.return_value = {"status": "ok"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.heartbeat()
        assert result is True
        assert ctx._heartbeat_count == 1

    @patch("workers.base.api_post")
    def test_heartbeat_failure(self, mock_api_post):
        mock_api_post.return_value = None
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.heartbeat()
        assert result is False
        assert ctx._heartbeat_count == 0

    @patch("workers.base.api_post")
    def test_add_log(self, mock_api_post):
        mock_api_post.return_value = {"status": "ok"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        ctx.add_log("test_action", "details")
        mock_api_post.assert_called_once()
        args = mock_api_post.call_args[0]
        assert "log" in args[0]

    @patch("workers.base.api_post")
    def test_complete(self, mock_api_post):
        mock_api_post.return_value = {"status": "completed"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.complete("All done")
        assert result is True
        assert ctx._running is False

    @patch("workers.base.api_post")
    def test_block(self, mock_api_post):
        mock_api_post.return_value = {"status": "blocked"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.block("Cannot proceed")
        assert result is True
        assert ctx._running is False

    @patch("workers.base.api_post")
    def test_permanent_block(self, mock_api_post):
        mock_api_post.return_value = {"status": "blocked"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.block("no indexable fields found")
        # Should use permanent-block endpoint
        assert result is True

    @patch("workers.base.api_post")
    def test_unclaim(self, mock_api_post):
        mock_api_post.return_value = {"status": "ok"}
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        result = ctx.unclaim()
        assert result is True
        assert ctx._running is False


class TestHeartbeatLoop:
    """heartbeat_loop() sends heartbeats on a timer."""

    @patch("workers.base.time.sleep", side_effect=InterruptedError)  # Exit immediately
    @patch("workers.base.WorkerContext.heartbeat", return_value=True)
    def test_stops_when_not_running(self, mock_heartbeat, mock_sleep):
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        ctx._running = False  # Already stopped
        thread = heartbeat_loop(ctx)
        thread.join(timeout=2)
        assert not thread.is_alive()

    @patch("workers.base.time.sleep", side_effect=[None, InterruptedError])
    @patch("workers.base.WorkerContext.heartbeat", return_value=True)
    def test_sends_heartbeats(self, mock_heartbeat, mock_sleep):
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        thread = heartbeat_loop(ctx)
        thread.join(timeout=3)
        assert mock_heartbeat.called

    @patch("workers.base.time.sleep", side_effect=[OSError("sleep failed"), None, InterruptedError])
    @patch("workers.base.WorkerContext.heartbeat", return_value=True)
    def test_survives_transient_sleep_failure(self, mock_heartbeat, mock_sleep):
        """A non-Interrupted sleep exception must not kill the loop."""
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        thread = heartbeat_loop(ctx)
        thread.join(timeout=3)
        # After the OSError the loop keeps beating, then InterruptedError exits.
        assert mock_heartbeat.called

    @patch("workers.base.time.sleep", side_effect=[None, InterruptedError])
    @patch("workers.base.WorkerContext.heartbeat", side_effect=[RuntimeError("api down")])
    def test_survives_heartbeat_failure(self, mock_heartbeat, mock_sleep):
        """A failed heartbeat must not kill the loop (fire-and-forget)."""
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123"}
        thread = heartbeat_loop(ctx)
        thread.join(timeout=3)
        assert not thread.is_alive()


class TestRunWorker:
    """run_worker() orchestrates the full worker lifecycle."""

    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=True)
    @patch("workers.base.WorkerContext.complete", return_value=True)
    def test_success_path(self, mock_complete, mock_load, mock_hb_loop):
        def work_fn(ctx):
            return True, "Task done"

        exit_code = run_worker("task_123", work_fn, timeout=30)
        assert exit_code == 0
        mock_complete.assert_called_once()

    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=True)
    @patch("workers.base.WorkerContext.block", return_value=True)
    def test_blocked_path(self, mock_block, mock_load, mock_hb_loop):
        def work_fn(ctx):
            return False, "Cannot proceed"

        exit_code = run_worker("task_123", work_fn, timeout=30)
        assert exit_code == 1
        mock_block.assert_called_once()

    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=False)
    def test_cannot_load_task(self, mock_load, mock_hb_loop):
        exit_code = run_worker("task_123", lambda ctx: (True, ""), timeout=30)
        assert exit_code == 2

    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=True)
    @patch("workers.base.WorkerContext.block", return_value=True)
    def test_timeout(self, mock_block, mock_load, mock_hb_loop):
        def slow_work(ctx):
            import time

            time.sleep(10)
            return True, "Done"

        exit_code = run_worker("task_123", slow_work, timeout=1)
        assert exit_code == 2

    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=True)
    @patch("workers.base.WorkerContext.block", return_value=True)
    def test_worker_crash(self, mock_block, mock_load, mock_hb_loop):
        def crashing_work(ctx):
            raise RuntimeError("Something went wrong")

        exit_code = run_worker("task_123", crashing_work, timeout=30)
        assert exit_code == 2
        mock_block.assert_called_once()

    @patch.dict(os.environ, {"KANBAN_LLM_TIMEOUT": "60"}, clear=False)
    @patch("workers.base.heartbeat_loop")
    @patch("workers.base.WorkerContext.load_task", return_value=True)
    @patch("workers.base.WorkerContext.complete", return_value=True)
    def test_timeout_default_from_env(self, mock_complete, mock_load, mock_hb_loop):
        """run_worker uses env var default when timeout=0."""

        def work_fn(ctx):
            return True, "Done"

        exit_code = run_worker("task_123", work_fn, timeout=0)
        assert exit_code == 0
        mock_complete.assert_called_once()


class TestWorktreeIsolation:
    """WorkerContext worktree isolation — each task works in its own worktree."""

    def _make_ctx(self, repo="test-repo", task_id="task_abc123"):
        ctx = WorkerContext(task_id)
        ctx.task = {"id": task_id, "title": "Test", "repo": repo, "description": ""}
        return ctx

    def test_repo_path_uses_worktree_when_set(self, tmp_path):
        ctx = self._make_ctx()
        ctx._worktree_path = str(tmp_path / "wt")
        (tmp_path / "wt").mkdir(parents=True)
        assert ctx.repo_path == str(tmp_path / "wt")

    def test_repo_path_falls_back_to_main_clone(self):
        ctx = self._make_ctx()
        ctx._worktree_path = "/nonexistent/wt"
        # repo "test-repo" won't exist at ~/test-repo → None
        assert ctx.repo_path is None

    @patch("subprocess.run")
    def test_setup_worktree_creates_and_sets_path(self, mock_run, tmp_path):
        main_clone = tmp_path / "test-repo"
        (main_clone / ".git").mkdir(parents=True)
        wt_path = tmp_path / "test-repo-kanban-taskabc123"  # safe_id strips '_'
        # worktree add succeeds (creates the dir as git would)
        wt_path.mkdir(parents=True)
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with patch(
            "os.path.expanduser",
            side_effect=lambda p: str(wt_path) if "kanban" in p else str(main_clone),
        ):
            ctx = self._make_ctx()
            result = ctx.setup_worktree()
        assert result is not None
        assert ctx._worktree_path == str(wt_path)

    @patch("subprocess.run")
    def test_setup_worktree_returns_none_when_not_git(self, mock_run, tmp_path):
        main_clone = tmp_path / "test-repo"
        main_clone.mkdir(parents=True)  # no .git
        with patch("os.path.expanduser", return_value=str(main_clone)):
            ctx = self._make_ctx()
            assert ctx.setup_worktree() is None

    @patch("subprocess.run")
    def test_setup_worktree_failure_falls_back(self, mock_run, tmp_path):
        main_clone = tmp_path / "test-repo"
        (main_clone / ".git").mkdir(parents=True)
        # worktree add fails
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: branch exists")
        with patch("os.path.expanduser", return_value=str(main_clone)):
            ctx = self._make_ctx()
            assert ctx.setup_worktree() is None
        assert ctx._worktree_path is None

    @patch("subprocess.run")
    def test_teardown_worktree_noop_when_none(self, mock_run):
        ctx = self._make_ctx()
        ctx._worktree_path = None
        ctx.teardown_worktree()
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_teardown_worktree_removes(self, mock_run, tmp_path):
        main_clone = tmp_path / "test-repo"
        (main_clone / ".git").mkdir(parents=True)
        wt_path = tmp_path / "test-repo-kanban-taskabc123"
        wt_path.mkdir(parents=True)
        with patch("os.path.expanduser", return_value=str(main_clone)):
            ctx = self._make_ctx()
            ctx._worktree_path = str(wt_path)
            ctx.teardown_worktree()
        assert ctx._worktree_path is None
        assert mock_run.call_count >= 3  # push + worktree remove + prune

    @patch("subprocess.run")
    def test_teardown_worktree_exception_safe(self, mock_run):
        mock_run.side_effect = RuntimeError("git exploded")
        ctx = self._make_ctx()
        ctx._worktree_path = "/tmp/some-wt"
        ctx.teardown_worktree()  # must not raise
        assert ctx._worktree_path is None
