use spacetimedb::{reducer, ReducerContext, Table};

use crate::queries::*;
use crate::tables::*;
use super::{now_ms, make_id, log_action, update_template_in_db};

// ── Task Templates (Recurring / Cron-Based) ─────────────────────────

#[reducer]
#[allow(clippy::too_many_arguments)]
pub fn add_task_template(
    ctx: &ReducerContext,
    id: String,
    title: String,
    description: String,
    priority: u8,
    repo: String,
    roadmap_item: String,
    required_skills: String,
    cron_schedule: String,
    created_by: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let template_id = if id.is_empty() {
        make_id("tpl", ctx)
    } else {
        id
    };
    let skills_opt = if required_skills.is_empty() {
        None
    } else {
        Some(required_skills)
    };

    ctx.db.task_templates().insert(TaskTemplate {
        id: template_id,
        title,
        description,
        priority,
        repo,
        roadmap_item,
        required_skills: skills_opt,
        cron_schedule,
        created_by,
        created_at: now,
        last_triggered_at: 0,
        active: true,
    });
    Ok(())
}

#[reducer]
pub fn remove_task_template(ctx: &ReducerContext, id: String) -> Result<(), String> {
    let template = find_template(ctx, &id)
        .ok_or_else(|| "Template not found".to_string())?;
    ctx.db.task_templates().delete(template);
    Ok(())
}

#[reducer]
#[allow(clippy::too_many_arguments)]
pub fn update_task_template(
    ctx: &ReducerContext,
    id: String,
    title: String,
    description: String,
    priority: u8,
    repo: String,
    roadmap_item: String,
    required_skills: String,
    cron_schedule: String,
    active: bool,
) -> Result<(), String> {
    let mut template = find_template(ctx, &id)
        .ok_or_else(|| "Template not found".to_string())?;

    if !title.is_empty() {
        template.title = title;
    }
    if !description.is_empty() {
        template.description = description;
    }
    template.priority = priority;
    if !repo.is_empty() {
        template.repo = repo;
    }
    if !roadmap_item.is_empty() {
        template.roadmap_item = roadmap_item;
    }
    template.required_skills = if required_skills.is_empty() {
        None
    } else {
        Some(required_skills)
    };
    if !cron_schedule.is_empty() {
        template.cron_schedule = cron_schedule;
    }
    template.active = active;

    update_template_in_db(ctx, &template);
    Ok(())
}

#[reducer]
pub fn trigger_task_templates(ctx: &ReducerContext) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut created_count = 0u32;
    let mut due_count = 0u32;

    let templates: Vec<TaskTemplate> = ctx
        .db
        .task_templates()
        .iter()
        .filter(|t| t.active)
        .collect();

    for template in templates {
        if !is_template_due(&template.cron_schedule, template.last_triggered_at, now) {
            continue;
        }

        due_count += 1;

        // Create a task from this template
        let task_id = make_id("task", ctx);
        let _sender = ctx.sender().to_string();

        ctx.db.tasks().insert(Task {
            id: task_id.clone(),
            title: template.title.clone(),
            description: template.description.clone(),
            priority: template.priority,
            status: TaskStatus::Available,
            assigned_to: None,
            repo: template.repo.clone(),
            branch: None,
            roadmap_item: template.roadmap_item.clone(),
            created_by: format!("template:{}", template.id),
            created_at: now,
            updated_at: now,
            depends_on: None,
            required_skills: template.required_skills.clone(),
            score: 0,
            position: Some((now / 1000) as u32),
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

        log_action(
            ctx,
            &task_id,
            "created_from_template",
            None,
            Some(&format!("template: {}", template.id)),
        );

        // Update template's last_triggered_at
        let mut updated = template.clone();
        updated.last_triggered_at = now;
        update_template_in_db(ctx, &updated);

        created_count += 1;
    }

    log_action(
        ctx,
        &format!("task_template_trigger_{}", now),
        "trigger_task_templates",
        None,
        Some(&format!("{} due, {} tasks created", due_count, created_count)),
    );
    Ok(())
}

// ── Automation Rules (#24) ────────────────────────────────────────

#[reducer]
#[allow(clippy::too_many_arguments)]
pub fn create_automation_rule(
    ctx: &ReducerContext,
    id: String,
    name: String,
    description: String,
    trigger_event: String,
    condition: String,
    action_type: String,
    action_config: String,
    repo: String,
    active: bool,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let rule_id = if id.is_empty() { make_id("rule", ctx) } else { id };
    ctx.db.automation_rules().insert(AutomationRule {
        id: rule_id,
        name,
        description,
        trigger_event,
        condition: if condition.is_empty() { None } else { Some(condition) },
        action_type,
        action_config,
        repo: if repo.is_empty() { None } else { Some(repo) },
        active,
        created_at: now,
        updated_at: now,
    });
    Ok(())
}

#[reducer]
#[allow(clippy::too_many_arguments)]
pub fn update_automation_rule(
    ctx: &ReducerContext,
    rule_id: String,
    name: String,
    description: String,
    trigger_event: String,
    condition: String,
    action_type: String,
    action_config: String,
    repo: String,
    active: bool,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut rule = find_automation_rule(ctx, &rule_id).ok_or_else(|| "Rule not found".to_string())?;
    if !name.is_empty() { rule.name = name; }
    if !description.is_empty() { rule.description = description; }
    if !trigger_event.is_empty() { rule.trigger_event = trigger_event; }
    rule.condition = if condition.is_empty() { None } else { Some(condition) };
    if !action_type.is_empty() { rule.action_type = action_type; }
    if !action_config.is_empty() { rule.action_config = action_config; }
    rule.repo = if repo.is_empty() { None } else { Some(repo) };
    rule.active = active;
    rule.updated_at = now;
    if let Some(old) = ctx.db.automation_rules().id().find(&rule_id) {
        ctx.db.automation_rules().delete(old);
    }
    ctx.db.automation_rules().insert(rule);
    Ok(())
}

#[reducer]
pub fn delete_automation_rule(ctx: &ReducerContext, rule_id: String) -> Result<(), String> {
    if let Some(old) = ctx.db.automation_rules().id().find(&rule_id) {
        ctx.db.automation_rules().delete(old);
    }
    Ok(())
}

// ── API Key Management (#23) ──────────────────────────────────────

#[reducer]
pub fn create_api_key(
    ctx: &ReducerContext,
    id: String,
    key_hash: String,
    name: String,
    repo_scope: String,
    permissions: String,
    created_by: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let key_id = if id.is_empty() { make_id("apikey", ctx) } else { id };
    ctx.db.api_keys().insert(ApiKey {
        id: key_id,
        key_hash,
        name,
        repo_scope: if repo_scope.is_empty() { None } else { Some(repo_scope) },
        permissions,
        created_by,
        created_at: now,
        last_used_at: now,
        active: true,
    });
    Ok(())
}

#[reducer]
pub fn revoke_api_key(ctx: &ReducerContext, key_id: String) -> Result<(), String> {
    let mut key = find_api_key(ctx, &key_id).ok_or_else(|| "API key not found".to_string())?;
    key.active = false;
    if let Some(old) = ctx.db.api_keys().id().find(&key_id) {
        ctx.db.api_keys().delete(old);
    }
    ctx.db.api_keys().insert(key);
    Ok(())
}

// ── Schema Migration Logging (#16) ─────────────────────────────────

#[reducer]
pub fn record_migration(
    ctx: &ReducerContext,
    version: String,
    description: String,
    applied_by: String,
    checksum: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let sender = ctx.sender().to_string();
    // Check already applied
    if ctx.db.schema_migrations().version().find(&version).is_some() {
        return Err(format!("Migration '{}' already applied", version));
    }
    ctx.db.schema_migrations().insert(SchemaMigration {
        version,
        description,
        applied_at: now,
        applied_by: if applied_by.is_empty() { sender } else { applied_by },
        checksum: if checksum.is_empty() { None } else { Some(checksum) },
    });
    Ok(())
}
