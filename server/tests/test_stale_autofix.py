"""Test stale-worker auto-fix behavior (replaces old alert-dedup tests).

The old stale_watcher fired a webhook alert when it released a stale task,
with a dedup map (_should_alert_stale / _stale_alerted_tasks) to prevent
spam. The user explicitly does not want to be notified about stale workers
— they should be auto-fixed silently. So the dedup machinery was removed
and the watcher now:

  1. NEVER fires a webhook for stale workers (auto-fix silently).
  2. Kills the lingering worker process before unclaiming, so a dead task
     can't keep a zombie `hermes chat` running that duplicates the work of
     the re-claimed task.
  3. Never force-releases a task whose worker is alive AND heartbeating —
     LLM workers legitimately run up to KANBAN_LLM_TIMEOUT (60 min), and
     the old 60-min force-release spawned duplicate workers.
"""

import asyncio
from unittest import mock

import pytest

import scheduler

_real_sleep = asyncio.sleep


class SleepController:
    """First sleep completes (loop body runs), second raises CancelledError."""

    def __init__(self):
        self.call_count = 0

    async def __call__(self, interval):
        self.call_count += 1
        if self.call_count >= 2:
            raise asyncio.CancelledError()
        await _real_sleep(0.001)


@pytest.mark.asyncio
async def test_stale_release_kills_worker_and_never_fires_webhook():
    """A genuinely stale task (no heartbeat, past stale_minutes) is released,
    its worker process is killed, and NO webhook alert fires."""
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

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None  # process still alive (hung)

    # Batch heartbeat returns a dict entry (t_stale -> None, no heartbeat),
    # so the batch path is taken (not the per-task fallback) and the task is
    # genuinely stale (hb_ts None, hb_age 999).
    batch_response = {"t_stale": None}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        with mock.patch.dict(
                            scheduler._worker_processes, {"t_stale": mock_proc}, clear=True
                        ):
                            with mock.patch.object(scheduler, "_kill_worker") as kill:
                                with mock.patch.object(scheduler, "fire_event") as fe:
                                    await scheduler.stale_watcher(120)
                                    kill.assert_called_once_with("t_stale")
                                    fe.assert_not_called()
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_stale_release_without_worker_process():
    """If no worker process is tracked, stale release still unclaims (no kill,
    no webhook)."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_stale2",
            "assigned_to": "test_agent",
            "title": "Stale no-proc task",
            "repo": "test",
            "updated_at": now_ms - 2_000_000,
        }
    ]
    batch_response = {"t_stale2": None}  # batch path, no heartbeat → stale

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        with mock.patch.dict(scheduler._worker_processes, {}, clear=True):
                            with mock.patch.object(scheduler, "_kill_worker") as kill:
                                with mock.patch.object(scheduler, "fire_event") as fe:
                                    await scheduler.stale_watcher(120)
                                    kill.assert_not_called()
                                    fe.assert_not_called()
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_force_release_skipped_for_alive_heartbeating_worker():
    """A task older than 60 min whose worker is alive AND heartbeating is NOT
    released — the old code force-released it and spawned a duplicate worker."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_long",
            "assigned_to": "test_agent",
            "title": "Long LLM task",
            "repo": "test",
            "updated_at": now_ms - 3_700_000,  # ~61 min ago
        }
    ]
    batch_response = {"t_long": now_ms - 5_000}  # fresh heartbeat

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None  # alive

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 45
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post") as post:
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        with mock.patch.dict(
                            scheduler._worker_processes, {"t_long": mock_proc}, clear=True
                        ):
                            await scheduler.stale_watcher(120)
                            post.assert_not_called()  # never unclaimed
    assert ctrl.call_count == 2


@pytest.mark.asyncio
async def test_force_release_still_fires_when_worker_dead():
    """If the worker process is dead (poll() != None), force-release after
    60 min still unclaims — nothing is running, so no duplicate-work risk."""
    ctrl = SleepController()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_dead",
            "assigned_to": "test_agent",
            "title": "Dead worker task",
            "repo": "test",
            "updated_at": now_ms - 3_700_000,  # ~61 min ago
        }
    ]
    batch_response = {"t_dead": now_ms - 5_000}  # fresh heartbeat, but process dead

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 1  # exited

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 45
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        with mock.patch.dict(
                            scheduler._worker_processes, {"t_dead": mock_proc}, clear=True
                        ):
                            with mock.patch.object(scheduler, "_kill_worker") as kill:
                                with mock.patch.object(scheduler, "fire_event") as fe:
                                    await scheduler.stale_watcher(120)
                                    kill.assert_not_called()  # already dead
                                    fe.assert_not_called()
    assert ctrl.call_count == 2
