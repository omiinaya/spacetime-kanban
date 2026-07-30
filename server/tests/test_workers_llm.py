"""Tests for server/workers/llm.py — LLM-driven worker."""

import os
import sys
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.base import WorkerContext
from workers.llm import (
    _build_prompt,
    _has_git_changes,
    _has_git_commits_since,
    run_llm_worker,
)


class TestBuildPrompt:
    """_build_prompt() constructs the LLM prompt correctly."""

    def test_basic_prompt(self):
        ctx = WorkerContext("task_123")
        ctx.task = {"title": "Fix the bug", "repo": "test-repo", "description": ""}
        prompt = _build_prompt(ctx)
        assert "Fix the bug" in prompt
        assert "test-repo" in prompt
        assert "WORKER_DONE" in prompt
        assert "WORKER_BLOCKED" in prompt

    def test_with_description(self):
        ctx = WorkerContext("task_123")
        ctx.task = {
            "title": "Refactor module",
            "repo": "test-repo",
            "description": "Extract the X component",
        }
        prompt = _build_prompt(ctx)
        assert "Extract the X component" in prompt

    def test_with_branch_and_pr(self):
        ctx = WorkerContext("task_123")
        ctx.task = {
            "title": "Task",
            "repo": "test-repo",
            "branch": "feat/test",
            "pr_url": "https://github.com/test/pull/1",
        }
        prompt = _build_prompt(ctx)
        assert "feat/test" in prompt
        assert "pull/1" in prompt

    def test_uses_escaped_newlines(self):
        ctx = WorkerContext("task_123")
        ctx.task = {"title": "Task", "repo": "test-repo"}
        prompt = _build_prompt(ctx)
        assert "\\n" in prompt  # Uses newline literals for hermes -z mode


class TestHasGitChanges:
    """_has_git_changes() checks for modified files."""

    @patch("workers.llm.subprocess.run")
    def test_with_changes(self, mock_run):
        mock_run.return_value = MagicMock(stdout="file1.py\nfile2.rs\n", returncode=0)
        result = _has_git_changes("/fake/repo")
        assert result == ["file1.py", "file2.rs"]

    @patch("workers.llm.subprocess.run")
    def test_no_changes(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = _has_git_changes("/fake/repo")
        assert result == []

    @patch("workers.llm.subprocess.run", side_effect=Exception("git not found"))
    def test_error_returns_empty(self, mock_run):
        result = _has_git_changes("/fake/repo")
        assert result == []


class TestHasGitCommitsSince:
    """_has_git_commits_since() checks for recent commits."""

    @patch("workers.llm.subprocess.run")
    def test_with_commits(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="abc123 First commit\ndef456 Second commit\n", returncode=0
        )
        result = _has_git_commits_since("/fake/repo")
        assert result is True

    @patch("workers.llm.subprocess.run")
    def test_no_commits(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = _has_git_commits_since("/fake/repo")
        assert result is False

    @patch("workers.llm.subprocess.run", side_effect=Exception("error"))
    def test_error_returns_false(self, mock_run):
        result = _has_git_commits_since("/fake/repo")
        assert result is False


class TestRunLlmWorker:
    """run_llm_worker() handles the full LLM workflow."""

    @pytest.fixture
    def worker_context(self, tmp_path):
        """Create a WorkerContext with a real repo_path from tmp_path."""
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir(parents=True)
        ctx = WorkerContext("task_123")
        ctx.task = {
            "id": "task_123",
            "title": "Fix auth bug",
            "repo": "test-repo",
            "description": "",
        }
        # Override repo_path to return our temp dir
        with patch.object(
            WorkerContext,
            "repo_path",
            new_callable=PropertyMock,
            return_value=str(repo_dir),
        ):
            yield ctx

    @patch("workers.llm._has_git_changes", return_value=["file1.py"])
    @patch("workers.llm.subprocess.Popen")
    def test_worker_done_marker(self, mock_popen, mock_git_changes, worker_context):
        """WORKER_DONE marker leads to completion."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I fixed the bug.\nWORKER_DONE: Fixed authentication bug",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True
        assert "Fixed authentication bug" in message

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.llm.subprocess.Popen")
    def test_worker_blocked_marker(self, mock_popen, mock_git_changes, worker_context):
        """WORKER_BLOCKED marker leads to blocked."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I cannot complete this.\nWORKER_BLOCKED: Missing API key",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "Missing API key" in message

    @patch("workers.llm._has_git_changes", side_effect=[["file1.py"], ["file1.py", "file2.rs"]])
    @patch("workers.llm.subprocess.Popen")
    def test_completion_indicator_with_changes(self, mock_popen, mock_git_changes, worker_context):
        """'task is complete' indicator with file changes = success."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I have made changes. The task is complete.",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True
        assert "file(s) changed" in message

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.base.WorkerContext.add_log")  # Prevent real API calls
    @patch("workers.llm.subprocess.Popen")
    def test_already_done_no_changes(
        self,
        mock_popen,
        mock_add_log,
        mock_git_changes,
        worker_context,
    ):
        """'task is complete' + 'already implemented' = success (no work needed)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "The task is complete. The feature was already implemented. Nothing to do.",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True
        assert "already satisfied" in message

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.llm.subprocess.Popen")
    def test_blocked_indicator(self, mock_popen, mock_git_changes, worker_context):
        """'I cannot' indicator leads to blocked."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I cannot complete this task because the API is unavailable.",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "LLM blocked" in message

    @patch("workers.llm.subprocess.Popen")
    def test_timeout(self, mock_popen, worker_context):
        """LLM timeout returns blocked."""
        from subprocess import TimeoutExpired

        mock_proc = MagicMock()
        # Only raise on first call, return empty bytes on second (cleanup)
        mock_proc.communicate.side_effect = [
            TimeoutExpired("hermes", 3600),
            (b"", b""),
        ]
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        # Also patch add_log to prevent real API calls to running server
        with patch("workers.base.WorkerContext.add_log"):
            success, message = run_llm_worker(worker_context)
        assert success is False
        assert "timed out" in message

    @patch("workers.llm.subprocess.Popen")
    def test_command_not_found(self, mock_popen, worker_context):
        """FileNotFoundError returns blocked."""
        mock_popen.side_effect = FileNotFoundError("hermes not found")

        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "not found" in message

    def test_no_repo_path(self):
        """Missing repo returns blocked."""
        ctx = WorkerContext("task_123")
        ctx.task = {"id": "task_123", "title": "Task", "repo": "nonexistent-repo"}
        success, message = run_llm_worker(ctx)
        assert success is False
        assert "Repo directory not found" in message

    # ── Additional coverage for uncovered lines ────────────────────────

    @patch("workers.llm._has_git_changes", side_effect=[[], ["file1.py"]])
    @patch("workers.llm.subprocess.Popen")
    def test_worker_done_marker_with_new_changes(
        self, mock_popen, mock_git_changes, worker_context
    ):
        """WORKER_DONE with new changes returns changes count (line 176)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I fixed the bug.\nWORKER_DONE: Fixed authentication bug",
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True
        assert "file(s) changed" in message

    @patch("workers.llm.subprocess.Popen")
    def test_os_error(self, mock_popen, worker_context):
        """OSError should return blocked (lines 160-161)."""
        mock_popen.side_effect = OSError("Permission denied")
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "Failed to run" in message

    @patch("workers.llm.subprocess.Popen")
    def test_generic_exception(self, mock_popen, worker_context):
        """Generic Exception should return blocked (lines 162-163)."""
        mock_popen.side_effect = RuntimeError("Unexpected error")
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "LLM worker error" in message

    @patch("workers.llm._has_git_changes", side_effect=[[], ["file1.py"]])
    @patch("workers.llm.subprocess.Popen")
    def test_fallback_meaningful_with_changes(
        self, mock_popen, mock_git_changes, worker_context
    ):
        """Fallback: meaningful output + new changes → success (lines 238-239)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I have done some work on the task. " * 10,
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.llm.subprocess.Popen")
    def test_fallback_not_meaningful_no_changes(
        self, mock_popen, mock_git_changes, worker_context
    ):
        """Fallback: empty output + no changes → blocked (lines 240-241)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("", "")
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "empty/trivial" in message

    @patch("workers.llm._has_git_changes", side_effect=[[], ["file1.py"]])
    @patch("workers.llm.subprocess.Popen")
    def test_fallback_not_meaningful_with_changes(
        self, mock_popen, mock_git_changes, worker_context
    ):
        """Fallback: minimal output + changes detected → success (lines 242-243)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = ("done", "")
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is True
        assert "Changes detected" in message

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.llm.subprocess.Popen")
    def test_fallback_stderr_present(self, mock_popen, mock_git_changes, worker_context):
        """Fallback: meaningful output, no changes, stderr present → blocked with stderr (lines 248-249)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I have done some work but I'm not sure if it's complete. "
            "Let me check if everything works. " * 2,
            "error: something went wrong",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "stderr" in message

    @patch("workers.llm._has_git_changes", return_value=[])
    @patch("workers.llm.subprocess.Popen")
    def test_fallback_no_stderr(self, mock_popen, mock_git_changes, worker_context):
        """Fallback: meaningful output, no changes, no stderr → default message (line 250)."""
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            "I have done some work but I'm not sure if it's complete. "
            "Let me check if everything works. " * 2,
            "",
        )
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        success, message = run_llm_worker(worker_context)
        assert success is False
        assert "did not report" in message
