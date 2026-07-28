use spacetimedb::{reducer, ReducerContext, Table};

use crate::queries::*;
use crate::tables::*;
use super::{
    now_ms, make_id, log_action, update_agent_in_db,
};

// ── Seed Data ───────────────────────────────────────────────────────

#[reducer]
pub fn seed_sample_tasks(ctx: &ReducerContext) -> Result<(), String> {
    let now = now_ms(ctx);
    let _sender = ctx.sender().to_string();

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
                        status: TaskStatus::Available,
                        assigned_to: None,
                        repo: repo.to_string(),
                        branch: None,
                        roadmap_item: roadmap.to_string(),
                        created_by: "seed".to_string(),
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
                        due_by: None,
                        sprint: None,
                        archived: false,
                        estimated_hours: None,
                        spent_hours: None,
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

// ── Agent Registry (Swarm Mode) ─────────────────────────────────────

#[reducer]
pub fn register_agent(
    ctx: &ReducerContext,
    agent_id: String,
    host: String,
    capabilities: String,
    repo_focus: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let cap_opt = if capabilities.is_empty() {
        None
    } else {
        Some(capabilities)
    };
    let repo_opt = if repo_focus.is_empty() {
        None
    } else {
        Some(repo_focus)
    };

    if let Some(mut existing) = find_agent(ctx, &agent_id) {
        // Update heartbeat and capabilities
        existing.host = host;
        existing.capabilities = cap_opt;
        existing.repo_focus = repo_opt;
        existing.status = SwarmAgentStatus::Online;
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
            status: SwarmAgentStatus::Online,
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

    let task_opt = if current_task_id.is_empty() {
        None
    } else {
        Some(current_task_id)
    };
    let agent_status = match status.as_str() {
        "online" => SwarmAgentStatus::Online,
        "busy" => SwarmAgentStatus::Busy,
        "offline" => SwarmAgentStatus::Offline,
        _ => SwarmAgentStatus::Online,
    };
    let new_status = if agent_status == SwarmAgentStatus::Busy || task_opt.is_some() {
        SwarmAgentStatus::Busy
    } else {
        SwarmAgentStatus::Online
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
    agent.capabilities = if capabilities.is_empty() {
        None
    } else {
        Some(capabilities)
    };
    agent.repo_focus = if repo_focus.is_empty() {
        None
    } else {
        Some(repo_focus)
    };
    agent.last_heartbeat = now;
    update_agent_in_db(ctx, &agent);
    Ok(())
}

// ── Webhook Subscriptions ───────────────────────────────────────────

#[reducer]
pub fn add_webhook_subscription(
    ctx: &ReducerContext,
    id: String,
    url: String,
    wh_type: String,
    events: String,
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
pub fn remove_webhook_subscription(
    ctx: &ReducerContext,
    wh_id: String,
) -> Result<(), String> {
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
    if !url.is_empty() {
        wh.url = url;
    }
    if !wh_type.is_empty() {
        wh.wh_type = wh_type;
    }
    if !events.is_empty() {
        wh.events = events;
    }
    if !label.is_empty() {
        wh.label = label;
    }
    if let Some(old) = ctx.db.webhook_subscriptions().id().find(&wh.id) {
        ctx.db.webhook_subscriptions().delete(old);
    }
    ctx.db.webhook_subscriptions().insert(wh);
    Ok(())
}

// ── Webhook Delivery Log ────────────────────────────────────────────

#[reducer]
#[allow(clippy::too_many_arguments)]
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
    // Before inserting, clean up delivery logs older than 7 days
    let cutoff = now.saturating_sub(7 * 24 * 60 * 60 * 1000);
    let old: Vec<_> = ctx.db.webhook_deliveries().iter()
        .filter(|d| d.delivered_at < cutoff)
        .collect();
    for d in old {
        ctx.db.webhook_deliveries().delete(d);
    }
    let delivery_id = if id.is_empty() {
        make_id("whdel", ctx)
    } else {
        id
    };
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

// ── Issue Links (GitHub sync) ───────────────────────────────────────

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
        status: IssueLinkStatus::Open,
        linked_at: now,
    });
    Ok(())
}

#[reducer]
pub fn unlink_issue(
    ctx: &ReducerContext,
    kanban_task_id: String,
) -> Result<(), String> {
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
    let new_status = match status.as_str() {
        "open" => IssueLinkStatus::Open,
        "closed" => IssueLinkStatus::Closed,
        _ => IssueLinkStatus::Open,
    };
    link.status = new_status;
    if let Some(old) = ctx.db.issue_links().kanban_task_id().find(&link.kanban_task_id) {
        ctx.db.issue_links().delete(old);
    }
    ctx.db.issue_links().insert(link);
    Ok(())
}

// ── Labels / Tags ───────────────────────────────────────────────────

#[reducer]
pub fn add_label(
    ctx: &ReducerContext,
    id: String,
    name: String,
    color: String,
    description: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let label_id = if id.is_empty() {
        make_id("label", ctx)
    } else {
        id
    };
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
    let assignments: Vec<TaskLabelAssignment> = ctx
        .db
        .task_label_assignments()
        .iter()
        .filter(|a| a.label_id == label_id)
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
    if !name.is_empty() {
        label.name = name;
    }
    if !color.is_empty() {
        label.color = color;
    }
    label.description = description;
    if let Some(old) = ctx.db.kanban_labels().id().find(&label.id) {
        ctx.db.kanban_labels().delete(old);
    }
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
    let _task =
        find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    let _label = find_label(ctx, &label_id)
        .ok_or_else(|| "Label not found".to_string())?;
    // Check not already assigned
    let exists = ctx
        .db
        .task_label_assignments()
        .iter()
        .any(|a| a.task_id == task_id && a.label_id == label_id);
    if !exists {
        ctx.db
            .task_label_assignments()
            .insert(TaskLabelAssignment {
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
    let assignment: Vec<TaskLabelAssignment> = ctx
        .db
        .task_label_assignments()
        .iter()
        .filter(|a| a.task_id == task_id && a.label_id == label_id)
        .collect();
    if assignment.is_empty() {
        return Err("Label assignment not found".to_string());
    }
    for a in assignment {
        ctx.db.task_label_assignments().delete(a);
    }
    Ok(())
}

#[reducer]
pub fn batch_assign_labels(
    ctx: &ReducerContext,
    task_ids: String,
    label_ids: String,
) -> Result<(), String> {
    let tasks: Vec<&str> = task_ids
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    let labels: Vec<&str> = label_ids
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
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
            let exists = ctx
                .db
                .task_label_assignments()
                .iter()
                .any(|a| a.task_id == *task_id && a.label_id == *label_id);
            if !exists {
                ctx.db
                    .task_label_assignments()
                    .insert(TaskLabelAssignment {
                        id: assignment_id(task_id, label_id),
                        task_id: task_id.to_string(),
                        label_id: label_id.to_string(),
                    });
                count += 1;
            }
        }
    }
    log_action(
        ctx,
        &format!("batch_label_assign_{}", count),
        "batch_assign_labels",
        None,
        Some(&format!(
            "{} tasks, {} labels: {} assignments",
            tasks.len(),
            labels.len(),
            count
        )),
    );
    Ok(())
}

#[reducer]
pub fn batch_unassign_labels(
    ctx: &ReducerContext,
    task_ids: String,
    label_ids: String,
) -> Result<(), String> {
    let tasks: Vec<&str> = task_ids
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    let labels: Vec<&str> = label_ids
        .split(',')
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
        .collect();
    if tasks.is_empty() || labels.is_empty() {
        return Err("task_ids and label_ids must be non-empty".to_string());
    }
    let mut count = 0u64;
    for task_id in &tasks {
        for label_id in &labels {
            let to_remove: Vec<TaskLabelAssignment> = ctx
                .db
                .task_label_assignments()
                .iter()
                .filter(|a| a.task_id == *task_id && a.label_id == *label_id)
                .collect();
            for a in to_remove {
                ctx.db.task_label_assignments().delete(a);
                count += 1;
            }
        }
    }
    log_action(
        ctx,
        &format!("batch_label_unassign_{}", count),
        "batch_unassign_labels",
        None,
        Some(&format!(
            "{} tasks, {} labels: {} removed",
            tasks.len(),
            labels.len(),
            count
        )),
    );
    Ok(())
}

// ── Dispatcher State ────────────────────────────────────────────────

#[reducer]
pub fn set_dispatcher_state(
    ctx: &ReducerContext,
    key: String,
    value: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    // Delete existing row for this key
    if let Some(old) = ctx.db.dispatcher_state().key().find(&key) {
        ctx.db.dispatcher_state().delete(old);
    }
    ctx.db.dispatcher_state().insert(DispatcherStateRow {
        key,
        value,
        updated_at: now,
    });
    Ok(())
}

#[reducer]
pub fn delete_dispatcher_state_row(
    ctx: &ReducerContext,
    key: String,
) -> Result<(), String> {
    let old = ctx.db.dispatcher_state().key().find(&key)
        .ok_or_else(|| "Key not found".to_string())?;
    ctx.db.dispatcher_state().delete(old);
    Ok(())
}
