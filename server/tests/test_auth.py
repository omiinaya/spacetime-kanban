"""Tests for server/auth.py."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from server.auth import verify_auth


class TestVerifyAuth:
    """Test API key authentication."""

    async def test_auth_disabled(self):
        with patch("config.settings.api_key", ""):
            result = await verify_auth(authorization=None, x_api_key=None)
            assert result is True

    async def test_valid_api_key_header(self):
        with patch("config.settings.api_key", "test-key-123"):
            result = await verify_auth(authorization=None, x_api_key="test-key-123")
            assert result is True

    async def test_valid_bearer_token(self):
        with patch("config.settings.api_key", "test-key-123"):
            result = await verify_auth(
                authorization="Bearer test-key-123", x_api_key=None
            )
            assert result is True

    async def test_invalid_api_key(self):
        with patch("config.settings.api_key", "real-key"):
            with pytest.raises(HTTPException) as exc:
                await verify_auth(authorization=None, x_api_key="wrong-key")
            assert exc.value.status_code == 401

    async def test_invalid_bearer(self):
        with patch("config.settings.api_key", "real-key"):
            with pytest.raises(HTTPException) as exc:
                await verify_auth(
                    authorization="Bearer wrong-token", x_api_key=None
                )
            assert exc.value.status_code == 401

    async def test_no_auth_header(self):
        with patch("config.settings.api_key", "real-key"):
            with pytest.raises(HTTPException) as exc:
                await verify_auth(authorization=None, x_api_key=None)
            assert exc.value.status_code == 401

    async def test_api_key_takes_precedence(self):
        with patch("config.settings.api_key", "api-key-val"):
            result = await verify_auth(
                authorization="Bearer wrong-bearer", x_api_key="api-key-val"
            )
            assert result is True
