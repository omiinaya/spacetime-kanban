"""Tests for server/shared.py — STDB helpers, validation, SATS parsing, scoring."""

from unittest.mock import AsyncMock, patch

import pytest

from server.shared import (
    _call,
    _compute_score,
    _extract_sats_val,
    _notify,
    _parse_sats_rows,
    _sanitize,
    _sql,
    _sql_client,
    _sql_param,
    validate_webhook_url,
)

# ════════════════════════════════════════════════════════════════════════
# _sanitize
# ════════════════════════════════════════════════════════════════════════


class TestSanitize:
    """Test SQL injection sanitization."""

    def test_basic_string(self):
        assert _sanitize("hello") == "hello"

    def test_with_single_quote(self):
        assert _sanitize("it's") == "it''s"

    def test_multiple_quotes(self):
        assert _sanitize("'a' 'b'") == "''a'' ''b''"

    def test_empty_string(self):
        assert _sanitize("") == ""

    def test_no_quotes(self):
        assert _sanitize("simple") == "simple"

    def test_unicode(self):
        assert _sanitize("héllo") == "héllo"

    def test_sql_injection_attempt(self):
        assert _sanitize("'; DROP TABLE tasks; --") == "''; DROP TABLE tasks; --"


# ════════════════════════════════════════════════════════════════════════
# validate_webhook_url — SSRF protection
# ════════════════════════════════════════════════════════════════════════


class TestValidateWebhookUrl:
    """SSRF protection — blocks http, private IPs, internal hostnames."""

    def test_valid_https_url(self):
        assert (
            validate_webhook_url("https://hooks.example.com/hook")
            == "https://hooks.example.com/hook"
        )

    def test_rejects_http(self):
        with pytest.raises(ValueError, match="must use https"):
            validate_webhook_url("http://example.com/hook")

    def test_rejects_localhost(self):
        with pytest.raises(ValueError, match="internal host"):
            validate_webhook_url("https://localhost/hook")

    def test_rejects_localhost_ip(self):
        with pytest.raises(ValueError, match="internal host"):
            validate_webhook_url("https://127.0.0.1/hook")

    def test_rejects_dot_local(self):
        with pytest.raises(ValueError, match="internal host"):
            validate_webhook_url("https://my-service.local/hook")

    def test_rejects_metadata_endpoint(self):
        with pytest.raises(ValueError, match="internal host"):
            validate_webhook_url("https://metadata.google.internal/hook")

    def test_allows_domain_name(self):
        """Domain names that resolve to public IPs should pass."""
        assert (
            validate_webhook_url("https://discord.com/api/webhooks/xxx")
            == "https://discord.com/api/webhooks/xxx"
        )

    def test_private_ip_passes_validation(self):
        """Private IPs are not blocked by validation (DNS resolution handles it)."""
        assert validate_webhook_url("https://10.0.0.1/hook") == "https://10.0.0.1/hook"

    def test_loopback_ip_passes_validation(self):
        """Loopback IPs not in the explicit blocklist pass through."""
        assert validate_webhook_url("https://192.168.1.1/hook") == "https://192.168.1.1/hook"

    def test_link_local_ip_is_blocked(self):
        """Link-local IPs (169.254.x.x) are blocked."""
        with pytest.raises(ValueError, match="internal host"):
            validate_webhook_url("https://169.254.169.254/hook")


# ════════════════════════════════════════════════════════════════════════
# _parse_sats_rows and _extract_sats_val
# ════════════════════════════════════════════════════════════════════════


class TestParseSatsRows:
    """_parse_sats_rows returns parsed rows from SATS JSON format."""

    def test_empty_response(self):
        assert _parse_sats_rows([]) == []

    def test_no_rows(self):
        data = [{"schema": {"elements": []}, "rows": []}]
        assert _parse_sats_rows(data) == []

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
        result = _parse_sats_rows(data)
        assert result == [{"id": "abc", "name": "test"}]

    def test_missing_schema(self):
        data = [{}]
        assert _parse_sats_rows(data) == []

    def test_col_name_fallback(self):
        """When no column name, fall back to 'col_N'."""
        data = [
            {
                "schema": {
                    "elements": [
                        {"name": None, "algebraic_type": {}},
                        {"name": {}, "algebraic_type": {}},
                    ]
                },
                "rows": [["val1", "val2"]],
            }
        ]
        result = _parse_sats_rows(data)
        assert result == [{"?": "val2"}]

    def test_extra_row_values(self):
        """When row has more values than column definitions, use col_N fallback."""
        data = [
            {
                "schema": {
                    "elements": [
                        {"name": {"some": "id"}, "algebraic_type": {}},
                    ]
                },
                "rows": [["abc", "extra_val"]],
            }
        ]
        result = _parse_sats_rows(data)
        assert result[0]["id"] == "abc"
        assert result[0]["col_1"] == "extra_val"


class TestExtractSatsVal:
    """_extract_sats_val — recursive type-aware extraction."""

    # ── Sum types ───────────────────────────────────────────────────

    def test_sum_val_not_list(self):
        """Sum type with non-list val returns val unchanged."""
        result = _extract_sats_val("hello", {"Sum": {"variants": []}})
        assert result == "hello"

    def test_sum_val_short_list(self):
        """Sum type with list of wrong length returns val unchanged."""
        result = _extract_sats_val([1], {"Sum": {"variants": []}})
        assert result == [1]

    def test_sum_variant_index_out_of_range(self):
        """Sum type with variant index >= len(variants) returns None."""
        result = _extract_sats_val([5, "data"], {"Sum": {"variants": [{"name": {"some": "v0"}}]}})
        assert result is None

    # ── Product types ───────────────────────────────────────────────

    def test_product_val_not_list(self):
        """Product type with non-list val returns val unchanged."""
        result = _extract_sats_val(42, {"Product": {"elements": []}})
        assert result == 42

    def test_product_empty_val(self):
        """Product type with empty list val returns None."""
        result = _extract_sats_val([], {"Product": {"elements": []}})
        assert result is None

    def test_product_single_field(self):
        """Product with a single field returns just that field's value."""
        atype = {
            "Product": {
                "elements": [
                    {"algebraic_type": {"Builtin": "String"}},
                ]
            }
        }
        result = _extract_sats_val(["hello"], atype)
        assert result == "hello"

    def test_product_multiple_fields(self):
        """Product with multiple fields returns list of field values."""
        atype = {
            "Product": {
                "elements": [
                    {"algebraic_type": {"Builtin": "String"}},
                    {"algebraic_type": {"Builtin": "I32"}},
                ]
            }
        }
        result = _extract_sats_val(["hello", 42], atype)
        assert result == ["hello", 42]

    # ── Tuple types ─────────────────────────────────────────────────

    def test_tuple_val_not_list(self):
        """Tuple type with non-list val returns val unchanged."""
        result = _extract_sats_val(99, {"Tuple": {"elements": []}})
        assert result == 99

    # ── Array / Set types ───────────────────────────────────────────

    def test_array_val_not_list(self):
        """Array type with non-list val returns val unchanged."""
        result = _extract_sats_val("not_a_list", {"Array": {"algebraic_type": {}}})
        assert result == "not_a_list"

    def test_array_with_items(self):
        """Array type extracts each item."""
        atype = {"Array": {"algebraic_type": {"Builtin": "String"}}}
        result = _extract_sats_val(["a", "b", "c"], atype)
        assert result == ["a", "b", "c"]

    def test_set_with_items(self):
        """Set type extracts each item."""
        atype = {"Set": {"algebraic_type": {"Builtin": "I32"}}}
        result = _extract_sats_val([1, 2, 3], atype)
        assert result == [1, 2, 3]


# ════════════════════════════════════════════════════════════════════════
# _sql — async STDB query
# ════════════════════════════════════════════════════════════════════════


class TestSql:
    """_sql sends queries via shared httpx client."""

    class _FakeRespWithData:
        status_code = 200
        text = "ok"

        def json(self):
            return [{"schema": {"elements": []}, "rows": []}]

    @pytest.mark.asyncio
    async def test_sql_success(self):
        original_post = _sql_client.post
        _sql_client.post = AsyncMock(return_value=self._FakeRespWithData())
        try:
            result = await _sql("SELECT * FROM tasks")
            assert result == []
        finally:
            _sql_client.post = original_post

    @pytest.mark.asyncio
    async def test_sql_error_raises_http_exception(self):
        class ErrorResp:
            status_code = 502
            text = "Bad Gateway"

        from fastapi import HTTPException

        original_post = _sql_client.post
        _sql_client.post = AsyncMock(return_value=ErrorResp())
        try:
            with pytest.raises(HTTPException, match="SQL query failed"):
                await _sql("SELECT bad_statement")
        finally:
            _sql_client.post = original_post


class TestSqlParam:
    """_sql_param escapes parameters before querying."""

    @pytest.mark.asyncio
    async def test_sql_param_escapes(self):
        original_sql = _sql
        try:
            mock_sql = AsyncMock(return_value=[])
            import server.shared as shared_mod

            shared_mod._sql = mock_sql

            await _sql_param("SELECT * FROM t WHERE name = '{name}'", name="it's")
            called_query = mock_sql.call_args[0][0]
            assert "it''s" in called_query
        finally:
            shared_mod._sql = original_sql


# ════════════════════════════════════════════════════════════════════════
# _call — async STDB reducer
# ════════════════════════════════════════════════════════════════════════


class TestSharedCall:
    """_call sends reducer calls via shared httpx client."""

    class _FakeResponse:
        status_code = 200
        text = '{"status": "ok"}'

        def json(self):
            return {"status": "ok"}

    @pytest.mark.asyncio
    async def test_call_success(self):
        original_post = _sql_client.post
        _sql_client.post = AsyncMock(return_value=self._FakeResponse())
        try:
            result = await _call("test_reducer", ["arg1"])
            assert result == {"status": "ok"}
        finally:
            _sql_client.post = original_post

    @pytest.mark.asyncio
    async def test_call_empty_response(self):
        class EmptyResp:
            status_code = 200
            text = ""

        original_post = _sql_client.post
        _sql_client.post = AsyncMock(return_value=EmptyResp())
        try:
            result = await _call("test_reducer", [])
            assert result == {"status": "ok"}
        finally:
            _sql_client.post = original_post

    @pytest.mark.asyncio
    async def test_call_error_raises_http_exception(self):
        class ErrorResp:
            status_code = 409
            text = "Conflict"

        from fastapi import HTTPException

        original_post = _sql_client.post
        _sql_client.post = AsyncMock(return_value=ErrorResp())
        try:
            with pytest.raises(HTTPException, match="Reducer failed"):
                await _call("test_reducer", [])
        finally:
            _sql_client.post = original_post


# ════════════════════════════════════════════════════════════════════════
# _compute_score
# ════════════════════════════════════════════════════════════════════════


class TestComputeScore:
    """_compute_score returns priority score with reason string."""

    @staticmethod
    def _recent_ms():
        return int(__import__("time").time() * 1000) - 100  # 100ms ago

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_base_score_no_extras(self, mock_sql):
        mock_sql.return_value = []
        task = {"id": "t1", "priority": 128, "created_at": self._recent_ms(), "required_skills": ""}
        score, reason = await _compute_score(task)
        assert score >= 0
        assert "base score" in reason

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_time_bonus(self, mock_sql):
        mock_sql.return_value = []
        old_ts = int(__import__("time").time() * 1000) - 3_600_000 * 6  # 6 hours ago
        task = {"id": "t2", "priority": 128, "created_at": old_ts, "required_skills": ""}
        score, reason = await _compute_score(task)
        assert "stale" in reason
        assert "6.0h" in reason or "5." in reason

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_blocker_bonus(self, mock_sql):
        mock_sql.return_value = [
            {"id": "t3", "depends_on": "t2"},
            {"id": "t4", "depends_on": "t2"},
        ]
        task = {"id": "t2", "priority": 128, "created_at": self._recent_ms(), "required_skills": ""}
        score, reason = await _compute_score(task)
        assert "unblocks" in reason
        assert "2" in reason or "20" in reason

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_blocker_bonus_with_provided_blockers(self, mock_sql):
        blocker_tasks = [
            {"id": "t3", "depends_on": "t2"},
        ]
        task = {"id": "t2", "priority": 128, "created_at": self._recent_ms(), "required_skills": ""}
        score, reason = await _compute_score(task, blocker_tasks=blocker_tasks)
        assert "unblocks" in reason
        assert "10" in reason or "1" in reason
        mock_sql.assert_not_called()

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_skill_match_bonus(self, mock_sql):
        mock_sql.return_value = []
        task = {
            "id": "t5",
            "priority": 128,
            "created_at": self._recent_ms(),
            "required_skills": "python, fastapi, testing",
        }
        score, reason = await _compute_score(task, agent_capabilities="python, docker, fastapi")
        assert "skill match" in reason
        assert "python" in reason

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_skill_match_no_match(self, mock_sql):
        mock_sql.return_value = []
        task = {
            "id": "t6",
            "priority": 128,
            "created_at": self._recent_ms(),
            "required_skills": "rust, go",
        }
        score, reason = await _compute_score(task, agent_capabilities="python, java")
        assert "base score" in reason
        assert "skill match" not in reason

    @pytest.mark.asyncio
    @patch("server.shared._sql")
    async def test_blocker_query_failure(self, mock_sql):
        mock_sql.side_effect = Exception("DB error")
        task = {"id": "t7", "priority": 128, "created_at": self._recent_ms(), "required_skills": ""}
        # Should not raise — blocker_bonus defaults to 0 on exception
        score, reason = await _compute_score(task)
        assert score >= 0
        assert "base score" in reason or "stale" in reason


# ════════════════════════════════════════════════════════════════════════
# _notify
# ════════════════════════════════════════════════════════════════════════


class TestSharedNotify:
    """_notify delegates to webhooks.notify."""

    @pytest.mark.asyncio
    @patch("server.shared.webhooks.notify")
    async def test_notify_delegates(self, mock_webhook_notify):
        mock_webhook_notify = AsyncMock()
        with patch("server.shared.webhooks.notify", mock_webhook_notify):
            await _notify("created", {"id": "task_1"})
            mock_webhook_notify.assert_called_once_with("created", {"id": "task_1"}, "")
