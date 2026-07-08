use std::cell::Cell;

use spacetimedb::{reducer, ReducerContext, Table};

#[spacetimedb::table(accessor = tasks, public)]
#[derive(Debug, Clone)]
pub struct Task {
    #[primary_key]
    pub id: String,
    pub title: String,
    pub description: String,
    pub priority: u8,
    pub status: String,
    pub assigned_to: Option<String>,
    pub repo: String,
    pub branch: Option<String>,
    pub roadmap_item: String,
    pub created_by: String,
    pub created_at: u64,
    pub updated_at: u64,
    pub depends_on: Option<String>,
    pub required_skills: Option<String>,
    pub score: u32,
    pub position: Option<u32>,
    // Failure tracking — retry limit enforcement
    pub fail_count: u32,
    pub max_attempts: u32,
    pub fail_reason: Option<String>,
    // Subtask decomposition
    pub subtask_of: Option<String>,
    pub subtasks: Option<String>,  // JSON array of child task IDs
}

#[spacetimedb::table(accessor = task_logs, public)]
#[derive(Debug, Clone)]
pub struct TaskLog {
    #[primary_key]
    pub id: String,
    pub task_id: String,
    pub action: String,
    pub agent_id: Option<String>,
    pub notes: Option<String>,
    pub timestamp: u64,
}

fn now_ms(ctx: &ReducerContext) -> u64 {
    ctx.timestamp.to_micros_since_unix_epoch() as u64 / 1000
}

fn make_id(prefix: &str, ctx: &ReducerContext) -> String {
    let counter = ID_COUNTER.with(|c| {
        let val = c.get();
        c.set(val + 1);
        val
    });
    let ts = now_ms(ctx);
    let discrim = ctx.sender().to_string();
    let short = if discrim.len() > 8 { &discrim[..8] } else { &discrim };
    format!("{}_{}_{}_{}", prefix, ts, short, counter)
}

thread_local! {
    static LOG_COUNTER: Cell<u64> = Cell::new(0);
    static ID_COUNTER: Cell<u64> = Cell::new(0);
}

fn log_action(
    ctx: &ReducerContext,
    task_id: &str,
    action: &str,
    agent_id: Option<&str>,
    notes: Option<&str>,
) {
    let counter = LOG_COUNTER.with(|c| {
        let val = c.get();
        c.set(val + 1);
        val
    });
    let id = format!("log_{}_{}", now_ms(ctx), counter);
    let now = now_ms(ctx);
    ctx.db.task_logs().insert(TaskLog {
        id,
        task_id: task_id.to_string(),
        action: action.to_string(),
        agent_id: agent_id.map(|s| s.to_string()),
        notes: notes.map(|s| s.to_string()),
        timestamp: now,
    });
}

fn find_task(ctx: &ReducerContext, task_id: &str) -> Option<Task> {
    ctx.db.tasks().iter().find(|t| t.id == task_id).map(|t| t.clone())
}

fn update_task_in_db(ctx: &ReducerContext, task: &Task) {
    // STDB v2.4 delete takes a row by value, not a closure
    let old: Vec<Task> = ctx.db.tasks().iter()
        .filter(|t| t.id == task.id)
        .map(|t| t.clone())
        .collect();
    for t in old {
        ctx.db.tasks().delete(t);
    }
    ctx.db.tasks().insert(task.clone());
}

fn delete_logs_for_task(ctx: &ReducerContext, task_id: &str) {
    let logs: Vec<TaskLog> = ctx.db.task_logs().iter()
        .filter(|l| l.task_id == task_id)
        .map(|l| l.clone())
        .collect();
    for log in logs {
        ctx.db.task_logs().delete(log);
    }
}

#[reducer]
pub fn add_task(
    ctx: &ReducerContext,
    id: String,
    title: String,
    description: String,
    priority: u8,
    repo: String,
    roadmap_item: String,
    created_by: String,
    initial_status: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let task_id = if id.is_empty() { make_id("task", ctx) } else { id };

    let status = if initial_status.is_empty() { "available".to_string() } else { initial_status };

    ctx.db.tasks().insert(Task {
        id: task_id.clone(),
        title,
        description,
        priority,
        status,
        assigned_to: None,
        repo,
        branch: None,
        roadmap_item,
        created_by,
        created_at: now,
        updated_at: now,
        depends_on: None,
        required_skills: None,
        score: 0,
        position: Some(now as u32),
        fail_count: 0,
        max_attempts: 3,
        fail_reason: None,
        subtask_of: None,
        subtasks: None,
    });

    log_action(ctx, &task_id, "created", None, None);
    Ok(())
}

#[reducer]
pub fn block_task_with_reason(
    ctx: &ReducerContext,
    task_id: String,
    reason: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    if task.status != "in_progress" {
        return Err(format!("Cannot block task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();

    // Increment fail_count and record reason
    task.fail_count += 1;
    task.fail_reason = if reason.is_empty() { None } else { Some(reason.clone()) };

    // If max_attempts reached, special handling — dispatcher will decide
    if task.fail_count >= task.max_attempts {
        task.status = "blocked".to_string();
        task.assigned_to = None;
    } else {
        // Under limit: return to available for retry
        task.status = "available".to_string();
        task.assigned_to = None;
    }

    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "blocked", agent.as_deref(), Some(&format!(
        "fail #{}/{}: {}", task.fail_count, task.max_attempts, reason
    )));
    Ok(())
}

#[reducer]
pub fn split_task(
    ctx: &ReducerContext,
    parent_task_id: String,
    child_titles_json: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut parent = find_task(ctx, &parent_task_id)
        .ok_or_else(|| "Parent task not found".to_string())?;

    if parent.status != "available" && parent.status != "blocked" {
        return Err(format!("Cannot split task with status: {}", parent.status));
    }

    // Parse child titles from JSON array
    let child_titles: Vec<String> = serde_json::from_str(&child_titles_json)
        .map_err(|e| format!("Invalid child titles JSON: {}", e))?;

    if child_titles.is_empty() {
        return Err("Must specify at least one child title".to_string());
    }

    let mut child_ids = Vec::new();
    let sender = ctx.sender().to_string();

    for title in &child_titles {
        let child_id = make_id("task", ctx);
        child_ids.push(child_id.clone());
        ctx.db.tasks().insert(Task {
            id: child_id.clone(),
            title: title.clone(),
            description: format!("Subtask of: {} ({})", parent.title, parent_task_id),
            priority: parent.priority,
            status: "available".to_string(),
            assigned_to: None,
            repo: parent.repo.clone(),
            branch: None,
            roadmap_item: parent.roadmap_item.clone(),
            created_by: sender.clone(),
            created_at: now,
            updated_at: now,
            depends_on: None,
            required_skills: parent.required_skills.clone(),
            score: 0,
            position: Some(now as u32),
            fail_count: 0,
            max_attempts: parent.max_attempts,
            fail_reason: None,
            subtask_of: Some(parent_task_id.clone()),
            subtasks: None,
        });
        log_action(ctx, &child_id, "created_as_subtask", None, Some(&format!("parent: {}", parent_task_id)));
    }

    // Update parent with subtask list and mark as blocked (tracked by children)
    parent.status = "blocked".to_string();
    parent.assigned_to = None;
    parent.updated_at = now;
    parent.fail_reason = Some(format!(
        "Split into {} subtask(s): {}",
        child_titles.len(),
        child_titles.join(", ")
    ));
    update_task_in_db(ctx, &parent);

    log_action(ctx, &parent_task_id, "split", None, Some(&format!(
        "{} child tasks created", child_titles.len()
    )));
    Ok(())
}

#[reducer]
pub fn reset_fail_count(
    ctx: &ReducerContext,
    task_id: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    task.fail_count = 0;
    task.fail_reason = None;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "fail_reset", task.assigned_to.as_deref(), None);
    Ok(())
}

#[reducer]
pub fn set_max_attempts(
    ctx: &ReducerContext,
    task_id: String,
    max_attempts: u32,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    task.max_attempts = max_attempts;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    Ok(())
}

#[reducer]
pub fn claim_task(ctx: &ReducerContext, task_id: String, agent_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    if task.status != "available" {
        return Err(format!("Task is not available (current status: {})", task.status));
    }

    // Check dependency: if task depends on another task, that dependency must be done
    if let Some(ref dep_id) = task.depends_on {
        let dep = find_task(ctx, dep_id)
            .ok_or_else(|| format!("Dependency task '{}' not found", dep_id))?;
        if dep.status != "done" {
            return Err(format!(
                "Cannot claim — dependency '{}' ({}) is not done (status: {})",
                dep_id, dep.title, dep.status
            ));
        }
    }

    task.status = "in_progress".to_string();
    task.assigned_to = Some(agent_id.clone());
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "claimed", Some(&agent_id), None);
    Ok(())
}

#[reducer]
pub fn unclaim_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    if task.status != "in_progress" && task.status != "blocked" {
        return Err(format!("Cannot unclaim task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = "available".to_string();
    task.assigned_to = None;
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "unclaimed", agent.as_deref(), None);
    Ok(())
}

#[reducer]
pub fn complete_task(ctx: &ReducerContext, task_id: String, result_notes: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    if task.status != "in_progress" {
        return Err(format!("Cannot complete task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = "done".to_string();
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "completed", agent.as_deref(), Some(&result_notes));
    Ok(())
}

#[reducer]
pub fn block_task(ctx: &ReducerContext, task_id: String, reason: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    if task.status != "in_progress" {
        return Err(format!("Cannot block task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = "blocked".to_string();
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "blocked", agent.as_deref(), Some(&reason));
    Ok(())
}

#[reducer]
pub fn update_task(
    ctx: &ReducerContext,
    task_id: String,
    title: String,
    description: String,
    priority: u8,
    branch: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    let branch_opt = if branch.is_empty() { None } else { Some(branch) };

    task.title = title;
    task.description = description;
    task.priority = priority;
    task.branch = branch_opt;
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    Ok(())
}

#[reducer]
pub fn set_dependency(
    ctx: &ReducerContext,
    task_id: String,
    depends_on: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;

    // If depends_on is empty, clear the dependency
    let dep = if depends_on.is_empty() {
        None
    } else {
        // Verify the dependency task exists
        let _dep_task = find_task(ctx, &depends_on)
            .ok_or_else(|| format!("Dependency task '{}' not found", depends_on))?;
        Some(depends_on.clone())
    };

    task.depends_on = dep;
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "dependency_set", task.assigned_to.as_deref(), Some(&depends_on));
    Ok(())
}

#[reducer]
pub fn delete_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    ctx.db.tasks().delete(task);
    delete_logs_for_task(ctx, &task_id);
    // Clean up label assignments
    let assignments: Vec<TaskLabelAssignment> = ctx
        .db
        .task_label_assignments()
        .iter()
        .filter(|a| a.task_id == task_id)
        .map(|a| a.clone())
        .collect();
    for a in assignments {
        ctx.db.task_label_assignments().delete(a);
    }
    // Clean up checklist items
    let checklist_items: Vec<TaskChecklistItem> = ctx.db.task_checklists().iter()
        .filter(|i| i.task_id == task_id)
        .map(|i| i.clone())
        .collect();
    for i in checklist_items {
        ctx.db.task_checklists().delete(i);
    }
    Ok(())
}

#[reducer]
pub fn seed_sample_tasks(ctx: &ReducerContext) -> Result<(), String> {
    let now = now_ms(ctx);
    let sender = ctx.sender().to_string();

    let samples = vec![
        ("Add DNS-over-HTTPS fallback", "When upstream DNS fails, fall back to Cloudflare DoH", 0u8, "sample-repo-p", "Phase 3 — DNS Resilience"),
        ("Implement ad-block list auto-update", "Daily pull from firebog.net, parse and dedupe", 1u8, "sample-repo-p", "Phase 3 — DNS Resilience"),
        ("Add query logging with retention", "Store last 24h of DNS queries, auto-purge", 1u8, "sample-repo-p", "Phase 2 — Observability"),
        ("Write integration tests for blocking engine", "Test coverage for DNS blocking edge cases", 2u8, "sample-repo-p", "Phase 2 — Observability"),
        ("Add Prometheus metrics endpoint", "Expose query count, block rate, latency p50/p99", 2u8, "sample-repo-p", "Phase 2 — Observability"),
        ("Set up CI/CD pipeline", "GitHub Actions: build, test, lint, deploy", 3u8, "sample-repo-p", "Phase 1 — Foundation"),
    ];

    for (title, desc, priority, repo, roadmap) in samples {
        let slug: String = title.chars().take(12).collect();
        let id = format!("sample_{}_{}", now, slug);
        ctx.db.tasks().insert(Task {
            id: id.clone(),
            title: title.to_string(),
            description: desc.to_string(),
            priority,
            status: "available".to_string(),
            assigned_to: None,
            repo: repo.to_string(),
            branch: None,
            roadmap_item: roadmap.to_string(),
            created_by: sender.clone(),
            created_at: now,
            updated_at: now,
            depends_on: None,
            required_skills: None,
            score: 0,
            position: Some(now as u32),
            fail_count: 0,
            max_attempts: 3,
            fail_reason: None,
            subtask_of: None,
            subtasks: None,
        });

        ctx.db.task_logs().insert(TaskLog {
            id: format!("log_{}_{}", now, slug),
            task_id: id,
            action: "created".to_string(),
            agent_id: None,
            notes: None,
            timestamp: now,
        });
    }

    Ok(())
}

// ── Agent Registry (Swarm Mode) ──────────────────────────────────────

#[spacetimedb::table(accessor = swarm_agents, public)]
#[derive(Debug, Clone)]
pub struct SwarmAgent {
    #[primary_key]
    pub id: String,                  // agent name (globally unique)
    pub host: String,                // machine hostname
    pub capabilities: Option<String>, // comma-separated skill tags
    pub repo_focus: Option<String>,  // repo they're focused on
    pub current_task_id: Option<String>,
    pub status: String,              // "online", "busy", "offline"
    pub last_heartbeat: u64,
    pub first_seen: u64,
}

fn find_agent(ctx: &ReducerContext, agent_id: &str) -> Option<SwarmAgent> {
    ctx.db.swarm_agents().iter()
        .find(|a| a.id == agent_id)
        .map(|a| a.clone())
}

fn update_agent_in_db(ctx: &ReducerContext, agent: &SwarmAgent) {
    let old: Vec<SwarmAgent> = ctx.db.swarm_agents().iter()
        .filter(|a| a.id == agent.id)
        .map(|a| a.clone())
        .collect();
    for a in old {
        ctx.db.swarm_agents().delete(a);
    }
    ctx.db.swarm_agents().insert(agent.clone());
}

#[reducer]
pub fn register_agent(
    ctx: &ReducerContext,
    agent_id: String,
    host: String,
    capabilities: String,
    repo_focus: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let cap_opt = if capabilities.is_empty() { None } else { Some(capabilities) };
    let repo_opt = if repo_focus.is_empty() { None } else { Some(repo_focus) };

    if let Some(mut existing) = find_agent(ctx, &agent_id) {
        // Update heartbeat and capabilities
        existing.host = host;
        existing.capabilities = cap_opt;
        existing.repo_focus = repo_opt;
        existing.status = "online".to_string();
        existing.last_heartbeat = now;
        update_agent_in_db(ctx, &existing);
        log_action(ctx, &agent_id, "agent_reconnected", Some(&agent_id), None);
    } else {
        ctx.db.swarm_agents().insert(SwarmAgent {
            id: agent_id.clone(),
            host,
            capabilities: cap_opt,
            repo_focus: repo_opt,
            current_task_id: None,
            status: "online".to_string(),
            last_heartbeat: now,
            first_seen: now,
        });
        log_action(ctx, &agent_id, "agent_registered", Some(&agent_id), None);
    }
    Ok(())
}

#[reducer]
pub fn agent_heartbeat(
    ctx: &ReducerContext,
    agent_id: String,
    status: String,
    current_task_id: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut agent = find_agent(ctx, &agent_id)
        .ok_or_else(|| "Agent not registered".to_string())?;

    let task_opt = if current_task_id.is_empty() { None } else { Some(current_task_id) };
    let new_status = if status == "busy" || task_opt.is_some() {
        "busy".to_string()
    } else {
        "online".to_string()
    };

    agent.current_task_id = task_opt;
    agent.status = new_status;
    agent.last_heartbeat = now;
    update_agent_in_db(ctx, &agent);
    Ok(())
}

#[reducer]
pub fn set_agent_capabilities(
    ctx: &ReducerContext,
    agent_id: String,
    capabilities: String,
    repo_focus: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut agent = find_agent(ctx, &agent_id)
        .ok_or_else(|| "Agent not registered".to_string())?;
    agent.capabilities = if capabilities.is_empty() { None } else { Some(capabilities) };
    agent.repo_focus = if repo_focus.is_empty() { None } else { Some(repo_focus) };
    agent.last_heartbeat = now;
    update_agent_in_db(ctx, &agent);
    Ok(())
}

// ── Task Skills (Capability Tags) ────────────────────────────────────

#[reducer]
pub fn set_task_skills(
    ctx: &ReducerContext,
    task_id: String,
    skills: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    task.required_skills = if skills.is_empty() { None } else { Some(skills.clone()) };
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "skills_set", task.assigned_to.as_deref(), Some(&skills));
    Ok(())
}

// ── Project Table (with Priority) ────────────────────────────────────────
// Each project is keyed by its repo slug (e.g. "sample-repo-q").
// The `repo` field on Task maps to this project's `id`.
// Project `priority` (0=most important, 3=lowest) is a multiplicative
// factor in the task suggestion scoring engine.

#[spacetimedb::table(accessor = kanban_projects, public)]
#[derive(Debug, Clone)]
pub struct KanbanProject {
    #[primary_key]
    pub id: String,           // repo slug — matches Task.repo
    pub name: String,         // display name
    pub description: String,
    pub color: String,        // hex colour e.g. "#0ea5e9"
    pub priority: u8,         // 0=most important … 3=lowest (same scale as Task.priority)
    pub active: bool,
    pub created_at: u64,
    pub updated_at: u64,
}

fn find_project(ctx: &ReducerContext, project_id: &str) -> Option<KanbanProject> {
    ctx.db.kanban_projects().iter()
        .find(|p| p.id == project_id)
        .map(|p| p.clone())
}

fn update_project_in_db(ctx: &ReducerContext, project: &KanbanProject) {
    let old: Vec<KanbanProject> = ctx.db.kanban_projects().iter()
        .filter(|p| p.id == project.id)
        .map(|p| p.clone())
        .collect();
    for p in old { ctx.db.kanban_projects().delete(p); }
    ctx.db.kanban_projects().insert(project.clone());
}

#[reducer]
pub fn add_project(
    ctx: &ReducerContext,
    id: String,           // repo slug — must match Task.repo
    name: String,
    description: String,
    color: String,
    priority: u8,         // 0=most important … 3=lowest
    active: bool,
) -> Result<(), String> {
    let now = now_ms(ctx);
    if id.is_empty() {
        return Err("Project id (repo slug) is required".into());
    }
    if find_project(ctx, &id).is_some() {
        return Err(format!("Project '{}' already exists", id));
    }
    let color = if color.is_empty() { "#6b7280" } else { &color };
    let label = if name.is_empty() { id.clone() } else { name };
    ctx.db.kanban_projects().insert(KanbanProject {
        id,
        name: label,
        description,
        color: color.to_string(),
        priority: if priority > 3 { 2 } else { priority },
        active,
        created_at: now,
        updated_at: now,
    });
    Ok(())
}

#[reducer]
pub fn update_project(
    ctx: &ReducerContext,
    id: String,
    name: String,
    description: String,
    color: String,
    priority: u8,
    active: bool,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut proj = find_project(ctx, &id)
        .ok_or_else(|| format!("Project '{}' not found", id))?;
    if !name.is_empty() { proj.name = name; }
    if !description.is_empty() { proj.description = description; }
    if !color.is_empty() { proj.color = color; }
    if priority <= 3 { proj.priority = priority; }
    proj.active = active;
    proj.updated_at = now;
    update_project_in_db(ctx, &proj);
    Ok(())
}

#[reducer]
pub fn delete_project(ctx: &ReducerContext, id: String) -> Result<(), String> {
    let proj = find_project(ctx, &id)
        .ok_or_else(|| format!("Project '{}' not found", id))?;
    ctx.db.kanban_projects().delete(proj);
    Ok(())
}

// ── Priority Scoring ─────────────────────────────────────────────────

#[reducer]
pub fn set_task_score(
    ctx: &ReducerContext,
    task_id: String,
    score: u32,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    task.score = score;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    Ok(())
}

#[reducer]
pub fn add_log(
    ctx: &ReducerContext,
    task_id: String,
    action: String,
    agent_id: String,
    notes: String,
) -> Result<(), String> {
    let _task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    let agent_opt = if agent_id.is_empty() { None } else { Some(agent_id.as_str()) };
    let notes_opt = if notes.is_empty() { None } else { Some(notes.as_str()) };
    log_action(ctx, &task_id, &action, agent_opt, notes_opt);
    Ok(())
}

// ── Webhook Subscriptions (STDB-native) ──────────────────────────────

#[spacetimedb::table(accessor = webhook_subscriptions, public)]
#[derive(Debug, Clone)]
pub struct WebhookSubscription {
    #[primary_key]
    pub id: String,
    pub url: String,
    pub wh_type: String,     // "discord", "slack", "telegram", "generic"
    pub events: String,       // comma-separated event types
    pub label: String,
    pub created_at: u64,
}

fn find_webhook(ctx: &ReducerContext, wh_id: &str) -> Option<WebhookSubscription> {
    ctx.db.webhook_subscriptions().iter()
        .find(|w| w.id == wh_id)
        .map(|w| w.clone())
}

#[reducer]
pub fn add_webhook_subscription(
    ctx: &ReducerContext,
    id: String,
    url: String,
    wh_type: String,
    events: String, // comma-separated, e.g. "created,claimed,completed,blocked"
    label: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    ctx.db.webhook_subscriptions().insert(WebhookSubscription {
        id,
        url,
        wh_type,
        events,
        label,
        created_at: now,
    });
    Ok(())
}

#[reducer]
pub fn remove_webhook_subscription(ctx: &ReducerContext, wh_id: String) -> Result<(), String> {
    let wh = find_webhook(ctx, &wh_id)
        .ok_or_else(|| "Webhook not found".to_string())?;
    ctx.db.webhook_subscriptions().delete(wh);
    Ok(())
}

#[reducer]
pub fn update_webhook_subscription(
    ctx: &ReducerContext,
    wh_id: String,
    url: String,
    wh_type: String,
    events: String,
    label: String,
) -> Result<(), String> {
    let mut wh = find_webhook(ctx, &wh_id)
        .ok_or_else(|| "Webhook not found".to_string())?;
    if !url.is_empty() { wh.url = url; }
    if !wh_type.is_empty() { wh.wh_type = wh_type; }
    if !events.is_empty() { wh.events = events; }
    if !label.is_empty() { wh.label = label; }
    let old: Vec<WebhookSubscription> = ctx.db.webhook_subscriptions().iter()
        .filter(|w| w.id == wh.id)
        .map(|w| w.clone())
        .collect();
    for w in old { ctx.db.webhook_subscriptions().delete(w); }
    ctx.db.webhook_subscriptions().insert(wh);
    Ok(())
}

// ── Issue Links (STDB-native, two-way GitHub sync) ───────────────────

#[spacetimedb::table(accessor = issue_links, public)]
#[derive(Debug, Clone)]
pub struct IssueLink {
    #[primary_key]
    pub kanban_task_id: String,
    pub issue_number: u32,
    pub repo: String,
    pub issue_url: String,
    pub html_url: String,
    pub status: String,      // "open" or "closed"
    pub linked_at: u64,
}

fn find_issue_link(ctx: &ReducerContext, task_id: &str) -> Option<IssueLink> {
    ctx.db.issue_links().iter()
        .find(|l| l.kanban_task_id == task_id)
        .map(|l| l.clone())
}

#[reducer]
pub fn link_issue(
    ctx: &ReducerContext,
    kanban_task_id: String,
    issue_number: u32,
    repo: String,
    issue_url: String,
    html_url: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    // Remove existing link for this task if any
    if let Some(existing) = find_issue_link(ctx, &kanban_task_id) {
        ctx.db.issue_links().delete(existing);
    }
    ctx.db.issue_links().insert(IssueLink {
        kanban_task_id,
        issue_number,
        repo,
        issue_url,
        html_url,
        status: "open".to_string(),
        linked_at: now,
    });
    Ok(())
}

#[reducer]
pub fn unlink_issue(ctx: &ReducerContext, kanban_task_id: String) -> Result<(), String> {
    let link = find_issue_link(ctx, &kanban_task_id)
        .ok_or_else(|| "Issue link not found".to_string())?;
    ctx.db.issue_links().delete(link);
    Ok(())
}

#[reducer]
pub fn update_issue_link_status(
    ctx: &ReducerContext,
    kanban_task_id: String,
    status: String,
) -> Result<(), String> {
    let mut link = find_issue_link(ctx, &kanban_task_id)
        .ok_or_else(|| "Issue link not found".to_string())?;
    link.status = status;
    let old: Vec<IssueLink> = ctx.db.issue_links().iter()
        .filter(|l| l.kanban_task_id == link.kanban_task_id)
        .map(|l| l.clone())
        .collect();
    for l in old { ctx.db.issue_links().delete(l); }
    ctx.db.issue_links().insert(link);
    Ok(())
}

// ── Labels / Tag System ───────────────────────────────────────────────

#[spacetimedb::table(accessor = kanban_labels, public)]
#[derive(Debug, Clone)]
pub struct KanbanLabel {
    #[primary_key]
    pub id: String,
    pub name: String,
    pub color: String,         // hex color, e.g. "#0ea5e9"
    pub description: String,
    pub created_at: u64,
}

#[spacetimedb::table(accessor = task_label_assignments, public)]
#[derive(Debug, Clone)]
pub struct TaskLabelAssignment {
    #[primary_key]
    pub id: String,              // composite: "task_id:label_id"
    pub task_id: String,
    pub label_id: String,
}

fn assignment_id(task_id: &str, label_id: &str) -> String {
    format!("{}:{}", task_id, label_id)
}

fn find_label(ctx: &ReducerContext, label_id: &str) -> Option<KanbanLabel> {
    ctx.db.kanban_labels().iter()
        .find(|l| l.id == label_id)
        .map(|l| l.clone())
}

#[reducer]
pub fn add_label(
    ctx: &ReducerContext,
    id: String,
    name: String,
    color: String,
    description: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let label_id = if id.is_empty() { make_id("label", ctx) } else { id };
    ctx.db.kanban_labels().insert(KanbanLabel {
        id: label_id,
        name,
        color,
        description,
        created_at: now,
    });
    Ok(())
}

#[reducer]
pub fn remove_label(ctx: &ReducerContext, label_id: String) -> Result<(), String> {
    let label = find_label(ctx, &label_id)
        .ok_or_else(|| "Label not found".to_string())?;
    ctx.db.kanban_labels().delete(label);
    // Clean up all task assignments for this label
    let assignments: Vec<TaskLabelAssignment> = ctx.db.task_label_assignments().iter()
        .filter(|a| a.label_id == label_id)
        .map(|a| a.clone())
        .collect();
    for a in assignments {
        ctx.db.task_label_assignments().delete(a);
    }
    Ok(())
}

#[reducer]
pub fn update_label(
    ctx: &ReducerContext,
    label_id: String,
    name: String,
    color: String,
    description: String,
) -> Result<(), String> {
    let mut label = find_label(ctx, &label_id)
        .ok_or_else(|| "Label not found".to_string())?;
    if !name.is_empty() { label.name = name; }
    if !color.is_empty() { label.color = color; }
    label.description = description;
    let old: Vec<KanbanLabel> = ctx.db.kanban_labels().iter()
        .filter(|l| l.id == label.id)
        .map(|l| l.clone())
        .collect();
    for l in old { ctx.db.kanban_labels().delete(l); }
    ctx.db.kanban_labels().insert(label);
    Ok(())
}

#[reducer]
pub fn assign_label_to_task(
    ctx: &ReducerContext,
    task_id: String,
    label_id: String,
) -> Result<(), String> {
    // Verify both exist
    let _task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    let _label = find_label(ctx, &label_id)
        .ok_or_else(|| "Label not found".to_string())?;
    // Check not already assigned
    let exists = ctx.db.task_label_assignments().iter()
        .any(|a| a.task_id == task_id && a.label_id == label_id);
    if !exists {
        ctx.db.task_label_assignments().insert(TaskLabelAssignment {
            id: assignment_id(&task_id, &label_id),
            task_id: task_id.clone(),
            label_id,
        });
    }
    Ok(())
}

#[reducer]
pub fn unassign_label_from_task(
    ctx: &ReducerContext,
    task_id: String,
    label_id: String,
) -> Result<(), String> {
    let assignment: Vec<TaskLabelAssignment> = ctx.db.task_label_assignments().iter()
        .filter(|a| a.task_id == task_id && a.label_id == label_id)
        .map(|a| a.clone())
        .collect();
    if assignment.is_empty() {
        return Err("Label assignment not found".to_string());
    }
    for a in assignment {
        ctx.db.task_label_assignments().delete(a);
    }
    Ok(())
}

// ── Webhook Delivery Log ─────────────────────────────────────────────

#[reducer]
pub fn batch_assign_labels(
    ctx: &ReducerContext,
    task_ids: String,
    label_ids: String,
) -> Result<(), String> {
    let tasks: Vec<&str> = task_ids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let labels: Vec<&str> = label_ids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if tasks.is_empty() || labels.is_empty() {
        return Err("task_ids and label_ids must be non-empty".to_string());
    }
    let mut count = 0u64;
    for task_id in &tasks {
        let _task = find_task(ctx, task_id)
            .ok_or_else(|| format!("Task not found: {task_id}"))?;
        for label_id in &labels {
            let _label = find_label(ctx, label_id)
                .ok_or_else(|| format!("Label not found: {label_id}"))?;
            let exists = ctx.db.task_label_assignments().iter()
                .any(|a| a.task_id == *task_id && a.label_id == *label_id);
            if !exists {
                ctx.db.task_label_assignments().insert(TaskLabelAssignment {
                    id: assignment_id(task_id, label_id),
                    task_id: task_id.to_string(),
                    label_id: label_id.to_string(),
                });
                count += 1;
            }
        }
    }
    log_action(ctx, &format!("batch_label_assign_{}", count), "batch_assign_labels", None, Some(&format!("{} tasks, {} labels: {} assignments", tasks.len(), labels.len(), count)));
    Ok(())
}

#[reducer]
pub fn batch_unassign_labels(
    ctx: &ReducerContext,
    task_ids: String,
    label_ids: String,
) -> Result<(), String> {
    let tasks: Vec<&str> = task_ids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    let labels: Vec<&str> = label_ids.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()).collect();
    if tasks.is_empty() || labels.is_empty() {
        return Err("task_ids and label_ids must be non-empty".to_string());
    }
    let mut count = 0u64;
    for task_id in &tasks {
        for label_id in &labels {
            let to_remove: Vec<TaskLabelAssignment> = ctx.db.task_label_assignments().iter()
                .filter(|a| a.task_id == *task_id && a.label_id == *label_id)
                .map(|a| a.clone())
                .collect();
            for a in to_remove {
                ctx.db.task_label_assignments().delete(a);
                count += 1;
            }
        }
    }
    log_action(ctx, &format!("batch_label_unassign_{}", count), "batch_unassign_labels", None, Some(&format!("{} tasks, {} labels: {} removed", tasks.len(), labels.len(), count)));
    Ok(())
}

// ── Webhook Delivery Log ─────────────────────────────────────────────

#[spacetimedb::table(accessor = webhook_deliveries, public)]
#[derive(Debug, Clone)]
pub struct WebhookDelivery {
    #[primary_key]
    pub id: String,
    pub webhook_id: String,
    pub event: String,
    pub url: String,
    pub status_code: u32,       // HTTP status code (0 = no response/error)
    pub response_body: String,   // truncated response or error message
    pub success: bool,
    pub delivered_at: u64,
}

#[reducer]
pub fn log_webhook_delivery(
    ctx: &ReducerContext,
    id: String,
    webhook_id: String,
    event: String,
    url: String,
    status_code: u32,
    response_body: String,
    success: bool,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let delivery_id = if id.is_empty() { make_id("whdel", ctx) } else { id };
    ctx.db.webhook_deliveries().insert(WebhookDelivery {
        id: delivery_id,
        webhook_id,
        event,
        url,
        status_code,
        response_body,
        success,
        delivered_at: now,
    });
    Ok(())
}

// ── Task Comments ─────────────────────────────────────────────────────

#[spacetimedb::table(accessor = task_comments, public)]
#[derive(Debug, Clone)]
pub struct TaskComment {
    #[primary_key]
    pub id: String,
    pub task_id: String,
    pub author: String,
    pub body: String,
    pub created_at: u64,
}

#[reducer]
pub fn add_comment(
    ctx: &ReducerContext,
    id: String,
    task_id: String,
    author: String,
    body: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let comment_id = if id.is_empty() { make_id("cmt", ctx) } else { id };
    ctx.db.task_comments().insert(TaskComment {
        id: comment_id,
        task_id,
        author,
        body,
        created_at: now,
    });
    Ok(())
}

#[reducer]
pub fn delete_comment(ctx: &ReducerContext, comment_id: String) -> Result<(), String> {
    let comment: Vec<TaskComment> = ctx.db.task_comments().iter()
        .filter(|c| c.id == comment_id)
        .map(|c| c.clone())
        .collect();
    if comment.is_empty() {
        return Err("Comment not found".to_string());
    }
    for c in comment {
        ctx.db.task_comments().delete(c);
    }
    Ok(())
}

// ── Task Checklists / Subtasks ─────────────────────────────────────────

#[spacetimedb::table(accessor = task_checklists, public)]
#[derive(Debug, Clone)]
pub struct TaskChecklistItem {
    #[primary_key]
    pub id: String,
    pub task_id: String,
    pub text: String,
    pub completed: bool,
    pub position: u32,
    pub created_at: u64,
}

fn find_checklist_item(ctx: &ReducerContext, item_id: &str) -> Option<TaskChecklistItem> {
    ctx.db.task_checklists().iter()
        .find(|i| i.id == item_id)
        .map(|i| i.clone())
}

#[reducer]
pub fn add_checklist_item(
    ctx: &ReducerContext,
    id: String,
    task_id: String,
    text: String,
) -> Result<(), String> {
    // Verify task exists
    let _task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    let now = now_ms(ctx);
    let item_id = if id.is_empty() { make_id("cl", ctx) } else { id };
    // Determine next position
    let max_pos = ctx.db.task_checklists().iter()
        .filter(|i| i.task_id == task_id)
        .map(|i| i.position)
        .max()
        .unwrap_or(0);
    ctx.db.task_checklists().insert(TaskChecklistItem {
        id: item_id,
        task_id,
        text,
        completed: false,
        position: max_pos + 1,
        created_at: now,
    });
    Ok(())
}

#[reducer]
pub fn toggle_checklist_item(ctx: &ReducerContext, item_id: String) -> Result<(), String> {
    let mut item = find_checklist_item(ctx, &item_id)
        .ok_or_else(|| "Checklist item not found".to_string())?;
    item.completed = !item.completed;
    let old: Vec<TaskChecklistItem> = ctx.db.task_checklists().iter()
        .filter(|i| i.id == item.id)
        .map(|i| i.clone())
        .collect();
    for i in old { ctx.db.task_checklists().delete(i); }
    ctx.db.task_checklists().insert(item);
    Ok(())
}

#[reducer]
pub fn remove_checklist_item(ctx: &ReducerContext, item_id: String) -> Result<(), String> {
    let item = find_checklist_item(ctx, &item_id)
        .ok_or_else(|| "Checklist item not found".to_string())?;
    ctx.db.task_checklists().delete(item);
    Ok(())
}

#[reducer]
pub fn reorder_checklist_items(
    ctx: &ReducerContext,
    item_id: String,
    new_position: u32,
) -> Result<(), String> {
    let mut item = find_checklist_item(ctx, &item_id)
        .ok_or_else(|| "Checklist item not found".to_string())?;
    item.position = new_position;
    let old: Vec<TaskChecklistItem> = ctx.db.task_checklists().iter()
        .filter(|i| i.id == item.id)
        .map(|i| i.clone())
        .collect();
    for i in old { ctx.db.task_checklists().delete(i); }
    ctx.db.task_checklists().insert(item);
    Ok(())
}

// ── Custom Task Order / Position ──────────────────────────────────────────

#[reducer]
pub fn reorder_task(
    ctx: &ReducerContext,
    task_id: String,
    new_position: u32,
) -> Result<(), String> {
    let mut task = find_task(ctx, &task_id)
        .ok_or_else(|| "Task not found".to_string())?;
    task.position = Some(new_position);
    task.updated_at = now_ms(ctx);
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "reordered", task.assigned_to.as_deref(), Some(&format!("position={}", new_position)));
    Ok(())
}

#[reducer]
pub fn bulk_reorder_tasks(
    ctx: &ReducerContext,
    items_json: String,
) -> Result<(), String> {
    // items_json is a JSON array of {task_id: String, position: u32}
    // Example: [{"task_id":"abc","position":0},{"task_id":"def","position":1}]
    let items: Vec<serde_json::Value> = serde_json::from_str(&items_json)
        .map_err(|e| format!("Invalid JSON: {}", e))?;
    let now = now_ms(ctx);
    for item in &items {
        let task_id = item["task_id"].as_str()
            .ok_or("Missing task_id field")?;
        let position = item["position"].as_u64()
            .ok_or("Missing or invalid position field")?;
        if let Some(mut task) = find_task(ctx, task_id) {
            task.position = Some(position as u32);
            task.updated_at = now;
            update_task_in_db(ctx, &task);
        }
    }
    log_action(ctx, "bulk_reorder", "bulk_reordered", None, Some(&format!("{} tasks", items.len())));
    Ok(())
}
