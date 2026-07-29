"""Tests for issue_sync module — STDB helpers, mapping API, error handling."""

from unittest.mock import MagicMock, patch

import pytest

from issue_sync import (
    _call,
    _parse_rows,
    _sanitize,
    _stdb_sql,
    get_link,
    get_task_id_for_issue,
    link_issue,
    list_links,
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
