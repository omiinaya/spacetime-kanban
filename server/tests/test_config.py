"""Tests for server/config.py."""

from config import settings


class TestSettings:
    """Test application settings."""

    def test_settings_have_required_fields(self):
        assert hasattr(settings, "stdb_host")
        assert hasattr(settings, "stdb_port")
        assert hasattr(settings, "server_port")
        assert hasattr(settings, "api_key")
        assert hasattr(settings, "agent_id")

    def test_default_port(self):
        assert settings.server_port > 0

    def test_agent_id_default(self):
        assert settings.agent_id

    def test_stdb_host_default(self):
        assert settings.stdb_host

    def test_stdb_port_default(self):
        assert settings.stdb_port > 0

    def test_worker_command_default(self):
        assert hasattr(settings, "worker_command")

    def test_auto_star_default_enabled(self):
        assert settings.auto_star_enabled is True

    def test_github_fields(self):
        assert hasattr(settings, "github_token")
        assert hasattr(settings, "github_default_repo")

    def test_scheduler_defaults(self):
        assert hasattr(settings, "scheduler_enabled")
        assert hasattr(settings, "stale_minutes")
