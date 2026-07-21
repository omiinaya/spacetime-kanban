"""Webhook event dispatcher — fires HTTP POSTs to subscribed URLs.

The kanban server fires events when significant state changes happen.
Each event has:
  - event: str (e.g. "task.blocked", "board.dead", "worker.stale")
  - timestamp: int (epoch ms)
  - data: dict (event-specific payload)

Discord-compatible by default — the payload uses `content` for message text
and Discord ignores unknown fields like `_event`, `_data`.
"""
import asyncio
import json
import time

import httpx

from config import settings


# ── Event constants ──────────────────────────────────────────────────
EVENT_TASK_BLOCKED = "task.blocked"
EVENT_TASK_COMPLETED = "task.completed"
EVENT_TASK_CLAIMED = "task.claimed"
EVENT_TASK_DELETED = "task.deleted"
EVENT_BOARD_DEAD = "board.dead"
EVENT_BOARD_STALLED = "board.stalled"
EVENT_WORKER_STALE = "worker.stale"
EVENT_METRICS_SNAPSHOT = "metrics.snapshot"


def _format_message(event: str, data: dict) -> str:
    """Return a human-readable Discord-friendly message for an event."""
    if event == EVENT_TASK_BLOCKED:
        t = data.get("title", "?")
        r = data.get("reason", "unknown")
        repo = data.get("repo", "?")
        return f"🚫 **Blocked**: `{t[:80]}` — {r} (repo: {repo})"
    elif event == EVENT_TASK_COMPLETED:
        t = data.get("title", "?")
        repo = data.get("repo", "?")
        return f"✅ **Completed**: `{t[:80]}` (repo: {repo})"
    elif event == EVENT_TASK_DELETED:
        t = data.get("title", "?")
        repo = data.get("repo", "?")
        return f"🗑️ **Deleted**: `{t[:80]}` (repo: {repo})"
    elif event == EVENT_BOARD_DEAD:
        ip = data.get("in_progress", 0)
        avail = data.get("available", 0)
        comps = data.get("completions_last_hour", 0)
        return (
            f"🔴 **Board Dead** — 0 completions in the last hour\n"
            f"Available: {avail} | In Progress: {ip} | Blocked: {data.get('blocked', 0)}\n"
            f"Last hour: {data.get('claims_last_hour', 0)} claims, {comps} completions"
        )
    elif event == EVENT_BOARD_STALLED:
        ratio = data.get("claim_complete_ratio", 0)
        return (
            f"⚠️ **Board Stalled** — claim:complete ratio = {ratio}:1\n"
            f"{data.get('claims_last_hour', 0)} claims but only "
            f"{data.get('completions_last_hour', 0)} completions in the last hour"
        )
    elif event == EVENT_WORKER_STALE:
        return (
            f"⏰ **Stale Worker** — task `{data.get('task_id', '?')[:30]}` "
            f"claimed {data.get('age_minutes', 0):.0f}m ago with no heartbeat"
        )
    elif event == EVENT_METRICS_SNAPSHOT:
        return (
            f"📊 **Board Snapshot**\n"
            f"Total: {data.get('total', 0)} | Available: {data.get('available', 0)} | "
            f"In Progress: {data.get('in_progress', 0)} | "
            f"Blocked: {data.get('blocked', 0)} | Done: {data.get('done', 0)}\n"
            f"Claims/hr: {data.get('claims_last_hour', 0)} | "
            f"Completions/hr: {data.get('completions_last_hour', 0)}"
        )
    return f"[{event}] {json.dumps(data)[:200]}"


async def fire_event(
    event: str,
    data: dict,
    webhook_url: str | None = None,
) -> bool:
    """Fire a webhook event to the configured URL.

    If webhook_url is None, uses settings.webhook_default_url.
    Discord-compatible: uses 'content' field for messages,
    'embeds' for rich embeds (future). Unknown fields are silently ignored.

    Returns True if at least one delivery succeeded.
    """
    url = webhook_url or settings.webhook_default_url
    if not url:
        return False  # No webhook configured — silent

    payload = {
        "content": _format_message(event, data),
        "_event": event,
        "_timestamp": int(time.time() * 1000),
        "_data": data,
    }

    body = json.dumps(payload).encode()

    last_error = None
    for attempt in range(settings.webhook_max_retries):
        try:
            async with httpx.AsyncClient(
                timeout=settings.webhook_timeout_seconds
            ) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code < 500:
                    return True
                last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            last_error = str(e)

        if attempt < settings.webhook_max_retries - 1:
            await asyncio.sleep(2**attempt)  # 1s, 2s, 4s backoff

    print(
        f"[webhook] Failed to deliver {event} "
        f"after {settings.webhook_max_retries} attempts: {last_error}"
    )
    return False
