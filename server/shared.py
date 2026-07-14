"""
Shared service helpers, Pydantic models, and auth for spacetimedb-kanban.

Originally extracted from main.py. Imported by both main.py and routes/*.py.
"""

import asyncio
import json
import secrets
import time
from typing import Any, Optional

import httpx
from fastapi import HTTPException, Header
from pydantic import BaseModel

from config import settings
import webhooks


# ── Auth dependency ───────────────────────────────────────────────────

async def verify_auth(authorization: str = Header(None), x_api_key: str = Header(None, alias="X-API-Key")):
    """Require API key for mutation endpoints. If API_KEY is not set, auth is disabled."""
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


# ── Pydantic models ──────────────────────────────────────────────────

class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: int
    status: str
    assigned_to: Optional[str] = None
    repo: str
    branch: Optional[str] = None
    roadmap_item: str
    created_by: str
    created_at: int
    updated_at: int
    depends_on: Optional[str] = None
    required_skills: Optional[str] = None
    score: int = 0
    position: Optional[int] = None
    fail_count: int = 0
    max_attempts: int = 3
    fail_reason: Optional[str] = None
    subtask_of: Optional[str] = None
    subtasks: Optional[str] = None
    due_by: Optional[int] = None


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str = ""
    created_by: str = "web-user"
    status: str = ""
    fail_count: int = 0
    max_attempts: int = 3
    fail_reason: Optional[str] = None
    subtask_of: Optional[str] = None
    subtasks: Optional[str] = None
    due_by: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    branch: Optional[str] = None
    required_skills: Optional[str] = None
    due_by: Optional[int] = None


class ClaimRequest(BaseModel):
    agent_id: str


class BlockRequest(BaseModel):
    reason: str = ""


class BlockWithReasonRequest(BaseModel):
    reason: str = ""


class SplitTaskRequest(BaseModel):
    child_titles: list[str]


class MaxAttemptsRequest(BaseModel):
    max_attempts: int = 3


class SetDependencyRequest(BaseModel):
    depends_on: str = ""  # empty string to clear


class SetSkillsRequest(BaseModel):
    skills: str = ""


class AgentRegisterRequest(BaseModel):
    agent_id: str
    host: str = ""
    capabilities: str = ""
    repo_focus: str = ""


class AgentHeartbeatRequest(BaseModel):
    agent_id: str
    status: str = "online"
    current_task_id: str = ""


class AgentCapabilitiesRequest(BaseModel):
    capabilities: str = ""
    repo_focus: str = ""


class CompleteRequest(BaseModel):
    result_notes: str = ""


class RoadmapImportRequest(BaseModel):
    content: str  # Raw ROADMAP.md content
    repo: str = ""  # Default repo slug for imported tasks
    created_by: str = "roadmap-import"


class LogOut(BaseModel):
    id: str
    task_id: str
    action: str
    agent_id: Optional[str] = None
    notes: Optional[str] = None
    timestamp: int


class AgentOut(BaseModel):
    id: str
    host: str = ""
    capabilities: Optional[str] = None
    repo_focus: Optional[str] = None
    current_task_id: Optional[str] = None
    status: str = "offline"
    last_heartbeat: int = 0
    first_seen: int = 0


class SuggestResult(BaseModel):
    task: TaskOut
    score: int
    reason: str = ""


class LabelOut(BaseModel):
    id: str
    name: str
    color: str
    description: str = ""
    created_at: int = 0


class LabelCreate(BaseModel):
    id: str = ""
    name: str
    color: str = "#0ea5e9"
    description: str = ""


class LabelUpdate(BaseModel):
    name: str = ""
    color: str = ""
    description: str = ""


# ── Project Models ────────────────────────────────────────────────────

class ProjectOut(BaseModel):
    id: str
    name: str
    description: str = ""
    color: str = "#6b7280"
    priority: int = 2
    active: bool = True
    created_at: int = 0
    updated_at: int = 0


class ProjectCreate(BaseModel):
    id: str  # repo slug
    name: str = ""
    description: str = ""
    color: str = "#0ea5e9"
    priority: int = 2
    active: bool = True


class ProjectUpdate(BaseModel):
    name: str = ""
    description: str = ""
    color: str = ""
    priority: Optional[int] = None  # None = don't change
    active: bool = True


class TaskLabelAssign(BaseModel):
    label_ids: list[str] = []


class CommentOut(BaseModel):
    id: str
    task_id: str
    author: str
    body: str
    created_at: int


class CommentCreate(BaseModel):
    body: str
    author: str = "web-user"


class ChecklistItemOut(BaseModel):
    id: str
    task_id: str
    text: str
    completed: bool = False
    position: int = 0
    created_at: int = 0


class ChecklistItemCreate(BaseModel):
    text: str


# ── Task Template Models ───────────────────────────────────────────────

class TemplateOut(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: Optional[str] = None
    cron_schedule: str
    created_by: str = ""
    created_at: int = 0
    last_triggered_at: int = 0
    active: bool = True


class TemplateCreate(BaseModel):
    id: str = ""
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str = ""
    cron_schedule: str
    created_by: str = "web-user"


class TemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    repo: Optional[str] = None
    roadmap_item: Optional[str] = None
    required_skills: Optional[str] = None
    cron_schedule: Optional[str] = None
    active: Optional[bool] = None


class ReorderRequest(BaseModel):
    task_id: str
    position: int


class BulkReorderRequest(BaseModel):
    items: list[ReorderRequest]


class WebhookCreateRequest(BaseModel):
    url: str
    type: str = "generic"
    events: list[str] = ["created", "claimed", "unclaimed", "completed", "blocked"]
    label: str = ""


class WebhookUpdateRequest(BaseModel):
    url: Optional[str] = None
    type: Optional[str] = None
    events: Optional[list[str]] = None
    label: Optional[str] = None


class IssueLinkRequest(BaseModel):
    task_id: str
    repo: str
    issue_number: int
    issue_url: str = ""
    html_url: str = ""


class IssueCreateRequest(BaseModel):
    task_id: str
    repo: str = ""
    labels: str = ""
    assignee: str = ""


class BatchLabelsRequest(BaseModel):
    task_ids: list[str]
    label_ids: list[str]


class AddLogRequest(BaseModel):
    task_id: str
    action: str
    agent_id: str = ""
    notes: str = ""


class DispatcherStateUpdate(BaseModel):
    key: str
    value: Any


# ── STDB helpers ─────────────────────────────────────────────────────

def _sanitize(val: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return val.replace("'", "''")


async def _sql(query: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            settings.stdb_sql_url,
            content=query,
            headers={"Content-Type": "application/sql"},
        )
    if resp.status_code >= 400:
        raise HTTPException(502, f"SQL query failed: {resp.text[:300]}")
    return _parse_sats_rows(resp.json())


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
                if val[0] == 0:
                    val = val[1] if val[1] and val[1] != [] else None
                else:
                    val = None
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


def _row_to_task(r: dict) -> TaskOut:
    return TaskOut(
        id=r["id"],
        title=r["title"],
        description=r.get("description", ""),
        priority=r.get("priority", 2),
        status=r["status"],
        assigned_to=r.get("assigned_to"),
        repo=r.get("repo", ""),
        branch=r.get("branch"),
        roadmap_item=r.get("roadmap_item", ""),
        created_by=r.get("created_by", ""),
        created_at=r.get("created_at", 0),
        updated_at=r.get("updated_at", 0),
        depends_on=r.get("depends_on"),
        required_skills=r.get("required_skills"),
        score=r.get("score", 0),
        position=r.get("position"),
        fail_count=r.get("fail_count", 0),
        max_attempts=r.get("max_attempts", 3),
        fail_reason=r.get("fail_reason"),
        subtask_of=r.get("subtask_of"),
        subtasks=r.get("subtasks"),
        due_by=r.get("due_by"),
    )


def _row_to_log(r: dict) -> LogOut:
    return LogOut(
        id=r["id"],
        task_id=r["task_id"],
        action=r["action"],
        agent_id=r.get("agent_id"),
        notes=r.get("notes"),
        timestamp=r.get("timestamp", 0),
    )


def _row_to_template(r: dict) -> TemplateOut:
    return TemplateOut(
        id=r["id"],
        title=r["title"],
        description=r.get("description", ""),
        priority=r.get("priority", 2),
        repo=r.get("repo", ""),
        roadmap_item=r.get("roadmap_item", ""),
        required_skills=r.get("required_skills"),
        cron_schedule=r.get("cron_schedule", ""),
        created_by=r.get("created_by", ""),
        created_at=r.get("created_at", 0),
        last_triggered_at=r.get("last_triggered_at", 0),
        active=r.get("active", True),
    )


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
