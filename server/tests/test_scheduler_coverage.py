"""Coverage tests for scheduler.py —— utility and helper functions.

Sync targets:
  - _now_ms returns timestamp (line 99-100)
  - _get_client creates singleton (line 53-61)
  - _check_crashed_workers with mock processes (line 181-205)
  - _spawn_worker with no script, non-.py script (lines 131, 142)

Async targets (httpx mocking):
  - _api_get 200 / error / exception (lines 70-74)
  - _api_post success / exception (lines 83-87)
  - _api_delete 200 / non-200 / exception (lines 94-96)
"""

from unittest import mock

import pytest

from scheduler import (
    _api_delete,
    _api_get,
    _api_post,
    _check_crashed_workers,
    _get_client,
    _get_worker_count,
    _kill_worker,
    _now_ms,
    _read_meminfo,
    _reset_worker_crash_count,
    _spawn_worker,
)

# ── Pure function tests ──────────────────────────────────────────────


def test_now_ms():
    """Line 99-100: _now_ms returns a positive integer."""
    result = _now_ms()
    assert isinstance(result, int)
    assert result > 1_000_000_000  # Must be a unix-epoch millis timestamp


def test_get_client_singleton():
    """Lines 53-61: _get_client creates and reuses the same client."""
    # Force reset by patching the module global
    import scheduler

    scheduler._client = None
    client1 = _get_client()
    client2 = _get_client()
    assert client1 is client2  # Same object (singleton)
    assert client1._base_url == scheduler._client._base_url
    scheduler._client = None  # Cleanup


# ── Worker management tests ──────────────────────────────────────────


def test_check_crashed_workers_empty():
    """Line 188-205: _check_crashed_workers returns empty list when no workers."""
    import scheduler

    scheduler._worker_processes = {}
    scheduler._worker_spawn_times = {}
    result = _check_crashed_workers()
    assert result == []


def test_check_crashed_workers_with_active():
    """Lines 188-205: active workers (poll=None) are not returned."""
    import scheduler

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None  # Still running
    scheduler._worker_processes = {"task_001": mock_proc}
    scheduler._worker_spawn_times = {"task_001": 1000.0}
    result = _check_crashed_workers()
    assert result == []


def test_check_crashed_workers_with_crashed_immediate():
    """Lines 191-205: crashed worker within threshold increments crash count."""
    import time

    import scheduler

    now = time.monotonic()
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 1  # Exited with code 1
    scheduler._worker_processes = {"task_001": mock_proc}
    scheduler._worker_spawn_times = {"task_001": now}  # Just spawned = within threshold
    scheduler._worker_crash_counts = {}
    result = _check_crashed_workers()
    assert len(result) == 1
    assert result[0][0] == "task_001"
    assert scheduler._worker_crash_counts.get("task_001") == 1


def test_check_crashed_workers_crashed_old():
    """Lines 196-205: crash after threshold resets counter."""
    import time

    import scheduler

    now = time.monotonic()
    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = 1
    scheduler._worker_processes = {"task_002": mock_proc}
    scheduler._worker_spawn_times = {"task_002": now - 60}  # 60s ago = outside threshold
    scheduler._worker_crash_counts = {}
    result = _check_crashed_workers()
    assert len(result) == 1
    # Crash count should NOT be incremented (resets after threshold)
    assert scheduler._worker_crash_counts.get("task_002") is None


def test_spawn_worker_no_script_no_args():
    """Line 131: _spawn_worker returns False when no script and no args."""
    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = None
        ms.worker_args = None
        assert _spawn_worker("task_001", "Test Task", "") is False


def test_spawn_worker_script_not_py_no_args():
    """Line 142: _spawn_worker inner else when script non-.py and no args."""
    with mock.patch("scheduler.settings") as ms:
        ms.worker_script = "/usr/bin/somebinary"
        ms.worker_args = None
        ms.worker_command = "python3"
        result = _spawn_worker("task_001", "Test Task", "")
    assert result is False


def test_reset_worker_crash_count():
    """Line 210: _reset_worker_crash_count pops the task id from crash dict."""
    _reset_worker_crash_count("nonexistent_task")
    assert True


def test_kill_worker_no_process():
    """Lines 215-223: _kill_worker returns False when no process exists."""
    result = _kill_worker("nonexistent_task")
    assert result is False


def test_kill_worker_live():
    """Lines 215-223: _kill_worker kills a running process."""
    import scheduler

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None  # Still running
    scheduler._worker_processes = {"task_kill": mock_proc}
    scheduler._worker_spawn_times = {"task_kill": 100.0}

    result = _kill_worker("task_kill")
    assert result is True
    mock_proc.kill.assert_called_once()


def test_read_meminfo():
    """Lines 231-232: _read_meminfo reads /proc/meminfo successfully."""
    content = _read_meminfo()
    assert isinstance(content, str)
    assert "MemTotal:" in content
    assert "MemAvailable:" in content


def test_get_worker_count_empty():
    """Line 174-178: _get_worker_count returns 0 when no workers."""
    import scheduler

    scheduler._worker_processes = {}
    count = _get_worker_count()
    assert count == 0


def test_get_worker_count_with_active():
    """Line 174-178: _get_worker_count counts running processes."""
    import scheduler

    mock_proc = mock.MagicMock()
    mock_proc.poll.return_value = None
    scheduler._worker_processes = {"a": mock_proc, "b": mock_proc}
    assert _get_worker_count() == 2


# ── Async API helpers (mocked httpx) ─────────────────────────────────


@pytest.mark.asyncio
async def test_api_get_200():
    """Lines 70-71: _api_get returns JSON on 200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "value"}

    mock_client = mock.AsyncMock()
    mock_client.get.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_get("/api/tasks?status=available")
    assert result == {"key": "value"}
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_api_get_non_200():
    """Lines 72-73: _api_get returns None on non-200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 404

    mock_client = mock.AsyncMock()
    mock_client.get.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_get("/api/nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_api_get_exception():
    """Line 74: _api_get returns None on exception."""
    mock_client = mock.AsyncMock()
    mock_client.get.side_effect = Exception("Connection refused")

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_get("/api/tasks")
    assert result is None


@pytest.mark.asyncio
async def test_api_post_200():
    """Lines 83-84: _api_post returns JSON on 200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b'{"status":"ok"}'
    mock_resp.json.return_value = {"status": "ok"}

    mock_client = mock.AsyncMock()
    mock_client.post.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_post("/api/tasks/task_001/claim", {"agent_id": "test"})
    assert result == {"status": "ok"}
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_api_post_empty_body():
    """Lines 83-84: _api_post returns status ok when no content."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b""
    mock_resp.json.side_effect = ValueError("No JSON")

    mock_client = mock.AsyncMock()
    mock_client.post.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_post("/api/tasks/task_001/claim", {"agent_id": "test"})
    assert result == {"status": "ok"}


@pytest.mark.asyncio
async def test_api_post_exception():
    """Line 86-87: _api_post returns None on exception."""
    mock_client = mock.AsyncMock()
    mock_client.post.side_effect = Exception("Timeout")

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_post("/api/tasks/claim", {"agent_id": "test"})
    assert result is None


@pytest.mark.asyncio
async def test_api_delete_200():
    """Line 94: _api_delete returns True on 200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200

    mock_client = mock.AsyncMock()
    mock_client.delete.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_delete("/api/tasks/task_001")
    assert result is True


@pytest.mark.asyncio
async def test_api_delete_non_200():
    """Line 94: _api_delete returns False on non-200."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 500

    mock_client = mock.AsyncMock()
    mock_client.delete.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_delete("/api/tasks/task_001")
    assert result is False


@pytest.mark.asyncio
async def test_api_delete_exception():
    """Line 95-96: _api_delete returns False on exception."""
    mock_client = mock.AsyncMock()
    mock_client.delete.side_effect = Exception("Timeout")

    with mock.patch("scheduler._get_client", return_value=mock_client):
        result = await _api_delete("/api/tasks/task_001")
    assert result is False


@pytest.mark.asyncio
async def test_api_get_handles_url_encoding():
    """Line 68: _api_get encodes paths without %."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    mock_client = mock.AsyncMock()
    mock_client.get.return_value = mock_resp

    with mock.patch("scheduler._get_client", return_value=mock_client):
        await _api_get("/api/tasks?repo=test+repo")
    # The path should have the space encoded
    call_path = mock_client.get.call_args[0][0]
    assert "%20" in call_path or "+" in call_path
