"""Kanban MCP Server — native Hermes integration with the task swarm.

Exposes the entire kanban system as MCP tools so Hermes can create,
claim, complete, and manage tasks with zero shell command overhead.
Auto-registers Hermes in the swarm on startup.

Transport: stdio (for Hermes native MCP client).

Uses MCP SDK FastMCP API (v1.23.x+).
"""

import json
import os
import urllib.error
import urllib.request
from urllib.parse import quote, urljoin

from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")


class KanbanAPIError(Exception):
    """Raised when the kanban API returns an HTTP error or is unreachable."""

    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


# ── Low-level API helpers ────────────────────────────────────────────────


def api_get(path: str) -> list | dict:
    """GET from the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe="/:?=&"))
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code) from e
    except Exception as e:
        raise KanbanAPIError(str(e)) from e


def api_post(path: str, body: dict | None = None) -> dict:
    """POST to the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe="/:?=&"))
    data = json.dumps(body or {}).encode() if body else None
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        text = resp.read().decode()
        return json.loads(text) if text else {"status": "ok"}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code) from e
    except Exception as e:
        raise KanbanAPIError(str(e)) from e


def api_patch(path: str, body: dict) -> dict:
    """PATCH the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe="/:?=&"))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code) from e
    except Exception as e:
        raise KanbanAPIError(str(e)) from e


def api_put(path: str, body: dict) -> dict:
    """PUT to the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe="/:?=&"))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code) from e
    except Exception as e:
        raise KanbanAPIError(str(e)) from e


def api_delete(path: str) -> dict:
    """DELETE from the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe="/:?=&"))
    req = urllib.request.Request(url, method="DELETE")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code) from e
    except Exception as e:
        raise KanbanAPIError(str(e)) from e


# ── Tool Functions ────────────────────────────────────────────────────────
# Each function is registered via Tool.from_function().
# Parameter names/descriptions/docs become the input schema.


async def kanban_list_tasks(status: str = "", repo: str = "") -> str:
    """List kanban tasks. Filter by status (available, claimed, blocked, completed) and/or repo."""
    params = {}
    if status:
        params["status"] = status
    if repo:
        params["repo"] = repo
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    tasks = api_get(f"/api/tasks{'?' + qs if qs else ''}")
    return json.dumps({"tasks": tasks, "count": len(tasks) if isinstance(tasks, list) else 0})


async def kanban_get_task(task_id: str) -> str:
    """Get full task details including activity logs and downstream blockers."""
    task = api_get(f"/api/tasks/{task_id}")
    logs = api_get(f"/api/tasks/{task_id}/logs")
    all_tasks = api_get("/api/tasks")
    downstream = []
    if isinstance(all_tasks, list):
        for t in all_tasks:
            if t.get("depends_on") == task_id:
                downstream.append(t)
    return json.dumps(
        {
            "task": task,
            "logs": logs if isinstance(logs, list) else [],
            "downstream_blockers": downstream,
            "blocker_count": len(downstream),
        }
    )


async def kanban_create_task(
    title: str,
    description: str = "",
    priority: int = 2,
    repo: str = "",
    roadmap_item: str = "",
    required_skills: str = "",
    created_by: str = "hermes",
) -> str:
    """Create a new kanban task."""
    body = {
        "title": title,
        "description": description,
        "priority": priority,
        "repo": repo,
        "roadmap_item": roadmap_item,
        "created_by": created_by,
    }
    result = api_post("/api/tasks", body)
    if required_skills:
        tasks = api_get("/api/tasks")
        if isinstance(tasks, list) and tasks:
            newest = max(tasks, key=lambda t: t.get("created_at", 0))
            api_post(f"/api/tasks/{newest['id']}/skills", {"skills": required_skills})
            result["task_id"] = newest["id"]
            result["skills_set"] = required_skills
    return json.dumps(result)


async def kanban_update_task(
    task_id: str,
    title: str = "",
    description: str = "",
    priority: int = -1,
    branch: str = "",
) -> str:
    """Update task title, description, priority, or branch."""
    body = {}
    if title:
        body["title"] = title
    if description:
        body["description"] = description
    if priority >= 0:
        body["priority"] = priority
    if branch:
        body["branch"] = branch
    if not body:
        raise KanbanAPIError("No fields to update", status_code=400)
    return json.dumps(api_patch(f"/api/tasks/{task_id}", body))


async def kanban_claim(task_id: str, agent_id: str = "hermes") -> str:
    """Claim a task. Assigns it to an agent and sets status to claimed."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/claim", {"agent_id": agent_id}))


async def kanban_complete(task_id: str, notes: str = "Completed") -> str:
    """Mark a task as completed with optional notes."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/complete", {"result_notes": notes}))


async def kanban_block(task_id: str, reason: str = "Blocked") -> str:
    """Mark a task as blocked with a reason."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/block", {"reason": reason}))


async def kanban_block_with_reason(task_id: str, reason: str) -> str:
    """Mark a task as blocked with a persistent reason (stored in fail_reason field)."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/block-with-reason", {"reason": reason}))


async def kanban_split_task(task_id: str, child_titles: list[str]) -> str:
    """Split a task into subtasks. Creates child tasks, marks parent with subtask refs."""
    if not child_titles:
        raise KanbanAPIError("child_titles must be a non-empty list", status_code=400)
    return json.dumps(api_post(f"/api/tasks/{task_id}/split", {"child_titles": child_titles}))


async def kanban_unclaim(task_id: str) -> str:
    """Release a task back to 'available' status."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/unclaim"))


async def kanban_delete_task(task_id: str) -> str:
    """Permanently delete a task."""
    return json.dumps(api_delete(f"/api/tasks/{task_id}"))


async def kanban_set_dependency(task_id: str, depends_on: str = "") -> str:
    """Set which task this task depends on (or clear the dependency with empty string)."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/dependency", {"depends_on": depends_on}))


async def kanban_set_skills(task_id: str, skills: str) -> str:
    """Set required skills on a task (comma-separated tags)."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/skills", {"skills": skills}))


async def kanban_suggest(agent_id: str = "", limit: int = 5) -> str:
    """Get top-N scored task suggestions for an agent."""
    params = f"limit={limit}"
    if agent_id:
        params += f"&agent_id={agent_id}"
    return json.dumps(api_get(f"/api/tasks/suggest?{params}"))


async def kanban_list_agents() -> str:
    """List all registered swarm agents with their status and capabilities."""
    agents = api_get("/api/agents")
    return json.dumps(
        {
            "agents": agents if isinstance(agents, list) else [],
            "count": len(agents) if isinstance(agents, list) else 0,
        }
    )


async def kanban_register_agent(
    agent_id: str,
    host: str = "",
    capabilities: str = "",
    repo_focus: str = "",
) -> str:
    """Register this agent in the kanban swarm so it can claim tasks and receive suggestions."""
    return json.dumps(
        api_post(
            "/api/agents/register",
            {
                "agent_id": agent_id,
                "host": host,
                "capabilities": capabilities,
                "repo_focus": repo_focus,
            },
        )
    )


async def kanban_heartbeat(
    agent_id: str,
    status: str = "online",
    current_task_id: str = "",
) -> str:
    """Send swarm heartbeat to keep this agent online. Call every 30-60s while active."""
    return json.dumps(
        api_post(
            f"/api/agents/{agent_id}/heartbeat",
            {
                "agent_id": agent_id,
                "status": status,
                "current_task_id": current_task_id,
            },
        )
    )


async def kanban_set_capabilities(agent_id: str, capabilities: str, repo_focus: str = "") -> str:
    """Update an agent's capabilities and repo focus."""
    return json.dumps(
        api_put(
            f"/api/agents/{agent_id}/capabilities",
            {
                "capabilities": capabilities,
                "repo_focus": repo_focus,
            },
        )
    )


async def kanban_list_projects() -> str:
    """List all registered projects with their priority, colour, and active status."""
    projects = api_get("/api/projects")
    return json.dumps(
        {
            "projects": projects if isinstance(projects, list) else [],
            "count": len(projects) if isinstance(projects, list) else 0,
        }
    )


async def kanban_add_project(
    id: str,
    name: str = "",
    description: str = "",
    color: str = "#0ea5e9",
    priority: int = 2,
    active: bool = True,
) -> str:
    """Register a new project/repo with a priority level for weighted task suggestion."""
    return json.dumps(
        api_post(
            "/api/projects",
            {
                "id": id,
                "name": name,
                "description": description,
                "color": color,
                "priority": priority,
                "active": active,
            },
        )
    )


async def kanban_update_project(
    project_id: str,
    name: str = "",
    description: str = "",
    color: str = "",
    priority: int = 3,
    active: bool = True,
) -> str:
    """Update a project's priority, name, colour, or active status."""
    body = {}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    if color:
        body["color"] = color
    if priority <= 3:
        body["priority"] = priority
    body["active"] = active
    return json.dumps(api_patch(f"/api/projects/{project_id}", body))


async def kanban_delete_project(project_id: str) -> str:
    """Delete a registered project."""
    return json.dumps(api_delete(f"/api/projects/{project_id}"))


async def kanban_suggest_by_project(limit: int = 10) -> str:
    """Get suggested tasks prioritised by project importance."""
    return json.dumps(api_get(f"/api/suggest-by-project?limit={limit}"))


async def kanban_add_log(
    task_id: str,
    action: str,
    agent_id: str = "hermes",
    notes: str = "",
) -> str:
    """Add an activity log entry to a task. Useful for tracking progress."""
    return json.dumps(
        api_post(
            f"/api/tasks/{task_id}/log",
            {
                "task_id": task_id,
                "action": action,
                "agent_id": agent_id,
                "notes": notes,
            },
        )
    )


async def kanban_get_logs(task_id: str) -> str:
    """Get the activity log for a task."""
    logs = api_get(f"/api/tasks/{task_id}/logs")
    return json.dumps(
        {
            "task_id": task_id,
            "logs": logs if isinstance(logs, list) else [],
            "count": len(logs) if isinstance(logs, list) else 0,
        }
    )


async def kanban_issue_link(task_id: str, repo: str, issue_number: int) -> str:
    """Link a kanban task to an existing GitHub issue."""
    return json.dumps(
        api_post(
            "/api/issues/link",
            {
                "task_id": task_id,
                "repo": repo,
                "issue_number": issue_number,
            },
        )
    )


async def kanban_issue_create(
    task_id: str, repo: str = "", labels: str = "", assignee: str = ""
) -> str:
    """Create a GitHub issue from a kanban task and auto-link them."""
    return json.dumps(
        api_post(
            "/api/issues/create",
            {
                "task_id": task_id,
                "repo": repo,
                "labels": labels,
                "assignee": assignee,
            },
        )
    )


async def kanban_issue_status(task_id: str) -> str:
    """Get the GitHub issue link status for a kanban task."""
    return json.dumps(api_get(f"/api/issues/{task_id}"))


async def kanban_issue_list(repo: str = "") -> str:
    """List all kanban-task <-> GitHub-issue links."""
    qs = f"?repo={repo}" if repo else ""
    links = api_get(f"/api/issues{qs}")
    return json.dumps(
        {
            "links": links if isinstance(links, list) else [],
            "count": len(links) if isinstance(links, list) else 0,
        }
    )


async def kanban_add_comment(task_id: str, body: str, author: str = "hermes") -> str:
    """Add a comment to a kanban task."""
    return json.dumps(
        api_post(
            f"/api/tasks/{task_id}/comments",
            {
                "body": body,
                "author": author,
            },
        )
    )


async def kanban_list_comments(task_id: str) -> str:
    """List all comments for a kanban task."""
    comments = api_get(f"/api/tasks/{task_id}/comments")
    return json.dumps(
        {
            "task_id": task_id,
            "comments": comments if isinstance(comments, list) else [],
            "count": len(comments) if isinstance(comments, list) else 0,
        }
    )


async def kanban_delete_comment(task_id: str, comment_id: str) -> str:
    """Delete a comment from a kanban task."""
    return json.dumps(api_delete(f"/api/tasks/{task_id}/comments/{comment_id}"))


async def kanban_add_checklist_item(task_id: str, text: str) -> str:
    """Add a checklist item to a kanban task."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/checklist", {"text": text}))


async def kanban_list_checklist(task_id: str) -> str:
    """List all checklist items for a task."""
    items = api_get(f"/api/tasks/{task_id}/checklist")
    completed = sum(1 for i in items if isinstance(i, dict) and i.get("completed"))
    return json.dumps(
        {
            "task_id": task_id,
            "items": items if isinstance(items, list) else [],
            "count": len(items) if isinstance(items, list) else 0,
            "completed": completed,
            "remaining": (len(items) if isinstance(items, list) else 0) - completed,
        }
    )


async def kanban_toggle_checklist_item(task_id: str, item_id: str) -> str:
    """Toggle a checklist item's completed state."""
    return json.dumps(api_post(f"/api/tasks/{task_id}/checklist/{item_id}/toggle"))


async def kanban_remove_checklist_item(task_id: str, item_id: str) -> str:
    """Remove a checklist item from a task."""
    return json.dumps(api_delete(f"/api/tasks/{task_id}/checklist/{item_id}"))


# ── Build Tool Registration ──────────────────────────────────────────────

app = FastMCP("spacetimedb-kanban")

# Register all tools
for fn in [
    kanban_list_tasks,
    kanban_get_task,
    kanban_create_task,
    kanban_update_task,
    kanban_claim,
    kanban_complete,
    kanban_block,
    kanban_block_with_reason,
    kanban_split_task,
    kanban_unclaim,
    kanban_delete_task,
    kanban_set_dependency,
    kanban_set_skills,
    kanban_suggest,
    kanban_list_agents,
    kanban_register_agent,
    kanban_heartbeat,
    kanban_set_capabilities,
    kanban_list_projects,
    kanban_add_project,
    kanban_update_project,
    kanban_delete_project,
    kanban_suggest_by_project,
    kanban_add_log,
    kanban_get_logs,
    kanban_issue_link,
    kanban_issue_create,
    kanban_issue_status,
    kanban_issue_list,
    kanban_add_comment,
    kanban_list_comments,
    kanban_delete_comment,
    kanban_add_checklist_item,
    kanban_list_checklist,
    kanban_toggle_checklist_item,
    kanban_remove_checklist_item,
]:
    app.add_tool(fn)


# ── Main entry point ─────────────────────────────────────────────────────


def main():
    """Run the MCP server over stdio."""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
