"""Task endpoints for spacetimedb-kanban."""

import asyncio
import contextlib
import csv
import io
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response

from shared import (
    AddLogRequest,
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
    LabelOut,
    MaxAttemptsRequest,
    ReorderRequest,
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
    TimeEstimatesRequest,
    _call,
    _compute_score,
    _notify,
    _row_to_task,
    _sql,
    _sql_param,
    verify_auth,
)
from webhook_dispatcher import fire_event, EVENT_TASK_BLOCKED, EVENT_TASK_COMPLETED

router = APIRouter()


# ── Task Suggestion (MUST be before /api/tasks/{task_id}) ─────────────


@router.get("/api/tasks/suggest", response_model=list[SuggestResult])
async def suggest_tasks(agent_id: str | None = None, limit: int = 5):
    """Return top-N recommended tasks based on priority scoring."""
    rows = await _sql("SELECT * FROM tasks WHERE status = 'available'")

    # Get agent capabilities if agent_id provided
    agent_caps = None
    if agent_id:
        try:
            agent_rows = await _sql_param(
                "SELECT capabilities FROM swarm_agents WHERE id = '{id}'", id=agent_id
            )
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


# ── Task List (MUST be before /api/tasks/{task_id}) ────────────────────


@router.get("/api/tasks", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = None,
    repo: str | None = None,
    label: str | None = None,
    search: str | None = None,
    limit: int = 2000,
):
    # If label filter provided, first get task IDs with that label
    label_task_ids: set[str] | None = None
    if label:
        rows = await _sql_param(
            "SELECT task_id FROM task_label_assignments WHERE label_id = '{label}'", label=label
        )
        label_task_ids = {r["task_id"] for r in rows}

    sql = "SELECT * FROM tasks"
    filters = []
    params: dict[str, str] = {}
    if status:
        filters.append("status = '{status}'")
        params["status"] = status
    if repo:
        filters.append("repo = '{repo}'")
        params["repo"] = repo
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    # Server-side LIMIT — 2000 default, 5000 hard cap
    sql += f" LIMIT {min(limit, 5000)}"
    if params:
        rows = await _sql_param(sql, **params)
    else:
        rows = await _sql(sql)
    tasks = [_row_to_task(r) for r in rows]
    if label_task_ids is not None:
        tasks = [t for t in tasks if t.id in label_task_ids]
    # Apply client-side search filter (STDB SQL has no ILIKE — do it in Python)
    if search:
        q = search.lower()
        tasks = [
            t
            for t in tasks
            if q in t.title.lower()
            or q in t.description.lower()
            or q in t.repo.lower()
            or (t.assigned_to and q in t.assigned_to.lower())
            or q in t.id.lower()
        ]
    tasks.sort(key=lambda t: (t.priority, -t.created_at))
    return tasks


# ── Seed / Clear / Export (MUST be before /api/tasks/{task_id}) ────────


@router.post("/api/tasks/seed", dependencies=[Depends(verify_auth)])
async def seed_tasks():
    """Seed sample tasks into the database."""
    await _call("seed_sample_tasks", [])
    return {"status": "seeded"}


@router.post("/api/tasks/clear", dependencies=[Depends(verify_auth)])
async def clear_all_tasks():
    """Delete ALL tasks via the delete_task reducer. Board reset."""
    rows = await _sql("SELECT id FROM tasks")
    deleted = 0
    for row in rows:
        tid = row.get("id")
        if tid:
            try:
                await _call("delete_task", [tid])
                deleted += 1
            except Exception:
                pass
    return {"status": "cleared", "deleted": deleted}


@router.get("/api/tasks/export")
async def export_tasks(format: str = "json", status: str = "", repo: str = ""):
    """Export tasks as CSV or JSON with optional filters."""
    sql = "SELECT * FROM tasks"
    filters = []
    params: dict[str, str] = {}
    if status:
        filters.append("status = '{status}'")
        params["status"] = status
    if repo:
        filters.append("repo = '{repo}'")
        params["repo"] = repo
    if filters:
        sql += " WHERE " + " AND ".join(filters)
    if params:
        rows = await _sql_param(sql, **params)
    else:
        rows = await _sql(sql)

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "title",
                "description",
                "priority",
                "status",
                "assigned_to",
                "repo",
                "branch",
                "roadmap_item",
                "created_by",
                "created_at",
                "updated_at",
                "depends_on",
                "required_skills",
                "score",
                "due_by",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.get("id", ""),
                    r.get("title", ""),
                    r.get("description", ""),
                    r.get("priority", 2),
                    r.get("status", ""),
                    r.get("assigned_to", ""),
                    r.get("repo", ""),
                    r.get("branch", ""),
                    r.get("roadmap_item", ""),
                    r.get("created_by", ""),
                    r.get("created_at", 0),
                    r.get("updated_at", 0),
                    r.get("depends_on", ""),
                    r.get("required_skills", ""),
                    r.get("score", 0),
                    r.get("due_by", ""),
                ]
            )
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


# ── Reorder (MUST be before /api/tasks/{task_id}) ──────────────────────


@router.post("/api/tasks/reorder", dependencies=[Depends(verify_auth)])
async def reorder_task(body: ReorderRequest):
    """Set a task's position for custom ordering."""
    await _call("reorder_task", [body.task_id, body.position])
    return {"status": "reordered", "task_id": body.task_id, "position": body.position}


@router.post("/api/tasks/bulk-reorder", dependencies=[Depends(verify_auth)])
async def bulk_reorder_tasks(body: BulkReorderRequest):
    """Bulk-set positions for multiple tasks (e.g. drag-drop within a column)."""
    items_json = json.dumps([{"task_id": it.task_id, "position": it.position} for it in body.items])
    await _call("bulk_reorder_tasks", [items_json])
    return {"status": "reordered", "count": len(body.items)}


# ── Batch Label Ops (MUST be before /api/tasks/{task_id}) ──────────────


@router.post("/api/tasks/batch/labels", status_code=200, dependencies=[Depends(verify_auth)])
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
        raise HTTPException(400, str(e)) from e


@router.post("/api/tasks/batch/unlabels", status_code=200, dependencies=[Depends(verify_auth)])
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
        raise HTTPException(400, str(e)) from e


# ── Task CRUD ──────────────────────────────────────────────────────────


@router.get("/api/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if not rows:
        raise HTTPException(404, "Task not found")
    return _row_to_task(rows[0])


@router.post("/api/tasks", status_code=201, dependencies=[Depends(verify_auth)])
async def create_task(body: TaskCreate):
    import uuid as _uuid

    # ── DEDUP: check for existing task with same title+repo that isn't done ──
    if body.title and body.repo:
        sanitized_title = body.title.replace("'", "''")
        sanitized_repo = body.repo.replace("'", "''")
        existing = await _sql_param(
            "SELECT id, status FROM tasks WHERE title = '{title}' "
            "AND repo = '{repo}' AND status != 'done' LIMIT 1",
            title=sanitized_title,
            repo=sanitized_repo,
        )
        if existing:
            return {
                "status": "exists",
                "id": existing[0]["id"],
                "message": f"Task with same title already exists in {body.repo} (status: {existing[0]['status']})",
            }

    task_id = f"task_{_uuid.uuid4().hex[:16]}"
    await _call(
        "add_task",
        [
            task_id,
            body.title,
            body.description,
            body.priority,
            body.repo,
            body.roadmap_item,
            body.created_by,
            body.status,
            body.due_by if body.due_by is not None else 0,
        ],
    )
    # Set skills if provided — using known task_id, no race condition
    if body.required_skills:
        await _call("set_task_skills", [task_id, body.required_skills])
    asyncio.ensure_future(
        _notify(
            "created",
            {
                "title": body.title,
                "id": task_id,
                "repo": body.repo,
            },
            body.created_by,
        )
    )
    return {"status": "created", "id": task_id}


@router.patch("/api/tasks/{task_id}", dependencies=[Depends(verify_auth)])
async def patch_task(task_id: str, body: TaskUpdate):
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if not rows:
        raise HTTPException(404, "Task not found")
    t = rows[0]
    title = body.title if body.title is not None else t.get("title", "")
    desc = body.description if body.description is not None else t.get("description", "")
    priority = body.priority if body.priority is not None else t.get("priority", 2)
    branch = body.branch if body.branch is not None else t.get("branch", "") or ""
    await _call("update_task", [task_id, title, desc, priority, branch])
    # Handle due_by separately via set_due_by reducer
    if body.due_by is not None:
        await _call("set_due_by", [task_id, body.due_by])
    elif "due_by" in body.model_dump(exclude_unset=True):
        # User explicitly set due_by to null — clear it
        await _call("set_due_by", [task_id, 0])
    # Handle sprint
    if body.sprint is not None:
        await _call("set_sprint", [task_id, body.sprint])
    elif "sprint" in body.model_dump(exclude_unset=True):
        # User explicitly set sprint to null — clear it
        await _call("set_sprint", [task_id, ""])
    # Handle archived
    if body.archived is not None:
        if body.archived:
            await _call("archive_task", [task_id])
        else:
            await _call("unarchive_task", [task_id])
    # Handle time estimates
    if body.estimated_hours is not None or body.spent_hours is not None:
        est = (
            body.estimated_hours
            if body.estimated_hours is not None
            else t.get("estimated_hours") or 0
        )
        spent = body.spent_hours if body.spent_hours is not None else t.get("spent_hours") or 0
        await _call("set_time_estimates", [task_id, est, spent])
    return {"status": "updated"}


@router.delete("/api/tasks/{task_id}", dependencies=[Depends(verify_auth)])
async def delete_task(task_id: str):
    await _call("delete_task", [task_id])
    return {"status": "deleted"}


# ── Task Lifecycle ─────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/claim", dependencies=[Depends(verify_auth)])
async def claim_task(task_id: str, body: ClaimRequest):
    await _call("claim_task", [task_id, body.agent_id])
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if rows:
        asyncio.ensure_future(_notify("claimed", rows[0]))
    return {"status": "claimed", "task_id": task_id, "assigned_to": body.agent_id}


async def _sync_to_github(task_id: str, event: str, notes: str = ""):
    """Push a kanban task state change back to a linked GitHub issue."""
    import logging

    import issue_sync
    from config import settings

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
                with contextlib.suppress(Exception):
                    issue_sync.add_issue_comment(
                        token, repo, issue_number, f"✅ Kanban task completed: {notes}"
                    )
        elif event == "unclaimed":
            issue_sync.reopen_issue(token, repo, issue_number)
            issue_sync.update_issue_status(task_id, "open")
            if notes:
                with contextlib.suppress(Exception):
                    issue_sync.add_issue_comment(
                        token, repo, issue_number, f"🔄 Kanban task reopened: {notes}"
                    )
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to sync task {task_id} to GitHub: {e}")


@router.post("/api/tasks/{task_id}/unclaim", dependencies=[Depends(verify_auth)])
async def unclaim_task(task_id: str):
    await _call("unclaim_task", [task_id])
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if rows:
        asyncio.ensure_future(_notify("unclaimed", rows[0]))
        asyncio.ensure_future(_sync_to_github(task_id, "unclaimed"))
    return {"status": "unclaimed", "task_id": task_id}


@router.post("/api/tasks/{task_id}/complete", dependencies=[Depends(verify_auth)])
async def complete_task(task_id: str, body: CompleteRequest | None = None):
    if body is None:
        body = CompleteRequest()
    await _call("complete_task", [task_id, body.result_notes])
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if rows:
        asyncio.ensure_future(_notify("completed", rows[0], body.result_notes))
        asyncio.ensure_future(_sync_to_github(task_id, "completed", body.result_notes))
        asyncio.ensure_future(fire_event(EVENT_TASK_COMPLETED, {
            "task_id": task_id,
            "title": rows[0].get("title", "?")[:80],
            "repo": rows[0].get("repo", "?"),
            "result_notes": body.result_notes or "",
        }))
    return {"status": "completed", "task_id": task_id}


@router.post("/api/tasks/{task_id}/block", dependencies=[Depends(verify_auth)])
async def block_task(task_id: str, body: BlockRequest | None = None):
    if body is None:
        body = BlockRequest()
    await _call("block_task", [task_id, body.reason])
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if rows:
        asyncio.ensure_future(_notify("blocked", rows[0], body.reason))
        asyncio.ensure_future(fire_event(EVENT_TASK_BLOCKED, {
            "task_id": task_id,
            "title": rows[0].get("title", "?")[:80],
            "repo": rows[0].get("repo", "?"),
            "reason": body.reason or "",
        }))
    return {"status": "blocked", "task_id": task_id}


@router.post("/api/tasks/{task_id}/block-with-reason", dependencies=[Depends(verify_auth)])
async def block_task_with_reason(task_id: str, body: BlockWithReasonRequest):
    await _call("block_task_with_reason", [task_id, body.reason])
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
    if rows:
        asyncio.ensure_future(_notify("blocked", rows[0], body.reason))
        asyncio.ensure_future(fire_event(EVENT_TASK_BLOCKED, {
            "task_id": task_id,
            "title": rows[0].get("title", "?")[:80],
            "repo": rows[0].get("repo", "?"),
            "reason": body.reason or "",
        }))
    return {"status": "blocked", "task_id": task_id, "reason": body.reason}


@router.post("/api/tasks/{task_id}/split", dependencies=[Depends(verify_auth)])
async def split_task(task_id: str, body: SplitTaskRequest):
    child_titles_json = json.dumps(body.child_titles)
    await _call("split_task", [task_id, child_titles_json])
    return {"status": "split", "parent_task_id": task_id, "child_count": len(body.child_titles)}


@router.post("/api/tasks/{task_id}/reset-fails", dependencies=[Depends(verify_auth)])
async def reset_fail_count(task_id: str):
    await _call("reset_fail_count", [task_id])
    return {"status": "reset", "task_id": task_id}


@router.post("/api/tasks/bulk-retry", dependencies=[Depends(verify_auth)])
async def bulk_retry_tasks(body: BulkRetryRequest):
    """Return blocked tasks to available (optionally resetting fail_count).

    Used by the dispatcher's auto-retry sweep and the triage page to recover
    circuit-breaker-blocked tasks. Each task gets unclaim (blocked → available)
    plus reset_fail_count so the circuit breaker gives it a fresh budget.
    """
    retried, failed = 0, []
    for task_id in body.task_ids:
        try:
            if body.reset_fails:
                await _call("reset_fail_count", [task_id])
            await _call("unclaim_task", [task_id])
            retried += 1
        except Exception as e:
            failed.append({"task_id": task_id, "error": str(e)[:100]})
    return {"status": "ok", "retried": retried, "failed": failed}


@router.post("/api/tasks/bulk-archive", dependencies=[Depends(verify_auth)])
async def bulk_archive_tasks(body: BulkArchiveRequest):
    """Archive a list of tasks (only unarchived ones are toggled)."""
    archived, failed = 0, []
    for task_id in body.task_ids:
        try:
            rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
            if not rows:
                failed.append({"task_id": task_id, "error": "not found"})
                continue
            if not rows[0].get("archived", False):
                await _call("toggle_archive", [task_id])
                archived += 1
        except Exception as e:
            failed.append({"task_id": task_id, "error": str(e)[:100]})
    return {"status": "ok", "archived": archived, "failed": failed}


@router.post("/api/tasks/{task_id}/max-attempts", dependencies=[Depends(verify_auth)])
async def set_max_attempts(task_id: str, body: MaxAttemptsRequest):
    await _call("set_max_attempts", [task_id, body.max_attempts])
    return {"status": "updated", "task_id": task_id, "max_attempts": body.max_attempts}


@router.post("/api/tasks/{task_id}/dependency", dependencies=[Depends(verify_auth)])
async def set_dependency(task_id: str, body: SetDependencyRequest):
    await _call("set_dependency", [task_id, body.depends_on])
    return {"status": "updated", "task_id": task_id, "depends_on": body.depends_on or None}


# ── Task Skills ────────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/skills", dependencies=[Depends(verify_auth)])
async def set_task_skills(task_id: str, body: SetSkillsRequest):
    await _call("set_task_skills", [task_id, body.skills])
    return {"status": "updated", "task_id": task_id, "skills": body.skills or None}


# ── Archive / Unarchive ────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/archive", dependencies=[Depends(verify_auth)])
async def archive_task(task_id: str):
    """Toggle archive on a task (calls toggle_archive reducer)."""
    await _call("toggle_archive", [task_id])
    return {"status": "toggled", "task_id": task_id}


@router.post("/api/tasks/{task_id}/unarchive", dependencies=[Depends(verify_auth)])
async def unarchive_task(task_id: str):
    """Unarchive a task (calls unarchive_task reducer)."""
    await _call("unarchive_task", [task_id])
    return {"status": "unarchived", "task_id": task_id}


# ── Sprint Management ─────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/sprint", dependencies=[Depends(verify_auth)])
async def set_task_sprint(task_id: str, body: SprintRequest):
    """Set a task's sprint assignment."""
    await _call("set_sprint", [task_id, body.sprint])
    return {"status": "updated", "task_id": task_id, "sprint": body.sprint}


# ── Time Estimates ────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/time-estimates", dependencies=[Depends(verify_auth)])
async def set_task_time_estimates(task_id: str, body: TimeEstimatesRequest):
    """Set estimated and spent hours on a task."""
    await _call("set_time_estimates", [task_id, body.estimated_hours, body.spent_hours])
    return {
        "status": "updated",
        "task_id": task_id,
        "estimated_hours": body.estimated_hours,
        "spent_hours": body.spent_hours,
    }


# ── Task Relations ────────────────────────────────────────────────────


@router.get("/api/tasks/{task_id}/relations", response_model=list[TaskRelationOut])
async def list_task_relations(task_id: str):
    """List all relations for a task."""
    rows = await _sql_param(
        "SELECT * FROM task_relations WHERE task_id = '{task_id}'",
        task_id=task_id,
    )
    # Also return relations where this task is the related_task_id
    reverse_rows = await _sql_param(
        "SELECT * FROM task_relations WHERE related_task_id = '{task_id}'",
        task_id=task_id,
    )
    all_rows = rows + reverse_rows
    return [
        TaskRelationOut(
            id=r["id"],
            task_id=r["task_id"],
            related_task_id=r["related_task_id"],
            relation_type=r["relation_type"],
            created_at=r.get("created_at", 0),
        )
        for r in all_rows
    ]


@router.post("/api/tasks/{task_id}/relations", dependencies=[Depends(verify_auth)])
async def add_task_relation(task_id: str, body: TaskRelationCreate):
    """Add a relation between two tasks."""
    await _call("add_task_relation", [task_id, body.related_task_id, body.relation_type])
    return {"status": "created", "task_id": task_id, "related_task_id": body.related_task_id}


@router.delete("/api/tasks/{task_id}/relations/{relation_id}", dependencies=[Depends(verify_auth)])
async def remove_task_relation(task_id: str, relation_id: str):
    """Remove a task relation."""
    await _call("remove_task_relation", [relation_id])
    return {"status": "deleted"}


# ── Task Comments ──────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/comments", status_code=201, dependencies=[Depends(verify_auth)])
async def add_comment(task_id: str, body: CommentCreate):
    """Add a comment to a task."""
    comment_id = f"cmt_{uuid.uuid4().hex[:16]}"
    await _call("add_comment", [comment_id, task_id, body.author, body.body])
    return {"status": "created", "id": comment_id}


@router.get("/api/tasks/{task_id}/comments", response_model=list[CommentOut])
async def list_comments(task_id: str):
    """List all comments for a task, oldest first."""
    rows = await _sql_param(
        "SELECT * FROM task_comments WHERE task_id = '{task_id}'", task_id=task_id
    )
    rows.sort(key=lambda r: r.get("created_at", 0))
    return [CommentOut(**r) for r in rows]


@router.delete("/api/tasks/{task_id}/comments/{comment_id}", dependencies=[Depends(verify_auth)])
async def delete_comment(task_id: str, comment_id: str):
    """Delete a comment from a task."""
    await _call("delete_comment", [comment_id])
    return {"status": "deleted"}


# ── Task Logs ──────────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/log", dependencies=[Depends(verify_auth)])
async def add_task_log(task_id: str, body: AddLogRequest):
    """Add an activity log entry to a task."""
    await _call("add_log", [body.task_id, body.action, body.agent_id, body.notes])
    return {"status": "logged", "task_id": task_id}


# ── Task Checklists ────────────────────────────────────────────────────


@router.post("/api/tasks/{task_id}/checklist", status_code=201, dependencies=[Depends(verify_auth)])
async def add_checklist_item(task_id: str, body: ChecklistItemCreate):
    """Add a checklist item to a task."""
    item_id = f"cl_{uuid.uuid4().hex[:16]}"
    await _call("add_checklist_item", [item_id, task_id, body.text])
    return {"status": "created", "id": item_id}


@router.get("/api/tasks/{task_id}/checklist", response_model=list[ChecklistItemOut])
async def list_checklist(task_id: str):
    """List all checklist items for a task, ordered by position."""
    rows = await _sql_param(
        "SELECT * FROM task_checklists WHERE task_id = '{task_id}'", task_id=task_id
    )
    rows.sort(key=lambda r: r.get("position", 0))
    return [ChecklistItemOut(**r) for r in rows]


@router.post("/api/tasks/{task_id}/checklist/{item_id}/toggle", dependencies=[Depends(verify_auth)])
async def toggle_checklist_item(task_id: str, item_id: str):
    """Toggle a checklist item's completed state."""
    await _call("toggle_checklist_item", [item_id])
    return {"status": "toggled"}


@router.delete("/api/tasks/{task_id}/checklist/{item_id}", dependencies=[Depends(verify_auth)])
async def remove_checklist_item(task_id: str, item_id: str):
    """Remove a checklist item."""
    await _call("remove_checklist_item", [item_id])
    return {"status": "deleted"}


@router.post(
    "/api/tasks/{task_id}/checklist/{item_id}/reorder", dependencies=[Depends(verify_auth)]
)
async def reorder_checklist_item(task_id: str, item_id: str, new_position: int):
    """Reorder a checklist item."""
    await _call("reorder_checklist_items", [item_id, new_position])
    return {"status": "reordered"}


# ── Task Labels ────────────────────────────────────────────────────────


@router.get("/api/tasks/{task_id}/labels", response_model=list[LabelOut])
async def get_task_labels(task_id: str):
    """Get all labels assigned to a task."""
    rows = await _sql(f"""
        SELECT l.* FROM kanban_labels l
        INNER JOIN task_label_assignments a ON l.id = a.label_id
        WHERE a.task_id = '{task_id}'
    """)
    return [
        LabelOut(
            id=r["id"],
            name=r["name"],
            color=r.get("color", "#0ea5e9"),
            description=r.get("description", ""),
            created_at=r.get("created_at", 0),
        )
        for r in rows
    ]


@router.post("/api/tasks/{task_id}/labels", dependencies=[Depends(verify_auth)])
async def set_task_labels(task_id: str, body: TaskLabelAssign):
    """Set labels for a task by replacing all current assignments."""
    existing = await _sql_param(
        "SELECT label_id FROM task_label_assignments WHERE task_id = '{task_id}'", task_id=task_id
    )
    current_ids = {r["label_id"] for r in existing}
    new_ids = set(body.label_ids)

    # Remove any labels not in the new set
    to_remove = current_ids - new_ids
    for lid in to_remove:
        with contextlib.suppress(Exception):
            await _call("unassign_label_from_task", [task_id, lid])

    # Add any labels not already assigned
    to_add = new_ids - current_ids
    for lid in to_add:
        with contextlib.suppress(Exception):
            await _call("assign_label_to_task", [task_id, lid])

    return {"status": "updated", "assigned": list(new_ids)}
