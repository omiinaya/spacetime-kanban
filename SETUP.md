# Setup — for agents

This document tells any AI agent (or human) how to install and configure the kanban coordination system. Follow these steps in order.

## Prerequisites

- Python 3.10+
- Access to the kanban server at `localhost:8725` (the API server must be running)
- Git (for hook installation)

## Step 1: Install the CLI

```bash
# Clone the repo
git clone https://github.com/omiinaya/spacetimedb-kanban.git
cd spacetimedb-kanban

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

## Step 2: Configure your identity

The CLI auto-detects your agent ID from:
1. `KANBAN_AGENT_ID` environment variable (highest priority)
2. Output of `whoami`
3. `git config user.name` (lowercased, spaces→hyphens)

Set it explicitly if needed:
```bash
export KANBAN_AGENT_ID=claude-vscode
# or
export KANBAN_AGENT_ID=hermes
```

Add to `~/.bashrc` to persist.

## Step 3: Verify connectivity

```bash
kanban info
kanban list --status=available
```

Expected output:
```
Repo: spacetimedb-kanban
Agent: your-agent-name

You have no tasks in progress.
Run:  kanban list --status=available
```

If you see connection errors, the API server at `localhost:8725` may not be running.

## Step 4: Opt in a repo for branch validation (per-repo)

Only do this for repos that participate in the kanban coordination:

```bash
cd ~/sample-repo-p   # the repo you want to protect
kanban install-hooks
```

This writes a `pre-push` hook to `.git/hooks/pre-push` that validates every branch name against the kanban on push. To remove:

```bash
cd ~/sample-repo-p
kanban uninstall-hooks
```

The hook only runs `kanban check-branch` — it does nothing else. Main/master branches are skipped.

## Step 5: Workflow

```bash
# See what's available
kanban list --status=available --repo=sample-repo-p

# Claim a task (atomic — fails if another agent already grabbed it)
kanban claim task_1748397912_abc12345

# Create a branch referencing the task
git checkout -b "feature/kanban-task_1748397912_abc12345--my-feature"

# Do the work, commit, push

# Mark complete
kanban complete task_1748397912_abc12345 --notes="Implemented + tests passed"
```

## Branch Convention

```
{type}/kanban-{task_id}--{slug}
```

The task ID is the `id` field from `kanban list` output (e.g. `task_1748397912_abc12345`). The `--` separator distinguishes the task ID from the human-readable slug.

```bash
# Valid:
feature/kanban-task_1748397912_abc12345--doh-fallback
fix/kanban-task_1748397913_abc12345--auth-bug

# Check before push:
kanban check-branch "$(git branch --show-current)"
```

## Uninstall

```bash
# Remove hooks from repos where they were installed
cd ~/sample-repo-p
kanban uninstall-hooks

# Remove the CLI
rm ~/.local/bin/kanban
```
