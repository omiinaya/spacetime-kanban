"""Extracted from main.py during route thinning (pure move, logic verbatim)."""

import json

from fastapi import APIRouter, Depends, HTTPException

from shared import (
    DispatcherStateUpdate,
    _call,
    _sql,
    _sql_param,
    verify_auth,
)

router = APIRouter()


@router.get("/api/dispatcher/state")
async def get_dispatcher_state(key: str | None = None):
    """Get dispatcher state from STDB. If key is provided, return only that key's value."""
    if key:
        rows = await _sql_param(
            "SELECT key, value FROM dispatcher_state WHERE key = '{key}'", key=key
        )
        if rows:
            return {key: json.loads(rows[0]["value"])}
        return {key: None}
    rows = await _sql("SELECT key, value FROM dispatcher_state")
    result = {}
    for r in rows:
        try:
            result[r["key"]] = json.loads(r["value"])
        except (json.JSONDecodeError, KeyError, TypeError):
            result[r.get("key", "?")] = r.get("value")
    return result


@router.post("/api/dispatcher/state", dependencies=[Depends(verify_auth)])
async def set_dispatcher_state(body: DispatcherStateUpdate):
    """Set a single key in dispatcher state via STDB reducer."""
    try:
        value_json = json.dumps(body.value)
        await _call("set_dispatcher_state", [body.key, value_json])
        return {"status": "ok", "key": body.key}
    except Exception as e:
        raise HTTPException(502, f"Failed to set dispatcher state: {e}") from e


@router.delete("/api/dispatcher/state/{key}", dependencies=[Depends(verify_auth)])
async def delete_dispatcher_state(key: str):
    """Delete a key from dispatcher state via STDB."""
    try:
        await _call("delete_dispatcher_state_row", [key])
        return {"status": "deleted", "key": key}
    except Exception as e:
        # If error is "Key not found", return 404
        if "Key not found" in str(e):
            raise HTTPException(404, f"Key not found: {key}") from e
        raise HTTPException(502, f"Failed to delete dispatcher state: {e}") from e
