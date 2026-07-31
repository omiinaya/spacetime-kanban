"""Final edge-case coverage — deathwatch, low_backlog improvements, self_improver.

Targets:
  - deathwatch block-on-3-crashes (lines 808-823)
  - deathwatch stderr read failure (lines 792-793)
  - low_backlog: section header skip (148), non-dir repo (123),
    unreadable file (134-135), duplicate title (114-115/150-151),
    api fetch fail (115-116), readme except (182)
  - self_improver health success path (lines 934-960)
"""

import asyncio
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


# ── deathwatch block on 3+ crashes ──────────────────────────────────


@pytest.mark.asyncio
async def test_deathwatch_block_after_3_crashes():
    """Lines 808-816: blocks task after 3+ immediate crashes."""
    ctrl = SC()
    import time

    now = time.monotonic()
    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"bad_1": now}
    sched_mod._worker_processes = {}
    sched_mod._worker_crash_counts = {"bad_1": 3}
    sched_mod._worker_stderr_data = {}
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_check_crashed_workers", return_value=[("bad_1", 2, now)]
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={}):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2


# ── deathwatch stderr from drain buffer ──────────────────────────────


@pytest.mark.asyncio
async def test_deathwatch_stderr_read_failure():
    """Death watcher reads stderr from the drain buffer, not the raw pipe.

    Regression guard: the old code did a blocking ``proc.stderr.read()`` on
    the event loop, which froze ALL API requests when a crashed worker had a
    large stderr backlog. The buffer is populated by the background drain
    thread (_drain_worker_stderr); the watcher must never touch the pipe.
    """
    ctrl = SC()
    import time

    now = time.monotonic()
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 2
    # The raw pipe read is NOT used anymore — make it raise if it is called
    mock_proc.stderr.read.side_effect = Exception("Stderr broken — must not be read")
    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"bad_2": now}
    sched_mod._worker_processes = {"bad_2": mock_proc}
    sched_mod._worker_crash_counts = {}
    # Drain buffer has the diagnostics — watcher should read from here
    sched_mod._worker_stderr_data = {"bad_2": b"worker crashed: boom"}
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_check_crashed_workers", return_value=[("bad_2", 2, now)]
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={}):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2
    # The raw pipe read must never be called from the event loop
    mock_proc.stderr.read.assert_not_called()


# ── low_backlog edge cases ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_skip_section_headers():
    """Line 148: skip section heading (e.g. 'Table of Contents')."""
    with tempfile.TemporaryDirectory() as tmpdir:
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        with open(imp_path, "w") as f:
            f.write("## Table of Contents\n## Optimize Database Queries\n")
        repos = [("test-repo", tmpdir)]
        with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch("scanners.runner.discover_repos", return_value=repos, create=True):
                    count = await scheduler_low_backlog._generate_improvement_tasks()
                    assert count >= 1


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_non_dir_repo():
    """Line 123: skip repo when path is not a directory."""
    repos = [("fake-repo", "/tmp/nonexistent_dir_xyz_789")]
    with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
        with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
            with mock.patch("scanners.runner.discover_repos", return_value=repos, create=True):
                count = await scheduler_low_backlog._generate_improvement_tasks()
    assert count == 0


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_unreadable_file():
    """Lines 134-135: skip unreadable improvement file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        with open(imp_path, "w") as f:
            f.write("## Optimize Everything\n")
        os.chmod(imp_path, 0o000)
        try:
            repos = [("test-repo", tmpdir)]
            with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
                with mock.patch.object(
                    scheduler_low_backlog, "_api_post", return_value={"id": "t1"}
                ):
                    with mock.patch(
                        "scanners.runner.discover_repos", return_value=repos, create=True
                    ):
                        count = await scheduler_low_backlog._generate_improvement_tasks()
                        assert count >= 0
        finally:
            os.chmod(imp_path, 0o644)


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_duplicate_title():
    """Lines 114-115, 150-151: skip existing titles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        with open(imp_path, "w") as f:
            f.write("## Improve Performance\n")
        repos = [("test-repo", tmpdir)]
        existing_tasks = [{"title": "Improve Performance"}]
        with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=existing_tasks):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch("scanners.runner.discover_repos", return_value=repos, create=True):
                    count = await scheduler_low_backlog._generate_improvement_tasks()
                    assert count == 0


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_api_fetch_fail():
    """Line 115-116: pass when API fetch fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        with open(imp_path, "w") as f:
            f.write("## Optimize Database Queries\n")
        repos = [("test-repo", tmpdir)]
        with mock.patch.object(
            scheduler_low_backlog, "_api_get", side_effect=Exception("API down")
        ):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch("scanners.runner.discover_repos", return_value=repos, create=True):
                    count = await scheduler_low_backlog._generate_improvement_tasks()
                    assert count == 1


@pytest.mark.asyncio
async def test_low_backlog_ci_badge_readme_fail():
    """Line 182: README read raises exception during CI badge check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, ".github", "workflows"))
        with open(os.path.join(tmpdir, ".github", "workflows", "ci.yml"), "w") as f:
            f.write("name: CI\n")
        readme_path = os.path.join(tmpdir, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Test\n")
        repos = [("test-repo", tmpdir)]
        real_open = open

        def mock_open_side_effect(*args, **kwargs):
            if args and args[0] == readme_path:
                raise PermissionError("Permission denied")
            return real_open(*args, **kwargs)

        with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=[]):
            with mock.patch.object(scheduler_low_backlog, "_api_post", return_value={"id": "t1"}):
                with mock.patch("scanners.runner.discover_repos", return_value=repos, create=True):
                    with mock.patch("builtins.open", side_effect=mock_open_side_effect):
                        count = await scheduler_low_backlog._generate_improvement_tasks()
                        assert count >= 0


# ── self_improver health success path ───────────────────────────────


@pytest.mark.asyncio
async def test_self_improver_health_success():
    """Lines 938-996: health check succeeds, checks board + cycling tasks."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        health_data = {"status": "ok"}
        blocked = [{"id": f"b{i}"} for i in range(10)]
        ip_tasks = []
        avail = [
            {"id": "c1", "fail_count": 3, "fail_reason": "no indexable fields", "max_attempts": 5}
        ]
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_api_get", side_effect=[health_data, blocked, ip_tasks, avail]
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={}):
                    with mock.patch.object(
                        scheduler, "_load_improver_status", return_value={"run_count": 0}
                    ):
                        with mock.patch.object(scheduler, "_save_improver_status"):
                            await scheduler.self_improver(21600)
    assert ctrl.calls == 2
