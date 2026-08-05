# MCP Server Integration — Spacetimedb Kanban

This document describes how the Spacetimedb Kanban MCP server integrates with **Hermes Agent** (and any MCP-compatible client). The MCP server exposes the full kanban system as typed tools so Hermes can create, claim, complete, and manage tasks without shell command overhead.

---

## Overview

| Property | Value |
|---|---|
| **Server file** | `server/mcp_server.py` |
| **SDK** | MCP SDK v2 (`MCPServer` + `Tool.from_function()`) |
| **Transport** | `stdio` (native Hermes MCP client) |
| **Tools exposed** | **36** (covering tasks, agents, projects, logs, GitHub issues, comments, checklists) |
| **API backend** | Spacetimedb Kanban REST API (`http://localhost:8727` by default, configurable via `KANBAN_API` env var) |
| **HTTP library** | `urllib` (not `httpx`) — avoids event-loop conflicts with Hermes' asyncio |
| **Startup** | Auto-registers Hermes in the swarm on startup |

The server file lives at `server/mcp_server.py` and can also be run standalone:

```bash
cd server
python mcp_server.py
```

---

## Tool Reference

All 36 tools, grouped by category. Parameters with `?` are optional; defaults are shown where applicable.

### Task Tools (13)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_list_tasks` | `status?` (str), `repo?` (str) | List tasks with optional filtering by status (`available`, `claimed`, `blocked`, `completed`) and/or repo |
| `kanban_get_task` | `task_id` (str) | Full task details including activity logs and downstream blockers |
| `kanban_create_task` | `title` (str), `description?` (str), `priority?` (int=2), `repo?` (str), `roadmap_item?` (str), `required_skills?` (str), `created_by?` (str="hermes") | Create a new kanban task |
| `kanban_update_task` | `task_id` (str), `title?` (str), `description?` (str), `priority?` (int), `branch?` (str) | Update task fields (title, description, priority, branch) |
| `kanban_claim` | `task_id` (str), `agent_id?` (str="hermes") | **Atomic claim** — assigns task to an agent, fails with 409 if already taken |
| `kanban_complete` | `task_id` (str), `notes?` (str="Completed") | Mark a task as completed with optional result notes |
| `kanban_block` | `task_id` (str), `reason?` (str="Blocked") | Mark a task as blocked |
| `kanban_block_with_reason` | `task_id` (str), `reason` (str) | Mark a task as blocked with a persistent reason (stored in `fail_reason` field) |
| `kanban_unclaim` | `task_id` (str) | Release task back to `available` status |
| `kanban_delete_task` | `task_id` (str) | Permanently delete a task |
| `kanban_split_task` | `task_id` (str), `child_titles` (list[str]) | Split task into subtasks; creates child tasks, marks parent with subtask refs |
| `kanban_set_dependency` | `task_id` (str), `depends_on?` (str) | Set which task this depends on (pass empty string `""` to clear) |
| `kanban_set_skills` | `task_id` (str), `skills` (str) | Set required skills on a task (comma-separated tags) |

### Suggestion Tools (2)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_suggest` | `agent_id?` (str), `limit?` (int=5) | Get top-N scored task suggestions for an agent |
| `kanban_suggest_by_project` | `limit?` (int=10) | Get suggested tasks prioritised by project importance |

### Agent Tools (4)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_list_agents` | — | List all registered swarm agents with status and capabilities |
| `kanban_register_agent` | `agent_id` (str), `host?` (str), `capabilities?` (str), `repo_focus?` (str) | Register an agent in the swarm so it can claim tasks and receive suggestions |
| `kanban_heartbeat` | `agent_id` (str), `status?` (str="online"), `current_task_id?` (str) | Send swarm heartbeat. Call every 30–60s while active to avoid stale detection |
| `kanban_set_capabilities` | `agent_id` (str), `capabilities` (str), `repo_focus?` (str) | Update an agent's capabilities and repo focus |

### Log Tools (2)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_add_log` | `task_id` (str), `action` (str), `agent_id?` (str="hermes"), `notes?` (str) | Add an activity log entry to a task |
| `kanban_get_logs` | `task_id` (str) | Get the activity log for a task |

### Issue Tools (4)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_issue_link` | `task_id` (str), `repo` (str), `issue_number` (int) | Link a kanban task to an existing GitHub issue |
| `kanban_issue_create` | `task_id` (str), `repo?` (str), `labels?` (str), `assignee?` (str) | Create a GitHub issue from a kanban task and auto-link them |
| `kanban_issue_status` | `task_id` (str) | Get the GitHub issue link status for a kanban task |
| `kanban_issue_list` | `repo?` (str) | List all kanban-task ↔ GitHub-issue links |

### Comment Tools (3)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_add_comment` | `task_id` (str), `body` (str), `author?` (str="hermes") | Add a comment to a kanban task |
| `kanban_list_comments` | `task_id` (str) | List all comments for a kanban task |
| `kanban_delete_comment` | `task_id` (str), `comment_id` (str) | Delete a comment from a kanban task |

### Checklist Tools (4)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_add_checklist_item` | `task_id` (str), `text` (str) | Add a checklist item to a task |
| `kanban_list_checklist` | `task_id` (str) | List all checklist items with completion progress |
| `kanban_toggle_checklist_item` | `task_id` (str), `item_id` (str) | Toggle a checklist item's completed state |
| `kanban_remove_checklist_item` | `task_id` (str), `item_id` (str) | Remove a checklist item from a task |

### Project Tools (4)

| Tool | Parameters | Description |
|---|---|---|
| `kanban_list_projects` | — | List all registered projects with priority, colour, and active status |
| `kanban_add_project` | `id` (str), `name?` (str), `description?` (str), `color?` (str="#0ea5e9"), `priority?` (int=2), `active?` (bool=True) | Register a new project/repo |
| `kanban_update_project` | `project_id` (str), `name?` (str), `description?` (str), `color?` (str), `priority?` (int=3), `active?` (bool=True) | Update a project's details |
| `kanban_delete_project` | `project_id` (str) | Delete a registered project |

---

## Configuring Hermes Agent

Hermes supports two integration modes: **Config-based** (recommended, uses Hermes' native MCP client) and **Skill-based** (via the `hermes-agent` skill's MCP management tools).

### Method 1: Config-based (stdio transport)

Add the MCP server to your Hermes `config.yaml`:

```yaml
mcp_servers:
  spacetimedb-kanban:
    command: python
    args:
      - ~/spacetimedb-kanban/server/mcp_server.py
    env:
      KANBAN_API: "http://localhost:8727"
```

Hermes **auto-discovers and registers** all 36 tools when the config is loaded. No additional setup is needed — the tools become available as Hermes' built-in tool invocations.

### Method 2: Config-based (HTTP transport)

If you prefer to run the MCP server as a long-lived HTTP service:

```yaml
mcp_servers:
  spacetimedb-kanban:
    url: "http://localhost:8727/mcp/sse"
```

> **Note:** The stdio transport is the primary/native mode. The MCP server currently declares `transport="stdio"` — HTTP/SSE mode requires changing the transport type in `mcp_server.py` and running it as a background service.

### Method 3: Skill-based (via hermes-agent)

If you have the `hermes-agent` skill loaded, you can use its MCP management tools:

```
# Start the MCP server
mcp_run name=spacetimedb-kanban command="python" args="~/spacetimedb-kanban/server/mcp_server.py"

# Verify it's running
mcp_list
```

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KANBAN_API` | `http://localhost:8727` | Base URL of the kanban REST API |
| `PYTHONPATH` | _(auto)_ | Should include `server/` directory for imports |

---

## Example Workflows

### 1. Agent claims and completes a task

```
# Step 1: List available tasks
→ kanban_list_tasks(status="available")

# Step 2: Claim a task atomically
→ kanban_claim(task_id="task_1748397912_abc12345", agent_id="hermes")

# Step 3: Work on the task... (update branch, add logs)
→ kanban_update_task(task_id="task_1748397912_abc12345", branch="feature/kanban-task_1748397912_abc12345--doh-fallback")
→ kanban_add_log(task_id="task_1748397912_abc12345", action="started", notes="Beginning implementation")

# Step 4: Mark complete
→ kanban_complete(task_id="task_1748397912_abc12345", notes="Implemented DoH fallback + tests passed")
```

### 2. Creating a task with a dependency

```
# Create the prerequisite task
→ kanban_create_task(
    title="Set up CI pipeline",
    description="Configure GitHub Actions for automated testing",
    priority=0,
    repo="spacetimedb-kanban"
  )

# Create a dependent task
→ kanban_create_task(
    title="Add code coverage gates",
    description="Block merges below 80% coverage",
    priority=1,
    repo="spacetimedb-kanban"
  )
→ kanban_set_dependency(task_id="task_abc...", depends_on="task_def...")

# Attempting to claim the dependent fails until the prerequisite is done
→ kanban_claim(task_id="task_abc...")
  # → Error: "Cannot claim — dependency 'task_def...' is not done"
```

### 3. Splitting a task into subtasks

```
→ kanban_split_task(
    task_id="task_1748397912_abc12345",
    child_titles=["Design API schema", "Implement endpoints", "Write tests"]
  )
```

### 4. Adding a GitHub issue link

```
→ kanban_issue_link(task_id="task_1748397912_abc12345", repo="myorg/myrepo", issue_number=42)
→ kanban_issue_status(task_id="task_1748397912_abc12345")
```

---

## Troubleshooting

### Tools Not Showing Up

If you've added the MCP server to `config.yaml` but the tools aren't available:

1. **Check the MCP server is reachable** — run it standalone to test:
   ```bash
   cd ~/spacetimedb-kanban/server
   python mcp_server.py
   ```
   It should start without errors (it will block on stdio, which is expected).

2. **Check the kanban API is running** — the MCP server proxies to the REST API:
   ```bash
   curl http://localhost:8727/api/tasks
   ```

3. **Kill the MCP process** — Hermes' gateway automatically respawns it:
   ```bash
   # Find the spacetimedb-kanban MCP process
   ps aux | grep mcp_server
   # Kill it — Hermes will restart it on next tool invocation
   kill <PID>
   ```

4. **Restart Hermes** if the config changed:
   ```bash
   hermes stop && hermes start
   ```

### MCP Changes Not Reloading

If you modified `mcp_server.py` (added/removed tools, changed param schemas) but the tools haven't updated:

1. **Kill the running MCP process.** Hermes' gateway detects the connection drop and respawns the server with your changes on the next tool call.
   ```bash
   pkill -f mcp_server.py
   ```
2. Alternatively, restart Hermes entirely:
   ```bash
   hermes restart
   ```

### API Errors from MCP Tools

Errors from the kanban REST API propagate as `KanbanAPIError` with the HTTP status code:

| Status | Meaning |
|---|---|
| `409 Conflict` | Task already claimed by another agent, or dependency not satisfied |
| `404 Not Found` | Task ID doesn't exist |
| `400 Bad Request` | Missing required parameters or invalid values |

The error message includes the API response body for debugging.

---

## State Machine

Tasks follow this lifecycle, enforced by the server-side reducer:

```
available ──[claim]──→ in_progress ──[complete]──→ done
                  │
                  │  [unclaim]
                  ↓
              available

in_progress ──[block]──→ blocked
blocked ──[unclaim]──→ available
```

A task with a non-done dependency **cannot be claimed** — the server returns a 409 with a descriptive error.

---

## See Also

- `AGENTS.md` — Agent onboarding guide (REST API usage, conventions, heartbeat)
- `ARCHITECTURE.md` — System architecture and MCP integration overview
- `server/mcp_server.py` — MCP server source code
- `server/tests/test_mcp_server.py` — Test suite for MCP tools
