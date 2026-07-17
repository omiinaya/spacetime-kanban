"""
Authentication dependency for spacetimedb-kanban.

Extracted from shared.py to keep concerns separated.
"""

import secrets

from fastapi import Header, HTTPException


async def verify_auth(
    authorization: str = Header(None), x_api_key: str = Header(None, alias="X-API-Key")
):
    """Require API key for mutation endpoints. If API_KEY is not set, auth is disabled."""
    from config import settings

    if not settings.api_key:
        return True  # Auth disabled
    # Check X-API-Key header
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return True
    # Check Authorization: Bearer <token>
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if secrets.compare_digest(token, settings.api_key):
            return True
    raise HTTPException(status_code=401, detail="Invalid or missing API key")
