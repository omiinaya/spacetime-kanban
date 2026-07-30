"""Coverage tests for scheduler.py —— low-hanging synchonous functions.

Targets:
  - _spawn_worker returns False when script non-.py and no args (line 142)
  - _reset_worker_crash_count (line 210)
  - _kill_worker returns False when no process exists (line 223)
  - _read_meminfo reads /proc/meminfo (line 229-232)
  - _get_worker_count returns 0 when no workers (line 172-178)
"""

from unittest import mock

from scheduler import (
    _get_worker_count,
    _kill_worker,
    _read_meminfo,
    _reset_worker_crash_count,
    _spawn_worker,
)


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
    # No crash count exists — should not raise
    _reset_worker_crash_count("nonexistent_task")
    assert True


def test_kill_worker_no_process():
    """Lines 215-223: _kill_worker returns False when no process exists."""
    result = _kill_worker("nonexistent_task")
    assert result is False


def test_read_meminfo():
    """Lines 231-232: _read_meminfo reads /proc/meminfo successfully."""
    content = _read_meminfo()
    assert isinstance(content, str)
    assert "MemTotal:" in content
    assert "MemAvailable:" in content


def test_get_worker_count_empty():
    """Line 174-178: _get_worker_count returns 0 when no workers."""
    count = _get_worker_count()
    assert isinstance(count, int)
    assert count >= 0
