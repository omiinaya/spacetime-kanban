"""Extracted from main.py during route thinning (pure move, logic verbatim)."""

from fastapi import APIRouter, Depends

from shared import (
    ApiKeyCreate,
    ApiKeyOut,
    _call,
    _sql,
    verify_auth,
)

router = APIRouter()


@router.get("/api/api-keys", response_model=list[ApiKeyOut], dependencies=[Depends(verify_auth)])
async def list_api_keys():
    """List all API keys."""
    rows = await _sql("SELECT * FROM api_keys")
    return [
        ApiKeyOut(
            id=r["id"],
            key_hash=r.get("key_hash", ""),
            name=r.get("name", ""),
            repo_scope=r.get("repo_scope"),
            permissions=r.get("permissions", "read"),
            created_by=r.get("created_by", ""),
            created_at=r.get("created_at", 0),
            last_used_at=r.get("last_used_at", 0),
            active=r.get("active", True),
        )
        for r in rows
    ]


@router.post("/api/api-keys", status_code=201, dependencies=[Depends(verify_auth)])
async def create_api_key(body: ApiKeyCreate):
    """Create a new API key."""
    import uuid as _uuid

    key_id = body.id or f"apikey_{_uuid.uuid4().hex[:16]}"
    await _call(
        "create_api_key",
        [
            key_id,
            body.key_hash,
            body.name,
            body.repo_scope,
            body.permissions,
            body.created_by,
        ],
    )
    return {"status": "created", "id": key_id}


@router.post("/api/api-keys/{key_id}/revoke", dependencies=[Depends(verify_auth)])
async def revoke_api_key(key_id: str):
    """Revoke an API key."""
    await _call("revoke_api_key", [key_id])
    return {"status": "revoked", "key_id": key_id}
