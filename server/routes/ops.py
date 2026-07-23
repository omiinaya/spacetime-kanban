"""Extracted from main.py during route thinning (pure move, logic verbatim)."""

import re

from fastapi import APIRouter, Depends

from shared import (
    MigrationCreate,
    MigrationOut,
    RoadmapImportRequest,
    TaskOut,
    _call,
    _row_to_task,
    _sql,
    _sql_param,
    verify_auth,
)

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.post("/api/roadmap/import", dependencies=[Depends(verify_auth)])
async def import_roadmap(body: RoadmapImportRequest):
    """Parse ROADMAP.md content and bulk-create kanban tasks."""

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

            tasks.append(
                {
                    "title": title,
                    "description": f"From {current_phase}",
                    "priority": priority,
                    "repo": body.repo,
                    "roadmap_item": current_phase,
                    "created_by": body.created_by,
                }
            )
            task_count += 1

            if len(tasks) >= 5:
                for t in tasks:
                    # Dedup: skip if task with same title+repo already exists
                    sanitized_title = t["title"].replace("'", "''")
                    sanitized_repo = t["repo"].replace("'", "''")
                    existing_rows = await _sql_param(
                        "SELECT id, status FROM tasks WHERE title = '{title}' AND repo = '{repo}' LIMIT 1",
                        title=sanitized_title,
                        repo=sanitized_repo,
                    )
                    if existing_rows and existing_rows[0].get('status') != 'done':
                        continue
                    await _call(
                        "add_task",
                        [
                            "",
                            t["title"],
                            t["description"],
                            t["priority"],
                            t["repo"],
                            t["roadmap_item"],
                            t["created_by"],
                            "",
                        ],
                    )
                tasks = []

    for t in tasks:
        # Dedup: skip if task with same title+repo already exists
        sanitized_title = t["title"].replace("'", "''")
        sanitized_repo = t["repo"].replace("'", "''")
        existing_rows = await _sql_param(
            "SELECT id, status FROM tasks WHERE title = '{title}' AND repo = '{repo}' LIMIT 1",
            title=sanitized_title,
            repo=sanitized_repo,
        )
        if existing_rows and existing_rows[0].get('status') != 'done':
            continue
        await _call(
            "add_task",
            [
                "",
                t["title"],
                t["description"],
                t["priority"],
                t["repo"],
                t["roadmap_item"],
                t["created_by"],
                "",
            ],
        )

    return {"status": "imported", "task_count": task_count}


@router.get("/api/calendar", response_model=list[TaskOut])
async def calendar_tasks():
    """Return tasks that have due_by dates set."""
    rows = await _sql("SELECT * FROM tasks")
    tasks = [_row_to_task(r) for r in rows if r.get("due_by")]
    tasks.sort(key=lambda t: t.due_by or 0)
    return tasks


@router.get("/api/cross-project")
async def cross_project_aggregation():
    """Return aggregate counts per repo."""
    rows = await _sql("SELECT * FROM tasks")
    repos: dict[str, dict] = {}
    for r in rows:
        repo = r.get("repo") or "(none)"
        if repo not in repos:
            repos[repo] = {
                "repo": repo,
                "total": 0,
                "available": 0,
                "in_progress": 0,
                "blocked": 0,
                "done": 0,
                "archived": 0,
            }
        repos[repo]["total"] += 1
        status = r.get("status", "unknown")
        if status in repos[repo]:
            repos[repo][status] += 1
        if r.get("archived", False):
            repos[repo]["archived"] += 1
    return list(repos.values())


@router.get("/api/migrations", response_model=list[MigrationOut])
async def list_migrations():
    """List applied schema migrations."""
    rows = await _sql("SELECT * FROM schema_migrations")
    rows = sorted(rows, key=lambda r: r.get("applied_at", 0))
    return [
        MigrationOut(
            version=r["version"],
            description=r.get("description", ""),
            applied_at=r.get("applied_at", 0),
            applied_by=r.get("applied_by", ""),
            checksum=r.get("checksum"),
        )
        for r in rows
    ]


@router.post("/api/migrations", status_code=201, dependencies=[Depends(verify_auth)])
async def record_migration(body: MigrationCreate):
    """Record a schema migration."""
    await _call(
        "record_migration",
        [
            body.version,
            body.description,
            body.applied_by,
            body.checksum,
        ],
    )
    return {"status": "recorded", "version": body.version}
