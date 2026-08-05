"""Outbound webhook notification system for spacetime-kanban.

Stores webhook subscriptions in STDB (webhook_subscriptions table).
Supports Discord embeds, Slack messages, Telegram, and generic JSON POST.
"""

import uuid
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import httpx

from config import settings


def _sanitize(val: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return val.replace("'", "''")


def _sql_param(query_template: str, **params) -> list[dict]:
    """Safe SQL query with named parameters — escapes all values."""
    escaped = {k: _sanitize(str(v)) for k, v in params.items()}
    query = query_template.format(**escaped)
    return _stdb_sql(query)


STDB_SQL_URL = (
    f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/sql"
)
STDB_CALL_URL = (
    f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/call"
)


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
    """Parse STDB SATS row format into dicts using recursive type-aware extraction."""
    if not resp_json:
        return []
    entry = resp_json[0]
    schema = entry.get("schema", {})
    elements = schema.get("elements", [])
    col_names: list[str] = []
    col_types: list[dict] = []
    for el in elements:
        name = el.get("name", {})
        if isinstance(name, dict):
            name = name.get("some", name)
        col_names.append(str(name) if name else "?")
        col_types.append(el.get("algebraic_type", {}))
    from shared import _extract_sats_val

    rows = entry.get("rows", [])
    result: list[dict] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            atype = col_types[i] if i < len(col_types) else {}
            row_dict[key] = _extract_sats_val(val, atype)
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
        result.append(
            {
                "id": r.get("id", ""),
                "url": r.get("url", ""),
                "type": r.get("wh_type", "generic"),
                "events": r.get("events", "").split(",") if r.get("events") else [],
                "label": r.get("label", ""),
                "created_at": r.get("created_at", 0),
            }
        )
    return result


def get_webhook(webhook_id: str) -> dict | None:
    """Get a specific webhook subscription."""
    rows = _sql_param(
        "SELECT * FROM webhook_subscriptions WHERE id = '{webhook_id}'", webhook_id=webhook_id
    )
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


def add_webhook(
    url: str, wh_type: str = "generic", events: list[str] | None = None, label: str = ""
) -> dict:
    """Register a new webhook subscription in STDB."""
    from shared import validate_webhook_url

    validate_webhook_url(url)
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
        "created_at": int(datetime.now(tz=UTC).timestamp() * 1000),
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


def update_webhook(webhook_id: str, updates: dict) -> dict | None:
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
        "created": "🆕",
        "claimed": "👤",
        "unclaimed": "↩️",
        "completed": "✅",
        "blocked": "🚧",
        "linked": "🔗",
        "test": "🔔",
    }.get(action, "🔔")
    color = {
        "created": 0x5865F2,
        "claimed": 0xFEE75C,
        "unclaimed": 0x808080,
        "completed": 0x57F287,
        "blocked": 0xED4245,
        "linked": 0x5865F2,
        "test": 0x5865F2,
    }.get(action, 0x5865F2)
    title = task.get("title", "?")
    task_id = task.get("id", "?")
    repo = task.get("repo", "")
    agent = task.get("assigned_to", extra) or extra
    embed: dict[str, Any] = {
        "embeds": [
            {
                "title": f"{emoji} {action.title()} — {title}",
                "color": color,
                "fields": [
                    {"name": "Task", "value": f"`{task_id}`", "inline": True},
                    {"name": "Repo", "value": repo or "—", "inline": True},
                ],
                "timestamp": datetime.now(tz=UTC).isoformat() + "Z",
            }
        ]
    }
    if agent and action not in ("blocked", "completed"):
        embed["embeds"][0]["fields"].append({"name": "Agent", "value": agent, "inline": True})
    if extra and action in ("blocked", "completed", "linked"):
        embed["embeds"][0]["fields"].append(
            {"name": "Notes", "value": extra[:500], "inline": False}
        )
    return embed


def _format_slack(action: str, task: dict, extra: str = "") -> dict:
    """Format as Slack webhook message."""
    emoji = {
        "created": ":new:",
        "claimed": ":bust_in_silhouette:",
        "unclaimed": ":leftwards_arrow_with_hook:",
        "completed": ":white_check_mark:",
        "blocked": ":no_entry:",
        "linked": ":link:",
        "test": ":bell:",
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
        "attachments": [
            {"color": "#5865F2", "fields": fields, "ts": int(datetime.now(tz=UTC).timestamp())}
        ],
    }


def _format_telegram(action: str, task: dict, extra: str = "") -> dict:
    """Format as Telegram message payload."""
    emoji = {
        "created": "🆕",
        "claimed": "👤",
        "unclaimed": "↩️",
        "completed": "✅",
        "blocked": "🚧",
        "linked": "🔗",
        "test": "🔔",
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
        "timestamp": datetime.now(tz=UTC).isoformat() + "Z",
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


# Retry config
MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


def _deliver_with_retry(
    wh_type: str, url: str, payload: dict, max_retries: int = MAX_RETRIES
) -> tuple[int, str, bool]:
    """Send a webhook with exponential backoff retry."""
    import time

    last_error = ""
    for attempt in range(max_retries):
        try:
            if wh_type == "telegram":
                resp = httpx.post(url, json=payload, timeout=5)
            elif wh_type == "generic":
                resp = httpx.post(
                    url, json=payload, headers={"Content-Type": "application/json"}, timeout=5
                )
            else:
                resp = httpx.post(url, json=payload, timeout=5)
            if resp.status_code < 500:
                return resp.status_code, resp.text[:500], True
            # Server error — retry with backoff
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            last_error = str(e)[:200]
        if attempt < max_retries - 1:
            time.sleep(BASE_DELAY * (2**attempt))
    # All retries exhausted
    return 0, last_error, False


# ── Dispatcher ────────────────────────────────────────────────────────


async def notify(action: str, task: dict, extra: str = ""):
    """Send notification to all matching webhooks."""
    webhooks = list_webhooks()
    tasks_to_send = []

    # Configured webhooks matching this event
    for wh in webhooks:
        if action in wh.get("events", []):
            payload = _format_payload(wh["type"], action, task, extra)
            tasks_to_send.append((wh["type"], wh["url"], payload))

    # Fire all (best-effort) with retry
    deliveries = []
    for wh_type, url, payload in tasks_to_send:
        code, body, success = _deliver_with_retry(wh_type, url, payload)

        # Find the webhook ID for logging
        wh_id = ""
        for wh in webhooks:
            if wh["url"] == url and wh["type"] == wh_type:
                wh_id = wh["id"]
                break

        deliveries.append(
            {
                "webhook_id": wh_id,
                "event": action,
                "url": url,
                "status_code": code,
                "response_body": body,
                "success": success,
            }
        )

    # Log deliveries to STDB (fire-and-forget)
    for d in deliveries:
        with suppress(Exception):
            _call(
                "log_webhook_delivery",
                [
                    "",
                    d["webhook_id"],
                    d["event"],
                    d["url"],
                    d["status_code"],
                    d["response_body"],
                    d["success"],
                ],
            )  # best-effort for logging too


def list_webhook_deliveries(webhook_id: str, limit: int = 20) -> list[dict]:
    """Get delivery history for a specific webhook."""
    rows = _sql_param(
        "SELECT * FROM webhook_deliveries WHERE webhook_id = '{webhook_id}'", webhook_id=webhook_id
    )
    rows.sort(key=lambda r: -(r.get("delivered_at", 0)))
    result = []
    for r in rows[:limit]:
        result.append(
            {
                "id": r.get("id", ""),
                "webhook_id": r.get("webhook_id", ""),
                "event": r.get("event", ""),
                "url": r.get("url", ""),
                "status_code": r.get("status_code", 0),
                "response_body": r.get("response_body", ""),
                "success": r.get("success", False),
                "delivered_at": r.get("delivered_at", 0),
            }
        )
    return result
