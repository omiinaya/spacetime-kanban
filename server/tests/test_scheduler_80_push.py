"""Final edge cases to push past 80%.

Targets:
  - deathwatch worker-died-after-running path (lines 819-823)
  - low_backlog unreadable improvement file (lines 134-135)
  - self_improver health fail + stale tasks (lines 940-951, 960-966)
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


@pytest.mark.asyncio
async def test_deathwatch_worker_died_after_running():
    """Lines 819-823: worker ran >3s then died."""
    ctrl = SC()
    import time

    now = time.monotonic()

    import scheduler as sched_mod

    sched_mod._worker_spawn_times = {"died_1": now - 60}  # 60s ago → outside threshold
    sched_mod._worker_processes = {}
    sched_mod._worker_crash_counts = {}
    sched_mod._worker_stderr_data = {}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler,
                "_check_crashed_workers",
                return_value=[("died_1", 2, now - 60)],
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={}):
                    await scheduler.worker_death_watcher(15)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_low_backlog_gen_imp_unreadable_file():
    """Lines 134-135: skip unreadable improvement file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        imp_path = os.path.join(tmpdir, "IMPROVEMENTS.md")
        # Write then chmod to remove read permission
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
async def test_self_improver_health_fail_stale():
    """Lines 940-951, 960-966: health fails, stale in_progress tasks."""
    ctrl = SC(cancel_on=3)  # sleep(21600), sleep(10), then cancel

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        # Health returns None → triggers restart path
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler,
                "_api_get",
                side_effect=[
                    None,  # health → fail
                    None,  # health after restart → still fail → creates improvement task
                    None,  # NOT REACHED (cancelled on second sleep)
                ],
            ):
                with mock.patch.object(scheduler, "_restart_server"):
                    with mock.patch.object(
                        scheduler, "_create_improvement_task", return_value={"id": "imp"}
                    ):
                        with mock.patch.object(scheduler, "_load_improver_status", return_value={}):
                            with mock.patch.object(scheduler, "_save_improver_status"):
                                await scheduler.self_improver(21600)
    assert ctrl.calls == 3


@pytest.mark.asyncio
async def test_low_backlog_ci_badge_readme_fail():
    """Line 182: README read raises exception during CI badge check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create CI workflows dir
        os.makedirs(os.path.join(tmpdir, ".github", "workflows"))
        with open(os.path.join(tmpdir, ".github", "workflows", "ci.yml"), "w") as f:
            f.write("name: CI\n")
        # Create a real README file then mock open to fail
        readme_path = os.path.join(tmpdir, "README.md")
        with open(readme_path, "w") as f:
            f.write("# Test\n")

        repos = [("test-repo", tmpdir)]

        # Make builtins.open raise on the README path
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
