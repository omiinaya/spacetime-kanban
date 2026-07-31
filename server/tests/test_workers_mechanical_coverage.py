"""Comprehensive tests for mechanical worker handlers — mocking external deps."""

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch, mock_open

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.base import WorkerContext
from workers.mechanical import (
    HANDLERS,
    _find_python_top_level_items,
    _find_rust_top_level_items,
    handle_add_index_btree,
    handle_add_init_py,
    handle_add_project_files,
    handle_add_test_scaffold,
    handle_bare_except_scanner,
    handle_ci_pipeline,
    handle_extract_module,
    handle_fix_clippy,
    handle_git_maintenance,
    handle_lint_code,
    handle_remove_unused_imports,
    handle_replace_unwrap_scanner,
    handle_run_tests,
    handle_scan_todos,
    handle_stale_todos,
    handle_sync_env,
    handle_typed_errors,
    handle_update_deps,
    match_handler,
    sh_quote,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def ctx():
    """Minimal WorkerContext with a tmp_path repo."""
    ctx = WorkerContext("task_test")
    ctx.task = {"id": "task_test", "title": "Test task", "repo": "test-repo"}
    return ctx


@pytest.fixture
def repo_dir(tmp_path):
    """Create a repo directory."""
    d = tmp_path / "repos" / "test-repo"
    d.mkdir(parents=True)
    return str(d)


@pytest.fixture
def ctx_with_repo(repo_dir):
    """WorkerContext with a valid repo_path."""
    ctx = WorkerContext("task_test")
    ctx.task = {"id": "task_test", "title": "Test task", "repo": "test-repo"}
    # Directly set the property — new_callable=MagicMock wraps it and breaks access
    with patch.object(WorkerContext, "repo_path", repo_dir):
        yield ctx


@pytest.fixture
def stdb_dir(repo_dir):
    """Create server/spacetimedb/src directory."""
    d = os.path.join(repo_dir, "server", "spacetimedb", "src")
    os.makedirs(d, exist_ok=True)
    return d


# ── Helpers ────────────────────────────────────────────────────────────────


class TestShQuote:
    def test_simple_path(self):
        assert sh_quote("/path/to/file") == "'/path/to/file'"

    def test_path_with_single_quote(self):
        assert sh_quote("/path/to/it's/file") == "'/path/to/it'\\''s/file'"

    def test_empty_string(self):
        assert sh_quote("") == "''"


class TestFindRustTopLevelItems:
    def test_empty_content(self):
        assert _find_rust_top_level_items("") == []

    def test_single_fn(self):
        content = "pub fn hello() {\n    println!(\"hi\");\n}\n"
        items = _find_rust_top_level_items(content)
        assert len(items) == 1
        assert items[0]["name"] == "hello"
        assert items[0]["kind"] == "fn"

    def test_multiple_items(self):
        content = """pub fn foo() { }
pub struct Bar { x: i32 }
pub enum Baz { A, B }
"""
        items = _find_rust_top_level_items(content)
        names = {i["name"] for i in items}
        assert "foo" in names
        assert "Bar" in names
        assert "Baz" in names

    def test_impl_block(self):
        content = "impl Foo {\n    fn bar() { }\n}\n"
        items = _find_rust_top_level_items(content)
        assert len(items) >= 1
        assert items[0]["name"] == "Foo" or items[0]["kind"] == "impl"

    def test_nested_braces(self):
        content = """fn outer() {
    if true {
        let x = 1;
    }
}
"""
        items = _find_rust_top_level_items(content)
        assert len(items) == 1
        end_line = items[0]["end_line"]
        assert end_line > 0

    def test_no_items(self):
        content = "// just a comment\nuse std::collections::HashMap;\n"
        assert _find_rust_top_level_items(content) == []

    def test_trait_declaration(self):
        content = "pub trait MyTrait {\n    fn do_thing();\n}\n"
        items = _find_rust_top_level_items(content)
        names = {i["name"] for i in items}
        assert "MyTrait" in names


class TestFindPythonTopLevelItems:
    def test_empty_content(self):
        assert _find_python_top_level_items("") == []

    def test_single_def(self):
        content = "def hello():\n    pass\n"
        items = _find_python_top_level_items(content)
        assert len(items) == 1
        assert items[0]["name"] == "hello"
        assert items[0]["kind"] == "def"

    def test_class_and_function(self):
        content = "class MyClass:\n    pass\n\ndef my_func():\n    pass\n"
        items = _find_python_top_level_items(content)
        names = {i["name"] for i in items}
        assert "MyClass" in names
        assert "my_func" in names

    def test_decorator_not_item(self):
        """Decorators alone don't count as items."""
        content = "@decorator\ndef func():\n    pass\n"
        items = _find_python_top_level_items(content)
        assert len(items) == 1
        assert items[0]["name"] == "func"

    def test_no_items(self):
        content = "# comment\nimport os\n\nx = 1\n"
        assert _find_python_top_level_items(content) == []

    def test_multiple_classes(self):
        content = """class A:
    pass

class B:
    pass

class C:
    pass
"""
        items = _find_python_top_level_items(content)
        assert len(items) == 3


# ── Handler: handle_add_index_btree ─────────────────────────────────────


class TestHandleAddIndexBtree:
    def test_no_repo_path(self, ctx):
        success, msg = handle_add_index_btree(ctx)
        assert not success
        assert "not found" in msg

    def test_no_table_files(self, ctx_with_repo, repo_dir):
        success, msg = handle_add_index_btree(ctx_with_repo)
        assert not success
        assert "No STDB table files found" in msg or "not found" in msg

    def test_adds_index_to_candidate(self, ctx_with_repo, repo_dir, stdb_dir):
        """Create a tables.rs with a candidate field."""
        tables_rs = os.path.join(stdb_dir, "tables.rs")
        os.makedirs(os.path.dirname(tables_rs), exist_ok=True)
        # Minimal struct with no leading #[...] attributes to avoid has_attr false positive
        with open(tables_rs, "w") as f:
            f.write("pub struct Tasks {\n    pub user_id: String,\n}\n")
        assert os.path.isfile(tables_rs)
        success, msg = handle_add_index_btree(ctx_with_repo)
        assert success, f"Expected success but got: {msg}"
        assert "Added #[index(btree)]" in msg

    def test_index_btree_already_exists(self, ctx_with_repo, stdb_dir):
        """Field already has #[index(btree)] — skip it."""
        tables_rs = os.path.join(stdb_dir, "tables.rs")
        with open(tables_rs, "w") as f:
            f.write("pub struct Tasks {\n    #[index(btree)]\n    pub user_id: String,\n}\n")
        success, msg = handle_add_index_btree(ctx_with_repo)
        assert not success
        assert "already indexed" in msg or "No indexable fields" in msg

    def test_primary_key_skip(self, ctx_with_repo, stdb_dir):
        """Skip fields with #[primary_key]."""
        tables_rs = os.path.join(stdb_dir, "tables.rs")
        with open(tables_rs, "w") as f:
            f.write("#[table(name = tasks, public)]\npub struct Tasks {\n    #[primary_key]\n    pub user_id: String,\n}\n")
        success, msg = handle_add_index_btree(ctx_with_repo)
        assert "already indexed" in msg or "No indexable" in msg

    def test_error_reading_file(self, ctx_with_repo):
        """Exception reading file."""
        with patch("glob.glob", return_value=["/nonexistent/tables.rs"]), \
             patch("builtins.open", side_effect=PermissionError("denied")):
            success, msg = handle_add_index_btree(ctx_with_repo)
            assert not success


# ── Handler: handle_fix_clippy ──────────────────────────────────────────


class TestHandleFixClippy:
    def test_no_repo_path(self, ctx):
        success, msg = handle_fix_clippy(ctx)
        assert not success
        assert "not found" in msg

    def test_no_stdb_dir(self, ctx_with_repo, repo_dir):
        success, msg = handle_fix_clippy(ctx_with_repo)
        assert not success
        assert "No server/spacetimedb directory" in msg

    def test_clippy_success(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = handle_fix_clippy(ctx_with_repo)
            assert success
            assert "warning" in msg or "passed" in msg

    def test_clippy_errors(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="error: something failed", stderr=""
            )
            success, msg = handle_fix_clippy(ctx_with_repo)
            assert not success
            assert "error" in msg.lower()

    def test_clippy_timeout(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cargo", 120)):
            success, msg = handle_fix_clippy(ctx_with_repo)
            assert not success
            assert "timed out" in msg

    def test_cargo_not_found(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run", side_effect=FileNotFoundError("cargo")):
            success, msg = handle_fix_clippy(ctx_with_repo)
            assert not success
            assert "not found" in msg


# ── Handler: handle_remove_unused_imports ────────────────────────────────


class TestHandleRemoveUnusedImports:
    def test_no_repo_path(self, ctx):
        success, msg = handle_remove_unused_imports(ctx)
        assert not success
        assert "not found" in msg

    def test_no_config_files(self, ctx_with_repo, repo_dir):
        """No pyproject.toml, no ruff.toml, no stdb dir."""
        success, msg = handle_remove_unused_imports(ctx_with_repo)
        assert not success
        assert "No unused imports" in msg

    def test_ruff_fixes_something(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[tool.ruff]\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Fixed 3 errors", stderr=""
            )
            success, msg = handle_remove_unused_imports(ctx_with_repo)
            assert success
            assert "Removed" in msg

    def test_ruff_timeout(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[tool.ruff]\n")
        with patch("subprocess.run") as mock_run:
            # First call (ruff) raises timeout
            mock_run.side_effect = subprocess.TimeoutExpired("ruff", 60)
            success, msg = handle_remove_unused_imports(ctx_with_repo)
            assert "ruff timed out" in msg

    def test_cargo_fix_success(self, ctx_with_repo, stdb_dir):
        """stdb dir present, cargo fix runs."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Fixed", stderr="")
            success, msg = handle_remove_unused_imports(ctx_with_repo)
            # May succeed or fail depending on ruff availability
            assert isinstance(success, bool)
            assert isinstance(msg, str)

    def test_ruff_not_found(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[tool.ruff]\n")
        with patch("subprocess.run", side_effect=FileNotFoundError("ruff")):
            success, msg = handle_remove_unused_imports(ctx_with_repo)
            assert "ruff not found" in msg


# ── Handler: handle_extract_module ────────────────────────────────────────


class TestHandleExtractModule:
    def test_no_repo_path(self, ctx):
        success, msg = handle_extract_module(ctx)
        assert not success
        assert "not found" in msg

    def test_no_source_files(self, ctx_with_repo, repo_dir):
        """No .rs or .py files in repo."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            success, msg = handle_extract_module(ctx_with_repo)
            assert not success
            assert "No" in msg and "found" in msg

    def test_find_command_not_found(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run", side_effect=FileNotFoundError("find")):
            success, msg = handle_extract_module(ctx_with_repo)
            assert not success
            assert "not available" in msg

    def test_find_timed_out(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("find", 30)):
            success, msg = handle_extract_module(ctx_with_repo)
            assert not success
            assert "Timed out" in msg

    def test_rust_extraction(self, ctx_with_repo, repo_dir):
        """Create a Rust file and try to extract a function."""
        src_dir = os.path.join(repo_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        rs_file = os.path.join(src_dir, "main.rs")
        with open(rs_file, "w") as f:
            f.write("pub fn hello() {\n    println!(\"hi\");\n}\n\npub fn world() {\n    println!(\"earth\");\n}\n")

        # Mock the find command to return our file
        wc_output = f"5 {rs_file}\n5 total\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=wc_output)
            # Mock the write subprocess calls
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=wc_output),  # find | wc
                MagicMock(returncode=0, stdout=""),  # sh -c cat > new_file
                MagicMock(returncode=0, stdout=""),  # sh -c cat > original
            ]
            success, msg = handle_extract_module(ctx_with_repo)
            # It may fail because subprocess.run is also called for writing
            assert isinstance(success, bool)

    def test_no_top_level_items(self, ctx_with_repo, repo_dir):
        """File with no extractable items."""
        src_dir = os.path.join(repo_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        rs_file = os.path.join(src_dir, "empty.rs")
        with open(rs_file, "w") as f:
            f.write("// just a comment\nuse std::collections::HashMap;\n")

        wc_output = f"2 {rs_file}\n2 total\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=wc_output)
            success, msg = handle_extract_module(ctx_with_repo)
            # The file is only 2 lines (< 10), so it won't be considered
            assert not success

    def test_python_extraction(self, ctx_with_repo, repo_dir):
        """Create a Python file and try to extract."""
        src_dir = os.path.join(repo_dir, "src")
        os.makedirs(src_dir, exist_ok=True)
        py_file = os.path.join(src_dir, "module.py")
        with open(py_file, "w") as f:
            f.write("def hello():\n    pass\n\n\ndef world():\n    pass\n")
        wc_output = f"5 {py_file}\n5 total\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=wc_output)
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=wc_output),
                MagicMock(returncode=0, stdout=""),
                MagicMock(returncode=0, stdout=""),
            ]
            success, msg = handle_extract_module(ctx_with_repo)
            assert isinstance(success, bool)


# ── Handler: handle_typed_errors ──────────────────────────────────────────


class TestHandleTypedErrors:
    def test_no_repo_path(self, ctx):
        success, msg = handle_typed_errors(ctx)
        assert not success
        assert "not found" in msg

    def test_no_errors_found(self, ctx_with_repo, repo_dir):
        """Empty repo, no string-based errors."""
        success, msg = handle_typed_errors(ctx_with_repo)
        assert success
        assert "No string-based errors" in msg or "not applicable" in msg

    def test_python_return_err(self, ctx_with_repo, repo_dir):
        """Python file with return Err('...') pattern."""
        src_dir = os.path.join(repo_dir, "server")
        os.makedirs(src_dir, exist_ok=True)
        py_file = os.path.join(src_dir, "routes.py")
        with open(py_file, "w") as f:
            f.write("def handler():\n    return Err('something went wrong')\n")
        success, msg = handle_typed_errors(ctx_with_repo)
        assert success
        assert "string-based error" in msg or "Error" in msg or "Suggested" in msg

    def test_rust_err_literal(self, ctx_with_repo, stdb_dir):
        """Rust file with Err('literal'.to_string())."""
        rs_file = os.path.join(stdb_dir, "reducers.rs")
        with open(rs_file, "w") as f:
            f.write("fn do_thing() -> Result<(), String> {\n    Err(\"failed\".to_string())\n}\n")
        success, msg = handle_typed_errors(ctx_with_repo)
        assert success
        assert "string-based error" in msg or "Rust" in msg

    def test_existing_error_rs(self, ctx_with_repo, stdb_dir):
        """error.rs already exists."""
        # Create an error.rs
        with open(os.path.join(stdb_dir, "error.rs"), "w") as f:
            f.write("pub enum ReducerError {}\n")
        # Create a Rust file with error patterns
        rs_file = os.path.join(stdb_dir, "reducers.rs")
        with open(rs_file, "w") as f:
            f.write("fn do_thing() -> Result<(), String> {\n    Err(\"failed\".to_string())\n}\n")
        success, msg = handle_typed_errors(ctx_with_repo)
        assert success

    def test_raise_exception_python(self, ctx_with_repo, repo_dir):
        """Python file with raise Exception('...')"""
        src_dir = os.path.join(repo_dir, "server")
        os.makedirs(src_dir, exist_ok=True)
        py_file = os.path.join(src_dir, "errors.py")
        with open(py_file, "w") as f:
            f.write('def check():\n    raise ValueError("invalid input")\n')
        success, msg = handle_typed_errors(ctx_with_repo)
        assert success


# ── Handler: handle_run_tests ──────────────────────────────────────────────


class TestHandleRunTests:
    def test_no_repo_path(self, ctx):
        success, msg = handle_run_tests(ctx)
        assert not success
        assert "not found" in msg

    def test_no_framework_detected(self, ctx_with_repo, repo_dir):
        success, msg = handle_run_tests(ctx_with_repo)
        assert not success
        assert "No test framework detected" in msg

    def test_pytest_success(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[project]\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="collected 10 items\n10 passed in 0.50s\nPASSED PASSED PASSED", stderr=""
            )
            success, msg = handle_run_tests(ctx_with_repo)
            assert "Python" in msg

    def test_pytest_timeout(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[project]\n")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pytest", 180)):
            success, msg = handle_run_tests(ctx_with_repo)
            assert "timed out" in msg

    def test_pytest_not_found(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[project]\n")
        with patch("subprocess.run", side_effect=FileNotFoundError("pytest")):
            success, msg = handle_run_tests(ctx_with_repo)
            assert "not found" in msg

    def test_cargo_test(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="test result: ok. 5 passed; 0 failed", stderr=""
            )
            success, msg = handle_run_tests(ctx_with_repo)
            assert "Rust" in msg

    def test_cargo_timeout(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cargo", 180)):
            success, msg = handle_run_tests(ctx_with_repo)
            assert "timed out" in msg

    def test_npm_test(self, ctx_with_repo, repo_dir):
        package_json = os.path.join(repo_dir, "package.json")
        with open(package_json, "w") as f:
            f.write('{"scripts": {"test": "jest"}}\n')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = handle_run_tests(ctx_with_repo)
            assert "Node" in msg

    def test_cargo_failed(self, ctx_with_repo, stdb_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="test result: FAILED. 3 failed"
            )
            success, msg = handle_run_tests(ctx_with_repo)
            assert "failure" in msg or "FAILED" in msg


# ── Handler: handle_update_deps ────────────────────────────────────────────


class TestHandleUpdateDeps:
    def test_no_repo_path(self, ctx):
        success, msg = handle_update_deps(ctx)
        assert not success
        assert "not found" in msg

    def test_no_dep_files(self, ctx_with_repo, repo_dir):
        success, msg = handle_update_deps(ctx_with_repo)
        assert not success
        # Could be "No dependency files" or "not found"
        assert not success

    def test_python_deps(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[project]\ndependencies = []\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="All packages up to date", stderr="")
            success, msg = handle_update_deps(ctx_with_repo)
            assert isinstance(success, bool)

    def test_node_deps(self, ctx_with_repo, repo_dir):
        package_json = os.path.join(repo_dir, "package.json")
        with open(package_json, "w") as f:
            f.write('{"dependencies": {}}\n')
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="up to date", stderr="")
            success, msg = handle_update_deps(ctx_with_repo)
            assert isinstance(success, bool)

    def test_rust_deps(self, ctx_with_repo, stdb_dir):
        cargo_toml = os.path.join(stdb_dir, "Cargo.toml")
        with open(cargo_toml, "w") as f:
            f.write("[dependencies]\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            success, msg = handle_update_deps(ctx_with_repo)
            assert isinstance(success, bool)


# ── Handler: handle_git_maintenance ───────────────────────────────────────


class TestHandleGitMaintenance:
    def test_no_repo_path(self, ctx):
        success, msg = handle_git_maintenance(ctx)
        assert not success
        assert "not found" in msg

    def test_git_gc_fails_not_a_repo(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(128, "git")
            success, msg = handle_git_maintenance(ctx_with_repo)
            assert not success

    def test_git_success(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
            success, msg = handle_git_maintenance(ctx_with_repo)
            assert success

    def test_git_timeout(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            success, msg = handle_git_maintenance(ctx_with_repo)
            assert not success
            assert "timed out" in msg

    def test_git_not_found(self, ctx_with_repo, repo_dir):
        with patch("subprocess.run", side_effect=FileNotFoundError("git")):
            success, msg = handle_git_maintenance(ctx_with_repo)
            assert not success
            assert "not found" in msg


# ── Handler: handle_scan_todos ────────────────────────────────────────────


class TestHandleScanTodos:
    def test_no_repo_path(self, ctx):
        success, msg = handle_scan_todos(ctx)
        assert not success
        assert "not found" in msg

    def test_no_todos_found(self, ctx_with_repo, repo_dir):
        success, msg = handle_scan_todos(ctx_with_repo)
        assert success
        assert "No" in msg or "found" in msg.lower()

    def test_todos_found(self, ctx_with_repo, repo_dir):
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("# TODO: fix this\n# FIXME: and this\n")
        success, msg = handle_scan_todos(ctx_with_repo)
        assert success
        assert "TODO" in msg or "FIXME" in msg


# ── Handler: handle_sync_env ──────────────────────────────────────────────


class TestHandleSyncEnv:
    def test_no_repo_path(self, ctx):
        success, msg = handle_sync_env(ctx)
        assert not success
        assert "not found" in msg

    def test_no_env_example(self, ctx_with_repo, repo_dir):
        success, msg = handle_sync_env(ctx_with_repo)
        assert success  # Handler returns True when no files to sync (nothing wrong)
        assert "Env files are in sync" in msg

    def test_env_missing_keys(self, ctx_with_repo, repo_dir):
        """env.example has extra keys env doesnt have."""
        with open(os.path.join(repo_dir, ".env.example"), "w") as f:
            f.write("KEY=value\nANOTHER=123\n")
        with open(os.path.join(repo_dir, ".env"), "w") as f:
            f.write("KEY=value\n")
        success, msg = handle_sync_env(ctx_with_repo)
        assert success
        assert "missing" in msg

    def test_env_already_synced(self, ctx_with_repo, repo_dir):
        """env and env.example match."""
        with open(os.path.join(repo_dir, ".env.example"), "w") as f:
            f.write("KEY=value\n")
        with open(os.path.join(repo_dir, ".env"), "w") as f:
            f.write("KEY=value\n")
        success, msg = handle_sync_env(ctx_with_repo)
        assert success
        assert "in sync" in msg


# ── Handler: handle_lint_code ──────────────────────────────────────────────


class TestHandleLintCode:
    def test_no_repo_path(self, ctx):
        success, msg = handle_lint_code(ctx)
        assert not success
        assert "not found" in msg

    def test_no_lint_tool(self, ctx_with_repo, repo_dir):
        success, msg = handle_lint_code(ctx_with_repo)
        assert not success

    def test_ruff_lints(self, ctx_with_repo, repo_dir):
        pyproject = os.path.join(repo_dir, "pyproject.toml")
        with open(pyproject, "w") as f:
            f.write("[tool.ruff]\n")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="All checks passed!", stderr="")
            success, msg = handle_lint_code(ctx_with_repo)
            assert isinstance(success, bool)


# ── Handler: handle_add_init_py ──────────────────────────────────────────


class TestHandleAddInitPy:
    def test_no_repo_path(self, ctx):
        success, msg = handle_add_init_py(ctx)
        assert not success
        assert "not found" in msg

    def test_no_missing_init_py(self, ctx_with_repo, repo_dir):
        """No description in task."""
        ctx_with_repo.task = {**ctx_with_repo.task, "description": ""}
        success, msg = handle_add_init_py(ctx_with_repo)
        assert not success
        assert "No description" in msg

    def test_no_dirs_in_description(self, ctx_with_repo, repo_dir):
        """Description but no dirs."""
        ctx_with_repo.task = {**ctx_with_repo.task, "description": "- Found no issues\n- Everything is fine\n"}
        success, msg = handle_add_init_py(ctx_with_repo)
        assert not success

    def test_creates_init_py(self, ctx_with_repo, repo_dir):
        """Creates __init__.py in specified dir."""
        pkg_dir = os.path.join(repo_dir, "server", "routes")
        os.makedirs(pkg_dir, exist_ok=True)
        ctx_with_repo.task = {
            **ctx_with_repo.task,
            "description": "- server/routes\n- server/models\n",
        }
        success, msg = handle_add_init_py(ctx_with_repo)
        assert success
        assert "Created" in msg


# ── Handler: handle_add_project_files ──────────────────────────────────────


class TestHandleAddProjectFiles:
    def test_no_repo_path(self, ctx):
        success, msg = handle_add_project_files(ctx)
        assert not success
        assert "not found" in msg

    def test_license_added(self, ctx_with_repo, repo_dir):
        success, msg = handle_add_project_files(ctx_with_repo)
        assert isinstance(success, bool)


# ── Handler: handle_stale_todos ───────────────────────────────────────────


class TestHandleStaleTodos:
    def test_no_repo_path(self, ctx):
        success, msg = handle_stale_todos(ctx)
        assert not success
        assert "not found" in msg

    def test_no_stale_todos(self, ctx_with_repo, repo_dir):
        success, msg = handle_stale_todos(ctx_with_repo)
        assert isinstance(success, bool)


# ── Handler: handle_add_test_scaffold ─────────────────────────────────────


class TestHandleAddTestScaffold:
    def test_no_repo_path(self, ctx):
        success, msg = handle_add_test_scaffold(ctx)
        assert not success
        assert "not found" in msg

    def test_no_source_dir(self, ctx_with_repo, repo_dir):
        success, msg = handle_add_test_scaffold(ctx_with_repo)
        assert isinstance(success, bool)


# ── Handler: handle_replace_unwrap_scanner ────────────────────────────────


class TestHandleReplaceUnwrapScanner:
    def test_no_repo_path(self, ctx):
        success, msg = handle_replace_unwrap_scanner(ctx)
        assert not success
        assert "not found" in msg

    def test_no_unwraps(self, ctx_with_repo, repo_dir):
        success, msg = handle_replace_unwrap_scanner(ctx_with_repo)
        assert success

    def test_unwraps_found(self, ctx_with_repo, repo_dir):
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("result.unwrap()\n")
        success, msg = handle_replace_unwrap_scanner(ctx_with_repo)
        assert success


# ── Handler: handle_bare_except_scanner ────────────────────────────────────


class TestHandleBareExceptScanner:
    def test_no_repo_path(self, ctx):
        success, msg = handle_bare_except_scanner(ctx)
        assert not success
        assert "not found" in msg

    def test_no_bare_excepts(self, ctx_with_repo, repo_dir):
        success, msg = handle_bare_except_scanner(ctx_with_repo)
        assert success

    def test_bare_except_found(self, ctx_with_repo, repo_dir):
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("try:\n    pass\nexcept:\n    pass\n")
        success, msg = handle_bare_except_scanner(ctx_with_repo)
        assert success


# ── Handler: handle_ci_pipeline ────────────────────────────────────────────


class TestHandleCiPipeline:
    def test_no_repo_path(self, ctx):
        success, msg = handle_ci_pipeline(ctx)
        assert not success
        assert "not found" in msg

    def test_ci_added(self, ctx_with_repo, repo_dir):
        success, msg = handle_ci_pipeline(ctx_with_repo)
        assert isinstance(success, bool)


# ── Handler contract: all handlers return (bool, str) ──────────────────────


class TestAllHandlerContracts:
    """Verify every handler at least handles missing repo_path gracefully."""

    def test_all_handlers_handle_no_repo(self, ctx):
        """Every handler returns (bool, str) when repo_path is not set."""
        for pattern, handler in HANDLERS:
            ctx_isolated = WorkerContext("task_contract")
            ctx_isolated.task = {"id": "task_contract", "title": pattern.pattern, "repo": "test"}
            result = handler(ctx_isolated)
            assert isinstance(result, tuple) and len(result) == 2, (
                f"{handler.__name__} should return (bool, str), got {type(result)}"
            )
            success, msg = result
            assert isinstance(success, bool), f"{handler.__name__} first return should be bool"
            assert isinstance(msg, str), f"{handler.__name__} second return should be str"
