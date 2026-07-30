"""Tests for _fast_seed.py — standalone task seeder."""
import json
import subprocess
import urllib.error
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from _fast_seed import (
    api_get,
    api_post,
    create_task,
    fetch_existing_titles,
    find_large_files,
    find_missing_init,
    find_missing_project_files,
    find_stale_todos,
    find_test_gaps,
    is_dup,
    main,
)

# ── api_get ──────────────────────────────────────────────────────────


class TestApiGet:
    def test_success_dict(self):
        """api_get returns parsed JSON dict on success."""
        data = json.dumps({"status": "ok", "count": 5}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp) as m:
            result = api_get("/api/tasks")
            assert result == {"status": "ok", "count": 5}
            m.assert_called_once()

    def test_success_list(self):
        """api_get returns parsed JSON list on success."""
        data = json.dumps([{"id": "t1"}]).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp):
            result = api_get("/api/tasks")
            assert result == [{"id": "t1"}]

    def test_returns_none_on_any_exception(self):
        """api_get returns None when urlopen raises."""
        with patch("_fast_seed.urllib.request.urlopen", side_effect=Exception("fail")):
            result = api_get("/api/tasks")
            assert result is None

    def test_request_uses_proper_url(self):
        """api_get constructs the full URL from API + path."""
        data = json.dumps({}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp) as m:
            api_get("/api/tasks?status=available")
            req = m.call_args[0][0]
            full_url = req.full_url if hasattr(req, 'full_url') else req.get_full_url()
            assert "/api/tasks?status=available" in full_url


# ── api_post ─────────────────────────────────────────────────────────


class TestApiPost:
    def test_success_with_content(self):
        """api_post returns parsed JSON on success."""
        resp_data = json.dumps({"id": "task_123"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp):
            result = api_post("/api/tasks", {"title": "T"})
            assert result == {"id": "task_123"}

    def test_success_empty_response(self):
        """api_post returns {'status': 'ok'} when response body is empty."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp):
            result = api_post("/api/tasks", {"title": "T"})
            assert result == {"status": "ok"}

    def test_sets_content_type_header(self):
        """api_post sends Content-Type: application/json via Request."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__.return_value = mock_resp
        with patch("_fast_seed.urllib.request.urlopen", return_value=mock_resp) as m:
            api_post("/api/tasks", {"title": "T"})
            req = m.call_args[0][0]
            # Header is stored as 'Content-type' by urllib Request
            assert req.type == "application/json" or req.headers.get("Content-type") == "application/json"
            assert req.method == "POST"

    def test_http_error_returns_none(self):
        """api_post returns None on HTTPError (logs but doesn't crash)."""
        err = urllib.error.HTTPError(
            "/api/tasks", 409, "Conflict", {}, None
        )
        err.read = lambda: b'{"detail": "dup"}'
        with patch("_fast_seed.urllib.request.urlopen", side_effect=err):
            result = api_post("/api/tasks", {"title": "Dup"})
            assert result is None

    def test_generic_error_returns_none(self):
        """api_post returns None on generic Exception (logs but doesn't crash)."""
        with patch("_fast_seed.urllib.request.urlopen", side_effect=Exception("timeout")):
            result = api_post("/api/tasks", {"title": "T"})
            assert result is None


# ── create_task ──────────────────────────────────────────────────────


class TestCreateTask:
    def test_success(self):
        """create_task returns True when api_post succeeds."""
        with patch("_fast_seed.api_post", return_value={"id": "t1"}):
            assert create_task("My task", "Desc", "sample-repo-p", priority=2) is True

    def test_failure(self):
        """create_task returns False when api_post returns None."""
        with patch("_fast_seed.api_post", return_value=None):
            assert create_task("My task", "Desc", "sample-repo-p") is False

    def test_passes_correct_payload(self):
        """create_task sends correct payload to api_post."""
        with patch("_fast_seed.api_post", return_value={"id": "t1"}) as m:
            create_task("Test task", "Test desc", "my-repo", priority=3)
            m.assert_called_once_with(
                "/api/tasks",
                {
                    "title": "Test task",
                    "description": "Test desc",
                    "priority": 3,
                    "repo": "my-repo",
                    "roadmap_item": "Scanner: task-generator",
                },
            )


# ── fetch_existing_titles ────────────────────────────────────────────


class TestFetchExistingTitles:
    def test_collects_from_all_four_statuses(self):
        """Fetches titles from all 4 status endpoints."""
        def side_effect(path):
            if "status=available" in path:
                return [{"title": " Avail Task "}]
            elif "status=inProgress" in path:
                return [{"title": "InProgress Task"}]
            elif "status=blocked" in path:
                return []
            elif "status=done" in path:
                return [{"title": "Done Task"}, {"title": "  "}]
            return []
        with patch("_fast_seed.api_get", side_effect=side_effect):
            titles = fetch_existing_titles()
            # "  " should be stripped and empty → skipped
            assert titles == {"avail task", "inprogress task", "done task"}

    def test_all_empty(self):
        """Returns empty set when no tasks exist or API fails."""
        with patch("_fast_seed.api_get", return_value=None):
            assert fetch_existing_titles() == set()

    def test_handles_empty_and_whitespace_titles(self):
        """Only non-whitespace titles are collected."""
        def side_effect(path):
            if "status=available" in path:
                return [{"title": "Real"}, {"title": ""}, {"title": "   "}]
            return []
        with patch("_fast_seed.api_get", side_effect=side_effect):
            titles = fetch_existing_titles()
            assert titles == {"real"}


# ── is_dup ───────────────────────────────────────────────────────────


class TestIsDup:
    def test_exact_match(self):
        assert is_dup("My Task", {"my task"}) is True

    def test_no_match(self):
        assert is_dup("Other", {"my task"}) is False

    def test_case_insensitive(self):
        assert is_dup("MY TASK", {"my task"}) is True

    def test_strips_whitespace(self):
        assert is_dup("  My Task  ", {"my task"}) is True

    def test_empty_existing(self):
        assert is_dup("Anything", set()) is False


# ── find_test_gaps ───────────────────────────────────────────────────


def _walk_structure(structure, top):
    """Yield (dirpath, dirnames, filenames) for paths under `top`."""
    top = top.rstrip("/")
    for dirpath, (dirs, files) in sorted(structure.items()):
        if dirpath == top or dirpath.startswith(top + "/"):
            yield dirpath, dirs, list(files)


class TestFindTestGaps:
    def test_no_src_dir(self):
        """Returns [] when src dirs don't exist."""
        with patch("os.path.isdir", return_value=False):
            assert find_test_gaps("my-repo", "/tmp/repo") == []

    def test_untested_modules_batched(self):
        """Batches untested modules into groups of 5."""
        struct = {
            "/tmp/repo/server": (["tests", "sub"], ["app.py", "routes.py", "utils.py", "db.py", "models.py", "config.py", "admin.py"]),
            "/tmp/repo/server/tests": ([], []),
            "/tmp/repo/server/sub": ([], ["helper.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.listdir", return_value=["test_app.py"]))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_test_gaps("my-repo", "/tmp/repo")
            # 7 untested (all except app.py) → batched into 5 + 2
            assert len(findings) == 2
            assert "5" in findings[0]["title"]
            assert "2" in findings[1]["title"]

    def test_no_gaps(self):
        """Returns [] when all modules have tests."""
        struct = {
            "/tmp/repo/server": (["tests"], ["app.py"]),
            "/tmp/repo/server/tests": ([], ["test_app.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.listdir", return_value=["test_app.py"]))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            assert find_test_gaps("my-repo", "/tmp/repo") == []

    def test_skips_hidden_and_venv(self):
        """Skips dirs starting with ., __, venv, node_modules, target."""
        struct = {
            "/tmp/repo/server": (
                [".hidden", "__pycache__", "venv", "node_modules", "target", "src", "normal"],
                ["app.py"],
            ),
            "/tmp/repo/server/src": ([], ["mod.py"]),
            "/tmp/repo/server/normal": ([], ["util.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.listdir", return_value=[]))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_test_gaps("my-repo", "/tmp/repo")
            # app.py (server) test_app.py doesn't exist → untested
            # mod.py (src) test_mod.py doesn't exist → untested
            # util.py (normal) test_util.py doesn't exist → untested
            # .hidden, __pycache__, venv, node_modules, target excluded from walk
            assert len(findings) == 1  # batched into 3
            assert "3" in findings[0]["title"]

    def test_skips_init_py(self):
        """Doesn't flag __init__.py as needing a test."""
        struct = {
            "/tmp/repo/server": ([], ["__init__.py", "app.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.listdir", return_value=[]))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_test_gaps("my-repo", "/tmp/repo")
            assert len(findings) == 1  # only app.py is untested
            assert "1" in findings[0]["title"]


# ── find_missing_init ────────────────────────────────────────────────


class TestFindMissingInit:
    def test_no_src_dir(self):
        with patch("os.path.isdir", return_value=False):
            assert find_missing_init("r", "/p") == []

    def test_finds_missing_init_py(self):
        """Reports dirs with Python files but no __init__.py."""
        struct = {
            "/p/server": (["sub"], ["main.py"]),
            "/p/server/sub": ([], ["helper.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_missing_init("r", "/p")
            assert len(findings) == 1
            assert "__init__.py" in findings[0]["title"]

    def test_no_missing_init(self):
        """Returns [] when all dirs have __init__.py."""
        struct = {
            "/p/server": (["sub"], ["main.py"]),
            "/p/server/sub": ([], ["__init__.py", "helper.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            assert find_missing_init("r", "/p") == []

    def test_skips_root_dir_itself(self):
        """Doesn't check the root src_dir itself for __init__.py."""
        struct = {
            "/p/server": (["sub"], []),
            "/p/server/sub": ([], ["helper.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_missing_init("r", "/p")
            assert len(findings) == 1
            assert "sub" in findings[0]["description"]

    def test_skips_excluded_dirs(self):
        """Doesn't enter venv, node_modules, .hidden dirs."""
        struct = {
            "/p/server": (["venv", "node_modules", ".hidden", "src"], ["main.py"]),
            "/p/server/src": ([], ["helper.py"]),
        }
        with ExitStack() as stack:
            stack.enter_context(patch("os.path.isdir", return_value=True))
            stack.enter_context(patch("os.walk", side_effect=lambda top, **kw: _walk_structure(struct, top)))
            findings = find_missing_init("r", "/p")
            # src has helper.py but no __init__.py
            assert len(findings) == 1
            assert "src" in findings[0]["description"]


# ── find_stale_todos ─────────────────────────────────────────────────


class TestFindStaleTodos:
    def test_no_todos(self):
        """Returns [] when git grep returns nothing."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = ""
            m.return_value.stderr = ""
            assert find_stale_todos("r", "/p") == []

    def test_fewer_than_3_markers(self):
        """Returns [] when total markers < 3."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "file1.py:2\nfile2.py:0\n"
            assert find_stale_todos("r", "/p") == []

    def test_creates_bulk_task_for_10_or_more(self):
        """Creates a single bulk task when total >= 10."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "src/main.py:5\nsrc/utils.py:3\nsrc/config.py:2\n"
            findings = find_stale_todos("r", "/p")
            assert len(findings) == 1
            assert "10" in findings[0]["title"]
            assert "stale" in findings[0]["title"].lower()

    def test_file_not_found_returns_empty(self):
        """Returns [] when git is not available."""
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert find_stale_todos("r", "/p") == []

    def test_timeout_returns_empty(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 15)):
            assert find_stale_todos("r", "/p") == []

    def test_between_3_and_9(self):
        """Returns [] when 3 <= total < 10."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "file1.py:5\n"
            assert find_stale_todos("r", "/p") == []

    def test_malformed_lines_skipped(self):
        """Lines without colon separator are skipped gracefully."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "src/main.py:5\nmalformed_no_colon\nsrc/utils.py:6\n"
            findings = find_stale_todos("r", "/p")
            assert len(findings) == 1
            assert "11" in findings[0]["title"]

    def test_non_numeric_count_skipped(self):
        """Lines with non-numeric count are skipped gracefully."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "src/main.py:5\nsrc/utils.py:not_a_number\nsrc/config.py:6\n"
            findings = find_stale_todos("r", "/p")
            assert len(findings) == 1
            assert "11" in findings[0]["title"]


# ── find_large_files ─────────────────────────────────────────────────


class TestFindLargeFiles:
    def test_no_large_files(self):
        """Returns [] when all files are under 300 lines."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = " 150 /p/app.py\n 200 /p/utils.py\n  total\n"
            assert find_large_files("r", "/p") == []

    def test_creates_task_with_large_files(self):
        """Creates a task for files >= 300 lines (top 5)."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = " 300 /p/app.py\n 500 /p/huge.py\n 50 /p/small.py\n  total\n"
            findings = find_large_files("r", "/p")
            assert len(findings) == 1
            assert "2" in findings[0]["title"]

    def test_empty_output(self):
        with patch("subprocess.run") as m:
            m.return_value.stdout = ""
            assert find_large_files("r", "/p") == []

    def test_exception_returns_empty(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 30)):
            assert find_large_files("r", "/p") == []

    def test_skips_lines_with_non_numeric_count(self):
        """Lines with non-numeric count in wc output are skipped gracefully."""
        with patch("subprocess.run") as m:
            m.return_value.stdout = "abc /p/file.py\n 300 /p/huge.py\n  total\n"
            findings = find_large_files("r", "/p")
            assert len(findings) == 1
            assert "large" in findings[0]["title"].lower()


# ── find_missing_project_files ───────────────────────────────────────


class TestFindMissingProjectFiles:
    def test_all_present(self):
        """Returns [] when all 4 required files exist."""
        with patch("os.path.isfile", return_value=True):
            assert find_missing_project_files("r", "/p") == []

    def test_all_missing(self):
        """Creates a task listing all 4 missing files by count."""
        with patch("os.path.isfile", return_value=False):
            findings = find_missing_project_files("r", "/p")
            assert len(findings) == 1
            assert "4" in findings[0]["title"]

    def test_one_kept_two_missing_lists_by_name(self):
        """When < 3 missing (only 1 or 2), title lists names individually."""
        def isfile(path):
            return "LICENSE" in path or "CONTRIBUTING.md" in path  # 2 found, 2 missing
        with patch("os.path.isfile", side_effect=isfile):
            findings = find_missing_project_files("r", "/p")
            assert len(findings) == 1
            assert "issue" in findings[0]["title"] or "PR" in findings[0]["title"]

    def test_three_missing_uses_count(self):
        """When >= 3 missing, title uses count format."""
        def isfile(path):
            return "LICENSE" in path  # only 1 found, 3 missing
        with patch("os.path.isfile", side_effect=isfile):
            findings = find_missing_project_files("r", "/p")
            assert len(findings) == 1
            assert "3" in findings[0]["title"]


# ── create_tasks_existing coverage ───────────────────────────────────


class TestCreateTasksExisting:
    def test_skip_non_git_repo(self):
        """Returns 0 when repo has no .git directory."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.os.path.isdir", side_effect=lambda p: ".git" not in p))
            from _fast_seed import create_tasks_existing
            count = create_tasks_existing("nonexistent", set())
            assert count == 0

    def test_runs_scanners_and_creates_tasks(self):
        """Scans and creates tasks from findings, deduping."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.os.path.isdir", return_value=True))
            # Mock all 5 scanner functions directly
            stack.enter_context(patch("_fast_seed.find_test_gaps", return_value=[
                {"title": "Add tests for 2 modules", "description": "desc", "priority": 3, "repo": "my-repo"},
            ]))
            stack.enter_context(patch("_fast_seed.find_missing_init", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_stale_todos", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_large_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_project_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.create_task", return_value=True))
            from _fast_seed import create_tasks_existing
            existing = set()
            count = create_tasks_existing("my-repo", existing)
            assert count == 1
            assert "add tests for 2 modules" in existing

    def test_skips_duplicate(self):
        """Skips findings whose title already exists."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.os.path.isdir", return_value=True))
            stack.enter_context(patch("_fast_seed.create_task", return_value=True))
            stack.enter_context(patch("_fast_seed.find_test_gaps", return_value=[
                {"title": "Existing task", "description": "desc", "priority": 3, "repo": "r"},
            ]))
            stack.enter_context(patch("_fast_seed.find_missing_init", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_stale_todos", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_large_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_project_files", return_value=[]))
            from _fast_seed import create_tasks_existing
            count = create_tasks_existing("r", {"existing task"})
            assert count == 0

    def test_scanner_error_does_not_block_other_scanners(self):
        """If one scanner fails, other scanners still run."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.os.path.isdir", return_value=True))
            stack.enter_context(patch("_fast_seed.find_test_gaps", side_effect=Exception("crash")))
            stack.enter_context(patch("_fast_seed.find_missing_init", return_value=[]))
            stack.enter_context(patch("_fast_seed.create_task", return_value=True))
            stack.enter_context(patch("_fast_seed.find_stale_todos", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_large_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_project_files", return_value=[]))
            from _fast_seed import create_tasks_existing
            count = create_tasks_existing("r", set())
            assert count == 0  # test_gaps crashed, no other scanners returned findings


# ── main ─────────────────────────────────────────────────────────────


class TestMain:
    def test_returns_0_when_tasks_created(self):
        """main() returns 0 when at least one task is created."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.fetch_existing_titles", return_value=set()))
            stack.enter_context(patch("_fast_seed.os.path.isdir", return_value=True))
            stack.enter_context(patch("_fast_seed.find_test_gaps", return_value=[]))
            # Only find_missing_init returns a finding (the rest are empty)
            stack.enter_context(patch("_fast_seed.find_missing_init", return_value=[
                {"title": "Add __init__.py to 1 package in test-repo",
                 "description": "desc", "priority": 3, "repo": "test-repo"},
            ]))
            stack.enter_context(patch("_fast_seed.find_stale_todos", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_large_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_project_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.create_task", return_value=True))
            assert main() == 0

    def test_returns_1_when_no_tasks_created(self):
        """main() returns 1 when no tasks created (all scanners empty)."""
        with ExitStack() as stack:
            stack.enter_context(patch("_fast_seed.fetch_existing_titles", return_value=set()))
            stack.enter_context(patch("_fast_seed.os.path.isdir", return_value=True))
            stack.enter_context(patch("_fast_seed.find_test_gaps", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_init", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_stale_todos", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_large_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.find_missing_project_files", return_value=[]))
            stack.enter_context(patch("_fast_seed.create_task", return_value=False))
            assert main() == 1
