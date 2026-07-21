"""Kanban worker base — shared lifecycle for all worker types.

Every worker follows the same protocol:
  1. Receive a claimed task_id
  2. Read task details from the API
  3. Do the work (LLM-driven or scripted)
  4. Send heartbeats every 15s while working
  5. Complete or block via API
  6. Exit with exit code (0=done, 1=blocked, 2=error)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")
AGENT_ID = os.environ.get("AGENT_ID", "hermes")
HEARTBEAT_INTERVAL = 15  # seconds between heartbeats


# ── API helpers ─────────────────────────────────────────────────────

def api_get(path: str, timeout: int = 15) -> dict | list | None:
    try:
        req = urllib.request.Request(f"{API_BASE}{path}")
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[worker] GET {path} failed: {e}", file=sys.stderr)
        return None


def api_post(path: str, data: dict, timeout: int = 15) -> dict | None:
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(f"{API_BASE}{path}", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=timeout)
        content = resp.read().decode()
        return json.loads(content) if content else {"status": "ok"}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()[:200]
        print(f"[worker] POST {path} HTTP {e.code}: {err_body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[worker] POST {path} failed: {e}", file=sys.stderr)
        return None


# ── Worker state ────────────────────────────────────────────────────

class WorkerContext:
    """Holds state for an active worker session."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self.task = None
        self._heartbeat_count = 0
        self._running = True

    def load_task(self) -> bool:
        """Fetch task details from the kanban API."""
        result = api_get(f"/api/tasks/{self.task_id}")
        if not result:
            print(f"[worker] Task {self.task_id[:20]} not found", file=sys.stderr)
            return False
        self.task = result
        return True

    @property
    def title(self) -> str:
        return (self.task or {}).get("title", "?")

    @property
    def repo(self) -> str:
        return (self.task or {}).get("repo", "")

    @property
    def repo_path(self) -> str | None:
        """Return the absolute path to the repo directory, or None."""
        repo = self.repo
        if not repo:
            return None
        path = os.path.expanduser(f"~/{repo}")
        return path if os.path.isdir(path) else None

    def heartbeat(self) -> bool:
        """Send a heartbeat via activity log. Returns False on failure."""
        result = api_post(
            f"/api/tasks/{self.task_id}/log",
            {
                "task_id": self.task_id,
                "action": "heartbeat",
                "agent_id": AGENT_ID,
                "notes": f"worker heartbeat #{self._heartbeat_count}",
            },
        )
        if result:
            self._heartbeat_count += 1
        return result is not None

    def add_log(self, action: str, details: str = ""):
        """Add an activity log entry."""
        api_post(
            f"/api/tasks/{self.task_id}/log",
            {
                "task_id": self.task_id,
                "action": action,
                "agent_id": AGENT_ID,
                "notes": details,
            },
        )

    def complete(self, notes: str = "") -> bool:
        """Mark the task as done."""
        self._running = False
        result = api_post(
            f"/api/tasks/{self.task_id}/complete",
            {"result_notes": notes or "Completed by worker"},
        )
        return result is not None

    def block(self, reason: str = "") -> bool:
        """Mark the task as blocked."""
        self._running = False
        result = api_post(
            f"/api/tasks/{self.task_id}/block",
            {"reason": reason or "Blocked by worker"},
        )
        return result is not None

    def unclaim(self) -> bool:
        """Release the task back to available."""
        self._running = False
        result = api_post(f"/api/tasks/{self.task_id}/unclaim", {})
        return result is not None


# ── Heartbeat loop ──────────────────────────────────────────────────

def heartbeat_loop(ctx: WorkerContext):
    """Run in a thread: send heartbeats every HEARTBEAT_INTERVAL seconds."""
    import threading

    def _loop():
        while ctx._running:
            time.sleep(HEARTBEAT_INTERVAL)
            if ctx._running:
                ctx.heartbeat()

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


# ── Entry helpers ──────────────────────────────────────────────────

def run_worker(task_id: str, work_fn):
    """Standard worker entry point.

    Args:
        task_id: The kanban task ID to work on.
        work_fn: Callable(WorkerContext) -> (success: bool, message: str)

    Returns exit code (0=done, 1=blocked, 2=error).
    """
    ctx = WorkerContext(task_id)
    if not ctx.load_task():
        print(f"[worker] Cannot load task {task_id[:20]}", file=sys.stderr)
        return 2

    print(f"[worker] Starting on: {ctx.title[:80]}", file=sys.stderr)
    ctx.add_log("worker_started", f"Worker started on: {ctx.title[:100]}")

    # Start heartbeat thread
    hb_thread = heartbeat_loop(ctx)

    try:
        success, message = work_fn(ctx)
        if success:
            ctx.complete(message)
            print(f"[worker] ✅ Completed: {message}", file=sys.stderr)
            return 0
        else:
            ctx.block(message)
            print(f"[worker] 🚫 Blocked: {message}", file=sys.stderr)
            return 1
    except Exception as e:
        error_msg = f"Worker crashed: {e}"
        ctx.block(error_msg)
        print(f"[worker] 💥 {error_msg}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2
    finally:
        ctx._running = False
        hb_thread.join(timeout=5)
