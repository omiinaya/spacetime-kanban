"""Regression tests for scanner-runner dedup (board-scale, repo-scoped).

Bug (2026-07-31): server/scanners/runner.py fetched limit=500 per status
and limit=200 for done verification, capping dedup coverage at ~2,000
titles on a 22K-task board (~9%). Older done tasks (e.g. "Replace bare
except:") fell outside the cap, so the scanner kept re-creating them.

Fix: one unfiltered board-scale fetch (limit=DEDUP_LIMIT, no status
filter) plus a (repo, title) dedup key so duplicates are only suppressed
WITHIN a repo — the same title is legitimate across repos.

These tests pin the fix:
  1. _dedup_key is repo-scoped + case-insensitive.
  2. _fetch_existing_titles covers the whole board in ONE unfiltered call
     (25K rows, no per-status truncation).
  3. Two scanner runs on a repo with 2,500 existing done tasks (5
     "Replace bare except:" copies sitting beyond the old limit=500)
     create ZERO new duplicate titles within a repo.
  4. The completion verifier's done fetch also uses the board-scale limit.
"""

import time
from collections import Counter
from unittest.mock import patch

from scanners import runner

# ── Fake scanner ────────────────────────────────────────────────────────


def scan_fake(repo_name, repo_path):
    """Always finds the same issue — the dedup target in these tests."""
    return [
        {
            "title": "Replace bare except:",
            "description": f"bare except in {repo_name}",
            "priority": 2,
            "skip_verify": True,
        }
    ]


def _preseed_board(n=2500, dup_title="Replace bare except:", dup_positions=(2000, 2005)):
    """Build a board of `n` done tasks; `dup_title` appears at the given
    indices — deliberately beyond the old per-status limit=500 so the old
    code could not see them."""
    now_ms = int(time.time() * 1000)
    board = []
    lo, hi = dup_positions
    for i in range(n):
        title = f"Existing done task {i}"
        if lo <= i < hi:
            title = dup_title
        board.append(
            {
                "id": f"task_preseeded_{i}",
                "title": title,
                "repo": "repo-a",
                "status": "done",
                "roadmap_item": "Scanner: fake",
                "updated_at": now_ms,
            }
        )
    return board


class _FakeAPI:
    """In-memory stand-in for the kanban REST API (GET + POST)."""

    def __init__(self, board):
        self.board = board
        self.get_calls: list[str] = []
        self.created: list[dict] = []

    def get(self, path: str):
        self.get_calls.append(path)
        if path == f"/api/tasks?limit={runner.DEDUP_LIMIT}":
            return self.board
        if path.startswith("/api/tasks?status=done&repo="):
            repo = path.split("repo=")[1].split("&")[0]
            return [t for t in self.board if t["repo"] == repo and t["status"] == "done"]
        if path.startswith("/api/tasks?repo="):
            repo = path.split("repo=")[1].split("&")[0]
            return [t for t in self.board if t["repo"] == repo]
        return None

    def post(self, path: str, data: dict):
        if path == "/api/tasks":
            task = dict(data)
            task["id"] = f"task_created_{len(self.created)}"
            task["status"] = "available"
            task["repo"] = data["repo"]
            self.board.append(task)
            self.created.append(task)
            return {"status": "ok"}
        return {"status": "ok"}


# ── Unit: dedup key ─────────────────────────────────────────────────────


class TestDedupKey:
    def test_repo_scoped_same_title_different_repos(self):
        """Same title in two repos is NOT a duplicate — distinct keys."""
        a = runner._dedup_key("repo-a", "Replace bare except:")
        b = runner._dedup_key("repo-b", "Replace bare except:")
        assert a != b

    def test_case_insensitive(self):
        """Whitespace + case are normalized away."""
        k1 = runner._dedup_key("  Repo-A ", "Replace Bare Except:")
        k2 = runner._dedup_key("repo-a", "replace bare except:")
        assert k1 == k2


# ── Unit: board-scale fetch ─────────────────────────────────────────────


class TestFetchExistingTitles:
    def test_covers_whole_board_in_one_unfiltered_call(self):
        """25K tasks (bigger than the old 4×500=2K cap) are ALL seen."""
        board = [{"repo": "repo-a", "title": f"task {i}"} for i in range(25_000)]
        api = _FakeAPI(board)
        with patch.object(runner, "_api_get", side_effect=api.get):
            existing = runner._fetch_existing_titles()

        assert len(existing) == 25_000
        assert ("repo-a", "task 0") in existing
        assert ("repo-a", "task 24999") in existing

    def test_single_request_no_status_filter(self):
        """The dedup fetch is ONE call with the board-scale limit and no
        status= filter — the old code made 4 calls capped at 500 each."""
        api = _FakeAPI([])
        with patch.object(runner, "_api_get", side_effect=api.get):
            runner._fetch_existing_titles()

        assert len(api.get_calls) == 1
        assert api.get_calls[0] == f"/api/tasks?limit={runner.DEDUP_LIMIT}"
        assert "status=" not in api.get_calls[0]


# ── Regression: two scanner runs → zero new duplicates within a repo ────


class TestTwoScannerRuns:
    def test_no_duplicate_titles_within_repo(self, monkeypatch):
        """Run the scanner twice against a repo that already has 2,500 done
        tasks (incl. 5 'Replace bare except:' beyond the old limit=500).
        The scanner must not re-create any of them — and the second run
        must create nothing at all."""
        board = _preseed_board()
        api = _FakeAPI(board)
        repos = [("repo-a", "/tmp/repo-a"), ("repo-b", "/tmp/repo-b")]

        monkeypatch.setenv("WEBHOOK_DEFAULT_URL", "")
        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "SCANNERS", [scan_fake]),
        ):
            run1 = runner.run_all_scanners(repos, time_budget=60)
            run2 = runner.run_all_scanners(repos, time_budget=60)

        # repo-a already had the title (5 done copies) → nothing created.
        # repo-b did not → exactly one legitimate task created in run 1.
        assert run1["fake"]["created"] == 1
        assert run2["fake"]["created"] == 0

        # The pre-existing 5 done copies must NOT have grown to 6.
        repo_a_dups = [
            t for t in board if t["repo"] == "repo-a" and t["title"] == "Replace bare except:"
        ]
        assert len(repo_a_dups) == 5
        # repo-b has exactly one (created in run 1, never duplicated in run 2).
        repo_b_dups = [
            t for t in board if t["repo"] == "repo-b" and t["title"] == "Replace bare except:"
        ]
        assert len(repo_b_dups) == 1

        # No two tasks CREATED by the scanner share a (repo, title) key.
        created_keys = [(t["repo"], t["title"].strip().lower()) for t in api.created]
        assert all(count == 1 for count in Counter(created_keys).values())

    def test_dedup_fetch_is_board_scale_in_full_run(self, monkeypatch):
        """The scanner run must query the board once at DEDUP_LIMIT with no
        status filter (old code: 4×limit=500) and use the board-scale limit
        for the done-tasks verifier fetch too (old code: limit=200)."""
        board = _preseed_board()
        api = _FakeAPI(board)
        repos = [("repo-a", "/tmp/repo-a")]

        monkeypatch.setenv("WEBHOOK_DEFAULT_URL", "")
        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "SCANNERS", [scan_fake]),
        ):
            runner.run_all_scanners(repos, time_budget=60)

        dedup_calls = [c for c in api.get_calls if c == f"/api/tasks?limit={runner.DEDUP_LIMIT}"]
        assert len(dedup_calls) >= 1
        done_calls = [c for c in api.get_calls if "status=done" in c]
        assert done_calls, "verifier should fetch done tasks"
        assert all(f"limit={runner.DEDUP_LIMIT}" in c for c in done_calls), (
            "verifier must use the board-scale limit, not limit=200"
        )


# ── Completion verifier uses board-scale limit ──────────────────────────


class TestVerifyCompletedTasksLimit:
    def test_done_fetch_uses_board_scale_limit(self):
        """_verify_completed_tasks must request done tasks at DEDUP_LIMIT
        (old code hardcoded limit=200, missing older done tasks)."""
        board = _preseed_board()
        api = _FakeAPI(board)
        with (
            patch.object(runner, "_api_get", side_effect=api.get),
            patch.object(runner, "_api_post", side_effect=api.post),
            patch.object(runner, "SCANNERS", []),  # verifier loop only
        ):
            regressed = runner._verify_completed_tasks([("repo-a", "/tmp/repo-a")], set())

        assert regressed == 0
        done_calls = [c for c in api.get_calls if "status=done" in c]
        assert done_calls
        assert all(f"limit={runner.DEDUP_LIMIT}" in c for c in done_calls)
        assert all("limit=200" not in c for c in done_calls)
