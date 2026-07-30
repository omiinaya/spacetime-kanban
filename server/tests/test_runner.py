"""Tests for server/scanners/runner.py scanner orchestration."""

import tempfile
from unittest.mock import Mock, patch


class TestScannerLayerMapping:
    """Verify scanner layer configuration is consistent."""

    def test_all_registered_scanners_have_layers(self):
        """Every registered scanner should have a layer mapping."""
        from scanners import SCANNERS, get_scanner_name
        from scanners.runner import SCANNER_LAYER

        for fn in SCANNERS:
            name = get_scanner_name(fn)
            assert name in SCANNER_LAYER, (
                f"Scanner '{name}' is registered but missing from SCANNER_LAYER"
            )

    def test_layers_are_in_range(self):
        """All layer values should be 0-4."""
        from scanners.runner import SCANNER_LAYER

        for name, layer in SCANNER_LAYER.items():
            assert 0 <= layer <= 4, f"Scanner '{name}' has invalid layer {layer}"


class TestVerifyCompletedTasks:
    """Test skip_verify behavior in _verify_completed_tasks."""

    def _make_mock_scanner(self, name: str, findings: list[dict]) -> Mock:
        """Helper: create a mock scanner function with a proper __name__."""
        fn = Mock(spec=lambda: None, __name__=f"scan_{name}")
        fn.return_value = findings
        return fn

    def test_skip_verify_prevents_reopen(self):
        """Findings with skip_verify=True should not trigger re-open."""
        from scanners.runner import _verify_completed_tasks

        mock_scanner = self._make_mock_scanner(
            "test_scanner",
            [
                {
                    "title": "Test Task with skip_verify",
                    "description": "A test finding",
                    "priority": 2,
                    "scanner": "test_scanner",
                    "skip_verify": True,
                }
            ],
        )

        with tempfile.TemporaryDirectory() as repo_path:
            repos = [("test-repo", repo_path)]
            with (
                patch("scanners.runner._api_get") as mock_get,
                patch("scanners.runner._api_post") as mock_post,
                patch("scanners.runner.SCANNERS", [mock_scanner]),
            ):
                now_ms = int(__import__("time").time() * 1000)
                mock_get.return_value = [
                    {
                        "id": "task_123",
                        "title": "Test Task with skip_verify",
                        "roadmap_item": "Scanner: test_scanner",
                        "status": "done",
                        "updated_at": now_ms - 1000,
                    }
                ]

                existing = set()
                result = _verify_completed_tasks(repos, existing)

                assert result == 0, "skip_verify task should not be re-opened"
                mock_post.assert_not_called()

    def test_no_skip_verify_does_reopen(self):
        """Findings without skip_verify should trigger re-open normally."""
        from scanners.runner import _verify_completed_tasks

        mock_scanner = self._make_mock_scanner(
            "test_scanner",
            [
                {
                    "title": "Test Task without skip_verify",
                    "description": "A test finding",
                    "priority": 2,
                    "scanner": "test_scanner",
                }
            ],
        )

        with tempfile.TemporaryDirectory() as repo_path:
            repos = [("test-repo", repo_path)]
            with (
                patch("scanners.runner._api_get") as mock_get,
                patch("scanners.runner._api_post") as mock_post,
                patch("scanners.runner.SCANNERS", [mock_scanner]),
            ):
                now_ms = int(__import__("time").time() * 1000)
                mock_get.return_value = [
                    {
                        "id": "task_456",
                        "title": "Test Task without skip_verify",
                        "roadmap_item": "Scanner: test_scanner",
                        "status": "done",
                        "updated_at": now_ms - 1000,
                    }
                ]

                existing = set()
                result = _verify_completed_tasks(repos, existing)

                assert result == 1, "task without skip_verify should be re-opened"
                mock_post.assert_called_once()
                args, _ = mock_post.call_args
                assert "task_456" in args[0], "should target the correct task"

    def test_old_tasks_not_reopened(self):
        """Tasks completed >7 days ago should not be checked."""
        from scanners.runner import _verify_completed_tasks

        mock_scanner = self._make_mock_scanner(
            "test_scanner",
            [
                {
                    "title": "Old Task",
                    "description": "An old finding",
                    "priority": 2,
                    "scanner": "test_scanner",
                }
            ],
        )

        with tempfile.TemporaryDirectory() as repo_path:  # noqa: SIM117 — nested with for readability
            with (
                patch("scanners.runner._api_get") as mock_get,
                patch("scanners.runner._api_post"),
                patch("scanners.runner.SCANNERS", [mock_scanner]),
            ):
                now_ms = int(__import__("time").time() * 1000)
                mock_get.return_value = [
                    {
                        "id": "task_789",
                        "title": "Old Task",
                        "roadmap_item": "Scanner: test_scanner",
                        "status": "done",
                        "updated_at": now_ms - (8 * 86400 * 1000),
                    }
                ]

                result = _verify_completed_tasks([("test-repo", repo_path)], set())
                assert result == 0, "old tasks should not be re-opened"
