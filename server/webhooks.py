"""Outbound webhook notification system for spacetimedb-kanban.

Stores webhook subscriptions in ~/.kanban/webhooks.json.
Supports Discord embeds, Slack messages, Telegram, and generic JSON POST.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

import httpx

WEBHOOKS_FILE = os.path.expanduser("~/.kanban/webhooks.json")


def _ensure_file():
    """Create the webhooks file if it doesn't exist."""
    os.makedirs(os.path.dirname(WEBHOOKS_FILE), exist_ok=True)
    if not os.path.exists(WEBHOOKS_FILE):
        with open(WEBHOOKS_FILE, "w") as f:
            json.dump([], f)


def _load_webhooks() -> list[dict]:
    _ensure_file()
    try:
        with open(WEBHOOKS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_webhooks(webhooks: list[dict]):
    _ensure_file()
    with open(WEBHOOKS_FILE, "w") as f:
        json.dump(webhooks, f, indent=2)


def list_webhooks() -> list[dict]:
    """Return all registered webhooks."""
    return _load_webhooks()


def get_webhook(webhook_id: str) -> Optional[dict]:
    for wh in _load_webhooks():
        if wh["id"] == webhook_id:
            return wh
    return None


def add_webhook(url: str, type: str = "generic", events: Optional[list[str]] = None,
                label: str = "") -> dict:
    """Register a new webhook subscription."""
    webhooks = _load_webhooks()
    wh = {
        "id": f"wh_{uuid.uuid4().hex[:12]}",
        "url": url,
        "type": type,
        "events": events or ["created", "claimed", "unclaimed", "completed", "blocked"],
        "label": label or f"{type}:{url[:40]}",
        "created_at": int(datetime.utcnow().timestamp() * 1000),
    }
    webhooks.append(wh)
    _save_webhooks(webhooks)
    return wh


def remove_webhook(webhook_id: str) -> bool:
    """Remove a webhook subscription."""
    webhooks = _load_webhooks()
    before = len(webhooks)
    webhooks = [wh for wh in webhooks if wh["id"] != webhook_id]
    _save_webhooks(webhooks)
    return len(webhooks) < before


def update_webhook(webhook_id: str, updates: dict) -> Optional[dict]:
    """Update a webhook's events, label, or URL."""
    webhooks = _load_webhooks()
    for wh in webhooks:
        if wh["id"] == webhook_id:
            if "url" in updates:
                wh["url"] = updates["url"]
            if "type" in updates:
                wh["type"] = updates["type"]
            if "events" in updates:
                wh["events"] = updates["events"]
            if "label" in updates:
                wh["label"] = updates["label"]
            _save_webhooks(webhooks)
            return wh
    return None


# ── Format helpers ────────────────────────────────────────────────────


def _format_discord(action: str, task: dict, extra: str = "") -> dict:
    """Format as Discord webhook embed."""
    emoji = {
        "created": "🆕", "claimed": "👤", "unclaimed": "↩️",
        "completed": "✅", "blocked": "🚧", "linked": "🔗",
    }.get(action, "🔔")
    color = {
        "created": 0x5865F2, "claimed": 0xFEE75C, "unclaimed": 0x808080,
        "completed": 0x57F287, "blocked": 0xED4245, "linked": 0x5865F2,
    }.get(action, 0x5865F2)
    title = task.get("title", "?")
    task_id = task.get("id", "?")
    repo = task.get("repo", "")
    agent = task.get("assigned_to", extra) or extra
    embed = {
        "embeds": [{
            "title": f"{emoji} {action.title()} — {title}",
            "color": color,
            "fields": [
                {"name": "Task", "value": f"`{task_id}`", "inline": True},
                {"name": "Repo", "value": repo or "—", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }]
    }
    if agent and action not in ("blocked", "completed"):
        embed["embeds"][0]["fields"].append({"name": "Agent", "value": agent, "inline": True})
    if extra and action in ("blocked", "completed", "linked"):
        embed["embeds"][0]["fields"].append({"name": "Notes", "value": extra[:500], "inline": False})
    return embed


def _format_slack(action: str, task: dict, extra: str = "") -> dict:
    """Format as Slack webhook message."""
    emoji = {
        "created": ":new:", "claimed": ":bust_in_silhouette:", "unclaimed": ":leftwards_arrow_with_hook:",
        "completed": ":white_check_mark:", "blocked": ":no_entry:", "linked": ":link:",
    }.get(action, ":bell:")
    title = task.get("title", "?")
    task_id = task.get("id", "?")
    repo = task.get("repo", "")
    agent = task.get("assigned_to", extra) or extra
    fields = [
        {"type": "mrkdwn", "text": f"*Task:* `{task_id}`"},
        {"type": "mrkdwn", "text": f"*Repo:* {repo or '—'}"},
    ]
    if agent and action not in ("blocked", "completed"):
        fields.append({"type": "mrkdwn", "text": f"*Agent:* {agent}"})
    if extra and action in ("blocked", "completed"):
        fields.append({"type": "mrkdwn", "text": f"*Notes:* {extra[:500]}"})
    return {
        "text": f"{emoji} *{action.title()}* — {title}",
        "attachments": [{"color": "#5865F2", "fields": fields, "ts": int(datetime.utcnow().timestamp())}],
    }


def _format_telegram(action: str, task: dict, extra: str = "") -> dict:
    """Format as Telegram message payload."""
    emoji = {
        "created": "🆕", "claimed": "👤", "unclaimed": "↩️",
        "completed": "✅", "blocked": "🚧", "linked": "🔗",
    }.get(action, "🔔")
    title = task.get("title", "?")
    task_id = task.get("id", "?")
    repo = task.get("repo", "")
    agent = task.get("assigned_to", extra) or extra
    parts = [f"{emoji} *{action.title()}* — {title}", f"`{task_id}` | Repo: {repo or '—'}"]
    if agent and action not in ("blocked", "completed"):
        parts.append(f"Agent: {agent}")
    if extra and action in ("blocked", "completed"):
        parts.append(f"Notes: {extra[:200]}")
    return {"text": "\n".join(parts), "parse_mode": "Markdown"}


def _format_generic(action: str, task: dict, extra: str = "") -> dict:
    """Format as generic JSON event."""
    return {
        "event": action,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "task": {
            "id": task.get("id"),
            "title": task.get("title"),
            "status": task.get("status"),
            "priority": task.get("priority"),
            "repo": task.get("repo"),
            "assigned_to": task.get("assigned_to"),
            "score": task.get("score", 0),
        },
        "extra": extra or None,
    }


_FORMATTERS = {
    "discord": _format_discord,
    "slack": _format_slack,
    "telegram": _format_telegram,
    "generic": _format_generic,
}


def _format_payload(wh_type: str, action: str, task: dict, extra: str = "") -> dict:
    """Format a notification payload for the given webhook type."""
    formatter = _FORMATTERS.get(wh_type, _format_generic)
    return formatter(action, task, extra)


# ── Dispatcher ────────────────────────────────────────────────────────


async def notify(action: str, task: dict, extra: str = "", discord_url: str = ""):
    """Send notification to all matching webhooks + legacy Discord URL."""
    webhooks = _load_webhooks()
    tasks_to_send = []

    # Legacy Discord webhook
    if discord_url:
        tasks_to_send.append(("discord", discord_url, _format_discord(action, task, extra)))

    # Configured webhooks matching this event
    for wh in webhooks:
        if action in wh.get("events", []):
            payload = _format_payload(wh["type"], action, task, extra)
            tasks_to_send.append((wh["type"], wh["url"], payload))

    # Fire all (best-effort)
    async with httpx.AsyncClient(timeout=5) as client:
        for wh_type, url, payload in tasks_to_send:
            try:
                if wh_type == "telegram":
                    # Telegram Bot API: chat_id is part of the webhook URL pattern
                    resp = await client.post(url, json=payload)
                elif wh_type == "generic":
                    resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                else:
                    resp = await client.post(url, json=payload)
                resp.raise_for_status()
            except Exception:
                pass  # best-effort
