"""Tests for issue_sync module — STDB helpers, mapping API, error handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from issue_sync import (
    GH_API_MAX_RETRIES,
    _call,
    _gh_headers,
    _gh_request,
    _parse_rows,
    _sanitize,
    _stdb_sql,
    add_issue_comment,
    close_issue,
    create_issue,
    find_existing_issue,
    get_issue,
    get_issue_comments,
    get_link,
    get_task_id_for_issue,
    link_issue,
    list_links,
    reopen_issue,
    search_issues,
    unlink_issue,
    update_issue_status,
)

# ── _sanitize ──────────────────────────────────────────────────────────


class TestSanitize:
    def test_normal_string(self):
        assert _sanitize("hello") == "hello"

    def test_single_quote_escaped(self):
        assert _sanitize("it's") == "it''s"
        assert _sanitize("'") == "''"
        assert _sanitize("a'b'c") == "a''b''c"

    def test_multiple_quotes(self):
        assert _sanitize("'''") == "''''''"

    def test_empty_string(self):
        assert _sanitize("") == ""

    def test_numeric_string(self):
        assert _sanitize("123") == "123"

    def test_special_chars_preserved(self):
        assert _sanitize("test@#$%") == "test@#$%"


# ── _parse_rows ────────────────────────────────────────────────────────


class TestParseRows:
    def test_empty_response(self):
        assert _parse_rows([]) == []

    def test_no_rows(self):
        data = [{"schema": {"elements": []}, "rows": []}]
        assert _parse_rows(data) == []

    def test_simple_row(self):
        data = [
            {
                "schema": {
                    "elements": [
                        {"name": {"some": "id"}, "algebraic_type": {}},
                        {"name": {"some": "name"}, "algebraic_type": {}},
                    ]
                },
                "rows": [["abc", "test"]],
            }
        ]
        result = _parse_rows(data)
        assert len(result) == 1
        assert result[0]["id"] == "abc"
        assert result[0]["name"] == "test"

    def test_missing_schema(self):
        data = [{}]
        assert _parse_rows(data) == []


# ── _stdb_sql ──────────────────────────────────────────────────────────


class TestStdbSql:
    @patch("httpx.post")
    def test_successful_query(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"schema": {"elements": []}, "rows": []}]
        mock_resp.text = "ok"
        mock_post.return_value = mock_resp

        result = _stdb_sql("SELECT 1")
        assert result == []

    @patch("httpx.post")
    def test_error_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Syntax error"
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="SQL query failed"):
            _stdb_sql("BAD SQL")


# ── _call ──────────────────────────────────────────────────────────────


class TestCall:
    @patch("httpx.post")
    def test_successful_call(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "ok"}'
        mock_resp.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_resp

        result = _call("test_reducer", ["arg1"])
        assert result == {"status": "ok"}

    @patch("httpx.post")
    def test_empty_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_resp.json.side_effect = ValueError
        mock_post.return_value = mock_resp

        result = _call("test_reducer", [])
        assert result == {"status": "ok"}

    @patch("httpx.post")
    def test_error_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="Reducer failed"):
            _call("test_reducer", [])


# ── Mapping API (with mocked HTTP) ─────────────────────────────────────


class TestGetMapping:
    @patch("issue_sync._sql_param")
    def test_get_link_found(self, mock_sql_param):
        mock_sql_param.return_value = [
            {
                "issue_number": 42,
                "repo": "owner/repo",
                "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
                "html_url": "https://github.com/owner/repo/issues/42",
                "status": "open",
                "linked_at": 1000,
            }
        ]
        result = get_link("task_1")
        assert result is not None
        assert result["issue_number"] == 42
        assert result["repo"] == "owner/repo"
        assert result["status"] == "open"

    @patch("issue_sync._sql_param")
    def test_get_link_not_found(self, mock_sql_param):
        mock_sql_param.return_value = []
        result = get_link("task_1")
        assert result is None

    @patch("issue_sync._sql_param")
    def test_get_task_id_for_issue_found(self, mock_sql_param):
        mock_sql_param.return_value = [{"kanban_task_id": "task_1"}]
        result = get_task_id_for_issue("owner/repo", 42)
        assert result == "task_1"

    @patch("issue_sync._sql_param")
    def test_get_task_id_for_issue_not_found(self, mock_sql_param):
        mock_sql_param.return_value = []
        result = get_task_id_for_issue("owner/repo", 42)
        assert result is None


class TestLinkIssue:
    @patch("issue_sync._call")
    @patch("issue_sync.get_link")
    def test_link_issue_success(self, mock_get_link, mock_call):
        mock_get_link.return_value = {
            "issue_number": 42,
            "repo": "owner/repo",
            "issue_url": "https://api.github.com/repos/owner/repo/issues/42",
            "html_url": "https://github.com/owner/repo/issues/42",
            "status": "open",
            "linked_at": 1000,
        }
        result = link_issue("task_1", "owner/repo", 42, "api_url", "html_url")
        mock_call.assert_called_once_with(
            "link_issue",
            ["task_1", 42, "owner/repo", "api_url", "html_url"],
        )
        assert result["issue_number"] == 42

    @patch("issue_sync._call")
    @patch("issue_sync.get_link")
    def test_link_issue_fallback(self, mock_get_link, mock_call):
        mock_get_link.return_value = None
        result = link_issue("task_1", "owner/repo", 42, "api_url", "html_url")
        assert result["issue_number"] == 42
        assert result["status"] == "open"


class TestUnlinkUpdate:
    @patch("issue_sync._call")
    def test_unlink_issue_success(self, mock_call):
        mock_call.return_value = {"status": "ok"}
        result = unlink_issue("task_1")
        assert result is True

    @patch("issue_sync._call")
    def test_unlink_issue_not_found(self, mock_call):
        mock_call.side_effect = RuntimeError("not found")
        result = unlink_issue("task_1")
        assert result is False

    @patch("issue_sync._call")
    def test_unlink_issue_other_error(self, mock_call):
        mock_call.side_effect = RuntimeError("database error")
        with pytest.raises(RuntimeError):
            unlink_issue("task_1")

    @patch("issue_sync._call")
    @patch("issue_sync.get_link")
    def test_update_status_success(self, mock_get_link, mock_call):
        mock_get_link.return_value = {"status": "closed"}
        result = update_issue_status("task_1", "closed")
        assert result["status"] == "closed"

    @patch("issue_sync._call")
    def test_update_status_not_found(self, mock_call):
        mock_call.side_effect = RuntimeError("not found")
        result = update_issue_status("task_1", "closed")
        assert result is None


class TestListLinks:
    @patch("issue_sync._sql_param")
    def test_list_links_with_repo(self, mock_sql_param):
        mock_sql_param.return_value = [
            {
                "kanban_task_id": "task_1",
                "issue_number": 42,
                "linked_at": 1000,
            }
        ]
        result = list_links(repo="owner/repo")
        assert len(result) == 1
        assert result[0]["kanban_task_id"] == "task_1"
        mock_sql_param.assert_called_once()

    @patch("issue_sync._stdb_sql")
    def test_list_links_all(self, mock_stdb_sql):
        mock_stdb_sql.return_value = []
        result = list_links()
        assert result == []
        mock_stdb_sql.assert_called_once_with("SELECT * FROM issue_links")


# ════════════════════════════════════════════════════════════════════════
# Async GitHub API tests
# ════════════════════════════════════════════════════════════════════════


class TestUpdateStatusReRaise:
    """update_issue_status re-raises non-'not found' RuntimeErrors."""

    @patch("issue_sync._call")
    def test_re_raises_on_other_error(self, mock_call):
        mock_call.side_effect = RuntimeError("database error")
        with pytest.raises(RuntimeError, match="database error"):
            update_issue_status("task_1", "closed")


class TestGhHeaders:
    """_gh_headers returns dict with Bearer auth."""

    def test_returns_bearer_auth(self):
        headers = _gh_headers("my-token")
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["Accept"] == "application/vnd.github.v3+json"
        assert "User-Agent" in headers

    def test_different_tokens(self):
        headers = _gh_headers("another-token")
        assert headers["Authorization"] == "Bearer another-token"


class TestGhRequest:
    """_gh_request retry logic and error handling."""

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_successful_request(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": 1, "number": 42}'
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await _gh_request("GET", "https://api.github.com/test", "token")
        assert result == {"id": 1, "number": 42}
        mock_client.request.assert_called_once_with(
            method="GET",
            url="https://api.github.com/test",
            json=None,
            headers=mock_client.request.call_args[1]["headers"],
        )

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_retry_on_5xx_then_succeed(self, mock_client_cls):
        mock_fail = MagicMock(status_code=500, text="Server Error")
        mock_success = MagicMock(status_code=200, text='{"ok": true}')
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(side_effect=[mock_fail, mock_success])
        mock_client_cls.return_value = mock_client

        result = await _gh_request("GET", "https://api.github.com/test", "token")
        assert result == {"ok": True}
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_all_retries_exhausted(self, mock_client_cls):
        mock_resp = MagicMock(status_code=500, text="Server Error")
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="GitHub API request failed after 3 attempts"):
            await _gh_request("GET", "https://api.github.com/test", "token")
        assert mock_client.request.call_count == GH_API_MAX_RETRIES

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_handles_timeout_exception(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="GitHub API request failed after 3 attempts"):
            await _gh_request("GET", "https://api.github.com/test", "token")
        assert mock_client.request.call_count == GH_API_MAX_RETRIES

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_handles_http_status_error(self, mock_client_cls):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_response
            )
        )
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="GitHub API request failed after 3 attempts"):
            await _gh_request("GET", "https://api.github.com/test", "token")
        assert mock_client.request.call_count == GH_API_MAX_RETRIES

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_handles_generic_exception(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(side_effect=ConnectionRefusedError("Connection refused"))
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="GitHub API request failed after 3 attempts"):
            await _gh_request("GET", "https://api.github.com/test", "token")
        assert mock_client.request.call_count == GH_API_MAX_RETRIES

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_retries_then_succeeds_after_timeout(self, mock_client_cls):
        mock_success = MagicMock(status_code=200, text='{"ok": true}')
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(
            side_effect=[httpx.TimeoutException("timeout"), mock_success]
        )
        mock_client_cls.return_value = mock_client

        result = await _gh_request("GET", "https://api.github.com/test", "token")
        assert result == {"ok": True}
        assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    @patch("issue_sync.httpx.AsyncClient")
    async def test_request_with_body_sets_content_type(self, mock_client_cls):
        """_gh_request with body sets Content-Type header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"id": 1}'
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.request = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await _gh_request(
            "POST", "https://api.github.com/test/repos/issues",
            "token", body={"title": "test"},
        )
        assert result == {"id": 1}
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["json"] == {"title": "test"}
        assert "Content-Type" in call_kwargs["headers"]
        assert call_kwargs["headers"]["Content-Type"] == "application/json"


class TestSearchIssues:
    """search_issues queries GitHub issues via _gh_request."""

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_search_with_results(self, mock_gh_req):
        mock_gh_req.return_value = {
            "items": [
                {"number": 1, "title": "Fix bug", "html_url": "https://github.com/...", "state": "open"},
                {"number": 2, "title": "Add feature", "html_url": "https://github.com/...", "state": "closed"},
            ]
        }
        results = await search_issues("token", "owner/repo", "bug")
        assert len(results) == 2
        assert results[0]["number"] == 1
        assert results[0]["title"] == "Fix bug"
        assert results[0]["state"] == "open"

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_search_no_results(self, mock_gh_req):
        mock_gh_req.return_value = {"items": []}
        results = await search_issues("token", "owner/repo", "nonexistent")
        assert results == []


class TestFindExistingIssue:
    """find_existing_issue searches for kanban-linked issues."""

    @pytest.mark.asyncio
    @patch("issue_sync.search_issues")
    async def test_found(self, mock_search):
        mock_search.return_value = [
            {"number": 42, "title": "Existing issue", "html_url": "url", "state": "open"}
        ]
        result = await find_existing_issue("token", "owner/repo", "task_1")
        assert result is not None
        assert result["number"] == 42
        mock_search.assert_called_once()

    @pytest.mark.asyncio
    @patch("issue_sync.search_issues")
    async def test_not_found(self, mock_search):
        mock_search.return_value = []
        result = await find_existing_issue("token", "owner/repo", "task_1")
        assert result is None


class TestCreateIssue:
    """create_issue with dedup checking."""

    @pytest.mark.asyncio
    @patch("issue_sync.find_existing_issue")
    @patch("issue_sync._gh_request")
    async def test_returns_existing_when_found(self, mock_gh_req, mock_find):
        mock_find.return_value = {"number": 42, "html_url": "url", "state": "open"}
        result = await create_issue("token", "owner/repo", "Title", task_id="task_1")
        assert result["issue_number"] == 42
        assert result["html_url"] == "url"
        assert result["state"] == "open"
        assert "issue_url" in result
        mock_gh_req.assert_not_called()

    @pytest.mark.asyncio
    @patch("issue_sync.find_existing_issue")
    @patch("issue_sync._gh_request")
    async def test_creates_new_when_not_found(self, mock_gh_req, mock_find):
        mock_find.return_value = None
        mock_gh_req.return_value = {
            "number": 1,
            "html_url": "https://github.com/...",
            "url": "https://api.github.com/...",
            "state": "open",
        }
        result = await create_issue("token", "owner/repo", "New issue", task_id="task_1")
        assert result["issue_number"] == 1
        assert result["state"] == "open"
        mock_gh_req.assert_called_once()

    @pytest.mark.asyncio
    @patch("issue_sync.find_existing_issue")
    @patch("issue_sync._gh_request")
    async def test_creates_with_body_labels_assignee(self, mock_gh_req, mock_find):
        mock_find.return_value = None
        mock_gh_req.return_value = {
            "number": 2,
            "html_url": "url",
            "url": "api_url",
            "state": "open",
        }
        result = await create_issue(
            "token",
            "owner/repo",
            "Title",
            body="Description",
            labels=["bug"],
            assignee="user",
        )
        assert result["issue_number"] == 2
        mock_gh_req.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/owner/repo/issues",
            "token",
            {"title": "Title", "body": "Description", "labels": ["bug"], "assignees": ["user"]},
        )

    @pytest.mark.asyncio
    @patch("issue_sync.find_existing_issue")
    @patch("issue_sync._gh_request")
    async def test_creates_without_task_id(self, mock_gh_req, mock_find):
        mock_gh_req.return_value = {
            "number": 3,
            "html_url": "url",
            "url": "api_url",
            "state": "open",
        }
        result = await create_issue("token", "owner/repo", "Title")
        assert result["issue_number"] == 3
        mock_find.assert_not_called()  # dedup skipped when no task_id
        mock_gh_req.assert_called_once()


class TestCloseReopenIssue:
    """close_issue and reopen_issue call _gh_request with PATCH."""

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_close_issue(self, mock_gh_req):
        mock_gh_req.return_value = {"state": "closed"}
        result = await close_issue("token", "owner/repo", 42)
        assert result["state"] == "closed"
        mock_gh_req.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/owner/repo/issues/42",
            "token",
            {"state": "closed"},
        )

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_reopen_issue(self, mock_gh_req):
        mock_gh_req.return_value = {"state": "open"}
        result = await reopen_issue("token", "owner/repo", 42)
        assert result["state"] == "open"
        mock_gh_req.assert_called_once_with(
            "PATCH",
            "https://api.github.com/repos/owner/repo/issues/42",
            "token",
            {"state": "open"},
        )


class TestGetIssue:
    """get_issue calls _gh_request with GET."""

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_get_issue(self, mock_gh_req):
        mock_gh_req.return_value = {"number": 42, "state": "open"}
        result = await get_issue("token", "owner/repo", 42)
        assert result["number"] == 42
        mock_gh_req.assert_called_once_with(
            "GET", "https://api.github.com/repos/owner/repo/issues/42", "token"
        )


class TestGetIssueComments:
    """get_issue_comments calls _gh_request with GET and handles non-list responses."""

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_returns_list(self, mock_gh_req):
        mock_gh_req.return_value = [{"body": "First!"}, {"body": "Second"}]
        result = await get_issue_comments("token", "owner/repo", 42)
        assert len(result) == 2
        assert result[0]["body"] == "First!"
        mock_gh_req.assert_called_once_with(
            "GET",
            "https://api.github.com/repos/owner/repo/issues/42/comments",
            "token",
        )

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_returns_empty_on_non_list(self, mock_gh_req):
        mock_gh_req.return_value = {}
        result = await get_issue_comments("token", "owner/repo", 42)
        assert result == []


class TestAddIssueComment:
    """add_issue_comment calls _gh_request with POST."""

    @pytest.mark.asyncio
    @patch("issue_sync._gh_request")
    async def test_add_comment(self, mock_gh_req):
        mock_gh_req.return_value = {"id": 123, "body": "Nice work!"}
        result = await add_issue_comment("token", "owner/repo", 42, "Nice work!")
        assert result["id"] == 123
        mock_gh_req.assert_called_once_with(
            "POST",
            "https://api.github.com/repos/owner/repo/issues/42/comments",
            "token",
            {"body": "Nice work!"},
        )
