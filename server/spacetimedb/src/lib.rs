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
    let ts = now_ms(ctx);
    let discrim = ctx.sender().to_string();
    let short = if discrim.len() > 8 { &discrim[..8] } else { &discrim };
    format!("{}_{}_{}", prefix, ts, short)
}

fn log_action(
    ctx: &ReducerContext,
    task_id: &str,
    action: &str,
    agent_id: Option<&str>,
    notes: Option<&str>,
) {
    let id = make_id("log", ctx);
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
    title: String,
    description: String,
    priority: u8,
    repo: String,
    roadmap_item: String,
    created_by: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let id = make_id("task", ctx);

    ctx.db.tasks().insert(Task {
        id: id.clone(),
        title,
        description,
        priority,
        status: "available".to_string(),
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
    });

    log_action(ctx, &id, "created", None, None);
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
