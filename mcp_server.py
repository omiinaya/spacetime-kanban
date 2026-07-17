"""Kanban MCP Server — native Hermes integration with the task swarm.

Exposes the entire kanban system as MCP tools so Hermes can create,
claim, complete, and manage tasks with zero shell command overhead.
Auto-registers Hermes in the swarm on startup.

Transport: stdio (for Hermes native MCP client).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from urllib.parse import quote, urljoin

from mcp.server import Server
from mcp.types import Tool, TextContent

API_BASE = os.environ.get("KANBAN_API", "http://localhost:8727")
app = Server("spacetimedb-kanban")


class KanbanAPIError(Exception):
    """Raised when the kanban API returns an HTTP error or is unreachable."""
    def __init__(self, message: str, status_code: int = 0):
        self.status_code = status_code
        super().__init__(message)


def api_get(path: str) -> list | dict:
    """GET from the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe='/:?=&'))
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
    except Exception as e:
        raise KanbanAPIError(str(e))


def api_post(path: str, body: dict | None = None) -> dict:
    """POST to the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe='/:?=&'))
    data = json.dumps(body or {}).encode() if body else None
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        text = resp.read().decode()
        return json.loads(text) if text else {"status": "ok"}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
    except Exception as e:
        raise KanbanAPIError(str(e))


def api_patch(path: str, body: dict) -> dict:
    """PATCH the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe='/:?=&'))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
    except Exception as e:
        raise KanbanAPIError(str(e))


def api_put(path: str, body: dict) -> dict:
    """PUT to the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe='/:?=&'))
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
    except Exception as e:
        raise KanbanAPIError(str(e))


def api_delete(path: str) -> dict:
    """DELETE from the kanban API. Raises KanbanAPIError on failure."""
    url = urljoin(API_BASE, quote(path, safe='/:?=&'))
    req = urllib.request.Request(url, method="DELETE")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise KanbanAPIError(f"HTTP {e.code}: {body}", status_code=e.code)
    except Exception as e:
        raise KanbanAPIError(str(e))

# ── Tool: list_tasks ─────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="kanban_list_tasks",
            description="List kanban tasks. Filter by status (available/claimed/blocked/completed) and/or repo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "Filter: available, claimed, blocked, completed", "default": ""},
                    "repo": {"type": "string", "description": "Filter by repo slug", "default": ""},
                },
            },
        ),
        Tool(
            name="kanban_get_task",
            description="Get full task details including activity logs and downstream blockers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_create_task",
            description="Create a new kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "description": {"type": "string", "description": "Task description", "default": ""},
                    "priority": {"type": "integer", "description": "Priority 0-3 (0=urgent, 3=low)", "default": 2},
                    "repo": {"type": "string", "description": "Repo slug", "default": ""},
                    "roadmap_item": {"type": "string", "description": "Optional roadmap phase", "default": ""},
                    "required_skills": {"type": "string", "description": "Comma-separated skills (e.g. 'rust,python,typescript')", "default": ""},
                    "created_by": {"type": "string", "description": "Agent/creator name", "default": "hermes"},
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="kanban_update_task",
            description="Update task title, description, priority, or branch.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "title": {"type": "string", "description": "New title", "default": ""},
                    "description": {"type": "string", "description": "New description", "default": ""},
                    "priority": {"type": "integer", "description": "New priority 0-3", "default": -1},
                    "branch": {"type": "string", "description": "Git branch name", "default": ""},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_claim",
            description="Claim a task. Assigns it to an agent and sets status to 'claimed'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "agent_id": {"type": "string", "description": "Agent identifier", "default": ""},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_complete",
            description="Mark a task as completed with optional notes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "notes": {"type": "string", "description": "Completion notes", "default": "Completed"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_block",
            description="Mark a task as blocked with a reason.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "reason": {"type": "string", "description": "Block reason", "default": "Blocked"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_block_with_reason",
            description="Mark a task as blocked with a persistent reason (stored in fail_reason field). Use this instead of kanban_block.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "reason": {"type": "string", "description": "Block reason (stored permanently)"},
                },
                "required": ["task_id", "reason"],
            },
        ),
        Tool(
            name="kanban_split_task",
            description="Split a task into subtasks. Creates child tasks and marks the parent with subtask references.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Parent task ID to split"},
                    "child_titles": {"type": "array", "items": {"type": "string"}, "description": "List of child task titles"},
                },
                "required": ["task_id", "child_titles"],
            },
        ),
        Tool(
            name="kanban_unclaim",
            description="Release a task back to 'available' status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_delete_task",
            description="Permanently delete a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_set_dependency",
            description="Set which task this task depends on (or clear the dependency).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to update"},
                    "depends_on": {"type": "string", "description": "Task ID this depends on, or empty string to clear", "default": ""},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_set_skills",
            description="Set required skills on a task (comma-separated tags).",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "skills": {"type": "string", "description": "Comma-separated skills, e.g. 'rust,python'"},
                },
                "required": ["task_id", "skills"],
            },
        ),
        Tool(
            name="kanban_suggest",
            description="Get top-N scored task suggestions for an agent. Uses priority scoring (base + stale + unblock + skill-match bonuses).",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent to tailor suggestions for (matches capabilities)", "default": ""},
                    "limit": {"type": "integer", "description": "Max suggestions", "default": 5},
                },
            },
        ),
        Tool(
            name="kanban_list_agents",
            description="List all registered swarm agents with their status and capabilities.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="kanban_register_agent",
            description="Register this agent in the kanban swarm so it can claim tasks and receive suggestions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Unique agent identifier"},
                    "host": {"type": "string", "description": "Hostname or origin", "default": ""},
                    "capabilities": {"type": "string", "description": "Comma-separated skills, e.g. 'rust,python,typescript,devops'"},
                    "repo_focus": {"type": "string", "description": "Primary repo focus", "default": ""},
                },
                "required": ["agent_id"],
            },
        ),
        Tool(
            name="kanban_heartbeat",
            description="Send a swarm heartbeat to keep this agent marked as online. Call regularly (every 30-60s) while active.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent identifier"},
                    "status": {"type": "string", "description": "Status: online, busy, idle, offline", "default": "online"},
                    "current_task_id": {"type": "string", "description": "Task ID currently working on", "default": ""},
                },
                "required": ["agent_id"],
            },
        ),
        Tool(
            name="kanban_set_capabilities",
            description="Update an agent's capabilities and repo focus.",
            inputSchema={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "Agent identifier"},
                    "capabilities": {"type": "string", "description": "Comma-separated skills"},
                    "repo_focus": {"type": "string", "description": "Primary repo", "default": ""},
                },
                "required": ["agent_id", "capabilities"],
            },
        ),
        # ── Project Management Tools ────────────────────────────────
        Tool(
            name="kanban_list_projects",
            description="List all registered projects with their priority, colour, and active status.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="kanban_add_project",
            description="Register a new project/repo with a priority level for weighted task suggestion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Repo slug (e.g. 'sample-repo-q') — this maps to the `repo` field on tasks"},
                    "name": {"type": "string", "description": "Display name", "default": ""},
                    "description": {"type": "string", "description": "Project description", "default": ""},
                    "color": {"type": "string", "description": "Hex colour e.g. '#0ea5e9'", "default": "#0ea5e9"},
                    "priority": {"type": "integer", "description": "Priority 0-3 (0=most important, 3=least)", "default": 2},
                    "active": {"type": "boolean", "description": "Whether to include this project in scoring", "default": True},
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="kanban_update_project",
            description="Update a project's priority, name, colour, or active status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project/repo slug"},
                    "name": {"type": "string", "description": "New display name", "default": ""},
                    "description": {"type": "string", "description": "New description", "default": ""},
                    "color": {"type": "string", "description": "New hex colour", "default": ""},
                    "priority": {"type": "integer", "description": "Priority 0-3 (0=most important)", "default": 3},
                    "active": {"type": "boolean", "description": "Whether this project is active in scoring", "default": True},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="kanban_delete_project",
            description="Delete a registered project.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project/repo slug"},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="kanban_suggest_by_project",
            description="Get suggested tasks prioritised by project importance. Tasks from higher-priority projects are scored higher.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max suggestions", "default": 10},
                },
            },
        ),
        Tool(
            name="kanban_add_log",
            description="Add an activity log entry to a task. Useful for tracking progress.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "action": {"type": "string", "description": "Action description, e.g. 'started work', 'investigating', 'found root cause', 'waiting on review'"},
                    "agent_id": {"type": "string", "description": "Agent making the entry", "default": ""},
                    "notes": {"type": "string", "description": "Detailed notes", "default": ""},
                },
                "required": ["task_id", "action"],
            },
        ),
        Tool(
            name="kanban_get_logs",
            description="Get the activity log for a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_issue_link",
            description="Link a kanban task to an existing GitHub issue.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Kanban task ID"},
                    "repo": {"type": "string", "description": "GitHub repo (owner/repo)"},
                    "issue_number": {"type": "integer", "description": "GitHub issue number"},
                },
                "required": ["task_id", "repo", "issue_number"],
            },
        ),
        Tool(
            name="kanban_issue_create",
            description="Create a GitHub issue from a kanban task and auto-link them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Kanban task ID"},
                    "repo": {"type": "string", "description": "GitHub repo (default: from config)", "default": ""},
                    "labels": {"type": "string", "description": "Comma-separated labels", "default": ""},
                    "assignee": {"type": "string", "description": "GitHub username to assign", "default": ""},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_issue_status",
            description="Get the GitHub issue link status for a kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Kanban task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_issue_list",
            description="List all kanban-task ⟷ GitHub-issue links.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Filter by repo (owner/repo)", "default": ""},
                },
            },
        ),
        Tool(
            name="kanban_add_comment",
            description="Add a comment to a kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "body": {"type": "string", "description": "Comment body text"},
                    "author": {"type": "string", "description": "Author name", "default": "hermes"},
                },
                "required": ["task_id", "body"],
            },
        ),
        Tool(
            name="kanban_list_comments",
            description="List all comments for a kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_delete_comment",
            description="Delete a comment from a kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "comment_id": {"type": "string", "description": "Comment ID to delete"},
                },
                "required": ["task_id", "comment_id"],
            },
        ),
        Tool(
            name="kanban_add_checklist_item",
            description="Add a checklist item to a kanban task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "text": {"type": "string", "description": "Checklist item text"},
                },
                "required": ["task_id", "text"],
            },
        ),
        Tool(
            name="kanban_list_checklist",
            description="List all checklist items for a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="kanban_toggle_checklist_item",
            description="Toggle a checklist item's completed state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "item_id": {"type": "string", "description": "Checklist item ID"},
                },
                "required": ["task_id", "item_id"],
            },
        ),
        Tool(
            name="kanban_remove_checklist_item",
            description="Remove a checklist item from a task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID"},
                    "item_id": {"type": "string", "description": "Checklist item ID"},
                },
                "required": ["task_id", "item_id"],
            },
        ),
    ]


# ── Tool call handler ─────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Route tool calls to the kanban API."""
    try:
        result = _route(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except KanbanAPIError as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "status_code": e.status_code,
                "tool": name,
            }, indent=2),
        )]


def _route(name: str, args: dict) -> dict:
    """Dispatch a tool call."""
    handlers = {
        "kanban_list_tasks": _handle_list_tasks,
        "kanban_get_task": _handle_get_task,
        "kanban_create_task": _handle_create_task,
        "kanban_update_task": _handle_update_task,
        "kanban_claim": _handle_claim,
        "kanban_complete": _handle_complete,
        "kanban_block": _handle_block,
        "kanban_block_with_reason": _handle_block_with_reason,
        "kanban_split_task": _handle_split_task,
        "kanban_unclaim": _handle_unclaim,
        "kanban_delete_task": _handle_delete,
        "kanban_set_dependency": _handle_set_dependency,
        "kanban_set_skills": _handle_set_skills,
        "kanban_suggest": _handle_suggest,
        "kanban_list_agents": _handle_list_agents,
        "kanban_register_agent": _handle_register_agent,
        "kanban_heartbeat": _handle_heartbeat,
        "kanban_set_capabilities": _handle_set_capabilities,
        "kanban_add_log": _handle_add_log,
        "kanban_get_logs": _handle_get_logs,
        "kanban_issue_link": _handle_issue_link,
        "kanban_issue_create": _handle_issue_create,
        "kanban_issue_status": _handle_issue_status,
        "kanban_issue_list": _handle_issue_list,
        "kanban_add_comment": _handle_add_comment,
        "kanban_list_comments": _handle_list_comments,
        "kanban_delete_comment": _handle_delete_comment,
        "kanban_add_checklist_item": _handle_add_checklist_item,
        "kanban_list_checklist": _handle_list_checklist,
        "kanban_toggle_checklist_item": _handle_toggle_checklist_item,
        "kanban_remove_checklist_item": _handle_remove_checklist_item,
        # Project tools
        "kanban_list_projects": _handle_list_projects,
        "kanban_add_project": _handle_add_project,
        "kanban_update_project": _handle_update_project,
        "kanban_delete_project": _handle_delete_project,
        "kanban_suggest_by_project": _handle_suggest_by_project,
    }
    handler = handlers.get(name)
    if not handler:
        raise KanbanAPIError(f"Unknown tool: {name}", status_code=400)
    return handler(args)


def _get_str(args: dict, key: str, default: str = "") -> str:
    v = args.get(key, default)
    return str(v) if v is not None else default


def _get_int(args: dict, key: str, default: int = 0) -> int:
    v = args.get(key, default)
    try:
        return int(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def _handle_list_tasks(args: dict) -> dict:
    status = _get_str(args, "status")
    repo = _get_str(args, "repo")
    params = {}
    if status:
        params["status"] = status
    if repo:
        params["repo"] = repo
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    tasks = api_get(f"/api/tasks{'?' + qs if qs else ''}")
    return {"tasks": tasks, "count": len(tasks) if isinstance(tasks, list) else 0}


def _handle_get_task(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    task = api_get(f"/api/tasks/{task_id}")
    # Enrich with logs
    logs = api_get(f"/api/tasks/{task_id}/logs")
    # Find downstream blockers (tasks that depend on this one)
    all_tasks = api_get("/api/tasks")
    downstream = []
    if isinstance(all_tasks, list):
        for t in all_tasks:
            if t.get("depends_on") == task_id:
                downstream.append(t)
    return {
        "task": task,
        "logs": logs if isinstance(logs, list) else [],
        "downstream_blockers": downstream,
        "blocker_count": len(downstream),
    }


def _handle_create_task(args: dict) -> dict:
    body = {
        "title": _get_str(args, "title"),
        "description": _get_str(args, "description"),
        "priority": _get_int(args, "priority", 2),
        "repo": _get_str(args, "repo"),
        "roadmap_item": _get_str(args, "roadmap_item"),
        "created_by": _get_str(args, "created_by", "hermes"),
    }
    result = api_post("/api/tasks", body)
    # Set skills if provided
    skills = _get_str(args, "required_skills")
    if skills:
        # Find the task we just created
        tasks = api_get("/api/tasks")
        if isinstance(tasks, list) and tasks:
            newest = max(tasks, key=lambda t: t.get("created_at", 0))
            api_post(f"/api/tasks/{newest['id']}/skills", {"skills": skills})
            result["task_id"] = newest["id"]
            result["skills_set"] = skills
    return result


def _handle_update_task(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    body = {}
    if args.get("title"):
        body["title"] = _get_str(args, "title")
    if args.get("description"):
        body["description"] = _get_str(args, "description")
    prio = _get_int(args, "priority", -1)
    if prio >= 0:
        body["priority"] = prio
    if args.get("branch"):
        body["branch"] = _get_str(args, "branch")
    if not body:
        raise KanbanAPIError("No fields to update", status_code=400)
    return api_patch(f"/api/tasks/{task_id}", body)


def _handle_claim(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    agent = _get_str(args, "agent_id", "hermes")
    return api_post(f"/api/tasks/{task_id}/claim", {"agent_id": agent})


def _handle_complete(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    notes = _get_str(args, "notes", "Completed")
    return api_post(f"/api/tasks/{task_id}/complete", {"result_notes": notes})


def _handle_block(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    reason = _get_str(args, "reason", "Blocked")
    return api_post(f"/api/tasks/{task_id}/block", {"reason": reason})


def _handle_block_with_reason(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    reason = _get_str(args, "reason", "Blocked")
    return api_post(f"/api/tasks/{task_id}/block-with-reason", {"reason": reason})


def _handle_split_task(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    child_titles = args.get("child_titles", [])
    if not child_titles:
        raise KanbanAPIError("child_titles is required and must be a non-empty list", status_code=400)
    return api_post(f"/api/tasks/{task_id}/split", {"child_titles": child_titles})


def _handle_unclaim(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    return api_post(f"/api/tasks/{task_id}/unclaim")


def _handle_delete(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    return api_delete(f"/api/tasks/{task_id}")


def _handle_set_dependency(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    depends_on = _get_str(args, "depends_on")
    return api_post(f"/api/tasks/{task_id}/dependency", {"depends_on": depends_on})


def _handle_set_skills(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    skills = _get_str(args, "skills")
    return api_post(f"/api/tasks/{task_id}/skills", {"skills": skills})


def _handle_suggest(args: dict) -> dict:
    agent = _get_str(args, "agent_id")
    limit = _get_int(args, "limit", 5)
    params = f"limit={limit}"
    if agent:
        params += f"&agent_id={agent}"
    return api_get(f"/api/tasks/suggest?{params}")


def _handle_list_agents(args: dict) -> dict:
    agents = api_get("/api/agents")
    return {
        "agents": agents if isinstance(agents, list) else [],
        "count": len(agents) if isinstance(agents, list) else 0,
    }


def _handle_register_agent(args: dict) -> dict:
    return api_post("/api/agents/register", {
        "agent_id": _get_str(args, "agent_id"),
        "host": _get_str(args, "host"),
        "capabilities": _get_str(args, "capabilities"),
        "repo_focus": _get_str(args, "repo_focus"),
    })


def _handle_heartbeat(args: dict) -> dict:
    agent_id = _get_str(args, "agent_id")
    return api_post(f"/api/agents/{agent_id}/heartbeat", {
        "agent_id": agent_id,
        "status": _get_str(args, "status", "online"),
        "current_task_id": _get_str(args, "current_task_id"),
    })


def _handle_set_capabilities(args: dict) -> dict:
    agent_id = _get_str(args, "agent_id")
    return api_put(f"/api/agents/{agent_id}/capabilities", {
        "capabilities": _get_str(args, "capabilities"),
        "repo_focus": _get_str(args, "repo_focus"),
    })


def _handle_add_log(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    return api_post(f"/api/tasks/{task_id}/log", {
        "task_id": task_id,
        "action": _get_str(args, "action"),
        "agent_id": _get_str(args, "agent_id", "hermes"),
        "notes": _get_str(args, "notes"),
    })


def _handle_get_logs(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    logs = api_get(f"/api/tasks/{task_id}/logs")
    return {
        "task_id": task_id,
        "logs": logs if isinstance(logs, list) else [],
        "count": len(logs) if isinstance(logs, list) else 0,
    }


def _handle_issue_link(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    repo = _get_str(args, "repo")
    issue_number = _get_int(args, "issue_number")
    return api_post("/api/issues/link", {
        "task_id": task_id,
        "repo": repo,
        "issue_number": issue_number,
    })


def _handle_issue_create(args: dict) -> dict:
    return api_post("/api/issues/create", {
        "task_id": _get_str(args, "task_id"),
        "repo": _get_str(args, "repo"),
        "labels": _get_str(args, "labels"),
        "assignee": _get_str(args, "assignee"),
    })


def _handle_issue_status(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    return api_get(f"/api/issues/{task_id}")


def _handle_issue_list(args: dict) -> dict:
    repo = _get_str(args, "repo")
    qs = f"?repo={repo}" if repo else ""
    links = api_get(f"/api/issues{qs}")
    return {
        "links": links if isinstance(links, list) else [],
        "count": len(links) if isinstance(links, list) else 0,
    }


def _handle_add_comment(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    body = _get_str(args, "body")
    author = _get_str(args, "author", "hermes")
    return api_post(f"/api/tasks/{task_id}/comments", {
        "body": body,
        "author": author,
    })


def _handle_list_comments(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    comments = api_get(f"/api/tasks/{task_id}/comments")
    return {
        "task_id": task_id,
        "comments": comments if isinstance(comments, list) else [],
        "count": len(comments) if isinstance(comments, list) else 0,
    }


def _handle_delete_comment(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    comment_id = _get_str(args, "comment_id")
    return api_delete(f"/api/tasks/{task_id}/comments/{comment_id}")


def _handle_add_checklist_item(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    text = _get_str(args, "text")
    return api_post(f"/api/tasks/{task_id}/checklist", {"text": text})


def _handle_list_checklist(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    items = api_get(f"/api/tasks/{task_id}/checklist")
    completed = sum(1 for i in items if isinstance(i, dict) and i.get("completed"))
    return {
        "task_id": task_id,
        "items": items if isinstance(items, list) else [],
        "count": len(items) if isinstance(items, list) else 0,
        "completed": completed,
        "remaining": (len(items) if isinstance(items, list) else 0) - completed,
    }


def _handle_toggle_checklist_item(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    item_id = _get_str(args, "item_id")
    return api_post(f"/api/tasks/{task_id}/checklist/{item_id}/toggle")


def _handle_remove_checklist_item(args: dict) -> dict:
    task_id = _get_str(args, "task_id")
    item_id = _get_str(args, "item_id")
    return api_delete(f"/api/tasks/{task_id}/checklist/{item_id}")


# ── Project Tool Handlers ────────────────────────────────────────────


def _handle_list_projects(args: dict) -> dict:
    projects = api_get("/api/projects")
    return {
        "projects": projects if isinstance(projects, list) else [],
        "count": len(projects) if isinstance(projects, list) else 0,
    }


def _handle_add_project(args: dict) -> dict:
    return api_post("/api/projects", {
        "id": _get_str(args, "id"),
        "name": _get_str(args, "name"),
        "description": _get_str(args, "description"),
        "color": _get_str(args, "color", "#0ea5e9"),
        "priority": _get_int(args, "priority", 2),
        "active": bool(args.get("active", True)),
    })


def _handle_update_project(args: dict) -> dict:
    project_id = _get_str(args, "project_id")
    body = {}
    n = _get_str(args, "name")
    if n:
        body["name"] = n
    d = _get_str(args, "description")
    if d:
        body["description"] = d
    c = _get_str(args, "color")
    if c:
        body["color"] = c
    p = _get_int(args, "priority", 3)
    if p <= 3:
        body["priority"] = p
    body["active"] = bool(args.get("active", True))
    return api_patch(f"/api/projects/{project_id}", body)


def _handle_delete_project(args: dict) -> dict:
    return api_delete(f"/api/projects/{_get_str(args, 'project_id')}")


def _handle_suggest_by_project(args: dict) -> dict:
    limit = _get_int(args, "limit", 10)
    return api_get(f"/api/suggest-by-project?limit={limit}")


# ── Main entry point ──────────────────────────────────────────────────

def main():
    """Run the MCP server over stdio."""
    from mcp.server.stdio import stdio_server
    import asyncio

    async def run():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
