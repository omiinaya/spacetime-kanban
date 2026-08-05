"""Extracted from main.py during route thinning (pure move, logic verbatim)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException

import webhooks
from shared import (
    WebhookCreateRequest,
    WebhookUpdateRequest,
    verify_auth,
)

router = APIRouter()


@router.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhook subscriptions."""
    return webhooks.list_webhooks()


@router.post("/api/webhooks", status_code=201, dependencies=[Depends(verify_auth)])
async def create_webhook(body: WebhookCreateRequest):
    """Register a new webhook subscription."""
    return webhooks.add_webhook(
        url=body.url,
        wh_type=body.type,
        events=body.events,
        label=body.label,
    )


@router.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str):
    """Get a specific webhook subscription."""
    wh = webhooks.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    return wh


@router.patch("/api/webhooks/{webhook_id}", dependencies=[Depends(verify_auth)])
async def update_webhook(webhook_id: str, body: WebhookUpdateRequest):
    """Update a webhook subscription."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    wh = webhooks.update_webhook(webhook_id, updates)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    return wh


@router.post("/api/webhooks/{webhook_id}/test", dependencies=[Depends(verify_auth)])
async def test_webhook(webhook_id: str):
    """Send a test ping to a webhook to verify it's working."""
    wh = webhooks.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    test_task = {
        "id": "test_ping",
        "title": "🔔 Test notification from spacetime-kanban",
        "description": "This is a test event to verify your webhook configuration.",
        "priority": 0,
        "status": "available",
        "assigned_to": None,
        "repo": "spacetime-kanban",
        "branch": None,
        "roadmap_item": "Integration Testing",
        "created_by": "webhook-test",
        "created_at": 0,
        "updated_at": 0,
        "depends_on": None,
        "required_skills": None,
        "score": 0,
    }
    from webhooks import _format_payload

    payload = _format_payload(wh["type"], "test", test_task, "Webhook test ping")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            if wh["type"] == "telegram":
                resp = await client.post(wh["url"], json=payload)
            else:
                resp = await client.post(
                    wh["url"],
                    json=payload,
                    headers={"Content-Type": "application/json"} if wh["type"] == "generic" else {},
                )
            resp.raise_for_status()
        return {"status": "sent", "webhook_id": webhook_id, "response_code": resp.status_code}
    except Exception as e:
        raise HTTPException(502, f"Webhook test failed: {str(e)[:200]}") from e


@router.delete("/api/webhooks/{webhook_id}", dependencies=[Depends(verify_auth)])
async def delete_webhook(webhook_id: str):
    """Remove a webhook subscription."""
    if not webhooks.remove_webhook(webhook_id):
        raise HTTPException(404, "Webhook not found")
    return {"status": "deleted"}


@router.get("/api/webhooks/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str, limit: int = 20):
    """Get delivery history for a webhook."""
    return webhooks.list_webhook_deliveries(webhook_id, limit)
