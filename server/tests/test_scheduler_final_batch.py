"""Coverage tests for scheduler.py remaining async functions + scheduler_low_backlog.py.

SleepController: first sleep completes (loop body runs), Nth raises CancelledError.

Targets (scheduler.py):
  - _seed_initial_workers (lines 839-862)
  - _create_improvement_task (lines 1062-1083)
  - _recover_stale_tasks (lines 1132-1170)
  - task_archiver (lines 622-708)
  - _task_fountain_loop (lines 1086-1129)
  - start_scheduler (lines 1173+)

Targets (scheduler_low_backlog.py):
  - _api_get, _api_post
  - _trigger_scanner
  - _get_actionable_available_count
  - check_backlog_and_trigger
"""

import asyncio
import time
from unittest import mock

import pytest

import scheduler
import scheduler_low_backlog

_real_sleep = asyncio.sleep


class SC:
    """First n sleep calls complete, then CancelledError (n default=2)."""

    def __init__(self, cancel_on=2):
        self.calls = 0
        self.cancel_on = cancel_on

    async def __call__(self, interval):
        self.calls += 1
        if self.calls >= self.cancel_on:
            raise asyncio.CancelledError()
        await _real_sleep(0.001)


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _seed_initial_workers
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_seed_initial_no_available():
    """Line 843-844: returns early when no tasks available."""
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        ms.max_workers = 3
        with mock.patch.object(scheduler, "_api_get", return_value=None):
            await scheduler._seed_initial_workers()


@pytest.mark.asyncio
async def test_seed_initial_claims_and_spawns():
    """Lines 850-860: claims tasks and spawns workers."""
    tasks = [
        {
            "id": "s1",
            "title": "Seed task",
            "repo": "test",
            "priority": 0,
            "fail_count": 0,
            "max_attempts": 3,
            "created_at": 100,
        }
    ]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        ms.max_workers = 3
        with mock.patch.object(scheduler, "_api_get", return_value=tasks):
            with mock.patch.object(scheduler, "_api_post", return_value={"status": "claimed"}):
                with mock.patch.object(scheduler, "_spawn_worker", return_value=True):
                    await scheduler._seed_initial_workers()


@pytest.mark.asyncio
async def test_seed_initial_spawn_fail():
    """Lines 858-860: unclaims when spawn fails."""
    tasks = [
        {
            "id": "s2",
            "title": "Fail seed",
            "repo": "test",
            "priority": 0,
            "fail_count": 0,
            "max_attempts": 3,
            "created_at": 100,
        }
    ]
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        ms.max_workers = 3
        with mock.patch.object(scheduler, "_api_get", return_value=tasks):
            with mock.patch.object(scheduler, "_api_post", return_value={"status": "claimed"}):
                with mock.patch.object(scheduler, "_spawn_worker", return_value=False):
                    await scheduler._seed_initial_workers()


@pytest.mark.asyncio
async def test_seed_initial_exception():
    """Line 861-862: exception caught."""
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        ms.max_workers = 3
        with mock.patch.object(scheduler, "_api_get", side_effect=RuntimeError("Bang")):
            await scheduler._seed_initial_workers()


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _create_improvement_task
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_improvement_task_success():
    """Lines 1066-1083: creates task successfully."""
    with mock.patch.object(scheduler, "_api_post", return_value={"id": "imp_001"}):
        result = await scheduler._create_improvement_task("Test Title", "Test desc", 2, "test-repo")
    assert result == {"id": "imp_001"}


@pytest.mark.asyncio
async def test_create_improvement_task_fail():
    """Lines 1081-1083: fail path when api returns None."""
    with mock.patch.object(scheduler, "_api_post", return_value=None):
        result = await scheduler._create_improvement_task("Fail Title", "Fail desc")
    assert result is None


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _recover_stale_tasks
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_recover_stale_no_stale():
    """Lines 1154-1155: returns 0 when no stale tasks."""
    with mock.patch.object(scheduler, "_api_get", return_value=[]):
        result = await scheduler._recover_stale_tasks()
    assert result == 0


@pytest.mark.asyncio
async def test_recover_stale_with_tasks():
    """Lines 1158-1170: recovers stale tasks."""
    stale = [{"id": "stale_1", "title": "Old task", "assigned_to": "dead_agent"}]
    with mock.patch.object(scheduler, "_api_get", return_value=stale):
        with mock.patch.object(scheduler, "_api_post", return_value={}):
            result = await scheduler._recover_stale_tasks()
    assert result == 1


@pytest.mark.asyncio
async def test_recover_stale_retry_then_success():
    """Lines 1142-1151: retries 3 times then succeeds."""
    with mock.patch.object(scheduler, "_api_get", side_effect=[None, None, []]):
        result = await scheduler._recover_stale_tasks()
    assert result == 0


@pytest.mark.asyncio
async def test_recover_stale_all_fail():
    """Lines 1148-1152: all 3 retries fail."""
    with mock.patch.object(scheduler, "_api_get", side_effect=[None, None, None]):
        result = await scheduler._recover_stale_tasks()
    assert result == 0


@pytest.mark.asyncio
async def test_recover_stale_skip_no_id():
    """Line 1160-1161: skip tasks with no id."""
    stale = [{"title": "No id task"}]
    with mock.patch.object(scheduler, "_api_get", return_value=stale):
        result = await scheduler._recover_stale_tasks()
    assert result == 0


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — task_archiver
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_archiver_no_seed_no_done_no_blocked():
    """Lines 639-700: no tasks of any type found."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", return_value=None):
                await scheduler.task_archiver(3600)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_archiver_archives_all_types():
    """Lines 640-697: archives seed tasks, old done, old blocked, retries stuck."""
    ctrl = SC()
    now = int(time.time() * 1000)
    day = 86400_000

    seed_tasks = [{"id": "seed_old", "created_by": "seed", "created_at": now - 2 * day}]
    done_tasks = [{"id": "done_old", "updated_at": now - 8 * day}]
    blocked_tasks = [
        {
            "id": "blocked_old",
            "updated_at": now - 2 * day,
            "fail_reason": None,
            "assigned_to": "someone",
        }
    ]

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_now_ms", return_value=now):
                with mock.patch.object(
                    scheduler, "_api_get", side_effect=[seed_tasks, done_tasks, blocked_tasks]
                ):
                    with mock.patch.object(scheduler, "_api_post", return_value={"retried": 1}):
                        await scheduler.task_archiver(3600)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_archiver_no_archives_logs():
    """Lines 700-701: logs when nothing to archive."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=[None, None, None]):
                with mock.patch.object(scheduler, "print") as mp:
                    await scheduler.task_archiver(3600)
                    # Should print "No tasks to archive"
                    assert any("No tasks to archive" in str(c) for c in mp.call_args_list)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_archiver_exception():
    """Lines 705-706: exception caught."""
    ctrl = SC()
    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            with mock.patch.object(scheduler, "_api_get", side_effect=RuntimeError("Archive fail")):
                await scheduler.task_archiver(3600)
    assert ctrl.calls == 2


# ═══════════════════════════════════════════════════════════════════════
# scheduler.py — _task_fountain_loop
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fountain_loop_subprocess():
    """Lines 1089-1121: runs fountain subprocess, handles output."""
    ctrl = SC()

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            # Mock create_subprocess_exec to return a process that outputs "Created 3 task"
            mock_proc = mock.AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = mock.AsyncMock(
                return_value=(b"Created 3 task(s) for repo test\n", b"")
            )

            with mock.patch.object(asyncio, "create_subprocess_exec", return_value=mock_proc):
                await scheduler._task_fountain_loop(60)
    assert ctrl.calls == 2


@pytest.mark.asyncio
async def test_fountain_loop_failure():
    """Lines 1122-1123: subprocess non-zero exit."""
    ctrl = SC()

    with mock.patch("scheduler.settings") as ms:
        ms.agent_id = "test"
        with mock.patch.object(scheduler.asyncio, "sleep", ctrl):
            mock_proc = mock.AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = mock.AsyncMock(return_value=(b"error", b"something broke"))

            with mock.patch.object(asyncio, "create_subprocess_exec", return_value=mock_proc):
                await scheduler._task_fountain_loop(60)
    assert ctrl.calls == 2


# ═══════════════════════════════════════════════════════════════════════
# scheduler_low_backlog.py
# ═══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_low_backlog_api_get_200():
    """_api_get returns JSON on 200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "val"}

    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.get.return_value = mock_resp
        result = await scheduler_low_backlog._api_get("/api/tasks")
    assert result == {"key": "val"}


@pytest.mark.asyncio
async def test_low_backlog_api_get_non200():
    """_api_get returns None on non-200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 500

    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.get.return_value = mock_resp
        result = await scheduler_low_backlog._api_get("/api/tasks")
    assert result is None


@pytest.mark.asyncio
async def test_low_backlog_api_get_exception():
    """_api_get returns None on exception."""
    with mock.patch("httpx.AsyncClient") as mclient:
        mclient.return_value.__aenter__.return_value.get.side_effect = Exception("Conn err")
        result = await scheduler_low_backlog._api_get("/api/tasks")
    assert result is None


@pytest.mark.asyncio
async def test_low_backlog_trigger_scanner_already_running():
    """_trigger_scanner returns early when already running."""
    scheduler_low_backlog._scanner_running = True
    result = await scheduler_low_backlog._trigger_scanner()
    assert result == {"status": "already_running"}
    scheduler_low_backlog._scanner_running = False


@pytest.mark.asyncio
async def test_low_backlog_trigger_scanner_success():
    """_trigger_scanner runs scanner successfully."""
    scheduler_low_backlog._scanner_running = False
    with mock.patch.object(scheduler_low_backlog, "_scanner_running", False):
        with mock.patch(
            "scheduler_low_backlog.run_all_scanners",
            return_value={"repo1": {"created": 5}},
            create=True,
        ):
            with mock.patch("asyncio.get_event_loop") as mel:
                mel.return_value.run_in_executor.return_value = {"repo1": {"created": 5}}
                result = await scheduler_low_backlog._trigger_scanner()
                assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_low_backlog_trigger_scanner_exception():
    """_trigger_scanner handles exception."""
    scheduler_low_backlog._scanner_running = False
    with mock.patch.object(scheduler_low_backlog, "_scanner_running", False):
        with mock.patch("asyncio.get_event_loop") as mel:
            mel.return_value.run_in_executor.side_effect = Exception("Scan fail")
            result = await scheduler_low_backlog._trigger_scanner()
            assert "error" in result


@pytest.mark.asyncio
async def test_low_backlog_actionable_count():
    """_get_actionable_available_count counts eligible tasks."""
    tasks = [
        {"id": "ok", "fail_count": 1, "max_attempts": 3},
        {"id": "dead", "fail_count": 5, "max_attempts": 3},
    ]
    with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=tasks):
        count = await scheduler_low_backlog._get_actionable_available_count()
    assert count == 1


@pytest.mark.asyncio
async def test_low_backlog_actionable_count_none():
    """_get_actionable_available_count returns 0 on None."""
    with mock.patch.object(scheduler_low_backlog, "_api_get", return_value=None):
        count = await scheduler_low_backlog._get_actionable_available_count()
    assert count == 0


@pytest.mark.asyncio
async def test_low_backlog_actionable_count_exception():
    """_get_actionable_available_count returns 0 on exception."""
    with mock.patch.object(scheduler_low_backlog, "_api_get", side_effect=Exception("Fail")):
        count = await scheduler_low_backlog._get_actionable_available_count()
    assert count == 0


@pytest.mark.asyncio
async def test_low_backlog_check_backlog_no_overview():
    """check_backlog_and_trigger returns False when no overview."""
    result = await scheduler_low_backlog.check_backlog_and_trigger(None)
    assert result is False


@pytest.mark.asyncio
async def test_low_backlog_check_backlog_high_count():
    """check_backlog_and_trigger returns False when available is above threshold."""
    scheduler_low_backlog._last_trigger_ms = 0
    overview = {"by_status": {"available": 20}}
    with mock.patch.object(
        scheduler_low_backlog, "_get_actionable_available_count", return_value=20
    ):
        with mock.patch.object(scheduler_low_backlog, "_trigger_scanner") as ts:
            result = await scheduler_low_backlog.check_backlog_and_trigger(overview)
            ts.assert_not_called()
    assert result is False


@pytest.mark.asyncio
async def test_low_backlog_check_backlog_triggers_scanner():
    """check_backlog_and_trigger triggers scanner when below threshold."""
    scheduler_low_backlog._last_trigger_ms = 0
    overview = {"by_status": {"available": 5}, "total_done": 10}
    with mock.patch.object(
        scheduler_low_backlog, "_get_actionable_available_count", return_value=5
    ):
        with mock.patch.object(
            scheduler_low_backlog, "_trigger_scanner", return_value={"repo1": {"created": 5}}
        ):
            result = await scheduler_low_backlog.check_backlog_and_trigger(overview)
    assert result is True
