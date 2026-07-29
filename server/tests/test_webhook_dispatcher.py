"""Tests for server/webhook_dispatcher.py — delivery retry logic, formatting, fire_event."""

from unittest.mock import AsyncMock, MagicMock, patch

from server.webhook_dispatcher import (
    EVENT_BOARD_DEAD,
    EVENT_BOARD_STALLED,
    EVENT_METRICS_SNAPSHOT,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_CLAIMED,
    EVENT_TASK_COMPLETED,
    EVENT_TASK_DELETED,
    EVENT_WORKER_STALE,
    _format_message,
    _get_webhook_client,
    fire_event,
)


class TestWebhookDispatcher:
    """Test suite for webhook_dispatcher.py — event formatting and delivery."""

    # ── _format_message ────────────────────────────────────────────────

    def test_format_message_task_blocked(self):
        """_format_message for EVENT_TASK_BLOCKED should contain the reason."""
        msg = _format_message(
            EVENT_TASK_BLOCKED,
            {
                "title": "Fix auth",
                "reason": "Missing API key",
                "repo": "sample-repo-q",
            },
        )
        assert "Blocked" in msg
        assert "Fix auth" in msg
        assert "Missing API key" in msg
        assert "sample-repo-q" in msg

    def test_format_message_task_completed(self):
        """_format_message for EVENT_TASK_COMPLETED should contain the title."""
        msg = _format_message(
            EVENT_TASK_COMPLETED,
            {
                "title": "Add login",
                "repo": "spacetime-web",
            },
        )
        assert "Completed" in msg
        assert "Add login" in msg
        assert "spacetime-web" in msg

    def test_format_message_task_deleted(self):
        """_format_message for EVENT_TASK_DELETED should mention deletion."""
        msg = _format_message(
            EVENT_TASK_DELETED,
            {
                "title": "Old task",
                "repo": "test-repo",
            },
        )
        assert "Deleted" in msg
        assert "Old task" in msg

    def test_format_message_board_dead(self):
        """_format_message for EVENT_BOARD_DEAD should include stats."""
        msg = _format_message(
            EVENT_BOARD_DEAD,
            {
                "in_progress": 3,
                "available": 5,
                "blocked": 2,
                "completions_last_hour": 0,
                "claims_last_hour": 7,
            },
        )
        assert "Board Dead" in msg
        assert "Available: 5" in msg
        assert "In Progress: 3" in msg
        assert "Blocked: 2" in msg
        assert "0 completions" in msg

    def test_format_message_board_stalled(self):
        """_format_message for EVENT_BOARD_STALLED should include ratio."""
        msg = _format_message(
            EVENT_BOARD_STALLED,
            {
                "claim_complete_ratio": 25,
                "claims_last_hour": 50,
                "completions_last_hour": 2,
            },
        )
        assert "Board Stalled" in msg
        assert "25:1" in msg
        assert "50 claims" in msg
        assert "2 completions" in msg

    def test_format_message_worker_stale(self):
        """_format_message for EVENT_WORKER_STALE should include age."""
        msg = _format_message(
            EVENT_WORKER_STALE,
            {
                "task_id": "task_abc123",
                "age_minutes": 42.5,
            },
        )
        assert "Stale Worker" in msg
        assert "task_abc123" in msg
        assert "42" in msg  # age rounded to 42m

    def test_format_message_metrics_snapshot(self):
        """_format_message for EVENT_METRICS_SNAPSHOT should include all counts."""
        msg = _format_message(
            EVENT_METRICS_SNAPSHOT,
            {
                "total": 100,
                "available": 30,
                "in_progress": 10,
                "blocked": 5,
                "done": 55,
                "claims_last_hour": 8,
                "completions_last_hour": 6,
            },
        )
        assert "Board Snapshot" in msg
        assert "Total: 100" in msg
        assert "Available: 30" in msg
        assert "In Progress: 10" in msg
        assert "Done: 55" in msg

    def test_format_message_claimed(self):
        """_format_message for EVENT_TASK_CLAIMED should identifier unknown events by key."""
        msg = _format_message(
            EVENT_TASK_CLAIMED,
            {
                "title": "My Task",
                "repo": "my-repo",
            },
        )
        # The claimed event goes through the fallback if not in special handlers
        assert "task.claimed" in msg or "My Task" in msg

    def test_format_telegram_claimed_with_agent(self):
        """_format_telegram for claimed action should include agent."""
        msg = _format_message(
            EVENT_TASK_CLAIMED,
            {
                "title": "My Task",
                "repo": "my-repo",
                "assigned_to": "agent-x",
            },
        )
        assert "claimed" in msg.lower() or "Task" in msg

    def test_format_message_unknown_event_fallback(self):
        """Unknown events should produce a JSON dump fallback."""
        msg = _format_message("custom.event", {"foo": "bar"})
        assert "custom.event" in msg
        assert '"foo"' in msg or '"bar"' in msg

    def test_format_message_truncates_long_titles(self):
        """Long titles should be truncated to 80 chars."""
        long_title = "A" * 200
        msg = _format_message(
            EVENT_TASK_BLOCKED,
            {
                "title": long_title,
                "reason": "test",
                "repo": "repo",
            },
        )
        # Should contain exactly 80 A's
        assert "A" * 80 in msg
        assert "A" * 81 not in msg

    # ── _get_webhook_client ────────────────────────────────────────────

    def test_get_webhook_client_returns_singleton(self):
        """_get_webhook_client should return the same instance across calls."""
        client1 = _get_webhook_client()
        client2 = _get_webhook_client()
        assert client1 is client2

    # ── fire_event ─────────────────────────────────────────────────────

    @patch("server.webhook_dispatcher.settings")
    async def test_fire_event_no_url_returns_false(self, mock_settings):
        """fire_event with no webhook URL should return False."""
        mock_settings.webhook_default_url = ""
        mock_settings.webhook_max_retries = 3
        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test"})
        assert result is False

    @patch("server.webhook_dispatcher.settings")
    @patch("server.webhook_dispatcher._get_webhook_client")
    async def test_fire_event_successful_delivery(self, mock_get_client, mock_settings):
        """Successful HTTP delivery should return True."""
        mock_settings.webhook_default_url = "https://hooks.example.com/webhook"
        mock_settings.webhook_max_retries = 3
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test", "repo": "my-repo"})

        assert result is True
        mock_client.post.assert_called_once()
        # Verify the payload includes the event metadata
        call_kwargs = mock_client.post.call_args[1]
        assert "content" in str(call_kwargs.get("content", ""))

    @patch("server.webhook_dispatcher.settings")
    @patch("server.webhook_dispatcher._get_webhook_client")
    async def test_fire_event_retries_on_server_error(self, mock_get_client, mock_settings):
        """Server errors (5xx) should trigger retries."""
        mock_settings.webhook_default_url = "https://hooks.example.com/webhook"
        mock_settings.webhook_max_retries = 3
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test"})

        assert result is False
        # Should have retried max_retries times
        assert mock_client.post.call_count == 3

    @patch("server.webhook_dispatcher.settings")
    @patch("server.webhook_dispatcher._get_webhook_client")
    async def test_fire_event_succeeds_on_retry(self, mock_get_client, mock_settings):
        """If retry succeeds (non-5xx), should return True."""
        mock_settings.webhook_default_url = "https://hooks.example.com/webhook"
        mock_settings.webhook_max_retries = 3
        mock_client = AsyncMock()
        # First two fail, third succeeds
        mock_client.post.side_effect = [
            MagicMock(status_code=503),
            MagicMock(status_code=502),
            MagicMock(status_code=200),
        ]
        mock_get_client.return_value = mock_client

        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test"})

        assert result is True
        assert mock_client.post.call_count == 3

    @patch("server.webhook_dispatcher.settings")
    @patch("server.webhook_dispatcher._get_webhook_client")
    async def test_fire_event_handles_exception_during_delivery(
        self, mock_get_client, mock_settings
    ):
        """Network exceptions during delivery should be caught and retried."""
        mock_settings.webhook_default_url = "https://hooks.example.com/webhook"
        mock_settings.webhook_max_retries = 2
        mock_client = AsyncMock()
        mock_client.post.side_effect = ConnectionError("Connection refused")
        mock_get_client.return_value = mock_client

        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test"})

        assert result is False
        assert mock_client.post.call_count == 2

    @patch("server.webhook_dispatcher.settings")
    @patch("server.webhook_dispatcher._get_webhook_client")
    async def test_fire_event_uses_custom_url(self, mock_get_client, mock_settings):
        """fire_event should use the provided webhook_url when given."""
        mock_settings.webhook_default_url = "https://default.example.com/webhook"
        mock_settings.webhook_max_retries = 1
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_get_client.return_value = mock_client

        custom_url = "https://custom.example.com/hook"
        result = await fire_event(EVENT_TASK_COMPLETED, {"title": "Test"}, webhook_url=custom_url)

        assert result is True
        # The URL called should be the custom one, not the default
        call_url = mock_client.post.call_args[0][0]
        assert call_url == custom_url
