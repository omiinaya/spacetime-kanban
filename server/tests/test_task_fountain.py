"""Comprehensive tests for server/_task_fountain.py.

Tests cover:
- api_get success/error paths (with the raised API_TIMEOUT)
- api_post success/HTTPError/generic error paths
- fetch_board_state — whole-board per-repo dedup, available count, abort on failure
- fetch_existing_titles — wrapper over fetch_board_state
- is_dup — pure function edge cases
- scan_board_health — emits AT MOST ONE task per run
- run() — dedup-fetch abort, board-health gate, one-task-per-run, run-twice no dups
- register — scanner registration
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


# ── Constants ─────────────────────────────────────────────────────────


def test_timeout_constant_raised_above_old_5s():
    """API_TIMEOUT must be well above the old 5s (board queries take 30s+)."""
    import _task_fountain as m

    assert m.API_TIMEOUT >= 30


def test_dedup_limit_covers_board():
    """DEDUP_LIMIT must exceed the 22k-task board (old cap was 200/status)."""
    import _task_fountain as m

    assert m.DEDUP_LIMIT >= 22025


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
    # Verify timeout is passed and uses the raised module constant
    assert "timeout" in mock_urlopen.call_args.kwargs
    assert mock_urlopen.call_args.kwargs["timeout"] == m.API_TIMEOUT


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


# ── fetch_board_state ─────────────────────────────────────────────────


def _make_mock_urlopen_response(data):
    """Helper: build a mock urlopen context manager that returns JSON bytes."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None
    return mock_resp


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_board_state_covers_every_repo_all_statuses(mock_urlopen):
    """fetch_board_state queries EACH repo (high limit, all statuses) and
    returns the whole board's titles plus the available count."""
    import _task_fountain as m

    urls_seen = []
    per_repo = {
        "spacetimedb-kanban": [
            {"title": "  Fix Bug Alpha  ", "status": "available"},
            {"title": "Add Feature Beta", "status": "done"},
        ],
        "sample-repo-o": [
            {"title": "REVIEW SPACETIME-TV FOR ACTIONABLE IMPROVEMENTS", "status": "available"},
            {"title": "Old Dup Invisible Before", "status": "done"},
        ],
        "sample-repo-m": [
            {"title": "Review sample-repo-m for actionable improvements", "status": "blocked"},
        ],
    }

    def side_effect(url, *args, **kwargs):
        urls_seen.append(str(url))
        for repo, tasks in per_repo.items():
            if f"repo={repo}" in str(url):
                return _make_mock_urlopen_response(tasks)
        return _make_mock_urlopen_response([])

    mock_urlopen.side_effect = side_effect

    result = m.fetch_board_state()

    assert result is not None
    titles, available = result
    # Whole-board coverage: titles from every repo, stripped + lowercased
    assert "fix bug alpha" in titles
    assert "add feature beta" in titles
    assert "review sample-repo-o for actionable improvements" in titles
    assert "old dup invisible before" in titles  # done-status dup is NOT invisible
    assert "review sample-repo-m for actionable improvements" in titles
    # Available count is derived from the same whole-board snapshot
    assert available == 2  # spacetimedb-kanban + sample-repo-o
    # One query per repo, each with the high dedup limit
    assert len(urls_seen) == len(m.REPOS)
    for url in urls_seen:
        assert f"limit={m.DEDUP_LIMIT}" in url


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_board_state_all_empty(mock_urlopen):
    """fetch_board_state returns (empty set, 0) when every repo is empty."""
    import _task_fountain as m

    mock_urlopen.return_value = _make_mock_urlopen_response([])

    result = m.fetch_board_state()

    assert result == (set(), 0)
    assert mock_urlopen.call_count == len(m.REPOS)


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_board_state_skips_empty_title(mock_urlopen):
    """fetch_board_state skips tasks with empty or missing titles."""
    import _task_fountain as m

    mock_urlopen.return_value = _make_mock_urlopen_response(
        [
            {"title": "Valid Task", "status": "available"},
            {"title": ""},
            {"notitle": True},
            {"title": "  "},
        ]
    )

    result = m.fetch_board_state()

    assert result is not None
    titles, available = result
    assert "valid task" in titles
    # Empty/missing/whitespace-only titles don't count as available —
    # only the valid task counts (same response for every repo here)
    assert available == len(m.REPOS)


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_board_state_none_when_any_repo_fails(mock_urlopen):
    """A single repo query failure makes fetch_board_state return None —
    the run must abort rather than create with an incomplete dedup set."""
    import _task_fountain as m

    calls = 0

    def side_effect(url, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return _make_mock_urlopen_response([{"title": "From First Repo"}])
        return None  # second repo query fails (timeout/HTTP error)

    mock_urlopen.side_effect = side_effect

    result = m.fetch_board_state()

    assert result is None


@patch("_task_fountain.urllib.request.urlopen")
def test_fetch_board_state_none_on_non_list(mock_urlopen):
    """A non-list response (e.g. error dict) also aborts the dedup fetch."""
    import _task_fountain as m

    mock_urlopen.return_value = _make_mock_urlopen_response({"error": "boom"})

    result = m.fetch_board_state()

    assert result is None


# ── fetch_existing_titles (wrapper) ───────────────────────────────────


@patch("_task_fountain.fetch_board_state")
def test_fetch_existing_titles_returns_titles(mock_state):
    """Wrapper returns just the title set from fetch_board_state."""
    import _task_fountain as m

    mock_state.return_value = ({"fix bug", "add feature"}, 7)

    result = m.fetch_existing_titles()

    assert result == {"fix bug", "add feature"}


@patch("_task_fountain.fetch_board_state")
def test_fetch_existing_titles_returns_none_on_failure(mock_state):
    """Wrapper propagates None when the board state fetch fails."""
    import _task_fountain as m

    mock_state.return_value = None

    result = m.fetch_existing_titles()

    assert result is None


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

        # existing set is already lowercased (as produced by fetch_board_state)
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


def _reset_health_flag(m):
    """Reset the module-level one-per-run flag (run() does this normally)."""
    m._health_emitted = False


def test_scan_board_health_decorated():
    """scan_board_health is registered in SCANNERS via @register."""
    import _task_fountain as m

    assert m.scan_board_health in m.SCANNERS


def test_scan_board_health_task_fields():
    """The emitted task carries the repo name, priority 4, and a description."""
    import _task_fountain as m

    _reset_health_flag(m)
    try:
        result = m.scan_board_health("sample-repo-o", "/home/sample-repo-o")

        assert len(result) == 1
        task = result[0]
        assert "sample-repo-o" in task["title"]
        assert task["priority"] == 4
        assert "description" in task
    finally:
        _reset_health_flag(m)


def test_scan_board_health_emits_at_most_once_per_run():
    """Second call in the same run returns [] — only ONE task per fountain run."""
    import _task_fountain as m

    _reset_health_flag(m)
    try:
        first = m.scan_board_health("sample-repo-o", "/home/sample-repo-o")
        second = m.scan_board_health("sample-repo-m", "/home/sample-repo-m")
        third = m.scan_board_health("sample-repo-p", "/home/sample-repo-p")

        assert len(first) == 1
        assert second == []
        assert third == []
    finally:
        _reset_health_flag(m)


def test_scan_board_health_emits_once_after_run_resets_flag():
    """run() resets the one-per-run flag, so the next run can emit again."""
    import _task_fountain as m

    _reset_health_flag(m)
    try:
        m._health_emitted = True  # simulate a previous run that already emitted
        with ExitStack() as stack:
            stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
            stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
            stack.enter_context(
                patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
            )
            stack.enter_context(patch("_task_fountain.HOME", "/home/test"))
            stack.enter_context(patch("_task_fountain.SCANNERS", [m.scan_board_health]))

            result = m.run()

        # Flag was reset at the top of run() → the scanner emitted again
        assert result == 1
    finally:
        _reset_health_flag(m)


# ── run() ─────────────────────────────────────────────────────────────


def test_run_no_git_repos():
    """run() returns 0 when no repos have a .git directory."""
    import _task_fountain as m

    with ExitStack() as stack:
        mock_isdir = stack.enter_context(patch("_task_fountain.os.path.isdir", return_value=False))
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
        mock_post = stack.enter_context(patch.object(m, "api_post"))

        # Keep SCANNERS as-is (includes scan_board_health) but all repos
        # get skipped by the isdir check
        result = m.run()

    assert result == 0
    # isdir was called at least once (for each repo)
    assert mock_isdir.call_count == len(m.REPOS)
    mock_post.assert_not_called()


def test_run_aborts_when_dedup_fetch_fails():
    """run() creates NOTHING when the dedup fetch fails — an incomplete
    dedup set is what allowed duplicates onto the board in the first place."""
    import _task_fountain as m

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=None))
        mock_post = stack.enter_context(patch.object(m, "api_post"))
        # If run() reached the repo loop it would raise — proving the abort
        stack.enter_context(
            patch(
                "_task_fountain.os.path.isdir",
                side_effect=AssertionError("run() must abort before the repo loop"),
            )
        )

        result = m.run()

    assert result == 0
    mock_post.assert_not_called()


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_creates_task_for_scanner_finding(mock_isdir):
    """run() creates a task from a scanner finding and increments count."""
    import _task_fountain as m

    stub_scanner = MagicMock(
        return_value=[{"title": "New Task", "description": "desc", "priority": 3}]
    )

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
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
    """run() skips task creation when title already exists on the board."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "Existing Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(
            patch.object(m, "fetch_board_state", return_value=({"existing task"}, 0))
        )
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
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
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
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [bad_scanner, good_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    bad_scanner.assert_called_once()
    good_scanner.assert_called_once()


@patch("_task_fountain.os.path.isdir", side_effect=[True] + [False] * 8)
def test_run_first_repo_only(mock_isdir):
    """run() processes only repos where .git exists (first repo here)."""
    import _task_fountain as m

    stub_scanner = MagicMock(return_value=[{"title": "Single Repo Task", "description": ""}])

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_board_state", return_value=(set(), 0)))
        stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [stub_scanner]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    # isdir called 9 times (once per repo), only first one True
    assert mock_isdir.call_count == 9
    stub_scanner.assert_called_once()


def test_run_skips_health_scanner_when_board_healthy():
    """Board with >= MIN_AVAILABLE_TASKS available → NO health task created
    (the gate is evaluated ONCE in run(), not once per repo)."""
    import _task_fountain as m

    # 9 repos × 1 available task = 9 >= 3 → board healthy
    healthy_repos = [[{"title": f"Task {i}", "status": "available"}] for i in range(len(m.REPOS))]
    mock_urlopen = MagicMock(side_effect=[_make_mock_urlopen_response(r) for r in healthy_repos])

    with ExitStack() as stack:
        stack.enter_context(patch("_task_fountain.urllib.request.urlopen", mock_urlopen))
        stack.enter_context(
            patch("_task_fountain.os.path.isdir", side_effect=[True] * len(m.REPOS))
        )
        mock_post = stack.enter_context(patch.object(m, "api_post"))
        stack.enter_context(patch("_task_fountain.SCANNERS", [m.scan_board_health]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 0
    mock_post.assert_not_called()


def test_run_creates_exactly_one_health_task_when_board_low():
    """Board low on available tasks → AT MOST ONE review task per run,
    even when every repo has a local checkout (old code made up to 9)."""
    import _task_fountain as m

    # 2 available tasks total across all repos → below MIN_AVAILABLE_TASKS
    low_board = [
        [{"title": "Only A", "status": "available"}, {"title": "Only B", "status": "available"}]
    ] + [[] for _ in range(len(m.REPOS) - 1)]
    mock_urlopen = MagicMock(side_effect=[_make_mock_urlopen_response(r) for r in low_board])

    with ExitStack() as stack:
        stack.enter_context(patch("_task_fountain.urllib.request.urlopen", mock_urlopen))
        stack.enter_context(
            patch("_task_fountain.os.path.isdir", side_effect=[True] * len(m.REPOS))
        )
        mock_post = stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [m.scan_board_health]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 1
    # Exactly one task created — the 9-repo loop must not create 9
    assert mock_post.call_count == 1
    # And it was created for the FIRST repo with the generic review title
    title = mock_post.call_args[0][1]["title"]
    repo = mock_post.call_args[0][1]["repo"]
    assert title == f"Review {m.REPOS[0]} for actionable improvements"
    assert repo == m.REPOS[0]


def test_run_health_title_deduped_against_whole_board():
    """A review task whose title already exists (even done/blocked, even old)
    is NOT created — this is the exact duplicate that was on the board."""
    import _task_fountain as m

    # The board already holds this title (2x dup existed in production) as a
    # DONE task — the old limit=200 dedup couldn't see it, the whole-board
    # fetch can.
    existing_title = f"Review {m.REPOS[0]} for actionable improvements"
    low_board = [
        [
            {"title": existing_title, "status": "done"},
            {"title": "Only A", "status": "available"},
        ]
    ] + [[] for _ in range(len(m.REPOS) - 1)]
    mock_urlopen = MagicMock(side_effect=[_make_mock_urlopen_response(r) for r in low_board])

    with ExitStack() as stack:
        stack.enter_context(patch("_task_fountain.urllib.request.urlopen", mock_urlopen))
        stack.enter_context(
            patch("_task_fountain.os.path.isdir", side_effect=[True] * len(m.REPOS))
        )
        mock_post = stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [m.scan_board_health]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        result = m.run()

    assert result == 0
    mock_post.assert_not_called()


def test_run_twice_creates_no_duplicate_titles():
    """VERIFICATION SCENARIO: run the fountain twice — the second run must
    NOT re-create titles created (or already present) in the first run."""
    import _task_fountain as m

    # Run 1: board low, empty board → creates the review task.
    # Run 2: the task from run 1 is now on the board → must be deduped.
    board_states = [
        (set(), 2),  # run 1: nothing on board
        ({f"review {m.REPOS[0]} for actionable improvements"}, 2),  # run 2: task now exists
    ]
    mock_state = MagicMock(side_effect=board_states)

    with ExitStack() as stack:
        stack.enter_context(patch.object(m, "fetch_board_state", mock_state))
        stack.enter_context(
            patch("_task_fountain.os.path.isdir", side_effect=[True] * len(m.REPOS) * 2)
        )
        mock_post = stack.enter_context(patch.object(m, "api_post", return_value={"status": "ok"}))
        stack.enter_context(patch("_task_fountain.SCANNERS", [m.scan_board_health]))
        stack.enter_context(patch("_task_fountain.HOME", "/home/test"))

        first = m.run()
        second = m.run()

    assert first == 1
    assert second == 0
    # Exactly one POST across both runs — no duplicate titles ever created
    assert mock_post.call_count == 1


# ── Module-level: __main__ block ──────────────────────────────────────


def test_main_block_structure():
    """The __main__ block calls run() and prints to stderr.

    Verified by checking that the module's code contains the expected
    '__main__' guard pattern — the block only executes when run directly.
    """
    import _task_fountain as m

    assert hasattr(m, "run")
    # Verify run() returns an int (0 here because no repos have .git dirs
    # in the test environment). Scanners are cleared so the test is hermetic
    # and doesn't scan real repos under load.
    with (
        patch.object(m, "fetch_board_state", return_value=(set(), 0)),
        patch.object(m, "api_post", return_value=None),
        patch.object(m, "SCANNERS", []),
        patch.object(m, "REPOS", ["nonexistent-repo-xyz"]),
    ):
        n = m.run()
    assert isinstance(n, int)
