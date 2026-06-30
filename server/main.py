import asyncio
import json
import os
import re
from datetime import datetime
import uuid
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import settings
import webhooks
import issue_sync

app = FastAPI(title="spacetimedb-kanban", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin, "http://localhost:5189", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str = ""
    created_by: str = "web-user"
    status: str = ""

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    branch: Optional[str] = None
    required_skills: Optional[str] = None

class ClaimRequest(BaseModel):
    agent_id: str

class BlockRequest(BaseModel):
    reason: str = ""

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

class TaskLabelAssign(BaseModel):
    label_ids: list[str] = []

# ── Static file serving (SPA dashboard) ──────────────────────────────

WEB_DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")
else:
    print(f"⚠ Web dist not found at {WEB_DIST} — dashboard not available")
    print("  Build it: cd web && npm run build")

@app.get("/")
async def serve_spa():
    index = os.path.join(WEB_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return {"status": "dashboard not built — run 'npm run build' in web/"}

# ── STDB helpers ─────────────────────────────────────────────────────

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
    )


async def _notify(action: str, task: dict, extra: str = ""):
    """Send notifications to all configured webhooks."""
    await webhooks.notify(action, task, extra, discord_url=settings.discord_webhook_url or "")

def _row_to_log(r: dict) -> LogOut:
    return LogOut(
        id=r["id"],
        task_id=r["task_id"],
        action=r["action"],
        agent_id=r.get("agent_id"),
        notes=r.get("notes"),
        timestamp=r.get("timestamp", 0),
    )

# ── Helper: ensure DB identity is set ────────────────────────────────

@app.on_event("startup")
async def startup():
    """Create the database if it doesn't exist."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{settings.stdb_base_url}/v1/database/{settings.stdb_db}"
        )
    if resp.status_code == 404:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.stdb_base_url}/v1/database",
                json={"name": settings.stdb_db},
            )
        print(f"Created database: {settings.stdb_db} (status={resp.status_code})")

# ── Endpoints ────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}

async def _compute_score(task: dict, agent_capabilities: str | None = None) -> tuple[int, str]:
    """Compute a priority score for a task. Higher = more recommended."""
    base = (4 - task.get("priority", 2)) * 20  # Urgent=80, High=60, Med=40, Low=20
    reasons = []

    # Time bonus: +5 per hour available, capped at +30
    now_ms = int(datetime.utcnow().timestamp() * 1000)
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


# Priority scoring route must be BEFORE /api/tasks/{task_id} to avoid shadowing
@app.get("/api/tasks/suggest", response_model=list[SuggestResult])
async def suggest_tasks(agent_id: str | None = None, limit: int = 5):
    """Return top-N recommended tasks based on priority scoring."""
    rows = await _sql("SELECT * FROM tasks WHERE status = 'available'")

    # Get agent capabilities if agent_id provided
    agent_caps = None
    if agent_id:
        try:
            agent_rows = await _sql(f"SELECT capabilities FROM swarm_agents WHERE id = '{agent_id}'")
            if agent_rows:
                agent_caps = agent_rows[0].get("capabilities")
        except Exception:
            pass

    results = []
    for r in rows:
        score, reason = await _compute_score(r, agent_caps)
        task_out = _row_to_task(r)
        results.append(SuggestResult(task=task_out, score=score, reason=reason))

    results.sort(key=lambda x: -x.score)
    return results[:limit]

@app.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(status: Optional[str] = None, repo: Optional[str] = None, label: Optional[str] = None):
    # If label filter provided, first get task IDs with that label
    label_task_ids: set[str] | None = None
    if label:
        rows = await _sql(f"SELECT task_id FROM task_label_assignments WHERE label_id = '{label}'")
        label_task_ids = {r["task_id"] for r in rows}

    sql = "SELECT * FROM tasks"
    filters = []
    if status:
        filters.append(f"status = '{status}'")
    if repo:
        filters.append(f"repo = '{repo}'")
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    rows = await _sql(sql)
    tasks = [_row_to_task(r) for r in rows]
    if label_task_ids is not None:
        tasks = [t for t in tasks if t.id in label_task_ids]
    tasks.sort(key=lambda t: (t.priority, -t.created_at))
    return tasks

@app.post("/api/tasks/seed")
async def seed_tasks():
    """Seed sample tasks into the database."""
    await _call("seed_sample_tasks", [])
    return {"status": "seeded"}


import csv
import io


@app.get("/api/tasks/export")
async def export_tasks(format: str = "json", status: str = "", repo: str = ""):
    """Export tasks as CSV or JSON with optional filters."""
    sql = "SELECT * FROM tasks"
    filters = []
    if status:
        filters.append(f"status = '{status}'")
    if repo:
        filters.append(f"repo = '{repo}'")
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    rows = await _sql(sql)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "title", "description", "priority", "status",
                         "assigned_to", "repo", "branch", "roadmap_item",
                         "created_by", "created_at", "updated_at",
                         "depends_on", "required_skills", "score"])
        for r in rows:
            writer.writerow([
                r.get("id", ""), r.get("title", ""), r.get("description", ""),
                r.get("priority", 2), r.get("status", ""), r.get("assigned_to", ""),
                r.get("repo", ""), r.get("branch", ""), r.get("roadmap_item", ""),
                r.get("created_by", ""), r.get("created_at", 0), r.get("updated_at", 0),
                r.get("depends_on", ""), r.get("required_skills", ""), r.get("score", 0),
            ])
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=kanban-tasks.csv"},
        )
    else:
        tasks = []
        for r in rows:
            tasks.append(_row_to_task(r).model_dump())
        return JSONResponse(
            content=tasks,
            headers={"Content-Disposition": "attachment; filename=kanban-tasks.json"},
        )


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if not rows:
        raise HTTPException(404, "Task not found")
    return _row_to_task(rows[0])

@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskCreate):
    import uuid as _uuid
    task_id = f"task_{_uuid.uuid4().hex[:16]}"
    await _call("add_task", [
        task_id,
        body.title,
        body.description,
        body.priority,
        body.repo,
        body.roadmap_item,
        body.created_by,
        body.status,
    ])
    # Set skills if provided — using known task_id, no race condition
    if body.required_skills:
        await _call("set_task_skills", [task_id, body.required_skills])
    asyncio.ensure_future(_notify("created", {
        "title": body.title,
        "id": task_id,
        "repo": body.repo,
    }, body.created_by))
    return {"status": "created", "id": task_id}


# ── Task Logs ────────────────────────────────────────────────────────


class AddLogRequest(BaseModel):
    task_id: str
    action: str
    agent_id: str = ""
    notes: str = ""


@app.post("/api/tasks/{task_id}/log")
async def add_task_log(task_id: str, body: AddLogRequest):
    """Add an activity log entry to a task."""
    await _call("add_log", [body.task_id, body.action, body.agent_id, body.notes])
    return {"status": "logged", "task_id": task_id}


@app.patch("/api/tasks/{task_id}")
async def patch_task(task_id: str, body: TaskUpdate):
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if not rows:
        raise HTTPException(404, "Task not found")
    t = rows[0]
    title = body.title if body.title is not None else t.get("title", "")
    desc = body.description if body.description is not None else t.get("description", "")
    priority = body.priority if body.priority is not None else t.get("priority", 2)
    branch = body.branch if body.branch is not None else t.get("branch", "") or ""
    await _call("update_task", [task_id, title, desc, priority, branch])
    return {"status": "updated"}

@app.post("/api/tasks/{task_id}/claim")
async def claim_task(task_id: str, body: ClaimRequest):
    result = await _call("claim_task", [task_id, body.agent_id])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify("claimed", rows[0]))
    return {"status": "claimed", "task_id": task_id, "assigned_to": body.agent_id}

@app.post("/api/tasks/{task_id}/unclaim")
async def unclaim_task(task_id: str):
    await _call("unclaim_task", [task_id])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify("unclaimed", rows[0]))
        asyncio.ensure_future(_sync_to_github(task_id, "unclaimed"))
    return {"status": "unclaimed", "task_id": task_id}

async def _sync_to_github(task_id: str, event: str, notes: str = ""):
    """Push a kanban task state change back to a linked GitHub issue."""
    link = issue_sync.get_link(task_id)
    if not link:
        return  # No GitHub issue linked
    token = settings.github_token
    if not token:
        return  # No token configured
    repo = link.get("repo", "")
    issue_number = link.get("issue_number", 0)
    if not repo or not issue_number:
        return
    try:
        if event == "completed":
            issue_sync.close_issue(token, repo, issue_number)
            issue_sync.update_issue_status(task_id, "closed")
            if notes:
                try:
                    issue_sync.add_issue_comment(token, repo, issue_number, f"✅ Kanban task completed: {notes}")
                except Exception:
                    pass
        elif event == "unclaimed":
            issue_sync.reopen_issue(token, repo, issue_number)
            issue_sync.update_issue_status(task_id, "open")
            if notes:
                try:
                    issue_sync.add_issue_comment(token, repo, issue_number, f"🔄 Kanban task reopened: {notes}")
                except Exception:
                    pass
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to sync task {task_id} to GitHub: {e}")


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: CompleteRequest = CompleteRequest()):
    await _call("complete_task", [task_id, body.result_notes])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify("completed", rows[0], body.result_notes))
        asyncio.ensure_future(_sync_to_github(task_id, "completed", body.result_notes))
    return {"status": "completed", "task_id": task_id}

@app.post("/api/tasks/{task_id}/block")
async def block_task(task_id: str, body: BlockRequest = BlockRequest()):
    await _call("block_task", [task_id, body.reason])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify("blocked", rows[0], body.reason))
    return {"status": "blocked", "task_id": task_id}

@app.post("/api/tasks/{task_id}/dependency")
async def set_dependency(task_id: str, body: SetDependencyRequest):
    await _call("set_dependency", [task_id, body.depends_on])
    return {"status": "updated", "task_id": task_id, "depends_on": body.depends_on or None}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    await _call("delete_task", [task_id])
    return {"status": "deleted"}

# ── Task Skills (Capability Tags) ──────────────────────────────────

@app.post("/api/tasks/{task_id}/skills")
async def set_task_skills(task_id: str, body: SetSkillsRequest):
    await _call("set_task_skills", [task_id, body.skills])
    return {"status": "updated", "task_id": task_id, "skills": body.skills or None}

# ── Priority Scoring / Suggestions ──────────────────────────────────

async def _row_to_agent(r: dict) -> AgentOut:
    return AgentOut(
        id=r["id"],
        host=r.get("host", ""),
        capabilities=r.get("capabilities"),
        repo_focus=r.get("repo_focus"),
        current_task_id=r.get("current_task_id"),
        status=r.get("status", "offline"),
        last_heartbeat=r.get("last_heartbeat", 0),
        first_seen=r.get("first_seen", 0),
    )


@app.post("/api/agents/register")
async def register_agent(body: AgentRegisterRequest):
    """Register or re-connect an agent in the swarm."""
    await _call("register_agent", [body.agent_id, body.host, body.capabilities, body.repo_focus])
    return {"status": "registered", "agent_id": body.agent_id}


@app.post("/api/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str, body: AgentHeartbeatRequest):
    """Send a heartbeat to the swarm."""
    await _call("agent_heartbeat", [agent_id, body.status, body.current_task_id])
    return {"status": "ok", "agent_id": agent_id}


@app.put("/api/agents/{agent_id}/capabilities")
async def set_agent_capabilities(agent_id: str, body: AgentCapabilitiesRequest):
    """Update an agent's capabilities and repo focus."""
    await _call("set_agent_capabilities", [agent_id, body.capabilities, body.repo_focus])
    return {"status": "updated", "agent_id": agent_id}


@app.get("/api/agents/health")
async def agent_health():
    """Return all agents enriched with current task details and staleness."""
    agents = await _sql("SELECT * FROM swarm_agents")
    tasks = await _sql("SELECT id, title, description, status, priority, repo FROM tasks")
    task_map = {t["id"]: t for t in tasks}

    now_ms = int(datetime.utcnow().timestamp() * 1000)
    stale_threshold = 5 * 60 * 1000  # 5 minutes

    result = []
    for r in agents:
        aid = r.get("id", "")
        current_task_id = r.get("current_task_id")
        task_info = None
        if current_task_id and current_task_id in task_map:
            t = task_map[current_task_id]
            task_info = {
                "id": t["id"],
                "title": t["title"],
                "status": t.get("status", ""),
                "priority": t.get("priority", 2),
                "repo": t.get("repo", ""),
            }

        last_hb = r.get("last_heartbeat", 0)
        age_ms = now_ms - last_hb
        stale = age_ms > stale_threshold if last_hb > 0 else True

        result.append({
            "id": aid,
            "host": r.get("host", ""),
            "status": r.get("status", "offline"),
            "capabilities": r.get("capabilities"),
            "repo_focus": r.get("repo_focus"),
            "current_task": task_info,
            "last_heartbeat": last_hb,
            "heartbeat_age_seconds": max(0, age_ms // 1000) if last_hb > 0 else -1,
            "stale": stale,
            "first_seen": r.get("first_seen", 0),
        })

    result.sort(key=lambda a: -a["last_heartbeat"])
    return result


@app.get("/api/agents", response_model=list[AgentOut])
async def list_agents():
    """List all registered swarm agents."""
    rows = await _sql("SELECT * FROM swarm_agents")
    agents = []
    for r in rows:
        a = await _row_to_agent(r)
        agents.append(a)
    agents.sort(key=lambda a: -a.last_heartbeat)
    return agents


@app.get("/api/agents/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: str):
    """Get a specific swarm agent's details."""
    rows = await _sql(f"SELECT * FROM swarm_agents WHERE id = '{agent_id}'")
    if not rows:
        raise HTTPException(404, "Agent not found")
    return await _row_to_agent(rows[0])



@app.exception_handler(404)
async def spa_fallback(request, exc):
    """Catch-all for SPA client-side routing."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    index = os.path.join(WEB_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# ── Roadmap Import ─────────────────────────────────────────────────

@app.post("/api/roadmap/import")
async def import_roadmap(body: RoadmapImportRequest):
    """Parse ROADMAP.md content and bulk-create kanban tasks."""
    import re
    lines = body.content.splitlines()
    current_phase = ""
    tasks = []
    task_count = 0

    for line in lines:
        phase_match = re.match(r"^##\s+(.+)$", line.strip())
        if phase_match:
            current_phase = phase_match.group(1).strip()
            continue

        task_match = re.match(r"^\s*-\s*\[(?P<status>[ x])\]\s+(?P<title>.+)$", line)
        if task_match:
            status = task_match.group("status")
            title = task_match.group("title").strip()
            if status == "x":
                continue
            phase_num_match = re.search(r"Phase\s+(\d+)", current_phase)
            priority = int(phase_num_match.group(1)) if phase_num_match else 3
            priority = min(max(priority - 1, 0), 3)

            tasks.append({
                "title": title,
                "description": f"From {current_phase}",
                "priority": priority,
                "repo": body.repo,
                "roadmap_item": current_phase,
                "created_by": body.created_by,
            })
            task_count += 1

            if len(tasks) >= 5:
                for t in tasks:
                    await _call("add_task", ["", t["title"], t["description"], t["priority"], t["repo"], t["roadmap_item"], t["created_by"], ""])
                tasks = []

    for t in tasks:
        await _call("add_task", ["", t["title"], t["description"], t["priority"], t["repo"], t["roadmap_item"], t["created_by"], ""])

    return {"status": "imported", "task_count": task_count}


# ── Webhook Subscriptions ────────────────────────────────────────────


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


@app.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhook subscriptions."""
    return webhooks.list_webhooks()


@app.post("/api/webhooks", status_code=201)
async def create_webhook(body: WebhookCreateRequest):
    """Register a new webhook subscription."""
    return webhooks.add_webhook(
        url=body.url,
        wh_type=body.type,
        events=body.events,
        label=body.label,
    )


@app.get("/api/webhooks/{webhook_id}")
async def get_webhook(webhook_id: str):
    """Get a specific webhook subscription."""
    wh = webhooks.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    return wh


@app.patch("/api/webhooks/{webhook_id}")
async def update_webhook(webhook_id: str, body: WebhookUpdateRequest):
    """Update a webhook subscription."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    wh = webhooks.update_webhook(webhook_id, updates)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    return wh


@app.post("/api/webhooks/{webhook_id}/test")
async def test_webhook(webhook_id: str):
    """Send a test ping to a webhook to verify it's working."""
    wh = webhooks.get_webhook(webhook_id)
    if not wh:
        raise HTTPException(404, "Webhook not found")
    test_task = {
        "id": "test_ping",
        "title": "🔔 Test notification from spacetimedb-kanban",
        "description": "This is a test event to verify your webhook configuration.",
        "priority": 0,
        "status": "available",
        "assigned_to": None,
        "repo": "spacetimedb-kanban",
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
                resp = await client.post(wh["url"], json=payload,
                    headers={"Content-Type": "application/json"} if wh["type"] == "generic" else {})
            resp.raise_for_status()
        return {"status": "sent", "webhook_id": webhook_id, "response_code": resp.status_code}
    except Exception as e:
        raise HTTPException(502, f"Webhook test failed: {str(e)[:200]}")

@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """Remove a webhook subscription."""
    if not webhooks.remove_webhook(webhook_id):
        raise HTTPException(404, "Webhook not found")
    return {"status": "deleted"}


@app.get("/api/webhooks/{webhook_id}/deliveries")
async def get_webhook_deliveries(webhook_id: str, limit: int = 20):
    """Get delivery history for a webhook."""
    return webhooks.list_webhook_deliveries(webhook_id, limit)


# ── Issue Sync ────────────────────────────────────────────────────────

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


@app.get("/api/issues")
async def list_issue_links(repo: str = ""):
    """List all kanban-task ⟷ GitHub-issue links."""
    return issue_sync.list_links(repo or None)


@app.get("/api/issues/{task_id}")
async def get_issue_link(task_id: str):
    """Get the GitHub issue link for a specific kanban task."""
    link = issue_sync.get_link(task_id)
    if not link:
        raise HTTPException(404, "No GitHub issue linked to this task")
    return {"kanban_task_id": task_id, **link}


@app.post("/api/issues/link")
async def link_issue(body: IssueLinkRequest):
    """Link a kanban task to an existing GitHub issue."""
    existing = issue_sync.get_link(body.task_id)
    if existing:
        raise HTTPException(409, f"Task already linked to {existing['html_url']}")
    link = issue_sync.link_issue(
        task_id=body.task_id,
        repo=body.repo,
        issue_number=body.issue_number,
        issue_url=body.issue_url or f"https://api.github.com/repos/{body.repo}/issues/{body.issue_number}",
        html_url=body.html_url or f"https://github.com/{body.repo}/issues/{body.issue_number}",
    )
    return {"status": "linked", **link}


@app.post("/api/issues/unlink")
async def unlink_issue(task_id: str):
    """Remove a kanban-task ⟷ GitHub-issue link."""
    if not issue_sync.unlink_issue(task_id):
        raise HTTPException(404, "No link found for this task")
    return {"status": "unlinked", "task_id": task_id}


@app.post("/api/issues/create")
async def create_issue_from_task(body: IssueCreateRequest):
    """Create a GitHub issue from a kanban task and link it."""
    # Fetch task details
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{body.task_id}'")
    if not rows:
        raise HTTPException(404, "Task not found")
    task = rows[0]

    token = settings.github_token
    if not token:
        raise HTTPException(400, "GitHub token not configured (set GITHUB_TOKEN env var)")

    repo = body.repo or settings.github_default_repo
    if not repo:
        raise HTTPException(400, "No repo specified and no github_default_repo configured")

    label_list = [l.strip() for l in body.labels.split(",") if l.strip()] if body.labels else []
    # Build issue body from task description + metadata
    issue_body = task.get("description", "") or ""
    meta = (
        f"\n\n---\n"
        f"_Created from kanban task `{body.task_id}`_"
        f"\n_Priority: {task.get('priority', 2)}_"
        f"\n_Skills: {task.get('required_skills', 'none')}_"
        f"\n_Roadmap: {task.get('roadmap_item', '—')}_"
    )
    issue_body += meta

    result = issue_sync.create_issue(token, repo, task["title"], issue_body, label_list, body.assignee or None)
    issue_sync.link_issue(body.task_id, repo, result["issue_number"], result["issue_url"], result["html_url"])
    issue_sync.update_issue_status(body.task_id, result["state"])

    # Add activity log
    try:
        await _call("add_log", [body.task_id, "github_issue_created", "", f"Issue #{result['issue_number']}: {result['html_url']}"])
    except Exception:
        pass

    return {
        "status": "created",
        "task_id": body.task_id,
        "issue_number": result["issue_number"],
        "html_url": result["html_url"],
    }


# ── GitHub Webhook ───────────────────────────────────────────────────

BRANCH_PATTERN = re.compile(
    r"^(?:feature|fix|chore|refactor|docs|test)/"
    r"kanban-([a-zA-Z0-9_]+)--"
    r".+$"
)


@app.post("/api/webhook/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events for PR linking and issue sync."""
    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()
    action = payload.get("action", "")
    repo_full = payload.get("repository", {}).get("full_name", "")

    # ── Issue events (two-way sync) ─────────────────────────────────
    if event == "issues":
        issue = payload.get("issue", {})
        issue_number = issue.get("number", 0)
        issue_title = issue.get("title", "")
        issue_html = issue.get("html_url", "")
        issue_state = issue.get("state", "open")
        issue_body = issue.get("body", "") or ""

        if action == "opened":
            # Create a kanban task linked to this issue
            # Extract the kanban task ID from the issue body (if it was created from kanban)
            task_id_match = re.search(r"kanban task `(task_\d+_[a-z0-9]+)`", issue_body)
            if task_id_match:
                # Already linked — just record the mapping
                existing_task_id = task_id_match.group(1)
                issue_sync.link_issue(existing_task_id, repo_full, issue_number, issue.get("url", ""), issue_html)
                issue_sync.update_issue_status(existing_task_id, issue_state)
                return {"status": "re-linked", "task_id": existing_task_id}

            # New issue from outside kanban — create task
            import uuid as _uuid
            gh_task_id = f"task_{_uuid.uuid4().hex[:16]}"
            await _call("add_task", [
                gh_task_id,
                issue_title,
                f"Issue #{issue_number}: {issue_html}\n\n{issue_body[:500]}",
                2,
                repo_full,
                f"GitHub Issues — {repo_full}",
                "github-webhook",
                "",
            ])
            await _call("add_log", [gh_task_id, "created", "github-webhook", f"From issue #{issue_number}: {issue_html}"])
            issue_sync.link_issue(gh_task_id, repo_full, issue_number, issue.get("url", ""), issue_html)
            issue_sync.update_issue_status(gh_task_id, issue_state)
            asyncio.ensure_future(_notify("created", {
                "title": issue_title, "id": gh_task_id, "repo": repo_full,
            }, f"Issue #{issue_number}"))
            return {"status": "created", "task_id": gh_task_id, "issue_number": issue_number}

        elif action == "closed":
            # Auto-complete the linked kanban task
            task_id = issue_sync.get_task_id_for_issue(repo_full, issue_number)
            if task_id:
                rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
                if rows and rows[0].get("status") != "done":
                    notes = f"GitHub issue #{issue_number} closed"
                    if rows[0].get("status") == "in_progress":
                        await _call("complete_task", [task_id, notes])
                    elif rows[0].get("status") == "available":
                        await _call("claim_task", [task_id, "github-webhook"])
                        await _call("complete_task", [task_id, notes])
                    else:
                        await _call("complete_task", [task_id, notes])
                    issue_sync.update_issue_status(task_id, "closed")
                    asyncio.ensure_future(_notify("completed", rows[0], notes))
                    return {"status": "completed", "task_id": task_id}
            return {"status": "ignored", "reason": "no linked task found"}

        elif action == "reopened":
            # Re-open the linked kanban task
            task_id = issue_sync.get_task_id_for_issue(repo_full, issue_number)
            if task_id:
                rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
                if rows and rows[0].get("status") == "done":
                    await _call("unclaim_task", [task_id])
                    try:
                        await _call("add_log", [task_id, "unclaimed", "github-webhook", f"Issue #{issue_number} reopened"])
                    except Exception:
                        pass
                    issue_sync.update_issue_status(task_id, "open")
                    asyncio.ensure_future(_notify("unclaimed", rows[0], f"Issue #{issue_number} reopened"))
                    return {"status": "reopened", "task_id": task_id}
            return {"status": "ignored", "reason": "no linked task or not done"}
        return {"status": "ignored", "action": action, "event": event}

    # ── PR events ───────────────────────────────────────────────────
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    pr = payload.get("pull_request", {})
    branch = (pr.get("head", {}) or {}).get("ref", "")
    pr_url = pr.get("html_url", "")
    pr_title = pr.get("title", "")

    if not branch:
        return {"status": "ignored", "reason": "no branch"}

    # Extract kanban task ID from branch name
    m = BRANCH_PATTERN.match(branch)
    if not m:
        return {"status": "ignored", "reason": "branch pattern mismatch"}

    task_id = m.group(1)

    if action == "opened" or action == "reopened":
        # Set branch field on the task — preserve original title
        try:
            rows = await _sql(f"SELECT title FROM tasks WHERE id = '{task_id}'")
            original_title = rows[0]["title"] if rows else pr_title
        except Exception:
            original_title = pr_title
        try:
            await _call("update_task", [task_id, original_title, f"PR: {pr_url}", 2, branch])
        except HTTPException:
            pass  # Task may not exist yet
        asyncio.ensure_future(_notify("linked", {
            "id": task_id,
            "title": original_title,
            "repo": payload.get("repository", {}).get("full_name", ""),
            "assigned_to": None,
        }, f"PR {pr_url}"))
        return {"status": "linked", "task_id": task_id, "action": action}

    elif action == "closed" and pr.get("merged", False):
        # Auto-complete the task when PR is merged
        notes = f"Merged via PR: {pr_url}"
        try:
            # Check if task exists and is in_progress or available
            rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
            if rows:
                t = rows[0]
                if t.get("status") == "in_progress":
                    await _call("complete_task", [task_id, notes])
                elif t.get("status") == "available":
                    # Claim as github-actions, then complete
                    await _call("claim_task", [task_id, "github-actions"])
                    await _call("complete_task", [task_id, notes])
                asyncio.ensure_future(_notify("completed", t, notes))
                return {"status": "completed", "task_id": task_id}
        except HTTPException:
            pass
        return {"status": "ignored", "reason": "task not found or not actionable"}

    return {"status": "ignored", "action": action}


@app.get("/api/logs", response_model=list[LogOut])
async def list_logs(
    task_id: Optional[str] = None,
    action: Optional[str] = None,
    agent_id: Optional[str] = None,
    search: Optional[str] = None,
    since: Optional[int] = None,
    until: Optional[int] = None,
    offset: int = 0,
    limit: int = 50,
):
    """List activity logs with filtering and pagination."""
    rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]

    # Apply filters
    if task_id:
        logs = [l for l in logs if l.task_id == task_id]
    if action:
        action_set = set(a.strip() for a in action.split(",") if a.strip())
        logs = [l for l in logs if l.action in action_set]
    if agent_id:
        logs = [l for l in logs if l.agent_id == agent_id]
    if search:
        q = search.lower()
        logs = [l for l in logs if
                (l.notes and q in l.notes.lower()) or
                q in l.task_id.lower() or
                q in l.action.lower()]
    if since:
        logs = [l for l in logs if l.timestamp >= since]
    if until:
        logs = [l for l in logs if l.timestamp <= until]

    logs.sort(key=lambda l: -l.timestamp)
    total = len(logs)
    page = logs[offset:offset + limit]
    return page


@app.get("/api/logs/stats")
async def logs_stats():
    """Get activity log summary statistics."""
    rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]

    now_ms = int(datetime.utcnow().timestamp() * 1000)
    day_ms = 86_400_000

    today = [l for l in logs if l.timestamp >= now_ms - day_ms]

    action_counts: dict[str, int] = {}
    agent_counts: dict[str, int] = {}
    for l in logs:
        action_counts[l.action] = action_counts.get(l.action, 0) + 1
        if l.agent_id:
            agent_counts[l.agent_id] = agent_counts.get(l.agent_id, 0) + 1

    # Get unique agents who have been active today
    today_agents = set()
    for l in today:
        if l.agent_id:
            today_agents.add(l.agent_id)

    return {
        "total_events": len(logs),
        "today_events": len(today),
        "active_agents_today": len(today_agents),
        "action_breakdown": action_counts,
        "top_agents": dict(sorted(agent_counts.items(), key=lambda x: -x[1])[:10]),
    }


# ── Labels ────────────────────────────────────────────────────────────


@app.get("/api/labels", response_model=list[LabelOut])
async def list_labels():
    """List all labels."""
    rows = await _sql("SELECT * FROM kanban_labels")
    return [LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                     description=r.get("description", ""), created_at=r.get("created_at", 0))
            for r in rows]


@app.post("/api/labels", status_code=201)
async def create_label(body: LabelCreate):
    """Create a new label."""
    result = await _call("add_label", [body.id, body.name, body.color, body.description])
    # Find the label we just created to return it
    rows = await _sql(f"SELECT * FROM kanban_labels WHERE name = '{body.name}'")
    if rows:
        r = rows[0]
        return LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                        description=r.get("description", ""), created_at=r.get("created_at", 0))
    return {"status": "created"}


@app.patch("/api/labels/{label_id}")
async def update_label(label_id: str, body: LabelUpdate):
    """Update a label's name, color, or description."""
    await _call("update_label", [label_id, body.name, body.color, body.description])
    rows = await _sql(f"SELECT * FROM kanban_labels WHERE id = '{label_id}'")
    if rows:
        r = rows[0]
        return LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                        description=r.get("description", ""), created_at=r.get("created_at", 0))
    return {"status": "updated"}


@app.delete("/api/labels/{label_id}")
async def delete_label(label_id: str):
    """Delete a label and remove it from all tasks."""
    await _call("remove_label", [label_id])
    return {"status": "deleted"}


class BatchLabelsRequest(BaseModel):
    task_ids: list[str]
    label_ids: list[str]


@app.post("/api/tasks/batch/labels", status_code=200)
async def batch_assign_labels(body: BatchLabelsRequest):
    """Batch assign labels to multiple tasks."""
    if not body.task_ids or not body.label_ids:
        raise HTTPException(400, "task_ids and label_ids must be non-empty")
    try:
        task_str = ",".join(body.task_ids)
        label_str = ",".join(body.label_ids)
        result = await _call("batch_assign_labels", [task_str, label_str])
        return {"status": "assigned", "result": result}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/tasks/batch/unlabels", status_code=200)
async def batch_unassign_labels(body: BatchLabelsRequest):
    """Batch unassign labels from multiple tasks."""
    if not body.task_ids or not body.label_ids:
        raise HTTPException(400, "task_ids and label_ids must be non-empty")
    try:
        task_str = ",".join(body.task_ids)
        label_str = ",".join(body.label_ids)
        result = await _call("batch_unassign_labels", [task_str, label_str])
        return {"status": "removed", "result": result}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks/{task_id}/labels", response_model=list[LabelOut])
async def get_task_labels(task_id: str):
    """Get all labels assigned to a task."""
    rows = await _sql(f"""
        SELECT l.* FROM kanban_labels l
        INNER JOIN task_label_assignments a ON l.id = a.label_id
        WHERE a.task_id = '{task_id}'
        ORDER BY l.name
    """)
    return [LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                     description=r.get("description", ""), created_at=r.get("created_at", 0))
            for r in rows]


@app.post("/api/tasks/{task_id}/labels")
async def set_task_labels(task_id: str, body: TaskLabelAssign):
    """Set labels for a task by replacing all current assignments."""
    existing = await _sql(f"SELECT label_id FROM task_label_assignments WHERE task_id = '{task_id}'")
    current_ids = {r["label_id"] for r in existing}
    new_ids = set(body.label_ids)

    # Remove any labels not in the new set
    to_remove = current_ids - new_ids
    for lid in to_remove:
        try:
            await _call("unassign_label_from_task", [task_id, lid])
        except Exception:
            pass

    # Add any labels not already assigned
    to_add = new_ids - current_ids
    for lid in to_add:
        try:
            await _call("assign_label_to_task", [task_id, lid])
        except Exception:
            pass

    return {"status": "updated", "assigned": list(new_ids)}


# ── Analytics ────────────────────────────────────────────────────────


@app.get("/api/analytics/overview")
async def analytics_overview():
    """High-level metrics: total, per-status, completed today/this week."""
    tasks = await _sql("SELECT * FROM tasks")
    logs = await _sql("SELECT * FROM task_logs")

    now = int(datetime.utcnow().timestamp() * 1000)
    day_ms = 86_400_000
    week_ms = 7 * day_ms

    total = len(tasks)
    by_status = {}
    for t in tasks:
        s = t.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    # Completed recently
    completed_today = sum(
        1 for t in tasks
        if t.get("status") == "done" and (now - t.get("updated_at", 0)) < day_ms
    )
    completed_week = sum(
        1 for t in tasks
        if t.get("status") == "done" and (now - t.get("updated_at", 0)) < week_ms
    )
    total_done = by_status.get("done", 0)

    # Repo breakdown
    repos = {}
    for t in tasks:
        r = t.get("repo") or "none"
        if r not in repos:
            repos[r] = {"total": 0, "done": 0, "in_progress": 0, "blocked": 0, "available": 0}
        repos[r]["total"] += 1
        s = t.get("status", "unknown")
        if s in repos[r]:
            repos[r][s] += 1

    return {
        "total": total,
        "by_status": by_status,
        "completed_today": completed_today,
        "completed_week": completed_week,
        "total_done": total_done,
        "repos": repos,
        "agent_count": len(await _sql("SELECT * FROM swarm_agents")),
    }


@app.get("/api/analytics/throughput")
async def analytics_throughput(days: int = 14):
    """Tasks completed per day for the last N days."""
    rows = await _sql("SELECT * FROM tasks")
    now = int(datetime.utcnow().timestamp() * 1000)
    day_ms = 86_400_000

    # Build a map of date -> count (only done tasks)
    daily: dict[str, int] = {}
    for t in rows:
        if t.get("status") != "done":
            continue
        updated = t.get("updated_at", 0)
        age_days = (now - updated) // day_ms
        if age_days > days:
            continue
        # Use actual date string
        dt = datetime.utcfromtimestamp(updated / 1000)
        date_str = dt.strftime("%b %d")
        daily[date_str] = daily.get(date_str, 0) + 1

    # Fill in missing days
    result = []
    for i in range(days, -1, -1):
        dt = datetime.utcfromtimestamp((now - i * day_ms) / 1000)
        date_str = dt.strftime("%b %d")
        result.append({"date": date_str, "completed": daily.get(date_str, 0)})
    return result


@app.get("/api/analytics/cycle-times")
async def analytics_cycle_times():
    """Average time from created to done per repo."""
    logs = await _sql("SELECT * FROM task_logs")

    # Group logs by task_id and find created vs completed timestamps
    task_times: dict[str, dict] = {}
    for log in logs:
        tid = log.get("task_id", "")
        action = log.get("action", "")
        ts = log.get("timestamp", 0)
        if tid not in task_times:
            task_times[tid] = {}
        if action == "created":
            task_times[tid]["created"] = ts
        elif action == "completed":
            task_times[tid]["completed"] = ts

    # Fetch task repos
    tasks = await _sql("SELECT * FROM tasks")
    task_repo = {t["id"]: t.get("repo", "") for t in tasks}

    repo_cycles: dict[str, list[int]] = {}
    for tid, times in task_times.items():
        if "created" in times and "completed" in times:
            cycle_ms = times["completed"] - times["created"]
            if cycle_ms > 0:
                repo = task_repo.get(tid, "")
                if repo not in repo_cycles:
                    repo_cycles[repo] = []
                repo_cycles[repo].append(cycle_ms)

    result = []
    for repo, cycles in sorted(repo_cycles.items()):
        avg_ms = sum(cycles) / len(cycles)
        result.append({
            "repo": repo or "(none)",
            "count": len(cycles),
            "avg_hours": round(avg_ms / 3_600_000, 1),
            "min_hours": round(min(cycles) / 3_600_000, 1),
            "max_hours": round(max(cycles) / 3_600_000, 1),
        })
    return result


@app.get("/api/analytics/agents")
async def analytics_agents():
    """Per-agent stats: tasks completed, stale rate."""
    agents = await _sql("SELECT * FROM swarm_agents")
    logs = await _sql("SELECT * FROM task_logs")
    tasks = await _sql("SELECT * FROM tasks")

    # Count completed tasks per agent from logs
    agent_completions: dict[str, int] = {}
    agent_stales: dict[str, int] = {}
    for log in logs:
        agent = log.get("agent_id") or ""
        action = log.get("action", "")
        if agent:
            if action == "completed":
                agent_completions[agent] = agent_completions.get(agent, 0) + 1
            elif action == "blocked":
                agent_stales[agent] = agent_stales.get(agent, 0) + 1

    result = []
    for a in agents:
        aid = a.get("id", "")
        result.append({
            "id": aid,
            "status": a.get("status", "offline"),
            "completed": agent_completions.get(aid, 0),
            "blocked": agent_stales.get(aid, 0),
            "capabilities": a.get("capabilities"),
            "repo_focus": a.get("repo_focus"),
            "last_heartbeat": a.get("last_heartbeat", 0),
        })
    return result


# ─── Auto-star GitHub repo on startup ────────────────────────────────────────

import threading as _threading
import urllib.request as _urllib_request
import os as _os
import logging as _logging

_logger = _logging.getLogger(__name__)


def _auto_star(repo: str):
    import time

    time.sleep(8)
    token = _os.environ.get("GITHUB_TOKEN") or _os.environ.get("ACC_GITHUB_TOKEN")
    if not token:
        return
    try:
        req = _urllib_request.Request(
            f"https://api.github.com/user/starred/{repo}",
            method="PUT",
            data=b"",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": f"{repo.split('/')[-1]}/1.0",
            },
        )
        with _urllib_request.urlopen(req, timeout=10) as resp:
            if resp.status == 204 or resp.status == 200:
                _logger.info(f"⭐ Starred {repo}")
            elif resp.status == 409:
                _logger.info(f"⭐ Already starred {repo}")
            else:
                _logger.warning(f"Failed to star {repo}: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        if e.code == 204 or e.code == 409:
            return  # success variants
        _logger.warning(f"Failed to star {repo}: HTTP {e.code}")
    except Exception as e:
        _logger.warning(f"Could not reach GitHub API: {e}")


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _threading.Thread(
        target=_auto_star, args=("omiinaya/spacetimedb-kanban",), daemon=True
    ).start()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.server_port, reload=True)
