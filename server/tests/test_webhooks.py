"""Tests for server/webhooks.py — URL validation, payload formatting, CRUD."""

from unittest.mock import MagicMock, patch

import pytest

from server.webhooks import (
    _call,
    _deliver_with_retry,
    _format_discord,
    _format_generic,
    _format_payload,
    _format_slack,
    _format_telegram,
    _parse_rows,
    _sanitize,
    _sql_param,
    _stdb_sql,
    add_webhook,
    get_webhook,
    list_webhook_deliveries,
    list_webhooks,
    notify,
    remove_webhook,
    update_webhook,
)

# We need to patch validate_webhook_url since it's from shared
# and makes network-like checks
URL_VALIDATION_PATH = "shared.validate_webhook_url"


class TestWebhooks:
    """Test suite for webhooks.py — formatting, delivery, CRUD."""

    # ── _format_discord ────────────────────────────────────────────────

    def test_format_discord_created(self):
        """Discord embed for 'created' action should have proper emoji and color."""
        task = {"id": "task_1", "title": "Fix login", "repo": "my-repo", "assigned_to": None}
        payload = _format_discord("created", task)
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1
        embed = payload["embeds"][0]
        assert "Created" in embed["title"]
        assert "Fix login" in embed["title"]
        assert embed["color"] == 0x5865F2
        fields = {f["name"]: f["value"] for f in embed["fields"]}
        assert fields["Task"] == "`task_1`"
        assert fields["Repo"] == "my-repo"

    def test_format_discord_completed(self):
        """Discord embed for 'completed' should include notes."""
        task = {"id": "task_2", "title": "Deploy", "repo": "infra", "assigned_to": "bot"}
        payload = _format_discord("completed", task, extra="All good!")
        embed = payload["embeds"][0]
        assert "Completed" in embed["title"]
        assert embed["color"] == 0x57F287
        notes_field = [f for f in embed["fields"] if f["name"] == "Notes"]
        assert len(notes_field) == 1
        assert notes_field[0]["value"] == "All good!"

    def test_format_discord_blocked(self):
        """Discord embed for 'blocked' should have red color and notes."""
        task = {"id": "task_3", "title": "Fix bug", "repo": "code", "assigned_to": "dev"}
        payload = _format_discord("blocked", task, extra="Need API key")
        embed = payload["embeds"][0]
        assert embed["color"] == 0xED4245
        assert "Blocked" in embed["title"]
        notes = [f for f in embed["fields"] if f["name"] == "Notes"]
        assert len(notes) == 1
        assert "Need API key" in notes[0]["value"]

    def test_format_discord_claimed(self):
        """Discord embed for 'claimed' should include Agent field."""
        task = {"id": "task_4", "title": "Build feature", "repo": "app", "assigned_to": "worker-1"}
        payload = _format_discord("claimed", task)
        fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
        assert fields["Agent"] == "worker-1"

    def test_format_discord_unclaimed_no_agent_in_fields(self):
        """Unclaimed should show the agent in the extra but not add Agent field."""
        task = {"id": "task_5", "title": "Chore", "repo": "ops"}
        payload = _format_discord("unclaimed", task)
        field_names = [f["name"] for f in payload["embeds"][0]["fields"]]
        assert "Agent" not in field_names

    # ── _format_slack ──────────────────────────────────────────────────

    def test_format_slack_created(self):
        """Slack message for 'created' should include title and emoji."""
        task = {"id": "t1", "title": "Setup CI", "repo": "infra", "assigned_to": None}
        payload = _format_slack("created", task)
        assert ":new:" in payload["text"]
        assert "Setup CI" in payload["text"]
        assert "attachments" in payload
        fields_text = [f["text"] for f in payload["attachments"][0]["fields"]]
        assert any("t1" in f for f in fields_text)

    # ── _format_telegram ───────────────────────────────────────────────

    def test_format_telegram_completed(self):
        """Telegram message for 'completed' should include notes."""
        task = {"id": "t2", "title": "Release v2", "repo": "app", "assigned_to": "bot"}
        payload = _format_telegram("completed", task, extra="Shipped!")
        assert "Completed" in payload["text"]
        assert "Release v2" in payload["text"]
        assert "Shipped!" in payload["text"]
        assert "parse_mode" in payload
        assert payload["parse_mode"] == "Markdown"

    # ── _format_generic ────────────────────────────────────────────────

    def test_format_generic_contains_event_and_task(self):
        """Generic format should include event name and task details."""
        task = {
            "id": "task_x",
            "title": "Refactor",
            "status": "available",
            "priority": 1,
            "repo": "my-repo",
            "assigned_to": None,
            "score": 50,
        }
        payload = _format_generic("created", task, extra="")
        assert payload["event"] == "created"
        assert payload["task"]["id"] == "task_x"
        assert payload["task"]["title"] == "Refactor"
        assert payload["task"]["status"] == "available"
        assert payload["task"]["priority"] == 1
        assert payload["task"]["score"] == 50
        assert payload["extra"] is None  # empty extra → None

    def test_format_generic_includes_extra(self):
        """Generic format should include extra when provided."""
        task = {
            "id": "t3",
            "title": "Fix",
            "status": "blocked",
            "priority": 0,
            "repo": "r",
            "assigned_to": "user",
            "score": 100,
        }
        payload = _format_generic("blocked", task, extra="Dependency missing")
        assert payload["extra"] == "Dependency missing"

    # ── _format_payload ────────────────────────────────────────────────

    def test_format_payload_routes_to_correct_formatter(self):
        """_format_payload should dispatch to the right formatter by type."""
        task = {"id": "t", "title": "Test", "repo": "r", "assigned_to": None}
        discord = _format_payload("discord", "created", task)
        assert "embeds" in discord
        generic = _format_payload("generic", "created", task)
        assert "event" in generic
        slack = _format_payload("slack", "created", task)
        assert "attachments" in slack
        telegram = _format_payload("telegram", "created", task)
        assert "parse_mode" in telegram

    def test_format_payload_unknown_type_falls_back_to_generic(self):
        """Unknown webhook type should fall back to generic formatter."""
        task = {
            "id": "t",
            "title": "Test",
            "repo": "r",
            "status": "available",
            "priority": 0,
            "assigned_to": None,
            "score": 0,
        }
        payload = _format_payload("unknown_type", "created", task)
        assert "event" in payload
        assert payload["event"] == "created"

    # ── _deliver_with_retry ────────────────────────────────────────────

    @patch("server.webhooks.httpx.post")
    def test_deliver_with_retry_success_first_attempt(self, mock_post):
        """First attempt success should return immediately."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})

        assert code == 200
        assert success is True
        mock_post.assert_called_once()

    @patch("server.webhooks.httpx.post")
    def test_deliver_with_retry_retries_on_5xx(self, mock_post):
        """Server error (5xx) should trigger retries with backoff."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})

        assert success is False
        assert "HTTP 500" in body
        # Should have retried MAX_RETRIES (3) times
        assert mock_post.call_count == 3

    @patch("server.webhooks.httpx.post")
    def test_deliver_with_retry_succeeds_on_retry(self, mock_post):
        """If retry succeeds after failure, should return success."""
        mock_post.side_effect = [
            MagicMock(status_code=503, text="Service Unavailable"),
            MagicMock(status_code=502, text="Bad Gateway"),
            MagicMock(status_code=200, text="OK"),
        ]

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})

        assert code == 200
        assert success is True
        assert mock_post.call_count == 3

    @patch("server.webhooks.httpx.post")
    def test_deliver_with_retry_handles_exception(self, mock_post):
        """Network exceptions should be caught and retried."""
        mock_post.side_effect = ConnectionError("Connection refused")

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})

        assert success is False
        assert "Connection refused" in body
        assert mock_post.call_count == 3

    @patch("server.webhooks.httpx.post")
    def test_deliver_with_retry_2xx_not_retried(self, mock_post):
        """2xx responses should be treated as success."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.text = ""
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})

        assert code == 204
        assert success is True
        mock_post.assert_called_once()

    # ── CRUD operations ────────────────────────────────────────────────

    @patch("server.webhooks._stdb_sql")
    def test_list_webhooks_empty(self, mock_stdb_sql):
        """list_webhooks with no rows should return empty list."""
        mock_stdb_sql.return_value = []
        result = list_webhooks()
        assert result == []
        mock_stdb_sql.assert_called_once_with("SELECT * FROM webhook_subscriptions")

    @patch("server.webhooks._stdb_sql")
    def test_list_webhooks_returns_formatted_rows(self, mock_stdb_sql):
        """list_webhooks should format DB rows into API dicts."""
        mock_stdb_sql.return_value = [
            {
                "id": "wh_abc",
                "url": "https://discord.com/api/webhooks/xxx",
                "wh_type": "discord",
                "events": "created,completed",
                "label": "discord:https://discord.com/api/webhooks/xxx",
                "created_at": 1000,
            }
        ]
        result = list_webhooks()
        assert len(result) == 1
        assert result[0]["id"] == "wh_abc"
        assert result[0]["type"] == "discord"
        assert result[0]["events"] == ["created", "completed"]
        assert result[0]["label"] == "discord:https://discord.com/api/webhooks/xxx"
        assert result[0]["created_at"] == 1000

    @patch("server.webhooks._sql_param")
    def test_get_webhook_found(self, mock_sql_param):
        """get_webhook should return the formatted webhook when found."""
        mock_sql_param.return_value = [
            {
                "id": "wh_xyz",
                "url": "https://hooks.example.com",
                "wh_type": "slack",
                "events": "claimed,completed",
                "label": "slack:https://hooks.example.com",
                "created_at": 2000,
            }
        ]
        result = get_webhook("wh_xyz")
        assert result is not None
        assert result["id"] == "wh_xyz"
        assert result["type"] == "slack"
        assert result["events"] == ["claimed", "completed"]

    @patch("server.webhooks._sql_param")
    def test_get_webhook_not_found(self, mock_sql_param):
        """get_webhook should return None when no rows returned."""
        mock_sql_param.return_value = []
        result = get_webhook("wh_nonexistent")
        assert result is None

    @patch("server.webhooks._call")
    @patch(URL_VALIDATION_PATH)
    def test_add_webhook(self, mock_validate, mock_call):
        """add_webhook should call the reducer and return formatted webhook."""
        mock_validate.return_value = "https://discord.com/api/webhooks/xxx"
        mock_call.return_value = {"status": "ok"}

        result = add_webhook(
            url="https://discord.com/api/webhooks/xxx",
            wh_type="discord",
            events=["created", "completed"],
            label="My webhook",
        )

        assert result["url"] == "https://discord.com/api/webhooks/xxx"
        assert result["type"] == "discord"
        assert result["events"] == ["created", "completed"]
        assert result["label"] == "My webhook"
        assert result["id"].startswith("wh_")
        mock_call.assert_called_once()
        mock_validate.assert_called_once_with("https://discord.com/api/webhooks/xxx")

    @patch("server.webhooks._call")
    @patch(URL_VALIDATION_PATH)
    def test_add_webhook_defaults(self, mock_validate, mock_call):
        """add_webhook with minimal args should use sensible defaults."""
        mock_validate.return_value = "https://hooks.example.com/test"
        mock_call.return_value = {"status": "ok"}

        result = add_webhook(url="https://hooks.example.com/test")

        assert result["type"] == "generic"
        assert "created" in result["events"]
        assert "claimed" in result["events"]
        assert "completed" in result["events"]
        # Label should be auto-generated
        assert result["label"].startswith("generic:")

    @patch("server.webhooks._call")
    def test_remove_webhook_success(self, mock_call):
        """remove_webhook should return True on success."""
        mock_call.return_value = {"status": "ok"}
        assert remove_webhook("wh_abc") is True
        mock_call.assert_called_once_with("remove_webhook_subscription", ["wh_abc"])

    @patch("server.webhooks._call")
    def test_remove_webhook_not_found(self, mock_call):
        """remove_webhook should return False when webhook not found."""
        mock_call.side_effect = RuntimeError("not found")
        assert remove_webhook("wh_nonexistent") is False

    @patch("server.webhooks.get_webhook")
    @patch("server.webhooks._call")
    def test_update_webhook_updates_fields(self, mock_call, mock_get):
        """update_webhook should modify the specified fields."""
        mock_get.return_value = {
            "id": "wh_abc",
            "url": "https://old.example.com",
            "type": "generic",
            "events": ["created"],
            "label": "old label",
        }
        mock_call.return_value = {"status": "ok"}
        # Need to mock get_webhook again for the return value after update
        mock_get.side_effect = [
            {
                "id": "wh_abc",
                "url": "https://old.example.com",
                "type": "generic",
                "events": ["created"],
                "label": "old label",
            },
            {
                "id": "wh_abc",
                "url": "https://new.example.com",
                "type": "discord",
                "events": ["created", "completed"],
                "label": "new label",
            },
        ]

        result = update_webhook(
            "wh_abc",
            {
                "url": "https://new.example.com",
                "type": "discord",
                "events": ["created", "completed"],
                "label": "new label",
            },
        )

        assert result is not None
        assert result["url"] == "https://new.example.com"
        assert result["type"] == "discord"
        assert result["events"] == ["created", "completed"]
        mock_call.assert_called_once()

    @patch("server.webhooks.get_webhook")
    def test_update_webhook_nonexistent(self, mock_get):
        """update_webhook should return None for non-existent webhook."""
        mock_get.return_value = None
        result = update_webhook("wh_nonexistent", {"url": "https://example.com"})
        assert result is None

    # ── list_webhook_deliveries ────────────────────────────────────────

    @patch("server.webhooks._sql_param")
    def test_list_webhook_deliveries_empty(self, mock_sql_param):
        """list_webhook_deliveries with no rows should return []."""
        mock_sql_param.return_value = []
        result = list_webhook_deliveries("wh_abc")
        assert result == []

    @patch("server.webhooks._sql_param")
    def test_list_webhook_deliveries_returns_sorted(self, mock_sql_param):
        """list_webhook_deliveries should return rows sorted by delivered_at desc."""
        mock_sql_param.return_value = [
            {
                "id": "del_1",
                "webhook_id": "wh_abc",
                "event": "created",
                "url": "https://example.com/hook",
                "status_code": 200,
                "response_body": "OK",
                "success": True,
                "delivered_at": 3000,
            },
            {
                "id": "del_2",
                "webhook_id": "wh_abc",
                "event": "completed",
                "url": "https://example.com/hook",
                "status_code": 200,
                "response_body": "OK",
                "success": True,
                "delivered_at": 1000,
            },
            {
                "id": "del_3",
                "webhook_id": "wh_abc",
                "event": "claimed",
                "url": "https://example.com/hook",
                "status_code": 200,
                "response_body": "OK",
                "success": True,
                "delivered_at": 2000,
            },
        ]
        result = list_webhook_deliveries("wh_abc")
        # Should be sorted descending by delivered_at
        timestamps = [d["delivered_at"] for d in result]
        assert timestamps == sorted(timestamps, reverse=True)
        assert len(result) == 3


# ════════════════════════════════════════════════════════════════════════
# Internal STDB Helpers
# ════════════════════════════════════════════════════════════════════════


class TestWebhookStdbHelpers:
    """_sanitize, _sql_param, _stdb_sql, _parse_rows, _call."""

    # ── _sanitize ───────────────────────────────────────────────────

    def test_sanitize_escapes_quotes(self):
        assert _sanitize("it's") == "it''s"
        assert _sanitize("'") == "''"

    def test_sanitize_preserves_normal(self):
        assert _sanitize("hello") == "hello"
        assert _sanitize("") == ""

    # ── _sql_param ──────────────────────────────────────────────────

    @patch("server.webhooks._stdb_sql")
    def test_sql_param_escapes_parameters(self, mock_stdb_sql):
        mock_stdb_sql.return_value = []
        _sql_param("SELECT * FROM t WHERE n = '{name}'", name="it's")
        # Verify the query was escaped before being sent
        called_query = mock_stdb_sql.call_args[0][0]
        assert "it''s" in called_query

    # ── _stdb_sql ───────────────────────────────────────────────────

    @patch("server.webhooks.httpx.post")
    def test_stdb_sql_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"schema": {"elements": []}, "rows": []}]
        mock_resp.text = "ok"
        mock_post.return_value = mock_resp

        result = _stdb_sql("SELECT 1")
        assert result == []
        mock_post.assert_called_once()

    @patch("server.webhooks.httpx.post")
    def test_stdb_sql_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Syntax error"
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="SQL query failed"):
            _stdb_sql("BAD SQL")

    # ── _parse_rows ─────────────────────────────────────────────────

    def test_parse_rows_empty(self):
        assert _parse_rows([]) == []

    def test_parse_rows_no_rows(self):
        data = [{"schema": {"elements": []}, "rows": []}]
        assert _parse_rows(data) == []

    def test_parse_rows_simple(self):
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

    # ── _call ───────────────────────────────────────────────────────

    @patch("server.webhooks.httpx.post")
    def test_call_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "ok"}'
        mock_resp.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_resp

        result = _call("test_reducer", ["arg1"])
        assert result == {"status": "ok"}

    @patch("server.webhooks.httpx.post")
    def test_call_empty_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = ""
        mock_post.return_value = mock_resp

        result = _call("test_reducer", [])
        assert result == {"status": "ok"}

    @patch("server.webhooks.httpx.post")
    def test_call_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError, match="Reducer failed"):
            _call("test_reducer", [])


# ════════════════════════════════════════════════════════════════════════
# remove_webhook edge cases
# ════════════════════════════════════════════════════════════════════════


class TestRemoveWebhookEdgeCases:
    """remove_webhook re-raise on non-'not found' errors."""

    @patch("server.webhooks._call")
    def test_remove_webhook_raises_on_other_error(self, mock_call):
        mock_call.side_effect = RuntimeError("database error")
        with pytest.raises(RuntimeError, match="database error"):
            remove_webhook("wh_abc")


# ════════════════════════════════════════════════════════════════════════
# Formatter edge cases
# ════════════════════════════════════════════════════════════════════════


class TestFormatterEdgeCases:
    """Slack, Telegram formatter edge cases."""

    # ── Slack: agent not added for blocked/completed ────────────────

    def test_format_slack_blocked_no_agent_field(self):
        task = {"id": "t1", "title": "Blocked task", "repo": "r", "assigned_to": "bot"}
        payload = _format_slack("blocked", task, extra="Blocked on X")
        fields = payload["attachments"][0]["fields"]
        # Agent field should NOT be present for blocked
        agent_fields = [f for f in fields if "Agent" in f.get("text", "")]
        assert len(agent_fields) == 0
        # Notes should be present
        notes_fields = [f for f in fields if "Notes" in f.get("text", "")]
        assert len(notes_fields) == 1

    def test_format_slack_completed_no_agent_field(self):
        task = {"id": "t2", "title": "Done", "repo": "r", "assigned_to": "bot"}
        payload = _format_slack("completed", task, extra="All done")
        fields = payload["attachments"][0]["fields"]
        agent_fields = [f for f in fields if "Agent" in f.get("text", "")]
        assert len(agent_fields) == 0

    def test_format_slack_includes_agent_for_non_blocked_completed(self):
        task = {"id": "t3", "title": "Claimed", "repo": "r", "assigned_to": "worker-1"}
        payload = _format_slack("claimed", task)
        fields = payload["attachments"][0]["fields"]
        agent_fields = [f for f in fields if "worker-1" in f.get("text", "")]
        assert len(agent_fields) == 1

    # ── Telegram: agent not added for blocked/completed ─────────────

    def test_format_telegram_blocked_no_agent(self):
        task = {"id": "t4", "title": "Blocked", "repo": "r", "assigned_to": "bot"}
        payload = _format_telegram("blocked", task, extra="Stuck")
        assert "Agent" not in payload["text"]
        assert "Notes" in payload["text"]

    def test_format_telegram_completed_no_agent(self):
        task = {"id": "t5", "title": "Done task", "repo": "r", "assigned_to": "bot"}
        payload = _format_telegram("completed", task, extra="Finished")
        assert "Agent" not in payload["text"]

    def test_format_telegram_with_agent_non_blocked(self):
        """Telegram includes agent field for non-blocked/completed actions."""
        task = {"id": "t6", "title": "Working", "repo": "r", "assigned_to": "worker-2"}
        payload = _format_telegram("claimed", task)
        assert "Agent" in payload["text"]
        assert "worker-2" in payload["text"]


# ════════════════════════════════════════════════════════════════════════
# Delivery retry branches
# ════════════════════════════════════════════════════════════════════════


class TestDeliverWithRetryBranches:
    """Telegram and generic delivery paths."""

    @patch("server.webhooks.httpx.post")
    def test_deliver_telegram_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("telegram", "https://t.me/bot", {})
        assert code == 200
        assert success is True
        mock_post.assert_called_once()

    @patch("server.webhooks.httpx.post")
    def test_deliver_generic_with_content_type(self, mock_post):
        """Generic delivery should include Content-Type header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("generic", "https://example.com/hook", {})
        assert code == 200
        assert success is True
        # Generic uses Content-Type header
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs.get("headers", {}).get("Content-Type") == "application/json"

    @patch("server.webhooks.httpx.post")
    def test_deliver_unknown_type(self, mock_post):
        """Unknown type falls through to else branch (plain JSON POST)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        mock_post.return_value = mock_resp

        code, body, success = _deliver_with_retry("custom", "https://example.com/hook", {})
        assert code == 200
        assert success is True
        mock_post.assert_called_once()


# ════════════════════════════════════════════════════════════════════════
# notify — main dispatcher (async)
# ════════════════════════════════════════════════════════════════════════


class TestNotify:
    """notify dispatches to matching webhooks and logs deliveries."""

    @pytest.mark.asyncio
    @patch("server.webhooks._call")
    @patch("server.webhooks._deliver_with_retry")
    @patch("server.webhooks._format_payload")
    @patch("server.webhooks.list_webhooks")
    async def test_sends_to_matching_hooks(self, mock_list, mock_format, mock_deliver, mock_call):
        mock_list.return_value = [
            {
                "id": "wh_1",
                "url": "https://hook.example.com",
                "type": "generic",
                "events": ["created", "completed"],
            },
            {
                "id": "wh_2",
                "url": "https://other.example.com",
                "type": "discord",
                "events": ["completed"],
            },
        ]
        mock_format.return_value = {"event": "created", "task": {}}
        mock_deliver.return_value = (200, "OK", True)
        mock_call.return_value = {"status": "ok"}

        await notify("created", {"id": "task_1", "title": "Test"}, extra="")

        # Only wh_1 matches "created" event
        mock_format.assert_called_once()
        mock_deliver.assert_called_once()
        # Delivery should be logged
        mock_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("server.webhooks._call")
    @patch("server.webhooks._deliver_with_retry")
    @patch("server.webhooks._format_payload")
    @patch("server.webhooks.list_webhooks")
    async def test_no_matching_hooks(self, mock_list, mock_format, mock_deliver, mock_call):
        mock_list.return_value = [
            {
                "id": "wh_1",
                "url": "https://hook.example.com",
                "type": "generic",
                "events": ["completed"],
            }
        ]

        await notify("created", {"id": "task_1", "title": "Test"})

        # No webhook matches "created" event
        mock_format.assert_not_called()
        mock_deliver.assert_not_called()
        mock_call.assert_not_called()

    @pytest.mark.asyncio
    @patch("server.webhooks._call")
    @patch("server.webhooks._deliver_with_retry")
    @patch("server.webhooks._format_payload")
    @patch("server.webhooks.list_webhooks")
    async def test_delivery_failure_still_logged(
        self, mock_list, mock_format, mock_deliver, mock_call
    ):
        mock_list.return_value = [
            {
                "id": "wh_1",
                "url": "https://hook.example.com",
                "type": "generic",
                "events": ["created"],
            }
        ]
        mock_format.return_value = {"event": "created"}
        mock_deliver.return_value = (0, "Connection refused", False)

        await notify("created", {"id": "task_1", "title": "Test"})

        # Even on failure, delivery should be logged
        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[0] == "log_webhook_delivery"
        assert call_args[1][6] is False  # success = False

    @pytest.mark.asyncio
    @patch("server.webhooks._call")
    @patch("server.webhooks._deliver_with_retry")
    @patch("server.webhooks._format_payload")
    @patch("server.webhooks.list_webhooks")
    async def test_logging_exception_suppressed(
        self, mock_list, mock_format, mock_deliver, mock_call
    ):
        """Exception during _call logging should not propagate (suppressed)."""
        mock_list.return_value = [
            {
                "id": "wh_1",
                "url": "https://hook.example.com",
                "type": "generic",
                "events": ["created"],
            }
        ]
        mock_format.return_value = {"event": "created"}
        mock_deliver.return_value = (200, "OK", True)
        mock_call.side_effect = RuntimeError("STDB unavailable")

        # Should not raise — exception is suppressed in the logging loop
        await notify("created", {"id": "task_1", "title": "Test"})
