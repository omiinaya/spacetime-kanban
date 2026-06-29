"""Outbound webhook notification system for spacetimedb-kanban.

Stores webhook subscriptions in STDB (webhook_subscriptions table).
Supports Discord embeds, Slack messages, Telegram, and generic JSON POST.
"""

import json
import uuid
from datetime import datetime
from typing import Optional

import httpx

from config import settings

STDB_SQL_URL = f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/sql"
STDB_CALL_URL = f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/call"


def _stdb_sql(query: str) -> list[dict]:
    """Execute a synchronous SQL query against STDB."""
    resp = httpx.post(
        STDB_SQL_URL,
        content=query,
        headers={"Content-Type": "application/sql"},
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"SQL query failed: {resp.text[:300]}")
    data = resp.json()
    return _parse_rows(data)


def _parse_rows(resp_json: list[dict]) -> list[dict]:
    """Parse STDB SATS row format into dicts."""
    if not resp_json:
        return []
    entry = resp_json[0]
    schema = entry.get("schema", {})
    elements = schema.get("elements", [])
    col_names: list[str] = []
    for el in elements:
        name = el.get("name", {})
        if isinstance(name, dict):
            name = name.get("some", name)
        col_names.append(str(name) if name else "?")
    rows = entry.get("rows", [])
    result: list[dict] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            if isinstance(val, list) and len(val) == 2:
                if val[0] == 0:
                    val = val[1] if val[1] and val[1] != [] else None
                else:
                    val = None
            row_dict[key] = val
        result.append(row_dict)
    return result


def _call(reducer: str, args: list) -> dict:
    """Call a synchronous STDB reducer."""
    resp = httpx.post(
        f"{STDB_CALL_URL}/{reducer}",
        json=args,
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Reducer failed: {resp.text[:300]}")
    text = resp.text.strip()
    if text:
        return resp.json()
    return {"status": "ok"}


# ── Public API (called from main.py) ──────────────────────────────────


def list_webhooks() -> list[dict]:
    """Return all registered webhooks from STDB."""
    rows = _stdb_sql("SELECT * FROM webhook_subscriptions")
    # Convert DB rows to the same dict format the API expects
    result = []
    for r in rows:
        result.append({
            "id": r.get("id", ""),
            "url": r.get("url", ""),
            "type": r.get("wh_type", "generic"),
            "events": r.get("events", "").split(",") if r.get("events") else [],
            "label": r.get("label", ""),
            "created_at": r.get("created_at", 0),
        })
    return result


def get_webhook(webhook_id: str) -> Optional[dict]:
    """Get a specific webhook subscription."""
    rows = _stdb_sql(f"SELECT * FROM webhook_subscriptions WHERE id = '{webhook_id}'")
    if not rows:
        return None
    r = rows[0]
    return {
        "id": r.get("id", ""),
        "url": r.get("url", ""),
        "type": r.get("wh_type", "generic"),
        "events": r.get("events", "").split(",") if r.get("events") else [],
        "label": r.get("label", ""),
        "created_at": r.get("created_at", 0),
    }


def add_webhook(url: str, wh_type: str = "generic", events: Optional[list[str]] = None,
                label: str = "") -> dict:
    """Register a new webhook subscription in STDB."""
    wh_id = f"wh_{uuid.uuid4().hex[:12]}"
    events_str = ",".join(events or ["created", "claimed", "unclaimed", "completed", "blocked"])
    label = label or f"{wh_type}:{url[:40]}"

    _call("add_webhook_subscription", [wh_id, url, wh_type, events_str, label])

    return {
        "id": wh_id,
        "url": url,
        "type": wh_type,
        "events": events_str.split(","),
        "label": label,
        "created_at": int(datetime.utcnow().timestamp() * 1000),
    }


def remove_webhook(webhook_id: str) -> bool:
    """Remove a webhook subscription from STDB."""
    try:
        _call("remove_webhook_subscription", [webhook_id])
        return True
    except RuntimeError as e:
        if "not found" in str(e).lower():
            return False
        raise


def update_webhook(webhook_id: str, updates: dict) -> Optional[dict]:
    """Update a webhook's events, label, or URL in STDB."""
    # Load current state
    current = get_webhook(webhook_id)
    if not current:
        return None

    url = updates.get("url", current["url"])
    wh_type = updates.get("type", current["type"])
    events_list = updates.get("events", current["events"])
    events_str = ",".join(events_list) if isinstance(events_list, list) else events_list
    label = updates.get("label", current["label"])

    _call("update_webhook_subscription", [webhook_id, url, wh_type, events_str, label])
    return get_webhook(webhook_id)


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
    webhooks = list_webhooks()
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
                    resp = await client.post(url, json=payload)
                elif wh_type == "generic":
                    resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
                else:
                    resp = await client.post(url, json=payload)
                resp.raise_for_status()
            except Exception:
                pass  # best-effort
