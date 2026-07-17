"""GitHub issue and webhook endpoints for spacetimedb-kanban."""

import asyncio
import contextlib
import re

from fastapi import APIRouter, Depends, HTTPException, Request

import issue_sync
from shared import (
    IssueCreateRequest,
    IssueLinkRequest,
    _call,
    _notify,
    _sql_param,
    verify_auth,
)

router = APIRouter()

BRANCH_PATTERN = re.compile(
    r"^(?:feature|fix|chore|refactor|docs|test)/"
    r"kanban-([a-zA-Z0-9_]+)--"
    r".+$"
)


# ── Issue Link CRUD ────────────────────────────────────────────────────


@router.get("/api/issues")
async def list_issue_links(repo: str = ""):
    """List all kanban-task ⟷ GitHub-issue links."""
    return issue_sync.list_links(repo or None)


@router.get("/api/issues/{task_id}")
async def get_issue_link(task_id: str):
    """Get the GitHub issue link for a specific kanban task."""
    link = issue_sync.get_link(task_id)
    if not link:
        raise HTTPException(404, "No GitHub issue linked to this task")
    return {"kanban_task_id": task_id, **link}


@router.post("/api/issues/link", dependencies=[Depends(verify_auth)])
async def link_issue(body: IssueLinkRequest):
    """Link a kanban task to an existing GitHub issue."""
    existing = issue_sync.get_link(body.task_id)
    if existing:
        raise HTTPException(409, f"Task already linked to {existing['html_url']}")
    link = issue_sync.link_issue(
        task_id=body.task_id,
        repo=body.repo,
        issue_number=body.issue_number,
        issue_url=body.issue_url
        or f"https://api.github.com/repos/{body.repo}/issues/{body.issue_number}",
        html_url=body.html_url or f"https://github.com/{body.repo}/issues/{body.issue_number}",
    )
    return {"status": "linked", **link}


@router.post("/api/issues/unlink", dependencies=[Depends(verify_auth)])
async def unlink_issue(task_id: str):
    """Remove a kanban-task ⟷ GitHub-issue link."""
    if not issue_sync.unlink_issue(task_id):
        raise HTTPException(404, "No link found for this task")
    return {"status": "unlinked", "task_id": task_id}


@router.post("/api/issues/create", dependencies=[Depends(verify_auth)])
async def create_issue_from_task(body: IssueCreateRequest):
    """Create a GitHub issue from a kanban task and link it."""
    from config import settings

    # Fetch task details
    rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=body.task_id)
    if not rows:
        raise HTTPException(404, "Task not found")
    task = rows[0]

    token = settings.github_token
    if not token:
        raise HTTPException(400, "GitHub token not configured (set GITHUB_TOKEN env var)")

    repo_full = body.repo or settings.github_default_repo
    if not repo_full:
        raise HTTPException(400, "No repo specified and no github_default_repo configured")

    label_list = (
        [rec.strip() for rec in body.labels.split(",") if rec.strip()] if body.labels else []
    )
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

    result = issue_sync.create_issue(
        token, repo_full, task["title"], issue_body, label_list, body.assignee or None
    )
    issue_sync.link_issue(
        body.task_id, repo_full, result["issue_number"], result["issue_url"], result["html_url"]
    )
    issue_sync.update_issue_status(body.task_id, result["state"])

    # Add activity log
    with contextlib.suppress(Exception):
        await _call(
            "add_log",
            [
                body.task_id,
                "github_issue_created",
                "",
                f"Issue #{result['issue_number']}: {result['html_url']}",
            ],
        )

    return {
        "status": "created",
        "task_id": body.task_id,
        "issue_number": result["issue_number"],
        "html_url": result["html_url"],
    }


# ── GitHub Webhook ───────────────────────────────────────────────────


@router.post("/api/webhook/github")
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
                issue_sync.link_issue(
                    existing_task_id, repo_full, issue_number, issue.get("url", ""), issue_html
                )
                issue_sync.update_issue_status(existing_task_id, issue_state)
                return {"status": "re-linked", "task_id": existing_task_id}

            # New issue from outside kanban — create task
            import uuid as _uuid

            gh_task_id = f"task_{_uuid.uuid4().hex[:16]}"
            await _call(
                "add_task",
                [
                    gh_task_id,
                    issue_title,
                    f"Issue #{issue_number}: {issue_html}\n\n{issue_body[:500]}",
                    2,
                    repo_full,
                    f"GitHub Issues — {repo_full}",
                    "github-webhook",
                    "",
                ],
            )
            await _call(
                "add_log",
                [
                    gh_task_id,
                    "created",
                    "github-webhook",
                    f"From issue #{issue_number}: {issue_html}",
                ],
            )
            issue_sync.link_issue(
                gh_task_id, repo_full, issue_number, issue.get("url", ""), issue_html
            )
            issue_sync.update_issue_status(gh_task_id, issue_state)
            asyncio.ensure_future(
                _notify(
                    "created",
                    {
                        "title": issue_title,
                        "id": gh_task_id,
                        "repo": repo_full,
                    },
                    f"Issue #{issue_number}",
                )
            )
            return {"status": "created", "task_id": gh_task_id, "issue_number": issue_number}

        elif action == "closed":
            # Auto-complete the linked kanban task
            task_id = issue_sync.get_task_id_for_issue(repo_full, issue_number)
            if task_id:
                rows = await _sql_param(
                    "SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id
                )
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
                rows = await _sql_param(
                    "SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id
                )
                if rows and rows[0].get("status") == "done":
                    await _call("unclaim_task", [task_id])
                    with contextlib.suppress(Exception):
                        await _call(
                            "add_log",
                            [
                                task_id,
                                "unclaimed",
                                "github-webhook",
                                f"Issue #{issue_number} reopened",
                            ],
                        )
                    issue_sync.update_issue_status(task_id, "open")
                    asyncio.ensure_future(
                        _notify("unclaimed", rows[0], f"Issue #{issue_number} reopened")
                    )
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
            rows = await _sql_param(
                "SELECT title FROM tasks WHERE id = '{task_id}'", task_id=task_id
            )
            original_title = rows[0]["title"] if rows else pr_title
        except Exception:
            original_title = pr_title
        with contextlib.suppress(HTTPException):
            await _call("update_task", [task_id, original_title, f"PR: {pr_url}", 2, branch])
            # Task may not exist yet — expected, not an error
        asyncio.ensure_future(
            _notify(
                "linked",
                {
                    "id": task_id,
                    "title": original_title,
                    "repo": payload.get("repository", {}).get("full_name", ""),
                    "assigned_to": None,
                },
                f"PR {pr_url}",
            )
        )
        return {"status": "linked", "task_id": task_id, "action": action}

    elif action == "closed" and pr.get("merged", False):
        # Auto-complete the task when PR is merged
        notes = f"Merged via PR: {pr_url}"
        try:
            # Check if task exists and is in_progress or available
            rows = await _sql_param("SELECT * FROM tasks WHERE id = '{task_id}'", task_id=task_id)
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
