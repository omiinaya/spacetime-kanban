"""Targeted coverage for remaining scheduler.py edge cases.

Covers:
  - Line 372-373: per-task fallback heartbeat found
  - Line 379: inner loop continue for other-agent tasks
  - Line 461-466: self-heal success and failure
  - Lines 504-543: deadboard alert-only after cooldown + stalled
  - Lines 585-586: backlog check exception
  - Lines 723-724: template_trigger exception

Each uses SleepController -- first sleep completes, second raises CancelledError.
"""

import asyncio
from unittest import mock

import pytest

import scheduler

_real_sleep = asyncio.sleep


class SC:
    """First n sleep calls complete, next raises CancelledError."""

    def __init__(self, cancel_on=2):
        self.calls = 0
        self.cancel_on = cancel_on

    async def __call__(self, interval):
        self.calls += 1
        if self.calls >= self.cancel_on:
            raise asyncio.CancelledError()
        await _real_sleep(0.001)


# ── stale_watcher edge cases ────────────────────────────────────────


@pytest.mark.asyncio
async def test_stale_heartbeat_fallback_found():
    """Lines 372-373: per-task fallback finds a heartbeat entry."""
    ctrl = SC()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "t_hb",
            "assigned_to": "test_agent",
            "title": "Has heartbeat",
            "updated_at": now_ms - 3_600_000,
        }
    ]
    # Batch fails (returns None, not a dict → empty heartbeat_map)
    # Per-task fallback returns logs with a heartbeat entry
    per_task_logs = [{"action": "heartbeat", "timestamp": now_ms - 60_000}]

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            # First: in_progress tasks. Second: batch returns emptystring (not dict → empty).
            # Third: per-task logs (the fallback)
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, {}, per_task_logs]):
                with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                    with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                        await scheduler.stale_watcher(120)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_stale_inner_loop_skip_other():
    """Line 379: inner loop continues for other-agent tasks."""
    ctrl = SC()
    now_ms = scheduler._now_ms()
    tasks = [
        {
            "id": "ours",
            "assigned_to": "test_agent",
            "title": "Our task",
            "updated_at": now_ms - 60_000,  # Grace period → continue at 385
        },
        {
            "id": "theirs",
            "assigned_to": "other_agent",
            "title": "Not ours",
            "updated_at": now_ms - 3_600_000,
        },
    ]
    batch_response = {"ours": now_ms, "theirs": now_ms}

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        ms.stale_minutes = 30
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[tasks, batch_response]):
                with mock.patch.object(scheduler, "_now_ms", return_value=now_ms):
                    await scheduler.stale_watcher(120)
    assert ctrl.calls == 2


# ── dead_board_monitor edge cases ───────────────────────────────────


@pytest.mark.asyncio
async def test_deadboard_self_heal_success():
    """Lines 461-463: no overview → restart → health check succeeds."""
    ctrl = SC(cancel_on=3)  # sleep(900), sleep(5), then cancel
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", side_effect=[None, {"status": "ok"}]):
                    with mock.patch.object(scheduler, "_restart_server"):
                        await scheduler.dead_board_monitor(900)
    assert ctrl.calls == 3


@pytest.mark.asyncio
async def test_deadboard_self_heal_fail():
    """Lines 464-466: health check returns None → self-heal failed."""
    ctrl = SC(cancel_on=3)  # sleep(900), sleep(5), then cancel
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                # First api_get (overview) returns None → triggers restart
                # Second api_get (health) returns None → heal failed
                with mock.patch.object(scheduler, "_api_get", side_effect=[None, None]):
                    with mock.patch.object(scheduler, "_restart_server"):
                        await scheduler.dead_board_monitor(900)
    assert ctrl.calls == 3


@pytest.mark.asyncio
async def test_deadboard_alert_only():
    """Lines 504-508: alert-only path when done == 0 (skip initial, within cooldown)."""
    ctrl = SC()
    overview = {
        "completions_last_hour": 0,
        "claims_last_hour": 5,
        "total": 10,
        "total_done": 0,  # done == 0 → skip initial alert
        "by_status": {"available": 3, "inProgress": 2, "blocked": 0},
        "claim_complete_ratio": 0.0,
    }
    # Mock _now_ms to return 0 so now_ms - last_alert_ms = 0 (within cooldown)
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", return_value=overview):
                    with mock.patch.object(scheduler, "_now_ms", return_value=0):
                        with mock.patch.object(scheduler, "fire_event") as fe:
                            await scheduler.dead_board_monitor(900)
                            # Neither path should fire
                            fe.assert_not_called()
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_deadboard_alert_only_cooldown_expired():
    """Lines 509-523: alert-only fires when cooldown expired but no initial alert (done=0)."""
    ctrl = SC()
    overview = {
        "completions_last_hour": 0,
        "claims_last_hour": 5,
        "total": 10,
        "total_done": 0,  # done == 0 → skip initial alert
        "by_status": {"available": 3, "inProgress": 2, "blocked": 0},
        "claim_complete_ratio": 0.0,
    }
    # Real _now_ms returns a large number → cooldown expired
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", return_value=overview):
                    with mock.patch.object(scheduler, "fire_event") as fe:
                        await scheduler.dead_board_monitor(900)
                        # Alert-only path should fire (done=0 → no initial, but cooldown expired)
                        assert fe.call_count == 1
                        event_name = fe.call_args[0][0]
                        assert event_name == "board.dead"
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_deadboard_stalled_after_cooldown():
    """Lines 525-543: stalled detection when ip=avail=0 (no initial/alert-only alert)."""
    ctrl = SC()
    # ip=0 and avail=0 → initial alert and alert-only are both skipped
    # ratio=50, claims=100, completions=0 → stalled fires
    overview = {
        "completions_last_hour": 0,
        "claims_last_hour": 100,
        "total": 100,
        "total_done": 50,
        "by_status": {"available": 0, "inProgress": 0, "blocked": 0},
        "claim_complete_ratio": 50.0,
    }
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_get_worker_count", return_value=0):
                with mock.patch.object(scheduler, "_api_get", return_value=overview):
                    with mock.patch.object(scheduler, "fire_event") as fe:
                        await scheduler.dead_board_monitor(900)
                        # Only stalled should fire
                        assert fe.call_count == 1
                        event_name = fe.call_args[0][0]
                        assert event_name == "board.stalled"
    assert ctrl.calls == 2


# ── metrics_collector edge cases ────────────────────────────────────


@pytest.mark.asyncio
async def test_metrics_overview_backlog_exception():
    """Lines 585-586: backlog check exception caught."""
    ctrl = SC()
    overview = {
        "total": 10,
        "total_done": 5,
        "completions_last_hour": 1,
        "claims_last_hour": 2,
        "by_status": {"available": 3, "inProgress": 1, "blocked": 0},
        "claim_complete_ratio": 2.0,
    }
    # Mock check_backlog_and_trigger to raise
    mock_backlog = mock.MagicMock()
    mock_backlog.check_backlog_and_trigger.side_effect = RuntimeError("Backlog fail")

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=overview):
                with mock.patch.object(scheduler, "fire_event"):
                    with mock.patch.dict(
                        "sys.modules",
                        {"scheduler_low_backlog": mock_backlog},
                    ):
                        await scheduler.metrics_collector(300)
    assert ctrl.calls == 2


# ── template_trigger edge cases ─────────────────────────────────────


@pytest.mark.asyncio
async def test_template_trigger_exception():
    """Lines 723-724: exception caught."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test_agent"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(
                scheduler, "_api_post", side_effect=RuntimeError("Template fail")
            ):
                await scheduler.template_trigger(900)
    assert ctrl.calls == 2
