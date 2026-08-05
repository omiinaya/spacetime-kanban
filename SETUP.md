# Setup — Agent CLI Guide

This document tells AI agents (and humans) how to install the `kanban` CLI tool, configure their identity, set up branch validation hooks, and follow the task workflow.

**For full project installation (Docker, manual, production), see [INSTALL.md](./INSTALL.md).**

---

## Prerequisites

- Python 3.11+ (for the backend — the CLI is standalone)
- Access to a running kanban server at `localhost:8727`
- Git (for branch hook installation)

## Step 1: Install the CLI

```bash
# Clone the repo (or copy the `kanban` script from an existing clone)
git clone https://github.com/omiinaya/spacetime-kanban.git
cd spacetime-kanban

# Install the kanban CLI to PATH
cp kanban ~/.local/bin/
chmod +x ~/.local/bin/kanban
```

Verify it works:
```bash
kanban --help
kanban list
```

If `~/.local/bin` isn't on your PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Step 2: Configure Your Identity

The CLI auto-detects your agent ID from:
1. `KANBAN_AGENT_ID` environment variable (highest priority)
2. Output of `whoami`
3. `git config user.name` (lowercased, spaces → hyphens)

Set it explicitly:
```bash
export KANBAN_AGENT_ID=claude-vscode   # for Claude in VS Code
export KANBAN_AGENT_ID=hermes          # for Hermes Agent
```

Add to `~/.bashrc` to persist.

## Step 3: Verify Connectivity

```bash
kanban info
kanban list --status=available
```

Expected output:
```
Repo: spacetime-kanban
Agent: your-agent-name

No tasks matching filters.
```

If you see connection errors, ensure the API server is running on `localhost:8727`.

## Step 4: Install Branch Hooks (per repo)

Only do this for repos that participate in the kanban coordination:

```bash
cd ~/my-project   # the repo you want to protect
kanban install-hooks
```

This installs a `pre-push` hook that validates every branch name against the kanban before push. To remove:

```bash
cd ~/my-project
kanban uninstall-hooks
```

## Step 5: Task Workflow

```bash
# See what's available in your repo
kanban list --status=available --repo=my-project

# Claim a task (atomic — fails with 409 if another agent already grabbed it)
kanban claim task_1748397912_abc12345

# Create a branch referencing the task
git checkout -b "feature/kanban-task_1748397912_abc12345--my-feature"

# Do the work, commit, push
# The pre-push hook auto-validates the branch name

# Mark complete when done
kanban complete task_1748397912_abc12345 --notes="Implemented feature + tests"
```

## Branch Convention

```
{type}/kanban-{task_id}--{slug}
```

- `type`: `feature`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`
- `task_id`: from `kanban list` output (e.g., `task_1748397912_abc12345`)
- `--`: separator between task ID and slug
- `slug`: short kebab-case description

```bash
# Valid
feature/kanban-task_1748397912_abc12345--doh-fallback
fix/kanban-task_1748397913_abc12345--auth-bug

# Validate a branch before push
kanban check-branch "$(git branch --show-current)"
```

## CLI Command Reference

| Command | Description |
|---|---|
| `kanban list` | List tasks (filter with --status, --repo) |
| `kanban claim <task_id>` | Atomically claim a task |
| `kanban unclaim <task_id>` | Release a task |
| `kanban complete <task_id>` | Mark task as done |
| `kanban block <task_id>` | Mark task as blocked |
| `kanban create --title=...` | Create a task |
| `kanban skills <id> --skills=...` | Set required skills |
| `kanban suggest` | Show recommended tasks |
| `kanban register` | Join the swarm |
| `kanban heartbeat` | Send agent pulse |
| `kanban roadmap-import` | Bulk-import from ROADMAP.md |
| `kanban info` | Show agent status and connection info |
| `kanban check-branch <name>` | Validate a branch name |
| `kanban install-hooks` | Install pre-push hook in current repo |
| `kanban uninstall-hooks` | Remove pre-push hook |
| `kanban watch` | Watch for work and claim automatically |
| `kanban dispatch` | Dispatch tasks to workers |
| `kanban webhook list/add/remove` | Manage webhook subscriptions |

## API Reference

For the full REST API reference, see [API.md](./API.md).

For MCP server integration with Hermes Agent, see [MCP.md](./MCP.md).

## Uninstall

```bash
# Remove hooks from all repos where they were installed
cd ~/my-project
kanban uninstall-hooks

# Remove the CLI
rm ~/.local/bin/kanban
```

## Troubleshooting

| Problem | Solution |
|---|---|
| `Connection refused` | Server at :8727 not running. Start with `python server/main.py` or `docker compose up` |
| `409 Conflict` | Another agent claimed the task. Run `kanban list` to find another |
| `404 Not Found` | Task ID doesn't exist. List tasks to find valid IDs |
| Branch name rejected by hook | Format must be `{type}/kanban-{task_id}--{slug}`. Use `kanban check-branch` to debug |

For more, see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).
