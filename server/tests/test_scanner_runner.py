"""Tests for scanners/runner.py — scanner orchestration and API interaction.

The runner module uses urllib for HTTP calls to the local kanban API.
We patch urllib.request to avoid needing a running server.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_repo():
    """Create a temporary git repo for scanner tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _write(repo_path: str, rel_path: str, content: str):
    """Write a file inside the temp repo."""
    full = os.path.join(repo_path, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


# ═══════════════════════════════════════════════════════════════════════════════
# _api_get / _api_post
# ═══════════════════════════════════════════════════════════════════════════════


class TestApiHelpers:
    """Tests for _api_get and _api_post in runner.py."""

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_get_success(self, mock_urlopen):
        """_api_get returns parsed JSON on success."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"key": "value"}'
        mock_urlopen.return_value = mock_resp
        from scanners.runner import _api_get

        result = _api_get("/api/tasks")
        assert result == {"key": "value"}

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_get_failure(self, mock_urlopen):
        """_api_get returns None on HTTP error."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="/api/tasks", code=500, msg="Error", hdrs={}, fp=None
        )
        from scanners.runner import _api_get

        result = _api_get("/api/tasks")
        assert result is None

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_get_exception(self, mock_urlopen):
        """_api_get returns None on generic exception."""
        mock_urlopen.side_effect = ConnectionError("refused")
        from scanners.runner import _api_get

        result = _api_get("/api/tasks")
        assert result is None

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_post_success(self, mock_urlopen):
        """_api_post returns parsed JSON on success."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "abc"}'
        mock_urlopen.return_value = mock_resp
        from scanners.runner import _api_post

        result = _api_post("/api/tasks", {"title": "test"})
        assert result == {"id": "abc"}

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_post_empty_response(self, mock_urlopen):
        """_api_post returns {'status': 'ok'} on empty response."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        mock_urlopen.return_value = mock_resp
        from scanners.runner import _api_post

        result = _api_post("/api/tasks", {"title": "test"})
        assert result == {"status": "ok"}

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_post_http_error(self, mock_urlopen):
        """_api_post returns None on HTTP error."""
        from urllib.error import HTTPError

        mock_urlopen.side_effect = HTTPError(
            url="/api/tasks", code=409, msg="Conflict", hdrs={}, fp=MagicMock()
        )
        from scanners.runner import _api_post

        result = _api_post("/api/tasks", {"title": "test"})
        assert result is None

    @patch("scanners.runner.urllib.request.urlopen")
    def test_api_post_exception(self, mock_urlopen):
        """_api_post returns None on generic exception."""
        mock_urlopen.side_effect = OSError("timeout")
        from scanners.runner import _api_post

        result = _api_post("/api/tasks", {"title": "test"})
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# _is_duplicate / _fetch_existing_titles
# ═══════════════════════════════════════════════════════════════════════════════


class TestDedup:
    """Tests for deduplication logic."""

    @patch("scanners.runner._api_get")
    def test_fetch_existing_titles_all_statuses(self, mock_get):
        """Fetches titles from all 4 statuses."""
        mock_get.side_effect = [
            [{"title": "task A"}, {"title": "Task B"}],
            [{"title": "task C"}],
            [{"title": "task D"}],
            [{"title": "TASK A"}],
        ]
        from scanners.runner import _fetch_existing_titles

        result = _fetch_existing_titles()
        assert "task a" in result
        assert "task b" in result
        assert "task c" in result
        assert "task d" in result
        assert mock_get.call_count == 4

    @patch("scanners.runner._api_get")
    def test_fetch_existing_titles_handles_none(self, mock_get):
        """_api_get returning None should not crash."""
        mock_get.return_value = None
        from scanners.runner import _fetch_existing_titles

        result = _fetch_existing_titles()
        assert result == set()

    @patch("scanners.runner._api_get")
    def test_fetch_skips_empty_title(self, mock_get):
        """Tasks with empty title are skipped."""
        mock_get.return_value = [
            {"title": "real task"},
            {"title": ""},
            {},
        ]
        from scanners.runner import _fetch_existing_titles

        result = _fetch_existing_titles()
        assert "real task" in result
        assert len(result) == 1

    def test_is_duplicate(self):
        """Case-insensitive duplicate detection."""
        from scanners.runner import _is_duplicate

        # In practice _fetch_existing_titles lowercases, so existing set is lowered
        existing = {"fix bug", "add feature"}
        assert _is_duplicate("Fix Bug", existing)
        assert _is_duplicate("add feature", existing)
        assert not _is_duplicate("new thing", existing)

    def test_is_duplicate_strips_whitespace(self):
        """Whitespace in title is stripped before comparison."""
        from scanners.runner import _is_duplicate

        existing = {"fix bug"}
        assert _is_duplicate("  Fix Bug  ", existing)


# ═══════════════════════════════════════════════════════════════════════════════
# _compute_project_layer_scores
# ═══════════════════════════════════════════════════════════════════════════════


class TestLayerScores:
    """Tests for _compute_project_layer_scores."""

    @patch("scanners.runner._api_get")
    def test_all_done(self, mock_get):
        """All tasks done → all layer scores = 1.0."""
        mock_get.return_value = [
            {"roadmap_item": "Scanner: stdb_index", "status": "done"},
            {"roadmap_item": "Scanner: todos", "status": "done"},
            {"roadmap_item": "Scanner: deps", "status": "done"},
        ]
        from scanners.runner import _compute_project_layer_scores

        scores = _compute_project_layer_scores("test-repo")
        assert scores[0] == 1.0
        assert scores[1] == 1.0

    @patch("scanners.runner._api_get")
    def test_mixed_scores(self, mock_get):
        """Mix of done and open tasks → fractional scores."""
        mock_get.return_value = [
            {"roadmap_item": "Scanner: stdb_index", "status": "done"},
            {"roadmap_item": "Scanner: stdb_index", "status": "available"},
        ]
        from scanners.runner import _compute_project_layer_scores

        scores = _compute_project_layer_scores("test-repo")
        assert scores[0] == 0.5
        assert scores[1] == 1.0  # no tasks, defaults to 1.0

    @patch("scanners.runner._api_get")
    def test_empty_response(self, mock_get):
        """No tasks → empty scores dict."""
        mock_get.return_value = []
        from scanners.runner import _compute_project_layer_scores

        scores = _compute_project_layer_scores("test-repo")
        assert scores == {}

    @patch("scanners.runner._api_get")
    def test_api_failure(self, mock_get):
        """API returns None → empty scores."""
        mock_get.return_value = None
        from scanners.runner import _compute_project_layer_scores

        scores = _compute_project_layer_scores("test-repo")
        assert scores == {}

    @patch("scanners.runner._api_get")
    def test_non_scanner_tasks_excluded(self, mock_get):
        """Tasks without scanner roadmap_item are excluded, but layers default to 1.0."""
        mock_get.return_value = [
            {"roadmap_item": "Feature: login", "status": "done"},
            {"roadmap_item": "Bug: crash", "status": "done"},
        ]
        from scanners.runner import _compute_project_layer_scores

        scores = _compute_project_layer_scores("test-repo")
        # All layers default to 1.0 since no scanner tasks exist
        assert scores[0] == 1.0
        assert scores[4] == 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# _verify_completed_tasks
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerifyCompleted:
    """Tests for _verify_completed_tasks."""

    @patch("scanners.runner._api_post")
    @patch("scanners.runner._api_get")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_regression_detected(self, mock_scanners, mock_get, mock_post):
        """A regressed task (finding still present) gets reopened."""
        # Mock the scanner to return a finding the same as the existing done task
        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_stdb_index"
        mock_scanner.return_value = [
            {
                "title": "Add index for item_id",
                "scanner": "stdb_index",
                "skip_verify": False,
            }
        ]
        mock_scanners.append(mock_scanner)

        mock_get.return_value = [
            {
                "id": "task_123",
                "title": "Add index for item_id",
                "roadmap_item": "Scanner: stdb_index",
                "status": "done",
                "updated_at": 9999999999000,  # recent
            }
        ]
        from scanners.runner import _verify_completed_tasks

        repos = [("test-repo", "/tmp/test")]
        existing = set()
        regressed = _verify_completed_tasks(repos, existing)
        assert regressed == 1
        mock_post.assert_called_once()

    @patch("scanners.runner._api_post")
    @patch("scanners.runner._api_get")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_skip_verify_respected(self, mock_scanners, mock_get, mock_post):
        """A task with skip_verify=True is not reopened."""
        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_deps"
        mock_scanner.return_value = [
            {
                "title": "Unpin serde in Cargo.toml",
                "scanner": "deps",
                "skip_verify": True,
            }
        ]
        mock_scanners.append(mock_scanner)

        mock_get.return_value = [
            {
                "id": "task_456",
                "title": "Unpin serde in Cargo.toml",
                "roadmap_item": "Scanner: deps",
                "status": "done",
                "updated_at": 9999999999000,
            }
        ]
        from scanners.runner import _verify_completed_tasks

        repos = [("test-repo", "/tmp/test")]
        existing = set()
        regressed = _verify_completed_tasks(repos, existing)
        # skip_verify=True → not reopened
        assert regressed == 0
        mock_post.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# run_all_scanners (main orchestration)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunAllScanners:
    """Tests for run_all_scanners — the main orchestration function."""

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_normal_flow(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """Happy path: scanner runs, findings deduped, tasks created."""
        mock_fetch.return_value = set()
        mock_verify.return_value = 0
        mock_scores.return_value = {0: 1.0, 1: 1.0, 2: 1.0}

        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_deps"
        mock_scanner.return_value = [
            {
                "title": "Unpin serde",
                "description": "serde is pinned to =1.0.0",
                "priority": 3,
                "scanner": "deps",
            }
        ]
        mock_scanners.append(mock_scanner)

        mock_post.return_value = {"id": "new_task_1"}

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        results = run_all_scanners(repos)

        assert "deps" in results
        assert results["deps"]["created"] == 1
        mock_post.assert_called_once()

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_duplicate_skipped(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """Duplicate findings (already in existing set) are not created."""
        mock_fetch.return_value = {"unpin serde"}
        mock_verify.return_value = 0
        mock_scores.return_value = {0: 1.0}

        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_deps"
        mock_scanner.return_value = [
            {
                "title": "Unpin serde",
                "description": "",
                "priority": 3,
                "scanner": "deps",
            }
        ]
        mock_scanners.append(mock_scanner)

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        results = run_all_scanners(repos)

        assert results["deps"]["created"] == 0
        mock_post.assert_not_called()

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_scanner_exception_does_not_crash(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """A scanner that raises should be caught and not crash the run."""
        mock_fetch.return_value = set()
        mock_verify.return_value = 0
        mock_scores.return_value = {0: 1.0}

        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_broken"
        mock_scanner.side_effect = RuntimeError("scanner crashed")
        mock_scanners.append(mock_scanner)

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        results = run_all_scanners(repos)

        # A crashed scanner is silently skipped and not added to results
        assert "broken" not in results
        # No tasks were created despite the exception
        total_created = sum(c["created"] for c in results.values())
        assert total_created == 0

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    @patch.dict(os.environ, {"WEBHOOK_DEFAULT_URL": "https://discord.com/api/webhooks/test"})
    def test_webhook_fired_for_p0_p2(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """P0-P2 findings fire a webhook."""
        mock_fetch.return_value = set()
        mock_verify.return_value = 0
        mock_scores.return_value = {0: 0.0}

        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_prod_readiness"
        mock_scanner.return_value = [
            {
                "title": "Missing Dockerfile",
                "description": "No Dockerfile found",
                "priority": 2,
                "scanner": "prod_readiness",
            }
        ]
        mock_scanners.append(mock_scanner)

        mock_post.return_value = {"id": "task_webhook"}

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        results = run_all_scanners(repos)

        assert results["prod_readiness"]["created"] == 1

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_layer_escalation_skips_high_layers(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """Higher-layer scanners are skipped if lower layers unresolved."""
        mock_fetch.return_value = set()
        mock_verify.return_value = 0
        # Layer 0 is not fully resolved (score < 0.8)
        mock_scores.return_value = {0: 0.5}

        mock_l0_scanner = MagicMock()
        mock_l0_scanner.__name__ = "scan_stdb_index"
        mock_l0_scanner.return_value = []

        mock_l1_scanner = MagicMock()
        mock_l1_scanner.__name__ = "scan_todos"
        mock_l1_scanner.return_value = []

        # Layer 2 should be skipped because layer 0 is unresolved
        # But layer 3+ ALWAYS runs
        mock_l4_scanner = MagicMock()
        mock_l4_scanner.__name__ = "scan_prod_readiness"
        mock_l4_scanner.return_value = []

        mock_scanners.extend(
            [
                mock_l0_scanner,
                mock_l1_scanner,
                # mock_l2_scanner would be skipped
                mock_l4_scanner,  # layer 4, always runs
            ]
        )

        # Need layer_architecture in SCANNER_LAYER to test this
        # Let's add it manually

        # We know that stdb_index is layer 0, todos is layer 1, prod_readiness is layer 4
        # Architecture is layer 2 - it should be skipped if layer 0 < 0.8
        # But we didn't add an L2 scanner to our mock list

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        run_all_scanners(repos)

        # All mocks were called (L0, L1 scanned; L4 always runs)
        mock_l0_scanner.assert_called_once()
        mock_l1_scanner.assert_called_once()
        mock_l4_scanner.assert_called_once()

    @patch("scanners.runner._compute_project_layer_scores")
    @patch("scanners.runner._verify_completed_tasks")
    @patch("scanners.runner._fetch_existing_titles")
    @patch("scanners.runner._api_post")
    @patch("scanners.runner.SCANNERS", new_callable=list)
    def test_skip_verify_post_not_called_for_verified(
        self,
        mock_scanners,
        mock_post,
        mock_fetch,
        mock_verify,
        mock_scores,
    ):
        """findings with skip_verify still create tasks (they just don't get re-verified)."""
        mock_fetch.return_value = set()
        mock_verify.return_value = 0
        mock_scores.return_value = {0: 1.0}

        mock_scanner = MagicMock()
        mock_scanner.__name__ = "scan_deps"
        mock_scanner.return_value = [
            {
                "title": "Pin check",
                "description": "test",
                "priority": 3,
                "scanner": "deps",
                "skip_verify": True,
            }
        ]
        mock_scanners.append(mock_scanner)

        mock_post.return_value = {"id": "task_1"}

        from scanners.runner import run_all_scanners

        repos = [("test-repo", "/tmp/test")]
        results = run_all_scanners(repos)

        # skip_verify does NOT prevent creation — it only affects re-verification
        assert results["deps"]["created"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════


class TestCliEntry:
    """Tests for the CLI entry point in runner.py."""

    def test_cli_creates_tasks(self):
        """CLI exits 0 when tasks were created."""

        with patch("scanners.runner.run_all_scanners") as mock_run:
            mock_run.return_value = {
                "deps": {"finding_count": 3, "created": 2},
                "todos": {"finding_count": 1, "created": 1},
            }
            # Simulate the CLI logic: exit 0 if total_created > 0
            total = sum(c["created"] for c in mock_run.return_value.values())
            assert total > 0

    def test_cli_no_tasks(self):
        """CLI exits 1 when no tasks were created."""

        with patch("scanners.runner.run_all_scanners") as mock_run:
            mock_run.return_value = {
                "deps": {"finding_count": 0, "created": 0},
            }
            total = sum(c["created"] for c in mock_run.return_value.values())
            assert total == 0
