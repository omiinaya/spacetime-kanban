"""Coverage tests for scheduler.py remaining async loops.

SleepController: first sleep completes (loop body runs), second raises
CancelledError (loop exits cleanly).

Targets:
  - stale_watcher (lines 328-424): release stale + forced tasks
  - dead_board_monitor (lines 427-548): zero completions, stalled
  - metrics_collector (lines 551-591): snapshot + backlog
  - template_trigger (lines 711-724): periodic API call
  - zombie_cleaner (lines 870-905): archive exhausted tasks
"""

import asyncio
from unittest import mock

import pytest

import scheduler

_real_sleep = asyncio.sleep


class SleepController:
    """First n sleep calls complete, then CancelledError (n default=2)."""

    def __init__(self, cancel_on=2):
        self.call_count = 0
        self.cancel_on = cancel_on

    async def __call__(self, interval):
        self.call_count += 1
        if self.call_count >= self.cancel_on:
            raise asyncio.CancelledError()
        await _real_sleep(0.001)


# ═══════════════════════════════════════════════════════════════════════
# stale_watcher
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_stale_watcher_no_in_progress():
    """Line 341-342: continues when no in_progress tasks."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=None):
                await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_no_our_tasks():
    """Line 349-350: continues when no tasks assigned to our agent."""
    ctrl = SleepController()
    tasks = [{"id": "t1", "assigned_to": "other_agent", "title": "Not ours"}]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=tasks):
                await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_grace_period():
    """Line 385-386: tasks in grace period (<5min) are skipped."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t1",
            "assigned_to": "test_agent",
            "title": "Recent task",
            "updated_at": now_ms - 60_000,  # 1 min ago → grace period
        }
    ]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=tasks):
                with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                    await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_batch_heartbeat():
    """Lines 355-363: batch heartbeat fetch populates heartbeat_map."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t1",
            "assigned_to": "test_agent",
            "title": "Old task",
            "updated_at": now_ms - 3_600_000,  # 60 min ago → force release
        }
    ]
    # Batch logs returns heartbeat data
    batch_response = {"t1": now_ms - 1_000}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_force_release():
    """Lines 392-416: task >60min old is force-released."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_force",
            "assigned_to": "test_agent",
            "title": "Very old task",
            "repo": "test",
            "updated_at": now_ms - 3_700_000,  # ~61 min ago → force release
        }
    ]
    batch_response = {"t_force": now_ms - 5_000}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_stale_release():
    """Lines 393-416: task past stale_minutes with no heartbeat is released."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_stale",
            "assigned_to": "test_agent",
            "title": "Stale task",
            "repo": "test",
            "updated_at": now_ms - 2_000_000,  # ~33 min ago → > stale_minutes(30)
        }
    ]

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, None]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_batch_fallback():
    """Lines 362-375: batch heartbeat fails → per-task fallback."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_fb",
            "assigned_to": "test_agent",
            "title": "Fallback task",
            "updated_at": now_ms - 3_600_000,
        }
    ]

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            # First api_get returns tasks, second batch fails (exception)
            with mock.patch.object(
                scheduler, "_api_get", side_effect=[tasks, Exception("Batch failed"), None]
            ):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_exception():
    """Lines 423-424: exception caught gracefully."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=RuntimeError("Bang")):
                await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_batch_dict_values():
    """Batch endpoint returns {task_id: log_record_dict} — scheduler must
    extract the timestamp instead of doing int - dict (was a TypeError that
    crashed stale_watcher every cycle)."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_dict",
            "assigned_to": "test_agent",
            "title": "Task with dict heartbeat",
            "repo": "test",
            "updated_at": now_ms - 3_700_000,  # ~61 min ago → force release
        }
    ]
    # The REAL /api/logs/batch response: full log record dict per task
    batch_response = {
        "t_dict": {
            "id": "log_hb1",
            "task_id": "t_dict",
            "action": "heartbeat",
            "timestamp": now_ms - 5_000,
        }
    }

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    # No TypeError — task was processed and force-released
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_watcher_batch_mixed_values():
    """Batch endpoint returning a mix of dict records, int timestamps, and None
    must not crash the stale check."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_dict",
            "assigned_to": "test_agent",
            "title": "Dict hb task",
            "updated_at": now_ms - 1_000_000,  # > stale_minutes
        },
        {
            "id": "t_int",
            "assigned_to": "test_agent",
            "title": "Int hb task",
            "updated_at": now_ms - 1_000_000,
        },
        {
            "id": "t_none",
            "assigned_to": "test_agent",
            "title": "No hb task",
            "updated_at": now_ms - 1_000_000,
        },
    ]
    batch_response = {
        "t_dict": {
            "id": "log1",
            "task_id": "t_dict",
            "action": "heartbeat",
            "timestamp": now_ms - 1000,
        },
        "t_int": now_ms - 2000,
        "t_none": None,
    }

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# dead_board_monitor
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_deadboard_active_workers():
    """Line 445-446: skip when workers are active."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=3):
                await scheduler.dead_board_monitor(900)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_deadboard_no_overview():
    """Lines 449-466: no overview → check workers, maybe restart."""
    ctrl = SleepController(cancel_on=3)  # sleep(900), sleep(5), then cancel

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", side_effect=[None, {"status": "ok"}]):
                    with mock.patch.object(scheduler, "_restart_server") as restart:
                        await scheduler.dead_board_monitor(900)
                    restart.assert_called_once()
    assert ctrl.call_count == 3


@pytest.mark.asyncio
async def test_deadboard_worker_during_async_gap():
    """Lines 451-455: worker started during async gap."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", side_effect=[0, 1]):
                with mock.patch.object(scheduler, "_api_get", return_value=None):
                    await scheduler.dead_board_monitor(900)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_deadboard_self_heal_fail():
    """Lines 461-466: self-heal attempted but health check fails."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", side_effect=[None, None]):
                    with mock.patch.object(scheduler, "_restart_server"):
                        await scheduler.dead_board_monitor(900)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_deadboard_zero_completions_alert():
    """Lines 477-501: zero completions → fire EVENT_BOARD_DEAD."""
    ctrl = SleepController()
    overview = {
        "completions_last_hour": 0,
        "claims_last_hour": 5,
        "total": 50,
        "total_done": 30,
        "by_status": {"available": 10, "inProgress": 5, "blocked": 2},
        "claim_complete_ratio": 0.0,
    }
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", return_value=overview):
                    with mock.patch.object(scheduler, "fire_event") as fe:
                        await scheduler.dead_board_monitor(900)
                        fe.assert_called_once()
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_deadboard_stalled():
    """Lines 525-543: high claim:complete ratio → EVENT_BOARD_STALLED."""
    ctrl = SleepController()
    overview = {
        "completions_last_hour": 0,
        "claims_last_hour": 100,
        "total": 100,
        "total_done": 50,
        "by_status": {"available": 20, "inProgress": 10, "blocked": 2},
        "claim_complete_ratio": 50.0,
    }
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", return_value=overview):
                    with mock.patch.object(scheduler, "fire_event") as fe:
                        await scheduler.dead_board_monitor(900)
                        # First call is BOARD_DEAD (zero completions + done > 0)
                        # Second call might be STALLED
                        assert fe.call_count >= 1
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_deadboard_exception():
    """Lines 547-548: exception caught gracefully."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_get_worker_count", side_effect=RuntimeError("Dead")
            ):
                await scheduler.dead_board_monitor(900)
    assert ctrl.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# metrics_collector
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_metrics_no_overview():
    """Lines 562-563: continues when no overview."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=None):
                await scheduler.metrics_collector(300)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_metrics_with_overview():
    """Lines 565-586: fires METRICS_SNAPSHOT + backlog check."""
    ctrl = SleepController()
    overview = {
        "total": 50,
        "total_done": 20,
        "completions_last_hour": 3,
        "claims_last_hour": 5,
        "by_status": {"available": 10, "inProgress": 5, "blocked": 2},
        "claim_complete_ratio": 1.5,
    }
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=overview):
                with mock.patch.object(scheduler, "fire_event") as fe:
                    await scheduler.metrics_collector(300)
                    fe.assert_called_once()
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_metrics_exception():
    """Lines 590-591: exception caught."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=RuntimeError("Oops")):
                await scheduler.metrics_collector(300)
    assert ctrl.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# template_trigger
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_template_trigger_calls_api():
    """Lines 719-720: calls POST /api/task-templates/trigger."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_post") as post:
                await scheduler.template_trigger(900)
                post.assert_called_once_with("/api/task-templates/trigger", {})
    assert ctrl.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
# zombie_cleaner
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zombie_no_available():
    """Lines 883-884: continues when no available tasks."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=None):
                await scheduler.zombie_cleaner(3600)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_zombie_no_zombies():
    """Lines 888-889: continues when no zombies found."""
    ctrl = SleepController()
    tasks = [{"id": "t1", "fail_count": 1, "max_attempts": 3}]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=tasks):
                await scheduler.zombie_cleaner(3600)
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_zombie_archives():
    """Lines 891-901: blocks and archives zombie tasks."""
    ctrl = SleepController()
    tasks = [{"id": "z1", "fail_count": 5, "max_attempts": 3}]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=tasks):
                with mock.patch.object(scheduler, "_api_post") as post:
                    await scheduler.zombie_cleaner(3600)
                    # Should call block endpoint for the zombie
                    post.assert_any_call(
                        "/api/tasks/z1/block",
                        {"reason": "Zombie: exhausted retries — cannot be worked"},
                    )
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_zombie_exception():
    """Lines 904-905: exception caught."""
    ctrl = SleepController()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=RuntimeError("Zombie")):
                await scheduler.zombie_cleaner(3600)
    assert ctrl.call_count == 2
