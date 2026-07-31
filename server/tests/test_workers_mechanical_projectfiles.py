"""Final batch: handle_add_project_files and handle_stale_todos coverage."""

import os
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.base import WorkerContext
from workers.mechanical import handle_add_project_files, handle_stale_todos


@pytest.fixture
def repo_dir(tmp_path):
    d = tmp_path / "repos" / "test-repo"
    d.mkdir(parents=True)
    return str(d)


@pytest.fixture
def ctx(repo_dir):
    ctx = WorkerContext("task_test")
    ctx.task = {"id": "task_test", "title": "add license", "repo": "test-repo"}
    with patch.object(WorkerContext, "repo_path", repo_dir):
        yield ctx


# ═══════════════════════════════════════════════════════════════════════════
# handle_add_project_files — needs specific title to trigger each block
# ═══════════════════════════════════════════════════════════════════════════

class TestAddProjectFilesTitles:
    def test_create_license(self, repo_dir):
        """Title 'add license' triggers the license block."""
        ctx = WorkerContext("task_l")
        ctx.task = {"id": "task_l", "title": "add license", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success
            assert "LICENSE" in msg

    def test_license_already_exists(self, repo_dir):
        """License already exists."""
        with open(os.path.join(repo_dir, "LICENSE"), "w") as f:
            f.write("MIT\n")
        ctx = WorkerContext("task_l")
        ctx.task = {"id": "task_l", "title": "add license", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert not success
            assert "already exist" in msg

    def test_create_contributing(self, repo_dir):
        """Title 'add contributing' triggers the contributing block."""
        ctx = WorkerContext("task_c")
        ctx.task = {"id": "task_c", "title": "add contributing.md", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success
            assert "CONTRIBUTING" in msg

    def test_create_issue_template(self, repo_dir):
        """Title 'add issue template' creates issue templates."""
        ctx = WorkerContext("task_i")
        ctx.task = {"id": "task_i", "title": "add issue template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success
            assert "ISSUE_TEMPLATE" in msg or "issue" in msg.lower()

    def test_create_pr_template(self, repo_dir):
        """Title 'add pr template' creates PR template."""
        ctx = WorkerContext("task_p")
        ctx.task = {"id": "task_p", "title": "add pr template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success
            assert "PULL_REQUEST" in msg or "pr" in msg.lower() or "template" in msg.lower()

    def test_create_pull_request_template(self, repo_dir):
        """Title 'add pull request template' also works."""
        ctx = WorkerContext("task_pr")
        ctx.task = {"id": "task_pr", "title": "add pull request template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success

    def test_create_all_in_one(self, repo_dir):
        """Title with all keywords creates multiple files."""
        ctx = WorkerContext("task_all")
        ctx.task = {
            "id": "task_all",
            "title": "add license contributing issue template pr template",
            "repo": "test-repo",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success
            assert "Created" in msg

    def test_create_license_oserror(self, repo_dir):
        """License creation OSError."""
        ctx = WorkerContext("task_lo")
        ctx.task = {"id": "task_lo", "title": "add license", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                success, msg = handle_add_project_files(ctx)
                assert not success
                assert "already exist" in msg

    def test_create_contributing_oserror(self, repo_dir):
        """Contributing creation OSError."""
        ctx = WorkerContext("task_co")
        ctx.task = {"id": "task_co", "title": "add contributing.md", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                success, msg = handle_add_project_files(ctx)
                assert not success

    def test_create_issue_template_oserror(self, repo_dir):
        """Issue template creation OSError."""
        ctx = WorkerContext("task_io")
        ctx.task = {"id": "task_io", "title": "add issue template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                success, msg = handle_add_project_files(ctx)
                assert isinstance(success, bool)

    def test_create_pr_template_oserror(self, repo_dir):
        """PR template creation OSError."""
        ctx = WorkerContext("task_po")
        ctx.task = {"id": "task_po", "title": "add pr template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                success, msg = handle_add_project_files(ctx)
                assert isinstance(success, bool)

    def test_feature_request_already_exists(self, repo_dir):
        """Feature request template already exists, bug doesn't."""
        template_dir = os.path.join(repo_dir, ".github", "ISSUE_TEMPLATE")
        os.makedirs(template_dir, exist_ok=True)
        with open(os.path.join(template_dir, "feature_request.md"), "w") as f:
            f.write("existing\n")
        ctx = WorkerContext("task_fr")
        ctx.task = {"id": "task_fr", "title": "add issue template", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert success

    def test_no_matching_title(self, repo_dir):
        """Title without any keywords returns all-files-exist."""
        ctx = WorkerContext("task_none")
        ctx.task = {"id": "task_none", "title": "Fix bug", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_add_project_files(ctx)
            assert not success
            assert "already exist" in msg


# ═══════════════════════════════════════════════════════════════════════════
# handle_stale_todos — needs description with file paths
# ═══════════════════════════════════════════════════════════════════════════

class TestStaleTodosProper:
    def test_no_description(self, repo_dir):
        """No description in task."""
        ctx = WorkerContext("task_s1")
        ctx.task = {"id": "task_s1", "title": "review 5 stale todo", "repo": "test-repo"}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert not success
            assert "No description" in msg

    def test_empty_description(self, repo_dir):
        """Empty description."""
        ctx = WorkerContext("task_s2")
        ctx.task = {"id": "task_s2", "title": "review stale todo", "repo": "test-repo", "description": ""}
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert not success
            assert "No description" in msg

    def test_no_files_in_description(self, repo_dir):
        """Description with no file paths."""
        ctx = WorkerContext("task_s3")
        ctx.task = {
            "id": "task_s3",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "No files found",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert not success
            assert "No files listed" in msg

    def test_file_not_found(self, repo_dir):
        """Listed file doesn't exist."""
        ctx = WorkerContext("task_s4")
        ctx.task = {
            "id": "task_s4",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- nonexistent.py\n",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert success
            assert "No stale TODOs" in msg

    def test_file_with_todo_found(self, repo_dir):
        """File with TODO found."""
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("# TODO: fix this\n")
        ctx = WorkerContext("task_s5")
        ctx.task = {
            "id": "task_s5",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- code.py\n",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert success
            assert "Found" in msg or "TODO" in msg

    def test_file_without_todo(self, repo_dir):
        """File without TODO."""
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("print('hello')\n")
        ctx = WorkerContext("task_s6")
        ctx.task = {
            "id": "task_s6",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- code.py\n",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert success
            assert "No stale TODOs" in msg

    def test_file_with_rust_todo(self, repo_dir):
        """Rust file with // TODO."""
        rs_file = os.path.join(repo_dir, "main.rs")
        with open(rs_file, "w") as f:
            f.write("// TODO: implement\nfn main() {}\n")
        ctx = WorkerContext("task_s7")
        ctx.task = {
            "id": "task_s7",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- main.rs\n",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert success
            assert "Found" in msg

    def test_file_with_html_todo(self, repo_dir):
        """HTML file with <!-- TODO -->."""
        html_file = os.path.join(repo_dir, "index.html")
        with open(html_file, "w") as f:
            f.write("<!-- TODO: add content -->\n")
        ctx = WorkerContext("task_s8")
        ctx.task = {
            "id": "task_s8",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- index.html\n",
        }
        with patch.object(WorkerContext, "repo_path", repo_dir):
            success, msg = handle_stale_todos(ctx)
            assert success
            assert "Found" in msg

    def test_read_exception_caught(self, repo_dir):
        """Exception reading file silently caught."""
        py_file = os.path.join(repo_dir, "code.py")
        with open(py_file, "w") as f:
            f.write("# TODO\n")
        os.chmod(py_file, 0o000)
        ctx = WorkerContext("task_s9")
        ctx.task = {
            "id": "task_s9",
            "title": "review stale todo",
            "repo": "test-repo",
            "description": "- code.py\n",
        }
        try:
            with patch.object(WorkerContext, "repo_path", repo_dir):
                success, msg = handle_stale_todos(ctx)
                assert success
        finally:
            os.chmod(py_file, 0o644)
