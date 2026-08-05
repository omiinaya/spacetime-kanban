"""Tests for blocked-task remediation (blocked_remediation.py + scheduler loop).

Covers:
- blocked_dismiss_reason classification (scanner artifacts, [Stale] copies,
  .venv references, non-existent paths)
- _extract_referenced_paths parsing
- run_blocked_remediation batching/archival/webhook behavior
- scheduler.blocked_remediator loop wiring
- analytics/health by_status excluding archived tasks
"""

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

import blocked_remediation as br


@pytest.fixture
def mock_all():
    """Mock STDB helpers for route tests (mirrors test_coverage_routes.mock_all)."""
    route_modules = {
        "routes.agents": ["_sql", "_sql_param", "_call"],
        "routes.analytics": ["_sql", "_sql_param"],
        "routes.health": [],
        "routes.labels": ["_sql", "_sql_param", "_call"],
        "routes.logs": ["_sql"],
        "routes.projects": ["_sql", "_sql_param", "_call"],
        "routes.tasks": ["_sql", "_sql_param", "_call", "_notify"],
        "routes.templates": ["_sql", "_sql_param", "_call"],
        "routes.ops": ["_sql", "_sql_param", "_call"],
        "routes.dispatcher": ["_sql", "_sql_param", "_call"],
        "routes.rules": ["_sql", "_sql_param", "_call"],
        "routes.apikeys": ["_sql", "_call"],
    }
    with ExitStack() as stack:
        sql = AsyncMock(return_value=[])
        param = AsyncMock(return_value=[])
        call = AsyncMock(return_value={"status": "ok"})
        notify = AsyncMock(return_value=None)
        mock_map = {"_sql": sql, "_sql_param": param, "_call": call, "_notify": notify}
        for mod, names in route_modules.items():
            for name in names:
                stack.enter_context(patch(f"{mod}.{name}", mock_map[name]))
        # Patch shared for dynamic imports (health endpoint)
        stack.enter_context(patch("shared._sql", mock_map["_sql"]))
        yield {"sql": sql, "param": param, "call": call, "notify": notify}


# ── blocked_dismiss_reason ───────────────────────────────────────────


class TestDismissReason:
    def test_stale_title_dismissed(self):
        task = {
            "title": "[Stale] Task stuck in_progress: whatever",
            "description": "",
            "fail_reason": "",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_no_indexable_fields_dismissed(self):
        task = {
            "title": "Add #[index(btree)] to 5 field(s) in sample-repo-d (35/35)",
            "description": "Found 5 foreign-key-like fields missing #[index(btree)]",
            "fail_reason": "No indexable fields found in sample-repo-d — all foreign keys already indexed",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_no_extractable_functions_dismissed(self):
        task = {
            "title": "Split 5 large source file(s) in spacetime-x",
            "description": "Recommend splitting large files",
            "fail_reason": "No extractable functions/classes found in /home/x/y.py",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_no_test_files_dismissed(self):
        task = {
            "title": "Add tests for 5 untested Python module(s) in sample-repo-r (3/7)",
            "description": "The following Python source files don't have corresponding test files",
            "fail_reason": "No test files created (all test files already exist)",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_one_top_level_item_dismissed(self):
        task = {
            "title": "Split 2 large source file(s) in sample-repo-n",
            "description": "Recommend splitting",
            "fail_reason": (
                "/home/test/sample-repo-n/server/proxy/src/admin_handlers.rs "
                "only has one top-level item — nothing to extract"
            ),
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_no_source_files_dismissed(self):
        task = {
            "title": "Add tests for 5 untested Rust module(s) in some-repo",
            "description": "Missing #[cfg(test)] blocks",
            "fail_reason": "No .rs or .py source files found in repo",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_no_init_py_dismissed(self):
        task = {
            "title": "Add __init__.py to 3 Python package(s) in some-repo",
            "description": "Directories with .py but no __init__.py",
            "fail_reason": "No __init__.py files created (all already exist)",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_venv_paths_dismissed(self):
        task = {
            "title": "Split 5 large source file(s) in spacetime-kanban (5/5)",
            "description": (
                "Found 689 large source file(s) ≥300 lines. Recommend splitting:\n"
                "  - /home/test/spacetime-kanban/server/.venv/lib/python3.11/"
                "site-packages/idna/uts46data.py (16896 lines)\n"
                "  - /home/test/spacetime-kanban/server/.venv/lib/python3.11/"
                "site-packages/mypy/checker.py (10012 lines)"
            ),
            "fail_reason": "",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_site_packages_in_fail_reason_dismissed(self):
        task = {
            "title": "Split 1 large source file(s) in some-repo",
            "description": "Recommend splitting",
            "fail_reason": "No extractable functions found in .../site-packages/foo.py",
        }
        assert br.blocked_dismiss_reason(task) is not None

    def test_nonexistent_relative_paths_dismissed(self, tmp_path):
        task = {
            "title": "Add tests for 5 untested Python module(s) in sample-repo-r (2/7)",
            "description": (
                "The following Python source files don't have corresponding test files:\n"
                "  - server/scanners/gaps.py\n"
                "  - server/routes/analytics.py"
            ),
            "fail_reason": "",
        }
        reason = br.blocked_dismiss_reason(task, repo_path=str(tmp_path))
        assert reason is not None
        assert "no longer exist" in reason

    def test_existing_paths_left_alone(self, tmp_path):
        (tmp_path / "server").mkdir()
        (tmp_path / "server" / "gaps.py").write_text("x = 1\n")
        task = {
            "title": "Add tests for 5 untested Python module(s) in sample-repo-r",
            "description": (
                "The following Python source files don't have corresponding test files:\n"
                "  - server/gaps.py"
            ),
            "fail_reason": "",
        }
        assert br.blocked_dismiss_reason(task, repo_path=str(tmp_path)) is None

    def test_existing_absolute_path_left_alone(self, tmp_path):
        real = tmp_path / "real.py"
        real.write_text("x = 1\n")
        task = {
            "title": "Split 2 large source file(s) in x",
            "description": f"Recommend splitting:\n  - {real} (999 lines)",
            "fail_reason": "",
        }
        assert br.blocked_dismiss_reason(task, repo_path=str(tmp_path)) is None

    def test_missing_absolute_path_dismissed(self, tmp_path):
        task = {
            "title": "Split 2 large source file(s) in x",
            "description": f"Recommend splitting:\n  - {tmp_path}/gone.py (999 lines)",
            "fail_reason": "",
        }
        assert br.blocked_dismiss_reason(task, repo_path=str(tmp_path)) is not None

    def test_clean_task_left_alone(self):
        task = {
            "title": "Add DNS-over-HTTPS fallback",
            "description": "When Pi-hole upstream fails, fall back to DoH",
            "fail_reason": "Blocked on upstream API rate limits",
        }
        assert br.blocked_dismiss_reason(task) is None


# ── _extract_referenced_paths ────────────────────────────────────────


class TestExtractPaths:
    def test_strips_line_annotations(self):
        desc = "Files:\n  - server/routes/tasks.py (1234 lines)\n  - /abs/path/thing.rs (999 lines)"
        assert br._extract_referenced_paths(desc) == [
            "server/routes/tasks.py",
            "/abs/path/thing.rs",
        ]

    def test_skips_non_path_bullets(self):
        desc = "Notes:\n  - 2 files need attention\n  - cleanup"
        assert br._extract_referenced_paths(desc) == []

    def test_skips_empty_token_after_annotation_strip(self):
        """A bullet that is ONLY a line-annotation must be skipped (no token)."""
        desc = "Files:\n  - (1234 lines)\n  - (999 lines)"
        assert br._extract_referenced_paths(desc) == []

    def test_empty_description(self):
        assert br._extract_referenced_paths("") == []


# ── _repo_path_for ────────────────────────────────────────────────────


class TestRepoPathFor:
    def test_empty_repo_returns_none(self):
        assert br._repo_path_for("") is None
        assert br._repo_path_for(None) is None


# ── run_blocked_remediation ──────────────────────────────────────────


class TestRunRemediation:
    @pytest.mark.asyncio
    async def test_no_blocked_tasks(self):
        async def get(path, timeout=60):
            return []

        posts = []
        events = []

        async def post(path, data, timeout=60):
            posts.append((path, data))
            return {"status": "ok", "archived": 0}

        async def fire(event, data):
            events.append((event, data))

        summary = await br.run_blocked_remediation(get, post, fire, now_ms=1_000_000_000)
        assert summary["fetched"] == 0
        assert summary["archived"] == 0
        assert posts == []
        assert events == []

    @pytest.mark.asyncio
    async def test_archives_and_fires_event(self):
        old = 1_000_000_000  # far in the past
        tasks = [
            {
                "id": "task_stale_copy",
                "title": "[Stale] Task stuck in_progress: Add tests (5/5)",
                "description": "Task task_abc has been in_progress without heartbeat",
                "fail_reason": "",
                "repo": "spacetime-kanban",
                "updated_at": old,
            },
            {
                "id": "task_noindex",
                "title": "Add #[index(btree)] to 5 field(s) in sample-repo-d (35/35)",
                "description": "Found fields missing #[index(btree)]",
                "fail_reason": "No indexable fields found in sample-repo-d",
                "repo": "sample-repo-d",
                "updated_at": old,
            },
            {
                "id": "task_venv",
                "title": "Split 5 large source file(s) in spacetime-kanban (5/5)",
                "description": "  - /x/.venv/lib/python3.11/site-packages/idna/uts46data.py (16896 lines)",
                "fail_reason": "",
                "repo": "spacetime-kanban",
                "updated_at": old,
            },
            {
                "id": "task_old_blocked",
                "title": "Add tests for 5 untested Python module(s) in sample-repo-r",
                "description": "The following Python source files don't have tests",
                "fail_reason": "",
                "repo": "no-such-repo",  # not on disk → file-existence check skipped
                "updated_at": old,
            },
            {
                "id": "task_fresh",
                "title": "Add DNS fallback",
                "description": "Real work item",
                "fail_reason": "",
                "repo": "sample-repo-p",
                "updated_at": 9_999_999_999_999,  # recent → not stale
            },
        ]

        async def get(path, timeout=60):
            return tasks

        posts = []
        events = []

        async def post(path, data, timeout=60):
            posts.append((path, list(data.get("task_ids", []))))
            return {"status": "ok", "archived": len(data.get("task_ids", []))}

        async def fire(event, data):
            events.append((event, data))

        summary = await br.run_blocked_remediation(
            get, post, fire, now_ms=10_000_000_000_000, stale_days=3, batch_size=2
        )
        assert summary["fetched"] == 5
        assert summary["archived"] == 4
        assert summary["auto_dismissed"] == 3  # [Stale], no-index, .venv
        assert summary["stale_archived"] == 1  # old blocked w/o other reason
        assert summary["active_blocked"] == 1
        # batched: 4 tasks in batches of 2 → 2 posts
        assert len(posts) == 2
        archived_ids = [tid for _path, ids in posts for tid in ids]
        assert "task_stale_copy" in archived_ids
        assert "task_noindex" in archived_ids
        assert "task_venv" in archived_ids
        assert "task_old_blocked" in archived_ids
        assert "task_fresh" not in archived_ids
        assert len(events) == 1
        assert events[0][0] == "board.blocked_remediated"
        assert events[0][1]["archived"] == 4

    @pytest.mark.asyncio
    async def test_failed_batches_not_counted(self):
        """A failed bulk-archive POST must not inflate the archived count."""
        tasks = [
            {
                "id": f"task_{i}",
                "title": f"Split 2 large source file(s) in repo-{i}",
                "description": f"  - /x/.venv/lib/site-packages/file{i}.py (900 lines)",
                "fail_reason": "",
                "repo": "r",
                "updated_at": 0,
            }
            for i in range(3)
        ]

        async def get(path, timeout=60):
            return tasks

        async def post(path, data, timeout=60):
            return None  # simulate timeout/error

        events = []

        async def fire(event, data):
            events.append((event, data))

        summary = await br.run_blocked_remediation(get, post, fire, now_ms=10_000_000_000_000)
        assert summary["archived"] == 0
        assert events == []  # nothing archived → no webhook

    @pytest.mark.asyncio
    async def test_per_tick_cap(self):
        tasks = [
            {
                "id": f"task_{i}",
                "title": f"Split 2 large source file(s) in repo-{i}",
                "description": f"  - /x/.venv/lib/site-packages/file{i}.py (900 lines)",
                "fail_reason": "",
                "repo": "r",
                "updated_at": 0,
            }
            for i in range(10)
        ]

        async def get(path, timeout=60):
            return tasks

        archived_total = []

        async def post(path, data, timeout=60):
            ids = list(data.get("task_ids", []))
            archived_total.extend(ids)
            return {"status": "ok", "archived": len(ids)}

        async def fire(event, data):
            pass

        summary = await br.run_blocked_remediation(
            get, post, fire, now_ms=10_000_000_000_000, max_archive_per_tick=4, batch_size=10
        )
        assert summary["archived"] == 4
        assert len(archived_total) == 4

    @pytest.mark.asyncio
    async def test_task_without_id_skipped(self):
        """A blocked row with no id must not crash the run — it's skipped."""
        tasks = [
            {"title": "[Stale] orphan", "description": "", "fail_reason": "", "updated_at": 0},
            {
                "id": "task_real",
                "title": "[Stale] real copy",
                "description": "Task task_abc has been in_progress",
                "fail_reason": "",
                "updated_at": 0,
            },
        ]
        posts = []

        async def get(path, timeout=60):
            return tasks

        async def post(path, data, timeout=60):
            posts.append(list(data.get("task_ids", [])))
            return {"status": "ok", "archived": len(data.get("task_ids", []))}

        async def fire(event, data):
            pass

        summary = await br.run_blocked_remediation(get, post, fire, now_ms=10_000_000_000_000)
        # Only the task WITH an id can be archived.
        assert [tid for batch in posts for tid in batch] == ["task_real"]
        assert summary["archived"] == 1

    @pytest.mark.asyncio
    async def test_post_non_dict_counts_nothing(self):
        """When api_post returns a non-dict (None / timeout / garbage), do NOT
        count the batch as archived.

        Only server-confirmed archives are counted — assuming a failed batch
        succeeded inflated the webhook report in production (the fetch/classify
        loop is idempotent, so unconfirmed batches are simply retried next
        hourly tick instead of being silently written off).
        """
        tasks = [
            {
                "id": f"task_{i}",
                "title": "[Stale] stuck {i}",
                "description": "Task task_abc has been in_progress",
                "fail_reason": "",
                "updated_at": 0,
            }
            for i in range(3)
        ]

        async def get(path, timeout=60):
            return tasks

        async def post(path, data, timeout=60):
            return None  # timeout / ambiguous failure — NOT confirmed

        async def fire(event, data):
            pass

        summary = await br.run_blocked_remediation(
            get, post, fire, now_ms=10_000_000_000_000, batch_size=2
        )
        assert summary["archived"] == 0  # nothing was confirmed archived
        assert summary["fetched"] == 3

    @pytest.mark.asyncio
    async def test_fire_event_failure_does_not_abort(self):
        """If the webhook raises, remediation still completes (no crash)."""
        tasks = [
            {
                "id": "task_x",
                "title": "[Stale] stuck",
                "description": "Task task_abc has been in_progress",
                "fail_reason": "",
                "updated_at": 0,
            }
        ]
        posts = []

        async def get(path, timeout=60):
            return tasks

        async def post(path, data, timeout=60):
            posts.append(list(data.get("task_ids", [])))
            return {"status": "ok", "archived": 1}

        async def fire(event, data):
            raise RuntimeError("webhook down")

        summary = await br.run_blocked_remediation(get, post, fire, now_ms=10_000_000_000_000)
        assert summary["archived"] == 1
        assert [tid for batch in posts for tid in batch] == ["task_x"]


# ── scheduler.blocked_remediator loop ────────────────────────────────


class TestSchedulerLoop:
    @pytest.mark.asyncio
    async def test_runs_immediately_and_archives(self):
        summary = {
            "fetched": 3,
            "auto_dismissed": 2,
            "stale_archived": 1,
            "archived": 3,
            "samples": [],
            "active_blocked": 0,
        }

        with (
            patch("scheduler.asyncio.sleep", side_effect=[asyncio.CancelledError()]),
            patch(
                "scheduler.run_blocked_remediation", new=AsyncMock(return_value=summary)
            ) as mock_run,
        ):
            from scheduler import blocked_remediator

            await blocked_remediator(interval=3600)

            # First iteration ran without sleeping (immediate cleanup),
            # then the loop hit CancelledError on its first real sleep.
            mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_noop_when_nothing_to_archive(self):
        summary = {
            "fetched": 0,
            "auto_dismissed": 0,
            "stale_archived": 0,
            "archived": 0,
            "samples": [],
            "active_blocked": 0,
        }

        with (
            patch("scheduler.asyncio.sleep", side_effect=[asyncio.CancelledError()]),
            patch(
                "scheduler.run_blocked_remediation", new=AsyncMock(return_value=summary)
            ) as mock_run,
        ):
            from scheduler import blocked_remediator

            await blocked_remediator(interval=3600)

            mock_run.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_remediator_exception_does_not_crash(self):
        """If run_blocked_remediation raises, the loop logs and continues (no crash)."""
        with (
            patch("scheduler.asyncio.sleep", side_effect=[asyncio.CancelledError()]),
            patch(
                "scheduler.run_blocked_remediation",
                new=AsyncMock(side_effect=RuntimeError("api exploded")),
            ),
        ):
            from scheduler import blocked_remediator

            await blocked_remediator(interval=3600)

            # If the except branch (869-870) didn't catch, the test would crash
            # with RuntimeError propagating out of blocked_remediator.

    @pytest.mark.asyncio
    async def test_remediator_cancelled_breaks_cleanly(self):
        """CancelledError must exit the loop without logging an error."""
        with (
            patch("scheduler.asyncio.sleep", side_effect=[asyncio.CancelledError()]),
            patch(
                "scheduler.run_blocked_remediation",
                new=AsyncMock(side_effect=asyncio.CancelledError()),
            ),
        ):
            from scheduler import blocked_remediator

            await blocked_remediator(interval=3600)
            # CancelledError caught by the `except asyncio.CancelledError: break`
            # branch — reaching here means the loop exited cleanly.


# ── Metrics exclude archived ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_analytics_overview_excludes_archived(client, mock_all):
    """Archived tasks must not inflate by_status / total / repos."""
    mock_all["sql"].return_value = [
        {"id": "t1", "status": "done", "repo": "r", "updated_at": 1, "archived": False},
        {"id": "t2", "status": "blocked", "repo": "r", "updated_at": 1, "archived": True},
        {"id": "t3", "status": "blocked", "repo": "r", "updated_at": 1, "archived": True},
        {"id": "t4", "status": "available", "repo": "r", "updated_at": 1, "archived": False},
    ]
    mock_all["param"].return_value = []

    resp = await client.get("/api/analytics/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["by_status"] == {"done": 1, "available": 1}
    assert data["total_done"] == 1
    assert data["repos"]["r"]["total"] == 2
    assert data["repos"]["r"]["blocked"] == 0


@pytest.mark.asyncio
async def test_health_board_excludes_archived(client, mock_all):
    """Archived blocked tasks must not show up in the health board summary."""
    mock_all["sql"].side_effect = [
        [{"cnt": 3}],  # COUNT(*) — includes archived
        [
            {"id": "t1", "status": "done", "archived": False},
            {"id": "t2", "status": "blocked", "archived": True},
            {"id": "t3", "status": "blocked", "archived": True},
        ],
    ]
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    board = resp.json()["board"]
    assert board["total"] == 1
    assert board["by_status"] == {"done": 1}
