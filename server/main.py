import json
import uuid
from typing import Any, Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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

class CompleteRequest(BaseModel):
    result_notes: str = ""

class LogOut(BaseModel):
    id: str
    task_id: str
    action: str
    agent_id: Optional[str] = None
    notes: Optional[str] = None
    timestamp: int

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
                if val[0] == 1 and val[1] is not None and val[1] != []:
                    val = val[1]
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
    return {"status": "claimed", "task_id": task_id, "assigned_to": body.agent_id}

@app.post("/api/tasks/{task_id}/unclaim")
async def unclaim_task(task_id: str):
    await _call("unclaim_task", [task_id])
    return {"status": "unclaimed", "task_id": task_id}

@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: CompleteRequest = CompleteRequest()):
    await _call("complete_task", [task_id, body.result_notes])
    return {"status": "completed", "task_id": task_id}

@app.post("/api/tasks/{task_id}/block")
async def block_task(task_id: str, body: BlockRequest = BlockRequest()):
    await _call("block_task", [task_id, body.reason])
    return {"status": "blocked", "task_id": task_id}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    await _call("delete_task", [task_id])
    return {"status": "deleted"}

@app.post("/api/tasks/seed")
async def seed_tasks():
    await _call("seed_sample_tasks", [])
    return {"status": "seeded"}

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

# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.server_port, reload=True)
