"""
Response formatting helpers for spacetimedb-kanban.

Converts STDB row dicts into Pydantic models.
Uses deferred imports to avoid circular dependencies with shared.py.
"""

from typing import Any


def _row_to_task(r: dict) -> Any:
    """Convert a STDB task row to a TaskOut model."""
    from models import TaskOut

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
        subtasks=r.get("subtaks"),
        due_by=r.get("due_by"),
        sprint=r.get("sprint"),
        archived=r.get("archived", False),
        estimated_hours=r.get("estimated_hours"),
        spent_hours=r.get("spent_hours"),
    )


def _row_to_log(r: dict) -> Any:
    """Convert a STDB log row to a LogOut model."""
    from models import LogOut

    return LogOut(
        id=r["id"],
        task_id=r["task_id"],
        action=r["action"],
        agent_id=r.get("agent_id"),
        notes=r.get("notes"),
        timestamp=r.get("timestamp", 0),
    )


def _row_to_agent(r: dict) -> Any:
    """Convert a STDB swarm_agents row to an AgentOut model."""
    from models import AgentOut

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


def _row_to_template(r: dict) -> Any:
    """Convert a STDB template row to a TemplateOut model."""
    from models import TemplateOut

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
