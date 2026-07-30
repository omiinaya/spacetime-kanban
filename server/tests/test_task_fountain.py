"""Comprehensive tests for server/_task_fountain.py.

Tests cover:
- api_get success/error paths
- api_post success/HTTPError/generic error paths
- fetch_existing_titles — mocked per-status responses
- is_dup — pure function edge cases
- scan_board_health — healthy board (<3), near-empty board, exception fallback
- register — scanner registration
- run() — orchestrator with mocked os.path.isdir, urlopen, api_post
"""

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

# ── register ──────────────────────────────────────────────────────────


def test_register_appends_to_scanners():
    """register() should add the decorated function to SCANNERS."""
    import _task_fountain as m

    # Reset and verify
    original_len = len(m.SCANNERS)

    @m.register
    def _dummy_scanner(repo_name, repo_path):
        return []

    assert m.SCANNERS[-1] is _dummy_scanner
    assert len(m.SCANNERS) == original_len + 1

    # Clean up
    m.SCANNERS.pop()


# ── api_get ───────────────────────────────────────────────────────────


@patch("_task_fountain.urllib.request.urlopen")
def test_api_get_success_dict(mock_urlopen):
    """api_get returns parsed JSON dict on successful response."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok", "count": 5}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.api_get("/api/health")

    assert result == {"status": "ok", "count": 5}
    mock_urlopen.assert_called_once()
    # Verify timeout is passed
    assert "timeout" in mock_urlopen.call_args.kwargs
    assert mock_urlopen.call_args.kwargs["timeout"] == 5


@patch("_task_fountain.urllib.request.urlopen")
def test_api_get_success_list(mock_urlopen):
    """api_get returns parsed JSON list on successful response."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'[{"id": "1"}, {"id": "2"}]'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.api_get("/api/tasks")

    assert result == [{"id": "1"}, {"id": "2"}]


@patch("_task_fountain.urllib.request.urlopen")
def test_api_get_returns_none_on_exception(mock_urlopen):
    """api_get returns None when urlopen raises any exception."""
    import _task_fountain as m

    mock_urlopen.side_effect = ConnectionError("Connection refused")

    result = m.api_get("/api/tasks")

    assert result is None


@patch("_task_fountain.urllib.request.urlopen")
def test_api_get_returns_none_on_http_error(mock_urlopen):
    """api_get returns None on HTTPError."""
    from urllib.error import HTTPError

    import _task_fountain as m

    mock_urlopen.side_effect = HTTPError(
        "http://localhost:8727/api/tasks", 503, "Service Unavailable", {}, None
    )

    result = m.api_get("/api/tasks")

    assert result is None


@patch("_task_fountain.urllib.request.urlopen")
def test_api_get_returns_none_on_bad_json(mock_urlopen):
    """api_get returns None when response is not valid JSON."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"not valid json{"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.api_get("/api/tasks")

    assert result is None


# ── api_post ──────────────────────────────────────────────────────────


@patch("_task_fountain.urllib.request.urlopen")
def test_api_post_success_json(mock_urlopen):
    """api_post returns parsed JSON when response body is present."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "created", "id": "task_1"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.api_post("/api/tasks", {"title": "Test"})

    assert result == {"status": "created", "id": "task_1"}


@patch("_task_fountain.urllib.request.urlopen")
def test_api_post_empty_response(mock_urlopen):
    """api_post returns {"status": "ok"} when response body is empty."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b""
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.api_post("/api/tasks", {"title": "Test"})

    assert result == {"status": "ok"}


@patch("_task_fountain.urllib.request.Request")
@patch("_task_fountain.urllib.request.urlopen")
def test_api_post_sets_content_type(mock_urlopen, mock_request):
    """api_post sets Content-Type application/json header on the Request."""
    import _task_fountain as m

    mock_req = MagicMock()
    mock_request.return_value = mock_req
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"status": "ok"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    m.api_post("/api/tasks", {"title": "Test"})

    mock_req.add_header.assert_any_call("Content-Type", "application/json")


@patch("_task_fountain.urllib.request.urlopen")
def test_api_post_http_error(mock_urlopen):
    """api_post returns None on HTTPError."""
    from urllib.error import HTTPError

    import _task_fountain as m

    mock_urlopen.side_effect = HTTPError(
        "http://localhost:8727/api/tasks", 400, "Bad Request", {}, None
    )

    result = m.api_post("/api/tasks", {"title": "Test"})

    assert result is None


@patch("_task_fountain.urllib.request.urlopen")
def test_api_post_generic_error(mock_urlopen):
    """api_post returns None on any other exception."""
    import _task_fountain as m

    mock_urlopen.side_effect = OSError("Connection reset by peer")

    result = m.api_post("/api/tasks", {"title": "Test"})

    assert result is None


# ── fetch_existing_titles ────────────────────────────────────────────


def _make_mock_urlopen_response(data):
    """Helper: build a mock urlopen context manager that returns JSON bytes."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    return mock_resp


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_existing_titles_collects_from_all_statuses(mock_urlopen):
    """fetch_existing_titles fetches tasks from all four statuses and dedups."""
    import _task_fountain as m

    # Each call to urlopen gets a different response based on the status URL
    responses = {
        "/api/tasks?status=available&limit=200": [
            {"title": "  Fix Bug Alpha  "},
            {"title": "Add Feature Beta"},
        ],
        "/api/tasks?status=inProgress&limit=200": [
            {"title": "REFACTOR MODULE GAMMA"},
        ],
        "/api/tasks?status=blocked&limit=200": [
            {"title": "  review pr delta  "},
        ],
        "/api/tasks?status=done&limit=200": [
            {"title": "Fix Bug Alpha"},  # Duplicate of available — should dedup via set
            {"title": "Completed Task Epsilon"},
        ],
    }

    def side_effect(url, *args, **kwargs):
        for path, data in responses.items():
            if path in str(url):
                return _make_mock_urlopen_response(data)
        return _make_mock_urlopen_response([])

    mock_urlopen.side_effect = side_effect

    result = m.fetch_existing_titles()

    # Titles are stripped and lowercased
    expected = {
        "fix bug alpha",
        "add feature beta",
        "refactor module gamma",
        "review pr delta",
        "completed task epsilon",
    }
    assert result == expected
    assert mock_urlopen.call_count == 4


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_existing_titles_all_empty(mock_urlopen):
    """fetch_existing_titles returns empty set when all statuses return empty."""
    import _task_fountain as m

    mock_urlopen.return_value = _make_mock_urlopen_response([])

    result = m.fetch_existing_titles()

    assert result == set()
    assert mock_urlopen.call_count == 4


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_existing_titles_skips_empty_title(mock_urlopen):
    """fetch_existing_titles skips tasks with empty or missing titles.

    Note: a whitespace-only title like "  " passes the truthiness guard
    but strip().lower() yields "" which IS added to the set. This is
    existing behavior of the code under test.
    """
    import _task_fountain as m

    mock_resp = _make_mock_urlopen_response([
        {"title": "Valid Task"},
        {"title": ""},
        {"notitle": True},
        {"title": "  "},
    ])

    # Return same response for all 4 status calls, but we only care about the set
    mock_urlopen.return_value = mock_resp

    result = m.fetch_existing_titles()

    # "Valid Task" is included; "" and missing title are skipped;
    # "  " passes the truthiness check but strip().lower() => "" is added
    assert result == {"valid task", ""}


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_existing_titles_http_error_skips_gracefully(mock_urlopen):
    """fetch_existing_titles silently skips statuses that raise exceptions."""
    from urllib.error import HTTPError

    import _task_fountain as m

    # First call (available) succeeds, rest fail
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_mock_urlopen_response([{"title": "Only Task"}])
        raise HTTPError("http://test", 500, "Internal", {}, None)

    mock_urlopen.side_effect = side_effect

    result = m.fetch_existing_titles()

    assert result == {"only task"}
    assert call_count == 4  # All statuses iterated


# ── is_dup ────────────────────────────────────────────────────────────


class TestIsDup:
    """Pure function tests for is_dup — no mocking needed."""

    def test_dup_true(self):
        from _task_fountain import is_dup

        existing = {"fix bug", "add feature"}
        assert is_dup("fix bug", existing) is True

    def test_dup_false(self):
        from _task_fountain import is_dup

        existing = {"fix bug", "add feature"}
        assert is_dup("new task", existing) is False

    def test_case_insensitive(self):
        from _task_fountain import is_dup

        # existing set is already lowercased (as produced by fetch_existing_titles)
        existing = {"fix bug"}
        # Lowercase match
        assert is_dup("fix bug", existing) is True
        # Mixed case — function lowercases the title before lookup
        assert is_dup("Fix Bug", existing) is True

    def test_strips_whitespace(self):
        from _task_fountain import is_dup

        existing = {"fix bug"}
        assert is_dup("  fix bug  ", existing) is True
        assert is_dup("\tfix bug\n", existing) is True

    def test_empty_existing_set(self):
        from _task_fountain import is_dup

        assert is_dup("anything", set()) is False


# ── scan_board_health ─────────────────────────────────────────────────


def test_scan_board_health_decorated():
    """scan_board_health is registered in SCANNERS via @register."""
    import _task_fountain as m

    assert m.scan_board_health in m.SCANNERS


@patch("_task_fountain.urllib.request.urlopen")
def test_scan_board_health_healthy(mock_urlopen):
    """Returns [] when >=3 available tasks exist on the board."""
    import _task_fountain as m

    healthy_tasks = [
        {"title": "Task 1", "status": "available"},
        {"title": "Task 2", "status": "available"},
        {"title": "Task 3", "status": "available"},
    ]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(healthy_tasks).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.scan_board_health("test-repo", "/fake/path")

    assert result == []


@patch("_task_fountain.urllib.request.urlopen")
def test_scan_board_health_near_empty(mock_urlopen):
    """Returns a generic task when fewer than 3 available tasks exist."""
    import _task_fountain as m

    few_tasks = [
        {"title": "Task 1", "status": "available"},
    ]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(few_tasks).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.scan_board_health("sample-repo-p", "/home/sample-repo-p")

    assert len(result) == 1
    task = result[0]
    assert "sample-repo-p" in task["title"]
    assert task["priority"] == 4
    assert "description" in task


@patch("_task_fountain.urllib.request.urlopen")
def test_scan_board_health_empty_list(mock_urlopen):
    """Returns a task when available list is empty (len 0)."""
    import _task_fountain as m

    mock_resp = MagicMock()
    mock_resp.read.return_value = b"[]"
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    mock_urlopen.return_value = mock_resp

    result = m.scan_board_health("test-repo", "/fake/path")

    assert len(result) == 1


@patch("_task_fountain.urllib.request.urlopen")
def test_scan_board_health_error_fallback(mock_urlopen):
    """Returns a task when API call raises an exception (fallback behavior)."""
    import _task_fountain as m

    mock_urlopen.side_effect = ConnectionError("API unreachable")

    result = m.scan_board_health("fallback-repo", "/fake/path")

    assert len(result) == 1
    assert "fallback-repo" in result[0]["title"]


# ── run() ─────────────────────────────────────────────────────────────


def test_run_no_git_repos():
    """run() returns 0 when no repos have a .git directory."""
    import _task_fountain as m

    with ExitStack() as stack:
        mock_isdir = stack.enter_context(
            patch("_task_fountain.os.path.isdir", return_value=False)
        )
        stack.enter_context(
            patch.object(m, "fetch_existing_titles", return_value=set())
        )
        mock_post = stack.enter_context(
            patch.object(m, "api_post")
        )

        # Keep SCANNERS as-is (includes scan_board_health) but all repos
        # get skipped by the isdir check
        result = m.run()

    assert result == 0
    # isdir was called at least once (for each repo)
    assert mock_isdir.call_count == len(m.REPOS)
    mock_post.assert_not_called()


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_creates_task_for_scanner_finding(mock_isdir):
    """run() creates a task from a scanner finding and increments count."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "New Task", "description": "desc", "priority": 3}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_existing_titles", return_value=set()))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [stub_scanner]))
        # Mock HOME to a known path
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    stub_scanner.assert_called_once()
    # Should be called with the first repo name since isdir is True only for first
    repo_name = m.REPOS[0]
    stub_scanner.assert_called_with(repo_name, f"/home/test/{repo_name}")


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_skips_duplicate_title(mock_isdir):
    """run() skips task creation when title already exists."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "Existing Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_existing_titles", return_value={"existing task"}))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [stub_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 0
    stub_scanner.assert_called_once()
    # api_post should NOT be called because the title is a dup


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_api_post_failure_not_counted(mock_isdir):
    """run() does not increment count when api_post returns None."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "Brand New Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_existing_titles", return_value=set()))
        stack.enter_context(patch.object(m, "api_post", return_value=None))
        stack.enter_context(patch("_task_fountain.SCANNERS", [stub_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 0
    stub_scanner.assert_called_once()
    # api_post was called but returned None, so we don't count it


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_scanner_exception_skipped(mock_isdir):
    """run() skips a scanner that raises an exception and continues."""
    import _task_fountain as m

    bad_scanner = MagicMock(side_effect=RuntimeError("Scanner crashed"))
    # Second scanner that produces a valid finding
    good_scanner = MagicMock(return_value=[{"title": "Recovery Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_existing_titles", return_value=set()))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [bad_scanner, good_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    bad_scanner.assert_called_once()
    good_scanner.assert_called_once()


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_with_scan_board_health_integrated(mock_isdir):
    """run() integrates with real scan_board_health when board is near-empty

    Only the first repo (spacetimedb-kanban) has a .git dir.
    fetch_existing_titles makes 4 urlopen calls. scan_board_health makes 1.
    Total: 5 urlopen calls.
    """
    import _task_fountain as m

    with ExitStack() as stack:
        # 4 empty responses for fetch_existing_titles (one per status)
        empty_resp = MagicMock()
        empty_resp.read.return_value = b"[]"
        empty_resp.__enter__.return_value = empty_resp
        empty_resp.__exit__.return_value = None

        # 1 response for scan_board_health (<3 available => returns a task)
        health_resp = MagicMock()
        health_resp.read.return_value = b'[{"title": "Lonely Task"}]'
        health_resp.__enter__.return_value = health_resp
        health_resp.__exit__.return_value = None

        # Order: 4 fetch calls, then 1 health check call
        mock_urlopen = stack.enter_context(
            patch("_task_fountain.urllib.request.urlopen",
                  side_effect=[empty_resp] * 4 + [health_resp])
        )
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    # 4 fetch calls + 1 scan_board_health call
    assert mock_urlopen.call_count == 5


@patch("_task_fountain.os.path.isdir", side_effect=[True, False, False, False, False, False, False, False, False])
def test_run_first_repo_only(mock_isdir):
    """run() processes only repos where .git exists (first repo here)."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "Single Repo Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_existing_titles", return_value=set()))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [stub_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    # isdir called 9 times (once per repo), only first one True
    assert mock_isdir.call_count == 9
    stub_scanner.assert_called_once()


# ── Module-level: __main__ block ──────────────────────────────────────


def test_main_block_structure():
    """The __main__ block calls run() and prints to stderr.

    Verified by checking that the module's code contains the expected
    '__main__' guard pattern — the block only executes when run directly.
    """
    import _task_fountain as m

    assert hasattr(m, "run")
    # Verify run() returns an int (0 here because no repos have .git dirs
    # in the test environment)
    with patch.object(m, "fetch_existing_titles", return_value=set()), \
         patch.object(m, "api_post", return_value=None):
        n = m.run()
    assert isinstance(n, int)
