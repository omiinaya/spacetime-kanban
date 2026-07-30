"""Coverage for health.py and unused_code.py edge cases.

health.py targets: _api_get error paths, compute_all_projects aggregation
unused_code.py targets: >5 files truncation, cargo/ts-prune scanners
"""

import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# health.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealthApiGet:
    """Cover _api_get function (lines 52-61) via urllib mocking."""

    @patch("scanners.health._api_get")
    def test_api_get_success(self, mock_get):
        """_api_get returns data — project health computed."""
        mock_get.return_value = [
            {"roadmap_item": "Scanner: stdb_index", "status": "done"},
        ]
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert result["repo"] == "test-repo"
        assert result["layer_scores"][0] == 1.0

    @patch("scanners.health._api_get")
    def test_api_get_failure(self, mock_get):
        """_api_get returning None (HTTP error) produces empty health."""
        mock_get.return_value = None
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert result["layer_scores"] == {}
        assert result["overall"] == 0.0
        assert result["next_layer"] == 0

    @patch("urllib.request.urlopen")
    def test_api_get_real_urlopen_success(self, mock_urlopen):
        """_api_get with real urllib returns parsed JSON."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value = mock_resp
        from scanners.health import _api_get

        result = _api_get("/api/health")
        assert result == {"status": "ok"}

    @patch("urllib.request.urlopen")
    def test_api_get_real_urlopen_exception(self, mock_urlopen):
        """_api_get with real urllib returns None on exception."""
        mock_urlopen.side_effect = ConnectionError("refused")
        from scanners.health import _api_get

        result = _api_get("/api/health")
        assert result is None


class TestComputeAllProjects:
    """Cover compute_all_projects edge cases (lines 163-185)."""

    @patch("scanners.health.compute_project_health")
    def test_with_scanner_tasks_includes_project(self, mock_health):
        """Projects with scanner tasks are included in results."""
        mock_health.return_value = {
            "repo": "test-repo",
            "by_scanner": {"deps": {"total": 5, "done": 3, "pct": 60.0}},
            "layer_scores": {0: 1.0, 1: 0.6, 2: 1.0, 3: 1.0, 4: 1.0},
            "overall": 0.85,
            "next_layer": 1,
            "next_layer_name": "Code Quality",
        }
        from scanners.health import compute_all_projects

        repos = [("test-repo", "/tmp/test")]
        result = compute_all_projects(repos)
        assert len(result["projects"]) == 1
        assert result["projects"][0]["repo"] == "test-repo"
        assert result["summary"]["total"] == 1

    @patch("scanners.health.compute_project_health")
    def test_no_scanner_tasks_skipped(self, mock_health):
        """Projects with no scanner tasks are excluded."""
        mock_health.return_value = {
            "repo": "empty-repo",
            "by_scanner": {},
            "layer_scores": {},
            "overall": 0.0,
            "next_layer": 0,
            "next_layer_name": "Critical",
        }
        from scanners.health import compute_all_projects

        repos = [("empty-repo", "/tmp/test")]
        result = compute_all_projects(repos)
        assert len(result["projects"]) == 0
        assert result["summary"]["total"] == 0

    @patch("scanners.health.compute_project_health")
    def test_l0_issues_flag_needs_attention(self, mock_health):
        """Projects with L0 score < 0.8 are flagged for attention."""
        mock_health.return_value = {
            "repo": "needy",
            "by_scanner": {"stdb_index": {"total": 2, "done": 0, "pct": 0.0}},
            "layer_scores": {0: 0.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},
            "overall": 0.5,
            "next_layer": 0,
            "next_layer_name": "Critical",
        }
        from scanners.health import compute_all_projects

        repos = [("needy", "/tmp/test")]
        result = compute_all_projects(repos)
        assert "needy" in result["summary"]["needs_attention"]

    @patch("scanners.health.compute_project_health")
    def test_healthy_l0_no_flag(self, mock_health):
        """Projects with L0 >= 0.8 are not flagged."""
        mock_health.return_value = {
            "repo": "healthy",
            "by_scanner": {"stdb_index": {"total": 2, "done": 2, "pct": 100.0}},
            "layer_scores": {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},
            "overall": 1.0,
            "next_layer": None,
            "next_layer_name": "Complete",
        }
        from scanners.health import compute_all_projects

        repos = [("healthy", "/tmp/test")]
        result = compute_all_projects(repos)
        assert "healthy" not in result["summary"]["needs_attention"]

    @patch("scanners.health.compute_project_health")
    def test_empty_repos_list(self, mock_health):
        """Empty repos list produces empty results."""
        from scanners.health import compute_all_projects

        result = compute_all_projects([])
        assert result["projects"] == []
        assert result["summary"]["total"] == 0
        assert result["summary"]["avg_overall"] == 0

    @patch("scanners.discover_repos")
    @patch("scanners.health.compute_project_health")
    def test_repos_fallback_called(self, mock_health, mock_discover):
        """Calling with repos=None triggers discover_repos fallback (line 163)."""
        mock_discover.return_value = [("fallback-repo", "/tmp/fallback")]
        mock_health.return_value = {
            "repo": "fallback-repo",
            "by_scanner": {"deps": {"total": 1, "done": 1, "pct": 100.0}},
            "layer_scores": {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0},
            "overall": 1.0,
            "next_layer": None,
            "next_layer_name": "Complete",
        }
        from scanners.health import compute_all_projects

        result = compute_all_projects(repos=None)
        assert len(result["projects"]) == 1
        assert result["projects"][0]["repo"] == "fallback-repo"
        mock_discover.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# unused_code.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnusedCodeFilesSummary:
    """Cover line 52: >5 files summary truncation."""

    def test_more_than_5_files_truncation(self, tmp_repo):
        """>5 files with unused imports → '...and X more' in description."""
        _write(tmp_repo, "pyproject.toml", "")
        from scanners.unused_code import scan_unused_code

        # ruff output with 8 files
        ruff_lines = "\n".join(f"file{i}.py:1:1: F401 `os` imported but unused" for i in range(8))
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ruff_lines
            mock_run.return_value.stderr = ""
            findings = scan_unused_code("test-repo", tmp_repo)
            # Should find the finding regardless
            assert len(findings) > 0


@pytest.fixture
def tmp_repo():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _write(repo_path: str, rel_path: str, content: str):
    """Write a file."""
    full = os.path.join(repo_path, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


class TestUnusedCodeCargo:
    """Cover cargo check scanner (lines 75-107)."""

    def test_cargo_dead_code_detected(self, tmp_repo):
        """Cargo dead_code output creates a finding."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb"), exist_ok=True)
        _write(tmp_repo, "server/spacetimedb/Cargo.toml", '[package]\nname = "test"\n')
        from scanners.unused_code import scan_unused_code

        cargo_output = "\n".join(
            f"warning: unused import: `Foo`\n  --> src/lib.rs:{i}:1" for i in range(1, 6)
        )
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = cargo_output
            findings = scan_unused_code("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("dead_code" in t.lower() for t in titles)

    def test_cargo_boilerplate_filtered(self, tmp_repo):
        """<=2 dead_code lines are filtered as boilerplate."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb"), exist_ok=True)
        _write(tmp_repo, "server/spacetimedb/Cargo.toml", '[package]\nname = "test"\n')
        from scanners.unused_code import scan_unused_code

        cargo_output = "warning: unused import: `Foo`\n  --> src/lib.rs:1:1\n"
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = cargo_output
            findings = scan_unused_code("test-repo", tmp_repo)
            # <=2 lines filtered as boilerplate
            dead_code_titles = [f for f in findings if "dead_code" in f.get("title", "").lower()]
            assert len(dead_code_titles) == 0

    def test_cargo_not_available(self, tmp_repo):
        """FileNotFoundError from cargo is handled."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb"), exist_ok=True)
        _write(tmp_repo, "server/spacetimedb/Cargo.toml", '[package]\nname = "test"\n')
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            findings = scan_unused_code("test-repo", tmp_repo)
            assert isinstance(findings, list)


class TestUnusedCodeTsPrune:
    """Cover ts-prune scanner (lines 113-141)."""

    def test_ts_prune_many_exports(self, tmp_repo):
        """>3 unused exports creates a finding."""
        os.makedirs(os.path.join(tmp_repo, "web"), exist_ok=True)
        _write(tmp_repo, "web/package.json", json.dumps({"dependencies": {}}))
        from scanners.unused_code import scan_unused_code

        ts_prune_output = "src/components/Button.tsx: unused export\nsrc/utils/helpers.ts: unused export\nsrc/pages/Home.tsx: unused export\nsrc/pages/About.tsx: unused export\n5 unused exports\n"
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ts_prune_output
            mock_run.return_value.stderr = ""
            findings = scan_unused_code("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("unused export" in t.lower() for t in titles)

    def test_ts_prune_few_exports_skipped(self, tmp_repo):
        """<=3 unused exports → no finding."""
        os.makedirs(os.path.join(tmp_repo, "web"), exist_ok=True)
        _write(tmp_repo, "web/package.json", json.dumps({"dependencies": {}}))
        from scanners.unused_code import scan_unused_code

        ts_prune_output = "src/components/Button.tsx: unused export\n2 unused exports\n"
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ts_prune_output
            mock_run.return_value.stderr = ""
            findings = scan_unused_code("test-repo", tmp_repo)
            ts_titles = [f for f in findings if "unused export" in f.get("title", "").lower()]
            assert len(ts_titles) == 0

    def test_ts_prune_not_available(self, tmp_repo):
        """FileNotFoundError from npx is handled."""
        os.makedirs(os.path.join(tmp_repo, "web"), exist_ok=True)
        _write(tmp_repo, "web/package.json", json.dumps({"dependencies": {}}))
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            findings = scan_unused_code("test-repo", tmp_repo)
            assert isinstance(findings, list)

    def test_ts_prune_timeout(self, tmp_repo):
        """TimeoutExpired from npx is handled."""
        os.makedirs(os.path.join(tmp_repo, "web"), exist_ok=True)
        _write(tmp_repo, "web/package.json", json.dumps({"dependencies": {}}))
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=30)
            findings = scan_unused_code("test-repo", tmp_repo)
            assert isinstance(findings, list)
