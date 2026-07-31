"""Tests for the worker stderr drain thread (scheduler._drain_worker_stderr).

Root cause regression: workers were spawned with stderr=PIPE and nothing
drained the pipe while the worker was alive. The OS pipe buffer is ~64KB,
so a chatty worker's write() blocked forever once the buffer filled — the
worker froze mid-task, stopped heartbeating, and the board raised
'stale worker' alerts. These tests prove:

  1. A worker writing MORE than the pipe buffer completes without hanging
     (the drain thread keeps the pipe empty).
  2. The drain buffer is bounded (only the tail is kept).
  3. Edge cases: None stream, read error, non-byte chunks.
"""

import subprocess
import sys
import threading

import pytest

import scheduler
from scheduler import _WORKER_STDERR_MAX_BYTES, _drain_worker_stderr, _spawn_worker

# ── _drain_worker_stderr unit tests ──────────────────────────────────


class _FakeStream:
    """A file-like object that yields fixed chunks then EOF."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.reads = 0

    def read(self, size):
        self.reads += 1
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class _FakeProc:
    def __init__(self, stream):
        self.stderr = stream


def test_drain_collects_stderr():
    """Chunks are accumulated into _worker_stderr_data."""
    scheduler._worker_stderr_data = {}
    proc = _FakeProc(_FakeStream([b"line1\n", b"line2\n", b"line3\n"]))
    _drain_worker_stderr("t_drain_1", proc)
    assert scheduler._worker_stderr_data["t_drain_1"] == b"line1\nline2\nline3\n"


def test_drain_bounded_buffer():
    """Buffer is capped at _WORKER_STDERR_MAX_BYTES (tail only)."""
    scheduler._worker_stderr_data = {}
    big = b"x" * (2 * _WORKER_STDERR_MAX_BYTES)
    # Feed in 8KB chunks so the loop sees multiple reads
    chunks = [big[i : i + 8192] for i in range(0, len(big), 8192)]
    proc = _FakeProc(_FakeStream(chunks))
    _drain_worker_stderr("t_drain_big", proc)
    data = scheduler._worker_stderr_data["t_drain_big"]
    assert len(data) == _WORKER_STDERR_MAX_BYTES
    # Tail is kept, head is dropped
    assert data == big[-_WORKER_STDERR_MAX_BYTES:]


def test_drain_none_stream():
    """proc.stderr is None → returns without error, no data stored."""
    scheduler._worker_stderr_data = {}
    proc = _FakeProc(None)
    _drain_worker_stderr("t_drain_none", proc)
    assert "t_drain_none" not in scheduler._worker_stderr_data


def test_drain_read_exception():
    """Read error is swallowed — drain must never crash the server."""

    class BoomStream:
        def read(self, size):
            raise OSError("pipe closed")

    scheduler._worker_stderr_data = {}
    proc = _FakeProc(BoomStream())
    # Should not raise
    _drain_worker_stderr("t_drain_boom", proc)
    assert "t_drain_boom" not in scheduler._worker_stderr_data


def test_drain_nonbytes_chunk():
    """Non-bytes chunks (e.g. a mock stream) are skipped, not extended."""

    class WeirdStream:
        def read(self, size):
            return object()

    scheduler._worker_stderr_data = {}
    proc = _FakeProc(WeirdStream())
    # Should not raise and not store garbage
    _drain_worker_stderr("t_drain_weird", proc)
    assert "t_drain_weird" not in scheduler._worker_stderr_data


# ── Real-subprocess regression: chatty worker must not hang ──────────


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pipe semantics")
def test_chatty_worker_does_not_hang(monkeypatch):
    """A worker writing >64KB to stderr completes instead of blocking.

    Regression for the root cause of stale-worker alerts: with no drain
    thread, the child's write() blocks forever once the OS pipe buffer
    (~64KB) fills. The drain thread keeps the pipe empty, so a 256KB
    stderr burst completes normally.
    """
    import scheduler as sched_mod

    sched_mod._worker_processes = {}
    sched_mod._worker_spawn_times = {}
    sched_mod._worker_stderr_data = {}
    sched_mod._worker_stderr_threads = {}
    sched_mod._worker_crash_counts = {}

    script = (
        "import sys\n"
        "sys.stderr.write('x' * 262144)\n"
        "sys.stderr.flush()\n"
        "sys.stderr.write('TAIL_MARKER\\n')\n"
    )
    with open("/tmp/chatty_worker_test.py", "w") as f:
        f.write(script)

    class _Settings:
        worker_script = "/tmp/chatty_worker_test.py"
        worker_args = ""
        worker_command = sys.executable
        agent_id = "test"
        server_port = 8727

    monkeypatch.setattr(sched_mod, "settings", _Settings())
    result = _spawn_worker("t_chatty", "Chatty test", "test-repo")
    assert result is True

    proc = sched_mod._worker_processes["t_chatty"]
    # Must exit on its own — old code hung here forever (pipe full)
    try:
        exit_code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("worker blocked on full stderr pipe (drain missing)") from None

    assert exit_code == 0
    # Wait for the drain thread to finish flushing its buffer
    drain_thread = sched_mod._worker_stderr_threads.get("t_chatty")
    if drain_thread:
        drain_thread.join(timeout=5)
    data = sched_mod._worker_stderr_data.get("t_chatty", b"")
    assert b"TAIL_MARKER" in data
    assert len(data) <= _WORKER_STDERR_MAX_BYTES

    sched_mod._worker_processes = {}
    sched_mod._worker_spawn_times = {}
    sched_mod._worker_stderr_data = {}
    sched_mod._worker_stderr_threads = {}


def test_spawn_worker_starts_drain_thread(monkeypatch):
    """_spawn_worker starts a drain thread for the worker's stderr pipe."""
    import scheduler as sched_mod

    class _FakeThread(threading.Thread):
        def __init__(self, **kwargs):
            self._kw = kwargs
            super().__init__(**kwargs)
            self.started = False
            self._handles.append(self)

        _handles = []

        def start(self):
            self.started = True

    sched_mod._worker_processes = {}
    sched_mod._worker_spawn_times = {}
    sched_mod._worker_stderr_data = {}
    sched_mod._worker_stderr_threads = {}

    class _Settings:
        worker_script = "/tmp/chatty_worker_test.py"
        worker_args = ""
        worker_command = sys.executable
        agent_id = "test"
        server_port = 8727

    monkeypatch.setattr(sched_mod, "settings", _Settings())
    monkeypatch.setattr(sched_mod.threading, "Thread", _FakeThread)
    result = _spawn_worker("t_drain_thread", "Test", "test-repo")
    assert result is True
    # The drain thread must have been created with _drain_worker_stderr target
    targets = [t._kw.get("target") for t in _FakeThread._handles]
    assert _drain_worker_stderr in targets
    # And recorded in the thread registry
    assert "t_drain_thread" in sched_mod._worker_stderr_threads
    # Cleanup real proc (if spawned)
    proc = sched_mod._worker_processes.get("t_drain_thread")
    if proc and proc.poll() is None:
        proc.kill()
    sched_mod._worker_processes = {}
    sched_mod._worker_spawn_times = {}
    sched_mod._worker_stderr_data = {}
    sched_mod._worker_stderr_threads = {}
