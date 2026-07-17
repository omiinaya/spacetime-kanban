"""Extracted from main.py during route thinning (pure move, logic verbatim)."""

from fastapi import APIRouter, Depends, HTTPException

from shared import (
    AutomationRuleCreate,
    AutomationRuleOut,
    AutomationRuleUpdate,
    _call,
    _sql,
    _sql_param,
    verify_auth,
)

router = APIRouter()


@router.get("/api/rules", response_model=list[AutomationRuleOut])
async def list_automation_rules():
    """List all automation rules."""
    rows = await _sql("SELECT * FROM automation_rules")
    return [
        AutomationRuleOut(
            id=r["id"],
            name=r.get("name", ""),
            description=r.get("description", ""),
            trigger_event=r.get("trigger_event", ""),
            condition=r.get("condition"),
            action_type=r.get("action_type", ""),
            action_config=r.get("action_config", ""),
            repo=r.get("repo"),
            active=r.get("active", True),
            created_at=r.get("created_at", 0),
            updated_at=r.get("updated_at", 0),
        )
        for r in rows
    ]


@router.post("/api/rules", status_code=201, dependencies=[Depends(verify_auth)])
async def create_automation_rule(body: AutomationRuleCreate):
    """Create a new automation rule."""
    import uuid as _uuid

    rule_id = body.id or f"rule_{_uuid.uuid4().hex[:16]}"
    await _call(
        "create_automation_rule",
        [
            rule_id,
            body.name,
            body.description,
            body.trigger_event,
            body.condition,
            body.action_type,
            body.action_config,
            body.repo,
            body.active,
        ],
    )
    return {"status": "created", "id": rule_id}


@router.get("/api/rules/{rule_id}", response_model=AutomationRuleOut)
async def get_automation_rule(rule_id: str):
    """Get a single automation rule."""
    rows = await _sql_param(
        "SELECT * FROM automation_rules WHERE id = '{rule_id}'",
        rule_id=rule_id,
    )
    if not rows:
        raise HTTPException(404, "Rule not found")
    r = rows[0]
    return AutomationRuleOut(
        id=r["id"],
        name=r.get("name", ""),
        description=r.get("description", ""),
        trigger_event=r.get("trigger_event", ""),
        condition=r.get("condition"),
        action_type=r.get("action_type", ""),
        action_config=r.get("action_config", ""),
        repo=r.get("repo"),
        active=r.get("active", True),
        created_at=r.get("created_at", 0),
        updated_at=r.get("updated_at", 0),
    )


@router.patch("/api/rules/{rule_id}", dependencies=[Depends(verify_auth)])
async def update_automation_rule(rule_id: str, body: AutomationRuleUpdate):
    """Update an automation rule."""
    rows = await _sql_param(
        "SELECT * FROM automation_rules WHERE id = '{rule_id}'",
        rule_id=rule_id,
    )
    if not rows:
        raise HTTPException(404, "Rule not found")
    existing = rows[0]
    name = body.name if body.name is not None else existing.get("name", "")
    description = (
        body.description if body.description is not None else existing.get("description", "")
    )
    trigger_event = (
        body.trigger_event if body.trigger_event is not None else existing.get("trigger_event", "")
    )
    condition = body.condition if body.condition is not None else existing.get("condition") or ""
    action_type = (
        body.action_type if body.action_type is not None else existing.get("action_type", "")
    )
    action_config = (
        body.action_config if body.action_config is not None else existing.get("action_config", "")
    )
    repo = body.repo if body.repo is not None else existing.get("repo") or ""
    active = body.active if body.active is not None else existing.get("active", True)
    await _call(
        "update_automation_rule",
        [
            rule_id,
            name,
            description,
            trigger_event,
            condition,
            action_type,
            action_config,
            repo,
            active,
        ],
    )
    return {"status": "updated", "id": rule_id}


@router.delete("/api/rules/{rule_id}", dependencies=[Depends(verify_auth)])
async def delete_automation_rule(rule_id: str):
    """Delete an automation rule."""
    await _call("delete_automation_rule", [rule_id])
    return {"status": "deleted"}
