"""Tests for the scanner's stale-available-task closer.

Complement to the regressed-done verifier: when a scanner task is still
available (never claimed) but its originating scanner no longer reports
the finding, the task is stale — closing it stops workers from burning
turns on non-issues.
"""

import time
from unittest.mock import patch

from scanners import runner


def scan_stale_fake(repo_name, repo_path):
    """Returns a finding the closer can make vanish between runs."""
    return [
        {
            "title": "Still broken thing",
            "description": f"present in {repo_name}",
            "priority": 2,
        }
    ]


def gone_scanner(repo_name, repo_path):
    """Scanner that no longer finds anything — the 'fixed' case."""
    return []


class _FakeAPI:
    """In-memory stand-in for the kanban REST API (GET + POST)."""

    def __init__(self, board):
        self.board = board
        self.posts: list[tuple[str, dict]] = []
        self.get_calls: list[str] = []

    def get(self, path: str):
        self.get_calls.append(path)
        if path == f"/api/tasks?limit={runner.DEDUP_LIMIT}":
            return self.board
        if path.startswith("/api/tasks?status=done&repo="):
            repo = path.split("repo=")[1].split("&")[0]
            return [t for t in self.board if t["repo"] == repo and t["status"] == "done"]
        if path.startswith("/api/tasks?status=available&repo="):
            repo = path.split("repo=")[1].split("&")[0]
            return [t for t in self.board if t["repo"] == repo and t["status"] == "available"]
        if path.startswith("/api/tasks?repo="):
            repo = path.split("repo=")[1].split("&")[0]
            return [t for t in self.board if t["repo"] == repo]
        return None

    def post(self, path: str, data: dict):
        self.posts.append((path, data))
        if path == "/api/tasks":
            task = dict(data)
            task["id"] = f"task_created_{len(self.board)}"
            task["status"] = "available"
            task["repo"] = data["repo"]
            self.board.append(task)
            return {"status": "ok"}
        return {"status": "ok"}


def _mk_task(tid, title, status="available", roadmap="Scanner: stale_fake", created_days_ago=1):
    now_ms = int(time.time() * 1000)
    return {
        "id": tid,
        "title": title,
        "repo": "repo-a",
        "status": status,
        "roadmap_item": roadmap,
        "created_at": now_ms - created_days_ago * 86400 * 1000,
        "updated_at": now_ms,
    }


class TestCloseStaleAvailableTasks:
    def test_stale_finding_vanished_closed(self):
        """Available scanner task whose finding is gone → block + archive."""
        board = [_mk_task("task_stale", "Still broken thing")]
        api = _FakeAPI(board)

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=gone_scanner),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 1
        # Stale task must be blocked (available → blocked) then archived
        paths = [p for p, _ in api.posts]
        assert "/api/tasks/task_stale/block" in paths
        assert "/api/tasks/task_stale/archive" in paths
        # No new task created
        assert not any(p == "/api/tasks" for p, _ in api.posts)

    def test_scanner_returns_nothing_closes(self):
        """Finder emits [] → its available task is stale and gets closed."""
        board = [_mk_task("task_gone", "Still broken thing")]
        api = _FakeAPI(board)

        def gone_scanner(repo_name, repo_path):
            return []

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=gone_scanner),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 1
        paths = [p for p, _ in api.posts]
        assert "/api/tasks/task_gone/block" in paths
        assert "/api/tasks/task_gone/archive" in paths

    def test_finding_still_present_untouched(self):
        """Available task whose finding STILL exists → left alone."""
        board = [_mk_task("task_live", "Still broken thing")]
        api = _FakeAPI(board)

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=scan_stale_fake),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 0
        assert api.posts == []

    def test_non_scanner_task_ignored(self):
        """A task without a 'Scanner:' roadmap_item is never touched."""
        board = [
            {
                "id": "task_manual",
                "title": "Manual user task",
                "repo": "repo-a",
                "status": "available",
                "roadmap_item": "Phase 2 — Features",
                "created_at": int(time.time() * 1000),
            }
        ]
        api = _FakeAPI(board)

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=scan_stale_fake),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 0
        assert api.posts == []

    def test_unknown_scanner_skipped(self):
        """If the scanner function can't be resolved, the task is untouched."""
        board = [_mk_task("task_x", "Some thing")]
        api = _FakeAPI(board)

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=None),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 0
        assert api.posts == []

    def test_old_task_ignored(self):
        """Tasks created >30 days ago are never auto-closed."""
        board = [_mk_task("task_old", "Still broken thing", created_days_ago=45)]
        api = _FakeAPI(board)

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=scan_stale_fake),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 0
        assert api.posts == []

    def test_scanner_exception_aborts_pass_safely(self):
        """A scanner that throws must not close anything."""
        board = [_mk_task("task_s", "Still broken thing")]
        api = _FakeAPI(board)

        def boom(repo_name, repo_path):
            raise RuntimeError("scanner exploded")

        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "_scanner_by_name", return_value=boom),
        ):
            closed = runner._close_stale_available_tasks([("repo-a", "/tmp/repo-a")], set())

        assert closed == 0
        assert api.posts == []
