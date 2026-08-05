"""Tests for auto_star module — GitHub auto-star on first install.

Covers the guard clauses (no token, no repo, marker present, invalid
repo format), identity checks (owner skips, unverifiable user skips),
star check (already starred skips), and the star action (success and
failure). All GitHub I/O is mocked — no network in tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auto_star import (
    DEFAULT_MARKER_DIR,
    _detect_repo_from_git,
    _marker_exists,
    _marker_path,
    _resolve_repo,
    _write_marker,
    maybe_auto_star,
)


@pytest.fixture(autouse=True)
def _clean_marker(tmp_path, monkeypatch):
    """Redirect the marker to a temp dir and clear it before each test."""
    monkeypatch.setattr("auto_star.DEFAULT_MARKER_DIR", str(tmp_path))
    yield
    # Clean up any marker created during the test
    import os

    if os.path.exists(_marker_path()):
        os.remove(_marker_path())


@pytest.fixture(autouse=True)
def _no_git_detection(monkeypatch):
    """Default: disable git-origin repo detection so tests are hermetic."""
    monkeypatch.setattr("auto_star._detect_repo_from_git", lambda: None)


def _resp(status: int, json_body: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_body or {}
    r.text = ""
    return r


class TestMarker:
    def test_marker_path_uses_default_dir(self, tmp_path):
        assert _marker_path().startswith(str(tmp_path))

    def test_marker_exists_false_when_absent(self):
        assert _marker_exists() is False

    def test_write_marker_then_exists(self):
        _write_marker()
        assert _marker_exists() is True


class TestGuardClauses:
    @pytest.mark.asyncio
    async def test_no_token_skips(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = ""
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            result = await maybe_auto_star()
        assert result is False
        # No marker written — a later config add should still work
        assert _marker_exists() is False

    @pytest.mark.asyncio
    async def test_disabled_skips(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = False
            with patch.object(auto_star_module(), "_get_authenticated_user") as get_user:
                result = await maybe_auto_star()
                get_user.assert_not_called()
        assert result is False
        assert _marker_exists() is False

    @pytest.mark.asyncio
    async def test_no_repo_skips(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = ""
            ms.auto_star_enabled = True
            result = await maybe_auto_star()
        assert result is False
        assert _marker_exists() is False

    @pytest.mark.asyncio
    async def test_invalid_repo_format_skips(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "not-a-repo-path"
            ms.auto_star_enabled = True
            result = await maybe_auto_star()
        assert result is False
        assert _marker_exists() is False

    @pytest.mark.asyncio
    async def test_marker_present_skips(self):
        _write_marker()
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            with patch.object(auto_star_module(), "_get_authenticated_user") as get_user:
                result = await maybe_auto_star()
                get_user.assert_not_called()
        assert result is False


def auto_star_module():
    import auto_star

    return auto_star


class TestIdentityChecks:
    @pytest.mark.asyncio
    async def test_owner_skips_and_marks(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "octocat/hello-world"
            ms.auto_star_enabled = True
            with patch.object(
                auto_star_module(), "_get_authenticated_user", new=AsyncMock(return_value="OCTOCAT")
            ):
                with patch.object(auto_star_module(), "_is_starred") as is_starred:
                    result = await maybe_auto_star()
                    is_starred.assert_not_called()
        assert result is False
        assert _marker_exists() is True  # never re-check on restart

    @pytest.mark.asyncio
    async def test_unverifiable_user_skips_and_marks(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_bad"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            with patch.object(
                auto_star_module(), "_get_authenticated_user", new=AsyncMock(return_value=None)
            ):
                with patch.object(auto_star_module(), "_star") as star:
                    result = await maybe_auto_star()
                    star.assert_not_called()
        assert result is False
        assert _marker_exists() is True  # don't retry with a bad token forever


class TestStarCheck:
    @pytest.mark.asyncio
    async def test_already_starred_returns_true_and_marks(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            with patch.object(
                auto_star_module(), "_get_authenticated_user", new=AsyncMock(return_value="someone")
            ):
                with patch.object(
                    auto_star_module(), "_is_starred", new=AsyncMock(return_value=True)
                ):
                    with patch.object(auto_star_module(), "_star") as star:
                        result = await maybe_auto_star()
                        star.assert_not_called()
        assert result is True  # the goal (starred) is already satisfied
        assert _marker_exists() is True


class TestStarAction:
    @pytest.mark.asyncio
    async def test_star_success(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            with patch.object(
                auto_star_module(), "_get_authenticated_user", new=AsyncMock(return_value="someone")
            ):
                with patch.object(
                    auto_star_module(), "_is_starred", new=AsyncMock(return_value=False)
                ):
                    with patch.object(auto_star_module(), "_star", new=AsyncMock(return_value=True)) as star:
                        result = await maybe_auto_star()
                        star.assert_called_once_with("ghp_xxx", "owner", "repo")
        assert result is True
        assert _marker_exists() is True

    @pytest.mark.asyncio
    async def test_star_failure_returns_false_but_marks(self):
        with patch("auto_star.settings") as ms:
            ms.github_token = "ghp_xxx"
            ms.github_default_repo = "owner/repo"
            ms.auto_star_enabled = True
            with patch.object(
                auto_star_module(), "_get_authenticated_user", new=AsyncMock(return_value="someone")
            ):
                with patch.object(
                    auto_star_module(), "_is_starred", new=AsyncMock(return_value=False)
                ):
                    with patch.object(
                        auto_star_module(), "_star", new=AsyncMock(return_value=False)
                    ) as star:
                        result = await maybe_auto_star()
                        star.assert_called_once()
        assert result is False
        assert _marker_exists() is True  # don't retry a failed star on every restart


class TestLowLevelHelpers:
    @pytest.mark.asyncio
    async def test_get_authenticated_user_success(self):
        from auto_star import _get_authenticated_user

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(200, {"login": "octocat"}))):
            assert await _get_authenticated_user("tok") == "octocat"

    @pytest.mark.asyncio
    async def test_get_authenticated_user_failure_returns_none(self):
        from auto_star import _get_authenticated_user

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(401))):
            assert await _get_authenticated_user("bad") is None

    @pytest.mark.asyncio
    async def test_is_starred_204(self):
        from auto_star import _is_starred

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(204))):
            assert await _is_starred("tok", "owner", "repo") is True

    @pytest.mark.asyncio
    async def test_is_starred_404(self):
        from auto_star import _is_starred

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(404))):
            assert await _is_starred("tok", "owner", "repo") is False

    @pytest.mark.asyncio
    async def test_star_204(self):
        from auto_star import _star

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(204))):
            assert await _star("tok", "owner", "repo") is True

    @pytest.mark.asyncio
    async def test_star_error(self):
        from auto_star import _star

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(return_value=_resp(403))):
            assert await _star("tok", "owner", "repo") is False

    @pytest.mark.asyncio
    async def test_star_exception_returns_false(self):
        from auto_star import _star

        async def boom(method, url, token):
            raise RuntimeError("network down")

        with patch.object(auto_star_module(), "_gh", new=AsyncMock(side_effect=boom)):
            assert await _star("tok", "owner", "repo") is False


class TestRepoDetection:
    def test_resolve_repo_prefers_git_over_config(self):
        with patch("auto_star.settings") as ms:
            ms.github_default_repo = "config/other"  # issue-sync target, wrong repo
            with patch.object(
                auto_star_module(), "_detect_repo_from_git", return_value="git/actual"
            ):
                assert _resolve_repo() == "git/actual"

    def test_resolve_repo_falls_back_to_config(self):
        with patch("auto_star.settings") as ms:
            ms.github_default_repo = "config/fallback"
            with patch.object(auto_star_module(), "_detect_repo_from_git", return_value=None):
                assert _resolve_repo() == "config/fallback"

    def test_resolve_repo_empty(self):
        with patch("auto_star.settings") as ms:
            ms.github_default_repo = ""
            with patch.object(auto_star_module(), "_detect_repo_from_git", return_value=None):
                assert _resolve_repo() == ""

    def test_detect_repo_https(self):
        with patch("subprocess.run") as run:
            out = MagicMock()
            out.stdout = "https://github.com/omiinaya/spacetime-kanban.git\n"
            run.return_value = out
            assert _detect_repo_from_git() == "omiinaya/spacetime-kanban"

    def test_detect_repo_ssh(self):
        with patch("subprocess.run") as run:
            out = MagicMock()
            out.stdout = "git@github.com:omiinaya/spacetime-kanban.git\n"
            run.return_value = out
            assert _detect_repo_from_git() == "omiinaya/spacetime-kanban"

    def test_detect_repo_gitlab_ignored(self):
        with patch("subprocess.run") as run:
            out = MagicMock()
            out.stdout = "https://gitlab.com/other/project.git\n"
            run.return_value = out
            assert _detect_repo_from_git() is None

    def test_detect_repo_no_output(self):
        with patch("subprocess.run") as run:
            out = MagicMock()
            out.stdout = ""
            run.return_value = out
            assert _detect_repo_from_git() is None

    def test_detect_repo_exception(self):
        with patch("subprocess.run", side_effect=RuntimeError("git missing")):
            assert _detect_repo_from_git() is None
