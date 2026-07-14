"""Label endpoints for spacetimedb-kanban."""

from fastapi import APIRouter, Depends

from shared import _call, _sql, _sql_param, verify_auth
from shared import LabelCreate, LabelOut, LabelUpdate

router = APIRouter()


@router.get("/api/labels", response_model=list[LabelOut])
async def list_labels():
    """List all labels."""
    rows = await _sql("SELECT * FROM kanban_labels")
    return [LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                     description=r.get("description", ""), created_at=r.get("created_at", 0))
            for r in rows]


@router.post("/api/labels", status_code=201, dependencies=[Depends(verify_auth)])
async def create_label(body: LabelCreate):
    """Create a new label."""
    result = await _call("add_label", [body.id, body.name, body.color, body.description])
    # Find the label we just created to return it
    rows = await _sql_param("SELECT * FROM kanban_labels WHERE name = '{name}'", name=body.name)
    if rows:
        r = rows[0]
        return LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                        description=r.get("description", ""), created_at=r.get("created_at", 0))
    return {"status": "created"}


@router.patch("/api/labels/{label_id}", dependencies=[Depends(verify_auth)])
async def update_label(label_id: str, body: LabelUpdate):
    """Update a label's name, color, or description."""
    await _call("update_label", [label_id, body.name, body.color, body.description])
    rows = await _sql_param("SELECT * FROM kanban_labels WHERE id = '{label_id}'", label_id=label_id)
    if rows:
        r = rows[0]
        return LabelOut(id=r["id"], name=r["name"], color=r.get("color", "#0ea5e9"),
                        description=r.get("description", ""), created_at=r.get("created_at", 0))
    return {"status": "updated"}


@router.delete("/api/labels/{label_id}", dependencies=[Depends(verify_auth)])
async def delete_label(label_id: str):
    """Delete a label and remove it from all tasks."""
    await _call("remove_label", [label_id])
    return {"status": "deleted"}
