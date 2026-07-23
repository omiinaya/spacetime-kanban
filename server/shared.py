"""
Shared service helpers, Pydantic models, and auth for spacetimedb-kanban.

Originally extracted from main.py. Imported by both main.py and routes/*.py.
"""

import asyncio
import time
from typing import Any

import httpx
from fastapi import HTTPException

import webhooks
from config import settings

# ── Auth dependency ───────────────────────────────────────────────────
# verify_auth has been moved to auth.py. Import from there:
#   from auth import verify_auth
# Or keep using:  from shared import verify_auth  (re-exported below)


# ── STDB helpers ─────────────────────────────────────────────────────


def _sanitize(val: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return val.replace("'", "''")


# Shared httpx client — reused across all SQL queries to avoid
# connection pool overhead on every request (was creating a new
# AsyncClient per query, causing 1-2s overhead each).
_sql_client = httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=5))


async def _sql(query: str) -> list[dict[str, Any]]:
    resp = await _sql_client.post(
        settings.stdb_sql_url,
        content=query,
        headers={"Content-Type": "application/sql"},
    )
    if resp.status_code >= 400:
        raise HTTPException(502, f"SQL query failed: {resp.text[:300]}")
    # Parse off the event loop: large result sets (e.g. unfiltered task_logs
    # at 460K+ rows) take tens of seconds of pure-Python SATS parsing and
    # would otherwise stall every concurrent request.
    return await asyncio.to_thread(_parse_sats_rows, resp.json())


async def _sql_param(query_template: str, **params: str) -> list[dict[str, Any]]:
    """Safe SQL query with named parameters — escapes all string values."""
    escaped = {k: _sanitize(str(v)) for k, v in params.items()}
    query = query_template.format(**escaped)
    return await _sql(query)


def _parse_sats_rows(resp_json: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    rows = entry.get("rows", [])
    result: list[dict[str, Any]] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            atype = col_types[i] if i < len(col_types) else {}
            val = _extract_sats_val(val, atype)
            row_dict[key] = val
        result.append(row_dict)
    return result


def _extract_sats_val(val: Any, atype: dict) -> Any:
    """Recursively extract a Python value from a SATS-encoded value, using the
    column's algebraic type schema to decode Sum/Product/Ref types.

    Encoding conventions:
      - Sum / Option: [variant_index, payload] — 2-element list
      - Product:      [field1, field2, ...]     — bare array (any length, including 0)
      - Tuple:        same as Product
      - Array / Set:  [elem1, elem2, ...]       — bare array
      - Ref:          [hash, ...]
      - Built-in:     native JSON (str, num, bool, null)
    """

    # ── Sum type: [variant_index, payload] ───────────────────────────
    if "Sum" in atype:
        if not isinstance(val, list) or len(val) != 2:
            return val
        variants = atype["Sum"].get("variants", [])
        var_idx = val[0]
        if var_idx >= len(variants):
            return None
        v = variants[var_idx]
        vname = v.get("name", {})
        if isinstance(vname, dict):
            vname = vname.get("some", str(var_idx))
        payload = val[1]
        vtype = v.get("algebraic_type", {})
        extracted = _extract_sats_val(payload, vtype)

        # Option type pattern: variants=["none","some"] → return None or inner value
        vnames = [str(x.get("name", {}).get("some", "")) for x in variants]
        if len(variants) == 2 and "none" in vnames and "some" in vnames:
            if str(vname).lower() == "none":
                return None
            return extracted

        # Return variant name for payload-less enums, otherwise name:value
        # Check the variant's schema type (not the extracted value) to distinguish
        # "no payload fields" from "payload that resolved to None/empty".
        # A variant whose type is an empty Product (0 elements) is truly payload-less;
        # anything else (non-empty Product, Array, plain String, etc.) preserves
        # the {name: extracted} structure even if extracted is None.
        is_payloadless = (
            isinstance(vtype, dict)
            and "Product" in vtype
            and isinstance(vtype["Product"].get("elements"), list)
            and len(vtype["Product"]["elements"]) == 0
        )
        if is_payloadless:
            return str(vname)
        return {str(vname): extracted}

    # ── Product type: val IS the field list directly ─────────────────
    if "Product" in atype:
        if not isinstance(val, list):
            return val
        elements = atype["Product"].get("elements", [])
        if not val:
            return None
        fields = []
        for j, field_val in enumerate(val):
            fel = elements[j] if j < len(elements) else {}
            ftype = fel.get("algebraic_type", {})
            fields.append(_extract_sats_val(field_val, ftype))
        return fields[0] if len(fields) == 1 else fields

    # ── Tuple type (unnamed product) — val IS the field list ─────────
    if "Tuple" in atype:
        if not isinstance(val, list):
            return val
        elements = atype["Tuple"].get("elements", [])
        fields = []
        for j, field_val in enumerate(val):
            fel = elements[j] if j < len(elements) else {}
            ftype = fel.get("algebraic_type", {})
            fields.append(_extract_sats_val(field_val, ftype))
        return fields

    # ── Array / Set type — val IS the element list ───────────────────
    if "Array" in atype or "Set" in atype:
        if not isinstance(val, list):
            return val
        inner = atype.get("Array", atype.get("Set", {}))
        itype = inner.get("algebraic_type", {})
        return [_extract_sats_val(item, itype) for item in val]

    # ── Ref type ────────────────────────────────────────────────────
    if "Ref" in atype:
        if isinstance(val, list) and len(val) > 0:
            return val[0]
        return val if val else None

    # ── Fallback: pass through unchanged when no type info available ─────
    # The old fallback treated 2-element lists as [tag, payload] and collapsed
    # non-zero-index or empty-payload values to None ("collapses Option and Sum
    # types to None"). Type-aware handlers above cover all SATS-encoded types
    # now, so the fallback just passes through.
    return val


async def _call(reducer: str, args: list) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.stdb_base_url}/v1/database/{settings.stdb_db}/call/{reducer}",
            json=args,
        )
    if resp.status_code >= 400:
        raise HTTPException(409, f"Reducer failed: {resp.text[:300]}")
    text = resp.text.strip()
    if text:
        return resp.json()
    return {"status": "ok"}


async def _compute_score(task: dict, agent_capabilities: str | None = None) -> tuple[int, str]:
    """Compute a priority score for a task. Higher = more recommended.
    Priority is u8 (0=urgent … 255=lowest). Maps to 100-0 range."""
    base = max(100 - task.get("priority", 128), 0)  # 0→100, 128→~50, 255→0
    reasons = []

    # Time bonus: +5 per hour available, capped at +30
    now_ms = int(time.time() * 1000)
    age_hours = (now_ms - task.get("created_at", now_ms)) / 3_600_000
    time_bonus = min(int(age_hours * 5), 30)
    if time_bonus > 0:
        reasons.append(f"+{time_bonus} stale ({(age_hours):.1f}h old)")

    # Dependency bonus: +10 per task that depends on this one (unblock value)
    try:
        all_tasks = await _sql("SELECT id, depends_on FROM tasks WHERE depends_on IS NOT NULL")
        blocker_count = sum(1 for t in all_tasks if t.get("depends_on") == task["id"])
        blocker_bonus = min(blocker_count * 10, 30)
        if blocker_bonus > 0:
            reasons.append(f"+{blocker_bonus} unblocks {blocker_count} task(s)")
    except Exception:
        blocker_bonus = 0

    # Skill match bonus: +15 per matching skill tag, capped at +30
    skill_bonus = 0
    task_skills = task.get("required_skills") or ""
    if agent_capabilities and task_skills:
        agent_tags = {t.strip().lower() for t in agent_capabilities.split(",") if t.strip()}
        task_tags = {t.strip().lower() for t in task_skills.split(",") if t.strip()}
        matched = agent_tags & task_tags
        skill_bonus = min(len(matched) * 15, 30)
        if skill_bonus > 0:
            reasons.append(f"+{skill_bonus} skill match ({', '.join(matched)})")

    total = base + time_bonus + blocker_bonus + skill_bonus
    reason_str = "; ".join(reasons) if reasons else "base score"
    return total, reason_str


async def _notify(action: str, task: dict, extra: str = ""):
    """Send notifications to all configured webhooks."""
    await webhooks.notify(action, task, extra)


# ── Re-exports for backward compatibility ────────────────────────────
# These functions were moved to auth.py and responses.py but are
# re-exported here so that existing imports like:
#   from shared import verify_auth, _row_to_task
# continue to work without modifying every route file.
# Model classes now live in models.py but are re-exported here too.

from auth import verify_auth  # noqa: E402, F401
from models import (  # noqa: E402, F401
    AddLogRequest,
    AgentCapabilitiesRequest,
    AgentHeartbeatRequest,
    AgentOut,
    AgentRegisterRequest,
    ApiKeyCreate,
    ApiKeyOut,
    AutomationRuleCreate,
    AutomationRuleOut,
    AutomationRuleUpdate,
    BatchLabelsRequest,
    BlockRequest,
    BlockWithReasonRequest,
    BulkArchiveRequest,
    BulkReorderRequest,
    BulkRetryRequest,
    ChecklistItemCreate,
    ChecklistItemOut,
    ClaimRequest,
    CommentCreate,
    CommentOut,
    CompleteRequest,
    DispatcherStateUpdate,
    IssueCreateRequest,
    IssueLinkRequest,
    LabelCreate,
    LabelOut,
    LabelUpdate,
    LogOut,
    MaxAttemptsRequest,
    MigrationCreate,
    MigrationOut,
    PermanentBlockRequest,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    ReorderRequest,
    RoadmapImportRequest,
    SetDependencyRequest,
    SetSkillsRequest,
    SplitTaskRequest,
    SprintRequest,
    SuggestResult,
    TaskCreate,
    TaskLabelAssign,
    TaskOut,
    TaskRelationCreate,
    TaskRelationOut,
    TaskUpdate,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    TimeEstimatesRequest,
    WebhookCreateRequest,
    WebhookUpdateRequest,
)
from responses import _row_to_agent, _row_to_log, _row_to_task, _row_to_template  # noqa: E402, F401
