"""Final coverage push — targeting remaining scheduler + low_backlog lines for 80%.

SleepController: first sleep completes (loop body runs), Nth raises CancelledError.
"""

import asyncio
import json
import os
import tempfile
from unittest import mock

import pytest

import scheduler
import scheduler_low_backlog

_real_sleep = asyncio.sleep


class SC:
    def __init__(self, cancel_on=2):
        self.calls = 0
        self.cancel_on = cancel_on

    async def __call__(self, interval):
        self.calls += 1
        if self.calls >= self.cancel_on:
            raise asyncio.CancelledError()
        await _real_sleep(0.001)


# ═══════════════════════════════════════════════════════════════════════
# scheduler_low_backlog.py — remaining
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_low_backlog_api_post_200():
    """_api_post returns JSON on 200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ok"}
    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.post.return_value = mock_resp
        result = await scheduler_low_backlog._api_post("/api/tasks/claim", {"a": 1})
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_low_backlog_api_post_non200():
    """_api_post returns None on non-200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 500
    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.post.return_value = mock_resp
        result = await scheduler_low_backlog._api_post("/api/tasks/claim", {"a": 1})
    assert result is None


@pytest.mark.asyncio
async def test_low_backlog_api_post_exception():
    """_api_post returns None on exception."""
    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.post.side_effect = Exception("Fail")
        result = await scheduler_low_backlog._api_post("/api/tasks/claim", {"a": 1})
    assert result is None


@pytest.mark.asyncio
async def test_low_backlog_trigger_scanner_success_creates():
    """Lines 71-73: scanner success with created tasks."""
    scheduler_low_backlog._scanner_running = False
    with mock.patch.object(scheduler_low_backlog, "_scanner_running", False):

        async def fake_executor(*args, **kwargs):
            return {"repo1": {"created": 3}, "repo2": {"created": 2}}

        with mock.patch("asyncio.get_event_loop") as mel:
            mel.return_value.run_in_executor.side_effect = fake_executor
            result = await scheduler_low_backlog._trigger_scanner()
            assert isinstance(result, dict)
            total = sum(c.get("created", 0) for c in result.values())
            assert total == 5


@pytest.mark.asyncio
async def test_low_backlog_generate_improvement_tasks_with_files():
    """Lines 102-203: generates tasks from improvement files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create an IMPROVEMENTS.md with headings
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        with open(imp_path, "w") as f:
            f.write(
                "# Improvements\n## Add unit tests for the API layer\n## Refactor the database module\n"
            )

        repos = [("test-repo", tmpdir)]

        with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch(
                    "scheduler_low_backlog.discover_repos", return_value=repos, create=True
                ):
                    count = await scheduler_low_backlog._generate_improvement_tasks()
                    assert count >= 2


@pytest.mark.asyncio
async def test_low_backlog_generate_improvement_exception():
    """Line 106-107: returns 0 when discover_repos fails."""
    with mock.patch(
        "scanners.runner.discover_repos", side_effect=ImportError("No scanners"), create=True
    ):
        count = await scheduler_low_backlog._generate_improvement_tasks()
    assert count == 0


@pytest.mark.asyncio
async def test_low_backlog_generate_improvement_ci_badge():
    """Lines 167-201: creates CI badge task when missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CI workflow dir + README without badge
        workflows_dir = os.path.join(tmpdir, ".github", "workflows")
        os.makedirs(workflows_dir)
        with open(os.path.join(workflows_dir, "test.yml"), "w") as f:
            f.write("name: CI\n")
        with open(os.path.join(tmpdir, "README.md"), "w") as f:
            f.write("# Test Project\nThis is a test.\n")

        repos = [("test-repo", tmpdir)]

        with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch(
                    "scheduler_low_backlog.discover_repos", return_value=repos, create=True
                ):
                    count = await scheduler_low_backlog._generate_improvement_tasks()
                    assert count >= 1


@pytest.mark.asyncio
async def test_low_backlog_check_backlog_critical():
    """Critical backlog: actionable <= 3 and done > 5."""
    scheduler_low_backlog._last_trigger_ms = 0
    overview = {"by_status": {"available": 2}, "total_done": 50}

    with mock.patch.object(
        scheduler_low_backlog, "_get_actionable_available_count", return_value=2
    ):
        with mock.patch.object(
            scheduler_low_backlog,
            "_trigger_scanner",
            return_value={"repo1": {"created": 3}},
        ):
            result = await scheduler_low_backlog.check_backlog_and_trigger(overview)
    assert result is True


@pytest.mark.asyncio
async def test_low_backlog_check_backlog_scanner_found_nothing():
    """Lines 263-268: scanner found nothing → generate improvement tasks."""
    scheduler_low_backlog._last_trigger_ms = 0
    overview = {"by_status": {"available": 5}, "total_done": 50}

    with mock.patch.object(
        scheduler_low_backlog, "_get_actionable_available_count", return_value=5
    ):
        with mock.patch.object(
            scheduler_low_backlog,
            "_trigger_scanner",
            return_value={"repo1": {"created": 0}},
        ):
            with mock.patch.object(
                scheduler_low_backlog, "_generate_improvement_tasks", return_value=2
            ):
                result = await scheduler_low_backlog.check_backlog_and_trigger(overview)
    assert result is True


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _restart_server
# ═══════════════════════════════════════════════════════════════════════


def test_restart_server():
    """Lines 918-921: prints exit message and calls os._exit(42)."""
    with mock.patch("os._exit") as mock_exit:
        with mock.patch("builtins.print") as mp:
            scheduler._restart_server()
            mp.assert_called_with(
                "[scheduler:self-heal] Exiting with code 42 for service manager restart"
            )
            mock_exit.assert_called_once_with(42)


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _load_improver_status / _save_improver_status
# ═══════════════════════════════════════════════════════════════════════


def test_load_improver_status_missing():
    """Line 1049: returns empty dict when file missing."""
    with mock.patch.object(scheduler, "_IMPROVER_STATUS_FILE", "/tmp/nonexistent_file_xyz.json"):
        result = scheduler._load_improver_status()
    assert result == {}


def test_load_improver_status_exists():
    """Lines 1044-1045: loads and returns JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"run_count": 5, "last_run": 1000}, f)
        fname = f.name
    try:
        with mock.patch.object(scheduler, "_IMPROVER_STATUS_FILE", fname):
            result = scheduler._load_improver_status()
        assert result == {"run_count": 5, "last_run": 1000}
    finally:
        os.unlink(fname)


def test_load_improver_status_corrupt():
    """Lines 1046-1048: returns empty on corrupt JSON."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not valid json{{{")
        fname = f.name
    try:
        with mock.patch.object(scheduler, "_IMPROVER_STATUS_FILE", fname):
            result = scheduler._load_improver_status()
        assert result == {}
    finally:
        os.unlink(fname)


def test_save_improver_status():
    """Lines 1053-1057: saves status to file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        fname = f.name
    try:
        with mock.patch.object(scheduler, "_IMPROVER_STATUS_FILE", fname):
            scheduler._save_improver_status({"run_count": 1})
        with open(fname) as f:
            data = json.load(f)
        assert data == {"run_count": 1}
    finally:
        os.unlink(fname)


def test_save_improver_status_exception():
    """Lines 1058-1059: handles write error."""
    with mock.patch.object(scheduler, "_IMPROVER_STATUS_FILE", "/nonexistent/status.json"):
        # Should not raise
        scheduler._save_improver_status({"run_count": 1})


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _task_fountain_loop exception handler
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fountain_loop_exception():
    """Lines 1126-1129: exception caught and logged."""
    ctrl = SC()
    with (
        mock.patch("scheduler.settings") as ms,
        mock.patch("scheduler.FOUNTAIN_LOG_PATH", os.path.join(tempfile.mkdtemp(), "fountain.log")),
    ):
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                asyncio, "create_subprocess_exec", side_effect=RuntimeError("Fountain boom")
            ):
                await scheduler._task_fountain_loop(60)
    assert ctrl.calls == 2


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — start_scheduler disabled
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_start_scheduler_disabled():
    """Lines 1181-1183: returns early when disabled via config."""
    import scheduler as sched_mod

    sched_mod._scheduler_tasks = []
    sched_mod._client = None
    sched_mod.scheduler_start_time = None

    with mock.patch("scheduler.settings") as ms:
        ms.scheduler_enabled = False
        await sched_mod.start_scheduler()
        assert sched_mod.scheduler_start_time is not None
        assert sched_mod._client is None  # Should not have been initialized


@pytest.mark.asyncio
async def test_start_scheduler_enabled():
    """Lines 1185-1237: starts all loops."""
    import scheduler as sched_mod

    sched_mod._scheduler_tasks = []
    sched_mod._client = None
    sched_mod.scheduler_start_time = None

    with mock.patch("scheduler.settings") as ms:
        ms.scheduler_enabled = True
        ms.dispatcher_interval_seconds = 30
        ms.stale_check_interval_seconds = 120
        ms.dead_board_interval_seconds = 900
        ms.template_interval_seconds = 900
        ms.metrics_interval_seconds = 300
        ms.scanner_interval_seconds = 21600
        ms.improver_interval_seconds = 21600
        ms.worker_script = "worker.py"

        with mock.patch.object(sched_mod, "_recover_stale_tasks", return_value=3):
            await sched_mod.start_scheduler()
            assert len(sched_mod._scheduler_tasks) >= 5
            assert sched_mod._client is not None


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — worker_death_watcher
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deathwatch_no_crashed():
    """Line 761-762: continues when no crashed workers."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_check_crashed_workers", return_value=[]):
                with mock.patch.object(scheduler, "_worker_spawn_times", {}):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_deathwatch_hung_worker():
    """Lines 742-759: detects and kills a hung worker."""
    ctrl = SC()
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None  # Still running

    import time

    old_time = time.monotonic()
    hung_time = old_time - 4000  # > KANBAN_LLM_TIMEOUT + 300

    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"hung_1": hung_time}
    sched_mod._worker_processes = {"hung_1": mock_proc}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_check_crashed_workers", return_value=[]):
                with mock.patch.dict("os.environ", {"KANBAN_LLM_TIMEOUT": "3600"}, clear=False):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2
    mock_proc.kill.assert_called_once()


@pytest.mark.asyncio
async def test_deathwatch_exit_0():
    """Lines 771-779: clean exit (exit=0) is logged and cleaned up."""
    ctrl = SC()
    import time

    now = time.monotonic()

    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"done_1": now - 100}
    sched_mod._worker_processes = {}
    sched_mod._worker_stderr_data = {}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_check_crashed_workers", return_value=[("done_1", 0, now - 100)]
            ):
                await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_deathwatch_crash_with_stderr():
    """Lines 781-826: crashed worker with stderr output."""
    ctrl = SC()

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 2  # Crashed
    mock_proc.stderr.read.return_value = b"error: something broke"

    import time

    now = time.monotonic()

    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"crash_1": now}
    sched_mod._worker_processes = {"crash_1": mock_proc}
    sched_mod._worker_crash_counts = {"crash_1": 2}
    sched_mod._worker_stderr_data = {}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_check_crashed_workers", return_value=[("crash_1", 2, now)]
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={}):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_deathwatch_exception():
    """Lines 835-836: exception caught."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_check_crashed_workers", side_effect=RuntimeError("Death fail")
            ):
                await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2
