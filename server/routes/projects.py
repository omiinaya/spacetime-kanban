"""Project endpoints for spacetimedb-kanban."""

import time

from fastapi import APIRouter, Depends, HTTPException

from shared import ProjectCreate, ProjectOut, ProjectUpdate, _call, _sql, _sql_param, verify_auth

router = APIRouter()


@router.get("/api/projects", response_model=list[ProjectOut])
async def list_projects():
    """List all registered projects."""
    rows = await _sql("SELECT * FROM kanban_projects")
    return [
        ProjectOut(
            id=r["id"],
            name=r.get("name", r["id"]),
            description=r.get("description", ""),
            color=r.get("color", "#6b7280"),
            priority=r.get("priority", 2),
            active=r.get("active", True),
            created_at=r.get("created_at", 0),
            updated_at=r.get("updated_at", 0),
        )
        for r in rows
    ]


@router.post("/api/projects", status_code=201, dependencies=[Depends(verify_auth)])
async def create_project(body: ProjectCreate):
    """Register a new project/repo with priority."""
    if not body.id:
        raise HTTPException(400, "id (repo slug) is required")
    await _call(
        "add_project",
        [
            body.id,
            body.name,
            body.description,
            body.color,
            body.priority,
            body.active,
        ],
    )
    rows = await _sql_param("SELECT * FROM kanban_projects WHERE id = '{id}'", id=body.id)
    if rows:
        r = rows[0]
        return ProjectOut(
            id=r["id"],
            name=r.get("name", r["id"]),
            description=r.get("description", ""),
            color=r.get("color", "#6b7280"),
            priority=r.get("priority", 2),
            active=r.get("active", True),
            created_at=r.get("created_at", 0),
            updated_at=r.get("updated_at", 0),
        )
    return {"status": "created"}


@router.patch("/api/projects/{project_id}", dependencies=[Depends(verify_auth)])
async def update_project(project_id: str, body: ProjectUpdate):
    """Update a project's priority, name, colour, or active status."""
    # If priority wasn't provided, fetch current value from DB
    if body.priority is None:
        rows = await _sql_param(
            "SELECT priority FROM kanban_projects WHERE id = '{project_id}'", project_id=project_id
        )
        prio = rows[0]["priority"] if rows else 2
    else:
        prio = body.priority
    await _call(
        "update_project",
        [
            project_id,
            body.name,
            body.description,
            body.color,
            prio,
            body.active,
        ],
    )
    rows = await _sql_param(
        "SELECT * FROM kanban_projects WHERE id = '{project_id}'", project_id=project_id
    )
    if rows:
        r = rows[0]
        return ProjectOut(
            id=r["id"],
            name=r.get("name", r["id"]),
            description=r.get("description", ""),
            color=r.get("color", "#6b7280"),
            priority=r.get("priority", 2),
            active=r.get("active", True),
            created_at=r.get("created_at", 0),
            updated_at=r.get("updated_at", 0),
        )
    return {"status": "updated"}


@router.delete("/api/projects/{project_id}", dependencies=[Depends(verify_auth)])
async def delete_project(project_id: str):
    """Delete a project registration."""
    await _call("delete_project", [project_id])
    return {"status": "deleted"}


@router.get("/api/suggest-by-project", response_model=list[dict])
async def suggest_by_project(limit: int = 10):
    """Return top-N suggested tasks using project-aware scoring engine (STDB reducer)."""
    try:
        result = await _call("suggest_tasks_by_project", [limit])
        if isinstance(result, dict) and "status" in result:
            return [{"notice": "reducer returned ok — no data"}]
        return result
    except HTTPException:
        pass
    # Fallback: compute via API
    rows = await _sql("SELECT * FROM tasks")
    projects = await _sql("SELECT id, priority, active FROM kanban_projects")
    proj_map = {p["id"]: p["priority"] for p in projects if p.get("active")}
    now_ms = int(time.time() * 1000)
    scored = []
    for t in rows:
        base = max(100 - t.get("priority", 128), 0)
        repo = t.get("repo", "")
        proj_boost = 0
        if repo and repo in proj_map:
            proj_boost = max(100 - proj_map[repo], 0)
        age_hours = (now_ms - t.get("created_at", now_ms)) / 3_600_000
        stale_bonus = min(int(age_hours), 40)
        score = base + proj_boost + stale_bonus
        parts = [f"score={score}", f"base={base}"]
        if proj_boost:
            parts.append(f"project_boost={proj_boost}")
        if stale_bonus > 0:
            parts.append(f"stale_bonus={stale_bonus}")
        scored.append(
            {
                "task_id": t["id"],
                "repo": repo,
                "title": t["title"],
                "score": score,
                "reason": " + ".join(parts),
            }
        )
    scored.sort(key=lambda x: -x["score"])
    return scored[:limit]
