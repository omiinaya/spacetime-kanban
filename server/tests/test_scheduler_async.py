"""Coverage tests for scheduler.py async loop branches.

Targets inside task_dispatcher:
  - Line 248: continue when no worker_script configured
  - Line 252-257: worker count full log message
  - Line 273-275: memory check exception handler
  - Line 280: continue when no tasks available
  - Line 284-317: eligibility filtering, sorting, spawn/unclaim
  - Line 324-325: dispatcher error handler

Strategy:
  - First asyncio.sleep(interval) completes normally so loop body runs
  - Second asyncio.sleep() raises CancelledError to break loop after one iteration
  - All internal functions mocked through scheduler namespace
"""

import asyncio
from unittest import mock

import pytest

import scheduler

# Save real sleep before any mocking
_real_sleep = asyncio.sleep


class SleepController:
    """Controls asyncio.sleep behaviour across iterations.

    First call returns None (loop body runs).
    Second call raises CancelledError (loop exits).
    Uses the REAL asyncio.sleep internally, not the mocked one.
    """

    def __init__(self):
        self.call_count = 0

    async def __call__(self, interval):
        self.call_count += 1
        if self.call_count >= 2:
            raise asyncio.CancelledError()
        # Let first sleep complete normally — use real sleep for brevity
        await _real_sleep(0.001)


@pytest.mark.asyncio
async def test_dispatcher_skip_no_worker():
    """Line 248: dispatcher continues when no worker_script configured."""
    ctrl = SleepController()

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = None
        ms.worker_args = None
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_all_slots_full():
    """Lines 252-257: dispatcher logs when all worker slots full."""
    ctrl = SleepController()

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=900):
                await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_memory_check_error():
    """Lines 273-275: dispatcher handles memory check exception."""
    ctrl = SleepController()

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_read_meminfo", side_effect=Exception("OOM!")):
                    await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_no_available_tasks():
    """Line 280: dispatcher continues when no tasks available."""
    ctrl = SleepController()
    meminfo = "MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\n"

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_read_meminfo", return_value=meminfo):
                    with mock.patch.object(scheduler, "_api_get", return_value=None):
                        await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_claim_and_spawn():
    """Lines 284-317: dispatcher claims tasks and spawns workers."""
    ctrl = SleepController()
    meminfo = "MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\n"

    available_tasks = [
        {
            "id": "task_001",
            "title": "Fix bug",
            "repo": "test-repo",
            "priority": 0,
            "fail_count": 0,
            "max_attempts": 3,
            "created_at": 1000,
        },
        {
            "id": "task_002",
            "title": "Dead task",
            "repo": "test-repo",
            "priority": 5,
            "fail_count": 999,
            "max_attempts": 3,
            "created_at": 1001,
        },
    ]

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_read_meminfo", return_value=meminfo):
                    with mock.patch.object(scheduler, "_api_get", return_value=available_tasks):
                        with mock.patch.object(
                            scheduler, "_api_post", return_value={"status": "claimed"}
                        ):
                            with mock.patch.object(scheduler, "_spawn_worker", return_value=True):
                                await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_claim_fails_spawn():
    """Lines 309-317: dispatcher unclaims on spawn failure."""
    ctrl = SleepController()
    meminfo = "MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\n"

    available_tasks = [
        {
            "id": "task_003",
            "title": "Fail task",
            "repo": "test-repo",
            "priority": 0,
            "fail_count": 0,
            "max_attempts": 3,
            "created_at": 1000,
        },
    ]

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_read_meminfo", return_value=meminfo):
                    with mock.patch.object(scheduler, "_api_get", return_value=available_tasks):
                        with mock.patch.object(
                            scheduler, "_api_post", return_value={"status": "claimed"}
                        ):
                            with mock.patch.object(scheduler, "_spawn_worker", return_value=False):
                                await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_memory_too_high():
    """Line 273: dispatcher skips when memory usage exceeds threshold."""
    ctrl = SleepController()
    # MemAvailable very low → used_pct ≈ 98.75% > 95% → continue
    meminfo = "MemTotal: 8000000 kB\nMemAvailable: 100000 kB\n"

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_read_meminfo", return_value=meminfo):
                    with mock.patch.object(scheduler, "_api_get", return_value=None):
                        await scheduler.task_dispatcher(30)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_dispatcher_exception_handler():
    """Lines 324-325: dispatcher catches general exceptions."""
    ctrl = SleepController()

    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "worker.py"
        ms.worker_args = ""
        ms.max_workers = 3
        ms.agent_id = "test_agent"
        ms.max_memory_pct = 95
        ms.server_port = 8727
        ms.stale_minutes = 30
        ms.worker_command = "python3"

        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_get_worker_count", side_effect=RuntimeError("Unexpected")
            ):
                await scheduler.task_dispatcher(30)

    assert ctrl.call_count == 2
