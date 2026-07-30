"""Tests for individual scanner modules (dep_scanner, gaps, layer_*, stdb_index, todo_scanner, unused_code).

Each scanner takes (repo_name, repo_path) and returns findings by checking
filesystem patterns.  We create temp directories with fixture files and
optionally patch subprocess calls for scanners that invoke git.
"""

import json
import os
import subprocess
import tempfile
from unittest.mock import patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_repo():
    """Create a temporary directory that acts as a 'repo' for scanner tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _write(repo_path: str, rel_path: str, content: str):
    """Write a file inside the temp repo."""
    full = os.path.join(repo_path, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)


# ═══════════════════════════════════════════════════════════════════════════════
# dep_scanner.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestDepScanner:
    """Tests for dep_scanner.py — scan_deps, _check_cargo_deps, _check_npm_deps."""

    def test_cargo_pinned_dep(self, tmp_repo):
        """Detect a Cargo dep pinned to exact version with =."""
        _write(
            tmp_repo,
            "Cargo.toml",
            '[package]\nname = "test"\n[dependencies]\nserde = "=1.0.0"\n',
        )
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("serde" in t and "Unpin" in t for t in titles)

    def test_cargo_git_dep(self, tmp_repo):
        """Detect a Cargo dep using a git URL."""
        _write(
            tmp_repo,
            "Cargo.toml",
            '[package]\nname = "test"\n[dependencies]\nfoo = { git = "https://github.com/x/foo" }\n',
        )
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("git" in t.lower() for t in titles)

    def test_no_cargo_toml(self, tmp_repo):
        """No Cargo.toml → no cargo findings."""
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_cargo_unparseable_toml(self, tmp_repo):
        """Malformed TOML should be silently skipped."""
        _write(tmp_repo, "Cargo.toml", "<<<<<NOT TOML>>>>>")
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_npm_pinned_dep(self, tmp_repo):
        """Detect an npm dep pinned to exact version."""
        _write(
            tmp_repo,
            "package.json",
            json.dumps({"dependencies": {"left-pad": "1.0.0"}}),
        )
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("Unpin" in t for t in titles)

    def test_npm_caret_version_not_pinned(self, tmp_repo):
        """Deps with ^ or ~ should NOT be flagged as pinned."""
        _write(
            tmp_repo,
            "package.json",
            json.dumps({"dependencies": {"express": "^4.18.0"}}),
        )
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("Unpin" in t for t in titles)

    def test_npm_duplicate_deps(self, tmp_repo):
        """Deps appearing in both root and web/package.json flagged."""
        _write(
            tmp_repo,
            "package.json",
            json.dumps({"dependencies": {"react": "^18.0.0"}}),
        )
        _write(
            tmp_repo,
            "web/package.json",
            json.dumps({"dependencies": {"react": "^18.0.0"}}),
        )
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("Deduplicate" in t for t in titles)

    def test_npm_unparseable_json(self, tmp_repo):
        """Malformed package.json should not crash."""
        _write(tmp_repo, "package.json", "{bad json}")
        from scanners.dep_scanner import scan_deps

        findings = scan_deps("test-repo", tmp_repo)
        assert isinstance(findings, list)


# ═══════════════════════════════════════════════════════════════════════════════
# gaps.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestGapsScanner:
    """Tests for gaps.py — scan_test_gaps."""

    def test_python_missing_test(self, tmp_repo):
        """A .py file without a corresponding test_*.py is flagged."""
        _write(tmp_repo, "server/foo.py", "def bar(): pass")
        os.makedirs(os.path.join(tmp_repo, "server/tests"), exist_ok=True)
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        # Title format: "Add tests for N untested Python module(s) in test-repo"
        assert any("untested Python" in t for t in titles)

    def test_python_has_test_skipped(self, tmp_repo):
        """A .py file with a matching test_*.py is NOT flagged."""
        _write(tmp_repo, "server/foo.py", "def bar(): pass")
        _write(tmp_repo, "server/tests/test_foo.py", "def test_bar(): pass")
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_no_server_dir(self, tmp_repo):
        """No server/ dir → no findings."""
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_rust_missing_tests(self, tmp_repo):
        """A .rs file without #[cfg(test)] is flagged."""
        _write(tmp_repo, "server/spacetimedb/src/lib.rs", "pub fn do_thing() {}")
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        # Title format: "Add unit tests for N untested Rust module(s) in test-repo"
        assert any("untested Rust" in t for t in titles)

    def test_rust_has_tests_skipped(self, tmp_repo):
        """A .rs file with #[cfg(test)] is NOT flagged."""
        _write(
            tmp_repo,
            "server/spacetimedb/src/lib.rs",
            "pub fn do_thing() {}\n#[cfg(test)]\nmod tests {}\n",
        )
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_tiny_mod_rs_excluded(self, tmp_repo):
        """A tiny mod.rs (<5 lines) is excluded from rust gap detection."""
        _write(
            tmp_repo,
            "server/spacetimedb/src/mod.rs",
            "pub mod foo;",
        )
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        # mod.rs with <5 lines and just re-exports should be excluded
        assert len(findings) == 0

    def test_python_chunking(self, tmp_repo):
        """Many untested Python files create chunked tasks."""
        for i in range(7):
            _write(tmp_repo, f"server/mod{i}.py", "x = 1")
        os.makedirs(os.path.join(tmp_repo, "server/tests"), exist_ok=True)
        from scanners.gaps import scan_test_gaps

        findings = scan_test_gaps("test-repo", tmp_repo)
        # 7 files at max 5 per task = 2 tasks
        assert len(findings) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# health.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestHealth:
    """Tests for health.py — compute_project_health, compute_all_projects."""

    @patch("scanners.health._api_get")
    def test_healthy_project(self, mock_get):
        """All layers complete → high scores."""
        mock_get.return_value = [
            {"roadmap_item": "Scanner: stdb_index", "status": "done"},
            {"roadmap_item": "Scanner: todos", "status": "done"},
            {"roadmap_item": "Scanner: deps", "status": "done"},
        ]
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert result["layer_scores"][0] == 1.0
        assert result["layer_scores"][1] == 1.0

    @patch("scanners.health._api_get")
    def test_partial_health(self, mock_get):
        """Some tasks not done → mixed scores."""
        mock_get.return_value = [
            {"roadmap_item": "Scanner: stdb_index", "status": "done"},
            {"roadmap_item": "Scanner: stdb_index", "status": "available"},
        ]
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert 0.0 < result["layer_scores"][0] < 1.0

    @patch("scanners.health._api_get")
    def test_api_unreachable(self, mock_get):
        """API failure → empty scores, next_layer = 0."""
        mock_get.return_value = None
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert result["layer_scores"] == {}
        assert result["next_layer"] == 0

    @patch("scanners.health._api_get")
    def test_no_scanner_tasks(self, mock_get):
        """Tasks without scanner roadmap_item are excluded."""
        mock_get.return_value = [
            {"roadmap_item": "Feature: login", "status": "done"},
        ]
        from scanners.health import compute_project_health

        result = compute_project_health("test-repo")
        assert result["layer_scores"][0] == 1.0  # no tasks → default 1.0

    @patch("scanners.health._api_get")
    def test_compute_all_projects(self, mock_get):
        """Aggregation over multiple repos with API returning nothing."""
        mock_get.return_value = None
        from scanners.health import compute_all_projects

        repos = [("repo-a", "/tmp/a"), ("repo-b", "/tmp/b")]
        result = compute_all_projects(repos)
        # Returns {'projects': [...], 'summary': {...}}
        assert "projects" in result
        assert "summary" in result


# ═══════════════════════════════════════════════════════════════════════════════
# layer_architecture.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchitectureScanner:
    """Tests for layer_architecture.py — scan_architecture."""

    def test_large_file_detected(self, tmp_repo):
        """A file >500 lines triggers a large-file finding."""
        _write(tmp_repo, "server/big.py", "\n".join(f"line{i}" for i in range(600)))
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("large" in t.lower() for t in titles)

    def test_small_file_not_flagged(self, tmp_repo):
        """A file <500 lines does NOT trigger."""
        _write(
            tmp_repo,
            "server/small.py",
            "\n".join(f"line{i}" for i in range(100)),
        )
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("large" in t.lower() for t in titles)

    def test_missing_init_py(self, tmp_repo):
        """A dir without __init__.py (non-root) is flagged."""
        os.makedirs(os.path.join(tmp_repo, "server", "somepkg"), exist_ok=True)
        _write(tmp_repo, "server/somepkg/mod.py", "x = 1")
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("__init__" in t.lower() for t in titles)

    def test_has_init_py_skipped(self, tmp_repo):
        """A dir with __init__.py is not flagged."""
        os.makedirs(os.path.join(tmp_repo, "server", "pkg"), exist_ok=True)
        _write(tmp_repo, "server/pkg/__init__.py", "")
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("__init__" in t.lower() for t in titles)

    def test_bare_except_detected(self, tmp_repo):
        """A file with bare except: triggers finding."""
        _write(tmp_repo, "server/bad.py", "try:\n    pass\nexcept:\n    pass\n")
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("except" in t.lower() for t in titles)

    def test_rust_unwrap_detected(self, tmp_repo):
        """A .rs file with >5 unwrap() calls triggers finding."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/lib.rs",
            "\n".join("x.unwrap();" for _ in range(8)),
        )
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("unwrap" in t.lower() for t in titles)

    def test_node_modules_excluded(self, tmp_repo):
        """node_modules directory is excluded from walking."""
        os.makedirs(os.path.join(tmp_repo, "node_modules"), exist_ok=True)
        _write(
            tmp_repo,
            "node_modules/giant.js",
            "\n".join(f"x = {i};" for i in range(600)),
        )
        from scanners.layer_architecture import scan_architecture

        findings = scan_architecture("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        # The giant.js file in node_modules should NOT be flagged
        assert not any("giant" in t.lower() for t in titles)


# ═══════════════════════════════════════════════════════════════════════════════
# layer_docs.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestDocsScanner:
    """Tests for layer_docs.py — scan_docs_ci."""

    def test_missing_readme(self, tmp_repo):
        """No README → finding."""
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("README" in t for t in titles)

    def test_has_readme(self, tmp_repo):
        """README exists → no missing-README finding."""
        _write(tmp_repo, "README.md", "# Test Repo")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("README" in t and "Missing" in t for t in titles)

    def test_missing_license(self, tmp_repo):
        """No LICENSE → finding (requires README)."""
        _write(tmp_repo, "README.md", "# Test")
        _write(tmp_repo, ".gitignore", "node_modules/")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("LICENSE" in t for t in titles)

    def test_has_license(self, tmp_repo):
        """LICENSE exists → no missing-LICENSE finding."""
        _write(tmp_repo, "LICENSE", "MIT License")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("LICENSE" in t for t in titles)

    def test_missing_gitignore(self, tmp_repo):
        """No .gitignore → finding (when readme exists)."""
        _write(tmp_repo, "README.md", "# Test")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any(".gitignore" in t.lower() for t in titles)

    def test_missing_ci(self, tmp_repo):
        """No .github/workflows → finding when lint configs exist."""
        _write(tmp_repo, "README.md", "# Test")
        _write(tmp_repo, ".gitignore", "")
        _write(tmp_repo, "pyproject.toml", "")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert any("CI" in t for t in titles)

    def test_pr_template_present(self, tmp_repo):
        """PR template exists → no finding."""
        _write(tmp_repo, "README.md", "# Test")
        _write(tmp_repo, ".github/PULL_REQUEST_TEMPLATE.md", "## Description")
        from scanners.layer_docs import scan_docs_ci

        findings = scan_docs_ci("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        assert not any("pull request" in t.lower() for t in titles)


# ═══════════════════════════════════════════════════════════════════════════════
# layer_security.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityScanner:
    """Tests for layer_security.py — scan_prod_readiness."""

    def test_env_committed_to_git(self, tmp_repo):
        """Detect .env in git history via mocked subprocess.run."""
        # Need a server/main.py to trigger server-specific checks
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(tmp_repo, "server/main.py", "print('hello')\n")

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            # text=True means stdout is str, not bytes
            mock_run.return_value.stdout = "abc123 Added .env\nabc124 Updated .env\n"
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any(".env" in t.lower() for t in titles)

    def test_no_env_finding(self, tmp_repo):
        """No .env in git history → no finding."""
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(tmp_repo, "server/main.py", "print('hello')\n")

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert not any(".env" in t.lower() for t in titles)

    def test_missing_dockerfile(self, tmp_repo):
        """Server project without Dockerfile → finding."""
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(tmp_repo, "server/main.py", "import uvicorn\n")

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("Docker" in t for t in titles)

    def test_has_dockerfile(self, tmp_repo):
        """Dockerfile exists → no missing-Docker finding."""
        _write(tmp_repo, "Dockerfile", "FROM python:3.11")
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(tmp_repo, "server/main.py", "import uvicorn\n")

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert not any("Docker" in t for t in titles)

    def test_missing_healthcheck(self, tmp_repo):
        """Server missing /health endpoint → finding."""
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(
            tmp_repo,
            "server/main.py",
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef root():\n    return 'ok'\n",
        )

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("health" in t.lower() for t in titles)

    def test_has_healthcheck(self, tmp_repo):
        """Server with /health endpoint → no finding."""
        os.makedirs(os.path.join(tmp_repo, "server"), exist_ok=True)
        _write(
            tmp_repo,
            "server/main.py",
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'ok': True}\n",
        )

        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert not any("health" in t.lower() for t in titles)

    def test_empty_repo_no_crash(self, tmp_repo):
        """Empty repo path → no errors."""
        with patch("scanners.layer_security.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            from scanners.layer_security import scan_prod_readiness

            findings = scan_prod_readiness("test-repo", tmp_repo)
            assert isinstance(findings, list)


# ═══════════════════════════════════════════════════════════════════════════════
# stdb_index.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestStdbIndexScanner:
    """Tests for stdb_index.py — scan_stdb_index."""

    def test_missing_id_field_not_indexed(self, tmp_repo):
        """A #[table] struct with _id field missing index is flagged."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "items")]\npub struct Item {\n    pub item_id: u64,\n    pub name: String,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        titles = [f["title"] for f in findings]
        # Title is generic: "Add #[index(btree)] to N field(s) in test-repo"
        assert any("field" in t for t in titles)

    def test_indexed_field_skipped(self, tmp_repo):
        """Fields with #[index(btree)] are not flagged."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "items")]\npub struct Item {\n    #[index(btree)]\n    pub item_id: u64,\n    pub name: String,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_no_table_struct(self, tmp_repo):
        """No #[table] struct → no findings."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/lib.rs",
            "pub fn nothing() {}",
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_primary_key_skipped(self, tmp_repo):
        """Fields with #[primary_key] are not flagged."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "items")]\npub struct Item {\n    #[primary_key]\n    pub item_id: u64,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_id_field_excluded(self, tmp_repo):
        """The bare 'id' field is excluded from FK detection."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "items")]\npub struct Item {\n    pub id: u64,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_unique_skipped(self, tmp_repo):
        """Fields with #[unique] are not flagged."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "items")]\npub struct Item {\n    #[unique]\n    pub user_name: String,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) == 0

    def test_name_suffix_detected(self, tmp_repo):
        """Field ending in _name (without index) is flagged."""
        os.makedirs(os.path.join(tmp_repo, "server/spacetimedb/src"), exist_ok=True)
        _write(
            tmp_repo,
            "server/spacetimedb/src/models.rs",
            '#[table(name = "users")]\npub struct User {\n    pub user_name: String,\n}\n',
        )
        from scanners.stdb_index import scan_stdb_index

        findings = scan_stdb_index("test-repo", tmp_repo)
        assert len(findings) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# todo_scanner.py  — uses subprocess.run with text=True (returns str stdout)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTodoScanner:
    """Tests for todo_scanner.py — scan_todos."""

    def test_bulk_todo_cleanup(self, tmp_repo):
        """>= 5 TODO markers → bulk cleanup task."""
        from scanners.todo_scanner import scan_todos

        with patch.object(subprocess, "run") as mock_run:
            # First call: git grep for all markers
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "file1.py:3\nfile2.py:2\n"

            # Second calls: git grep for each tag (TODO, FIXME, HACK, XXX)
            mock_run.return_value.stdout = "file1.py:3\nfile2.py:2\n"

            findings = scan_todos("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("TODO" in t for t in titles)

    def test_few_todos_no_finding(self, tmp_repo):
        """<5 TODO markers → no cleanup task."""
        from scanners.todo_scanner import scan_todos

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "file1.py:2\n"
            findings = scan_todos("test-repo", tmp_repo)
            assert len(findings) == 0

    def test_git_returns_one(self, tmp_repo):
        """git return code 1 still parsed (empty grep)."""
        from scanners.todo_scanner import scan_todos

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            findings = scan_todos("test-repo", tmp_repo)
            assert isinstance(findings, list)

    def test_git_unavailable(self, tmp_repo):
        """FileNotFoundError → empty findings."""
        from scanners.todo_scanner import scan_todos

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            findings = scan_todos("test-repo", tmp_repo)
            assert len(findings) == 0

    def test_timeout_handled(self, tmp_repo):
        """TimeoutExpired → empty findings."""
        from scanners.todo_scanner import scan_todos

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
            findings = scan_todos("test-repo", tmp_repo)
            assert len(findings) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# unused_code.py  — uses subprocess.run with text=True
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnusedCodeScanner:
    """Tests for unused_code.py — scan_unused_code."""

    def test_ruff_unused_imports_found(self, tmp_repo):
        """ruff output is parsed and a finding created."""
        _write(tmp_repo, "pyproject.toml", "")
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "app.py:1:1: F401 `os` imported but unused\n"
            mock_run.return_value.stderr = ""
            findings = scan_unused_code("test-repo", tmp_repo)
            titles = [f["title"] for f in findings]
            assert any("unused" in t.lower() for t in titles)

    def test_ruff_clean_no_finding(self, tmp_repo):
        """Clean ruff output → no finding."""
        _write(tmp_repo, "pyproject.toml", "")
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            findings = scan_unused_code("test-repo", tmp_repo)
            assert len(findings) == 0

    def test_ruff_not_installed(self, tmp_repo):
        """FileNotFoundError from ruff → no finding."""
        _write(tmp_repo, "pyproject.toml", "")
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            findings = scan_unused_code("test-repo", tmp_repo)
            assert len(findings) == 0

    def test_no_python_project(self, tmp_repo):
        """No pyproject.toml/ruff.toml → ruff check skipped."""
        from scanners.unused_code import scan_unused_code

        with patch.object(subprocess, "run"):
            findings = scan_unused_code("test-repo", tmp_repo)
            assert len(findings) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# scanners/__init__.py — registry utilities
# ═══════════════════════════════════════════════════════════════════════════════


class TestScannerInit:
    """Tests for scanners/__init__.py — registry, discover_repos, get_scanner_name."""

    def test_register_scanner_decorator(self):
        """@register_scanner adds to SCANNERS list."""
        from scanners import SCANNERS, register_scanner

        original_count = len(SCANNERS)

        @register_scanner
        def scan_dummy(repo_name, repo_path):
            return []

        assert len(SCANNERS) == original_count + 1
        assert scan_dummy in SCANNERS

    def test_get_scanner_name(self):
        """get_scanner_name strips scan_ prefix."""
        from scanners import get_scanner_name

        def scan_foo(repo_name, repo_path):
            return []

        assert get_scanner_name(scan_foo) == "foo"

    def test_discover_repos_empty(self):
        """No .git dirs → empty list."""
        with tempfile.TemporaryDirectory() as empty_dir:
            real_home = os.environ.get("HOME", "")
            try:
                os.environ["HOME"] = empty_dir
                from scanners import discover_repos

                repos = discover_repos(max_repos=10)
                assert len(repos) == 0
            finally:
                os.environ["HOME"] = real_home
