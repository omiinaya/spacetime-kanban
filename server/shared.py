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
    for el in elements:
        name = el.get("name", {})
        if isinstance(name, dict):
            name = name.get("some", name)
        col_names.append(str(name) if name else "?")
    rows = entry.get("rows", [])
    result: list[dict[str, Any]] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            if isinstance(val, list) and len(val) == 2:
                val = (val[1] if val[1] and val[1] != [] else None) if val[0] == 0 else None
            row_dict[key] = val
        result.append(row_dict)
    return result


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
