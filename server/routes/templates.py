"""Task template endpoints for spacetimedb-kanban."""

import uuid

from fastapi import APIRouter, HTTPException

from shared import (
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
    _call,
    _row_to_template,
    _sql,
    _sql_param,
)

router = APIRouter()


@router.get("/api/task-templates", response_model=list[TemplateOut])
async def list_task_templates():
    rows = await _sql("SELECT * FROM task_templates")
    return [_row_to_template(r) for r in rows]


@router.post("/api/task-templates", status_code=201, response_model=TemplateOut)
async def create_task_template(body: TemplateCreate):
    template_id = f"tpl_{uuid.uuid4().hex[:12]}"
    await _call(
        "add_task_template",
        [
            template_id,
            body.title,
            body.description,
            body.priority,
            body.repo,
            body.roadmap_item,
            body.required_skills,
            body.cron_schedule,
            body.created_by,
        ],
    )
    rows = await _sql_param("SELECT * FROM task_templates WHERE id = '{id}'", id=template_id)
    if not rows:
        raise HTTPException(500, "Template not found after creation")
    return _row_to_template(rows[0])


@router.patch("/api/task-templates/{template_id}")
async def update_task_template(template_id: str, body: TemplateUpdate):
    rows = await _sql_param("SELECT * FROM task_templates WHERE id = '{id}'", id=template_id)
    if not rows:
        raise HTTPException(404, "Template not found")

    await _call(
        "update_task_template",
        [
            template_id,
            body.title,
            body.description,
            body.priority if body.priority != 128 else 2,  # sentinel for no change
            body.repo,
            body.roadmap_item,
            body.required_skills,
            body.cron_schedule,
            body.active,
        ],
    )
    rows = await _sql_param("SELECT * FROM task_templates WHERE id = '{id}'", id=template_id)
    return _row_to_template(rows[0]) if rows else None


@router.delete("/api/task-templates/{template_id}")
async def delete_task_template(template_id: str):
    try:
        await _call("remove_task_template", [template_id])
        return {"status": "deleted"}
    except RuntimeError as e:
        if "not found" in str(e).lower():
            raise HTTPException(404, "Template not found") from e
        raise HTTPException(500, str(e)) from e


@router.post("/api/task-templates/trigger")
async def trigger_task_templates():
    """Check all active templates and create tasks for due ones. Returns stats."""
    try:
        await _call("trigger_task_templates", [])
        # Read the most recent trigger log to get stats
        # STDB SQL doesn't support ORDER BY + LIMIT — fetch all and sort in Python
        logs = await _sql("SELECT * FROM task_logs WHERE action = 'trigger_task_templates'")
        if logs:
            logs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return {"status": "triggered", "notes": logs[0].get("notes", "")}
        return {"status": "triggered", "notes": "completed"}
    except Exception as e:
        raise HTTPException(500, f"Trigger failed: {e}") from e
