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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings

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

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    created_by: str = "web-ui"

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    branch: Optional[str] = None

class ClaimRequest(BaseModel):
    agent_id: str

class BlockRequest(BaseModel):
    reason: str = ""

class SetDependencyRequest(BaseModel):
    depends_on: str = ""  # empty string to clear

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
    )


async def _notify_discord(action: str, task: dict, extra: str = ""):
    """Send a Discord webhook notification for a task event."""
    if not settings.discord_webhook_url:
        return
    emoji = {
        "created": "🆕",
        "claimed": "👤",
        "unclaimed": "↩️",
        "completed": "✅",
        "blocked": "🚧",
    }.get(action, "🔔")
    color = {
        "created": 0x5865F2,
        "claimed": 0xFEE75C,
        "unclaimed": 0x808080,
        "completed": 0x57F287,
        "blocked": 0xED4245,
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
    if agent:
        embed["embeds"][0]["fields"].append({"name": "Agent", "value": agent, "inline": True})
    if extra and action in ("blocked", "completed"):
        embed["embeds"][0]["fields"].append({"name": "Notes", "value": extra[:500], "inline": False})
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(settings.discord_webhook_url, json=embed)
    except Exception:
        pass  # notifications are best-effort

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

@app.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(status: Optional[str] = None, repo: Optional[str] = None):
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
    tasks.sort(key=lambda t: (t.priority, -t.created_at))
    return tasks

@app.get("/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if not rows:
        raise HTTPException(404, "Task not found")
    return _row_to_task(rows[0])

@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskCreate):
    await _call("add_task", [
        body.title,
        body.description,
        body.priority,
        body.repo,
        body.roadmap_item,
        body.created_by,
    ])
    asyncio.ensure_future(_notify_discord("created", {
        "title": body.title,
        "id": "pending",
        "repo": body.repo,
    }, body.created_by))
    return {"status": "created"}

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
        asyncio.ensure_future(_notify_discord("claimed", rows[0]))
    return {"status": "claimed", "task_id": task_id, "assigned_to": body.agent_id}

@app.post("/api/tasks/{task_id}/unclaim")
async def unclaim_task(task_id: str):
    await _call("unclaim_task", [task_id])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify_discord("unclaimed", rows[0]))
    return {"status": "unclaimed", "task_id": task_id}

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: CompleteRequest = CompleteRequest()):
    await _call("complete_task", [task_id, body.result_notes])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify_discord("completed", rows[0], body.result_notes))
    return {"status": "completed", "task_id": task_id}

@app.post("/api/tasks/{task_id}/block")
async def block_task(task_id: str, body: BlockRequest = BlockRequest()):
    await _call("block_task", [task_id, body.reason])
    rows = await _sql(f"SELECT * FROM tasks WHERE id = '{task_id}'")
    if rows:
        asyncio.ensure_future(_notify_discord("blocked", rows[0], body.reason))
    return {"status": "blocked", "task_id": task_id}

@app.post("/api/tasks/{task_id}/dependency")
async def set_dependency(task_id: str, body: SetDependencyRequest):
    await _call("set_dependency", [task_id, body.depends_on])
    return {"status": "updated", "task_id": task_id, "depends_on": body.depends_on or None}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    await _call("delete_task", [task_id])
    return {"status": "deleted"}

@app.post("/api/tasks/seed")
async def seed_tasks():
    await _call("seed_sample_tasks", [])
    return {"status": "seeded"}

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
                    await _call("add_task", [t["title"], t["description"], t["priority"], t["repo"], t["roadmap_item"], t["created_by"]])
                tasks = []

    for t in tasks:
        await _call("add_task", [t["title"], t["description"], t["priority"], t["repo"], t["roadmap_item"], t["created_by"]])

    return {"status": "imported", "task_count": task_count}


# ── GitHub Webhook ─────────────────────────────────────��───────────

BRANCH_PATTERN = re.compile(
    r"^(?:feature|fix|chore|refactor|docs|test)/"
    r"kanban-([a-zA-Z0-9_]+)--"
    r".+$"
)


@app.post("/api/webhook/github")
async def github_webhook(request: Request):
    """Receive GitHub webhook events for PR linking."""
    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    payload = await request.json()
    action = payload.get("action", "")
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
        # Set branch field on the task
        try:
            await _call("update_task", [task_id, pr_title, "", 2, branch])
        except HTTPException:
            pass  # Task may not exist yet
        try:
            await _call("update_task", [task_id, pr_title, f"PR: {pr_url}", 2, branch])
        except HTTPException:
            pass
        asyncio.ensure_future(_notify_discord("linked", {
            "id": task_id,
            "title": pr_title,
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
                asyncio.ensure_future(_notify_discord("completed", t, notes))
                return {"status": "completed", "task_id": task_id}
        except HTTPException:
            pass
        return {"status": "ignored", "reason": "task not found or not actionable"}

    return {"status": "ignored", "action": action}


@app.get("/api/logs", response_model=list[LogOut])
async def list_logs(task_id: Optional[str] = None, limit: int = 50):
    if task_id:
        rows = await _sql(f"SELECT * FROM task_logs WHERE task_id = '{task_id}'")
    else:
        rows = await _sql("SELECT * FROM task_logs")
    logs = [_row_to_log(r) for r in rows]
    logs.sort(key=lambda l: -l.timestamp)
    return logs[:limit]

@app.get("/api/agents")
async def list_agents():
    """List currently active agents (assigned to in_progress tasks)."""
    rows = await _sql("SELECT assigned_to FROM tasks WHERE status = 'in_progress'")
    seen: set[str] = set()
    for r in rows:
        val = r.get("assigned_to")
        if val and isinstance(val, str):
            seen.add(val)
    return {"agents": sorted(seen)}

@app.exception_handler(404)
async def spa_fallback(request, exc):
    """Catch-all for SPA client-side routing."""
    if request.url.path.startswith("/api/"):
        raise exc
    index = os.path.join(WEB_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(index)
    raise exc

# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.server_port, reload=True)
