use spacetimedb::{reducer, ReducerContext, Table};

use crate::queries::*;
use crate::tables::*;
use super::{now_ms, make_id, log_action, update_task_in_db, delete_logs_for_task};

// ── Task Reducers ───────────────────────────────────────────────────

#[reducer]
#[allow(clippy::too_many_arguments)]
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
    due_by: u64,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let task_id = if id.is_empty() {
        make_id("task", ctx)
    } else {
        id
    };

    let status = if initial_status.is_empty() {
        TaskStatus::Available
    } else {
        // Parse from string — fallback to Available
        match initial_status.as_str() {
            "in_progress" => TaskStatus::InProgress,
            "blocked" => TaskStatus::Blocked,
            "done" => TaskStatus::Done,
            _ => TaskStatus::Available,
        }
    };
    let due = if due_by > 0 { Some(due_by) } else { None };

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
        position: Some((now / 1000) as u32),
        fail_count: 0,
        max_attempts: 3,
        fail_reason: None,
        subtask_of: None,
        subtasks: None,
        due_by: due,
        sprint: None,
        archived: false,
        estimated_hours: None,
        spent_hours: None,
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
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    if task.status != TaskStatus::InProgress {
        return Err(format!("Cannot block task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();

    // Increment fail_count and record reason
    task.fail_count += 1;
    task.fail_reason = if reason.is_empty() {
        None
    } else {
        Some(reason.clone())
    };

    // If max_attempts reached, special handling — dispatcher will decide
    if task.fail_count >= task.max_attempts {
        task.status = TaskStatus::Blocked;
        task.assigned_to = None;
    } else {
        // Under limit: return to available for retry
        task.status = TaskStatus::Available;
        task.assigned_to = None;
    }

    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(
        ctx,
        &task_id,
        "blocked",
        agent.as_deref(),
        Some(&format!(
            "fail #{}/{}: {}",
            task.fail_count, task.max_attempts, reason
        )),
    );
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

    if parent.status != TaskStatus::Available && parent.status != TaskStatus::Blocked {
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
            status: TaskStatus::Available,
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
            position: Some((now / 1000) as u32),
            fail_count: 0,
            max_attempts: parent.max_attempts,
            fail_reason: None,
            subtask_of: Some(parent_task_id.clone()),
            subtasks: None,
            due_by: None,
            sprint: None,
            archived: false,
            estimated_hours: None,
            spent_hours: None,
        });
        log_action(
            ctx,
            &child_id,
            "created_as_subtask",
            None,
            Some(&format!("parent: {}", parent_task_id)),
        );
    }

    // Update parent with subtask list and mark as blocked (tracked by children)
    parent.status = TaskStatus::Blocked;
    parent.assigned_to = None;
    parent.updated_at = now;
    parent.fail_reason = Some(format!(
        "Split into {} subtask(s): {}",
        child_titles.len(),
        child_titles.join(", ")
    ));
    update_task_in_db(ctx, &parent);

    log_action(
        ctx,
        &parent_task_id,
        "split",
        None,
        Some(&format!("{} child tasks created", child_titles.len())),
    );
    Ok(())
}

#[reducer]
pub fn reset_fail_count(
    ctx: &ReducerContext,
    task_id: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
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
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.max_attempts = max_attempts;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    Ok(())
}

#[reducer]
pub fn claim_task(ctx: &ReducerContext, task_id: String, agent_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    if task.status != TaskStatus::Available {
        return Err(format!(
            "Task is not available (current status: {})",
            task.status
        ));
    }

    // Check dependency: if task depends on another task, that dependency must be done
    if let Some(ref dep_id) = task.depends_on {
        let dep = find_task(ctx, dep_id)
            .ok_or_else(|| format!("Dependency task '{}' not found", dep_id))?;
        if dep.status != TaskStatus::Done {
            return Err(format!(
                "Cannot claim — dependency '{}' ({}) is not done (status: {})",
                dep_id, dep.title, dep.status
            ));
        }
    }

    task.status = TaskStatus::InProgress;
    task.assigned_to = Some(agent_id.clone());
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "claimed", Some(&agent_id), None);
    Ok(())
}

#[reducer]
pub fn unclaim_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    if task.status != TaskStatus::InProgress && task.status != TaskStatus::Blocked {
        return Err(format!("Cannot unclaim task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = TaskStatus::Available;
    task.assigned_to = None;
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(ctx, &task_id, "unclaimed", agent.as_deref(), None);
    Ok(())
}

#[reducer]
pub fn complete_task(
    ctx: &ReducerContext,
    task_id: String,
    result_notes: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    if task.status != TaskStatus::InProgress {
        return Err(format!("Cannot complete task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = TaskStatus::Done;
    task.updated_at = now;
    update_task_in_db(ctx, &task);

    log_action(
        ctx,
        &task_id,
        "completed",
        agent.as_deref(),
        Some(&result_notes),
    );
    Ok(())
}

#[reducer]
pub fn block_task(ctx: &ReducerContext, task_id: String, reason: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    if task.status != TaskStatus::InProgress {
        return Err(format!("Cannot block task with status: {}", task.status));
    }

    let agent = task.assigned_to.clone();
    task.status = TaskStatus::Blocked;
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
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

    let branch_opt = if branch.is_empty() {
        None
    } else {
        Some(branch)
    };

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
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;

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

    log_action(
        ctx,
        &task_id,
        "dependency_set",
        task.assigned_to.as_deref(),
        Some(&depends_on),
    );
    Ok(())
}

#[reducer]
pub fn delete_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    ctx.db.tasks().delete(task);
    delete_logs_for_task(ctx, &task_id);
    // Clean up label assignments (uses btree index on task_id)
    let assignments: Vec<TaskLabelAssignment> = ctx
        .db
        .task_label_assignments()
        .task_id()
        .filter(task_id.as_str())
        .collect();
    for a in assignments {
        ctx.db.task_label_assignments().delete(a);
    }
    // Clean up checklist items (uses btree index on task_id)
    let checklist_items: Vec<TaskChecklistItem> = ctx
        .db
        .task_checklists()
        .task_id()
        .filter(task_id.as_str())
        .collect();
    for i in checklist_items {
        ctx.db.task_checklists().delete(i);
    }
    Ok(())
}

// ── Task Skills (Capability Tags) ───────────────────────────────────

#[reducer]
pub fn set_task_skills(
    ctx: &ReducerContext,
    task_id: String,
    skills: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.required_skills = if skills.is_empty() {
        None
    } else {
        Some(skills.clone())
    };
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(
        ctx,
        &task_id,
        "skills_set",
        task.assigned_to.as_deref(),
        Some(&skills),
    );
    Ok(())
}

// ── Due Date ────────────────────────────────────────────────────────

#[reducer]
pub fn set_due_by(
    ctx: &ReducerContext,
    task_id: String,
    due_by: u64,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.due_by = if due_by > 0 { Some(due_by) } else { None };
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(
        ctx,
        &task_id,
        "due_by_set",
        task.assigned_to.as_deref(),
        Some(
            &if due_by > 0 {
                format!("due_by={}", due_by)
            } else {
                "due_by=cleared".to_string()
            },
        ),
    );
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
    let _task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    let agent_opt = if agent_id.is_empty() {
        None
    } else {
        Some(agent_id.as_str())
    };
    let notes_opt = if notes.is_empty() {
        None
    } else {
        Some(notes.as_str())
    };
    log_action(ctx, &task_id, &action, agent_opt, notes_opt);
    Ok(())
}

// ── Task Comments ───────────────────────────────────────────────────

#[reducer]
pub fn add_comment(
    ctx: &ReducerContext,
    id: String,
    task_id: String,
    author: String,
    body: String,
) -> Result<(), String> {
    let now = now_ms(ctx);
    let comment_id = if id.is_empty() {
        make_id("cmt", ctx)
    } else {
        id
    };
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
    let comment = ctx.db.task_comments().id().find(&comment_id)
        .ok_or_else(|| "Comment not found".to_string())?;
    ctx.db.task_comments().delete(comment);
    Ok(())

}

// ── Task Checklists / Subtasks ──────────────────────────────────────

#[reducer]
pub fn add_checklist_item(
    ctx: &ReducerContext,
    id: String,
    task_id: String,
    text: String,
) -> Result<(), String> {
    // Verify task exists
    let _task =
        find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    let now = now_ms(ctx);
    let item_id = if id.is_empty() {
        make_id("cl", ctx)
    } else {
        id
    };
    // Determine next position (uses btree index on task_id)
    let max_pos = ctx
        .db
        .task_checklists()
        .task_id()
        .filter(task_id.as_str())
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
pub fn toggle_checklist_item(
    ctx: &ReducerContext,
    item_id: String,
) -> Result<(), String> {
    let mut item = find_checklist_item(ctx, &item_id)
        .ok_or_else(|| "Checklist item not found".to_string())?;
    item.completed = !item.completed;
    if let Some(old) = ctx.db.task_checklists().id().find(&item.id) {
        ctx.db.task_checklists().delete(old);
    }
    ctx.db.task_checklists().insert(item);
    Ok(())
}

#[reducer]
pub fn remove_checklist_item(
    ctx: &ReducerContext,
    item_id: String,
) -> Result<(), String> {
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
    if let Some(old) = ctx.db.task_checklists().id().find(&item.id) {
        ctx.db.task_checklists().delete(old);
    }
    ctx.db.task_checklists().insert(item);
    Ok(())
}

// ── Custom Task Order / Position ────────────────────────────────────

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
    log_action(
        ctx,
        &task_id,
        "reordered",
        task.assigned_to.as_deref(),
        Some(&format!("position={}", new_position)),
    );
    Ok(())
}

#[reducer]
pub fn bulk_reorder_tasks(
    ctx: &ReducerContext,
    items_json: String,
) -> Result<(), String> {
    // items_json is a JSON array of {task_id: String, position: u32}
    let items: Vec<serde_json::Value> = serde_json::from_str(&items_json)
        .map_err(|e| format!("Invalid JSON: {}", e))?;
    let now = now_ms(ctx);
    for item in &items {
        let task_id = item["task_id"]
            .as_str()
            .ok_or("Missing task_id field")?;
        let position = item["position"]
            .as_u64()
            .ok_or("Missing or invalid position field")?;
        if let Some(mut task) = find_task(ctx, task_id) {
            task.position = Some(position as u32);
            task.updated_at = now;
            update_task_in_db(ctx, &task);
        }
    }
    log_action(
        ctx,
        "bulk_reorder",
        "bulk_reordered",
        None,
        Some(&format!("{} tasks", items.len())),
    );
    Ok(())
}

// ── Sprint Tracking (#17) ────────────────────────────────────────

#[reducer]
pub fn set_sprint(ctx: &ReducerContext, task_id: String, sprint: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.sprint = if sprint.is_empty() { None } else { Some(sprint.clone()) };
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "sprint_set", task.assigned_to.as_deref(),
        Some(&if sprint.is_empty() { "sprint=cleared".to_string() } else { format!("sprint={}", sprint) }));
    Ok(())
}

// ── Archive / Unarchive (#19) ─────────────────────────────────────

#[reducer]
pub fn toggle_archive(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.archived = !task.archived;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    let action = if task.archived { "archived" } else { "unarchived" };
    log_action(ctx, &task_id, action, task.assigned_to.as_deref(), None);
    Ok(())
}

#[reducer]
pub fn archive_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.archived = true;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "archived", task.assigned_to.as_deref(), None);
    Ok(())
}

#[reducer]
pub fn unarchive_task(ctx: &ReducerContext, task_id: String) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.archived = false;
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "unarchived", task.assigned_to.as_deref(), None);
    Ok(())
}

// ── Time Estimates (#20) ─────────────────────────────────────────

#[reducer]
pub fn set_time_estimates(ctx: &ReducerContext, task_id: String, estimated_hours: u32, spent_hours: u32) -> Result<(), String> {
    let now = now_ms(ctx);
    let mut task = find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    task.estimated_hours = if estimated_hours > 0 { Some(estimated_hours) } else { None };
    task.spent_hours = if spent_hours > 0 { Some(spent_hours) } else { None };
    task.updated_at = now;
    update_task_in_db(ctx, &task);
    log_action(ctx, &task_id, "time_estimates_set", task.assigned_to.as_deref(),
        Some(&format!("est={}h spent={}h", estimated_hours, spent_hours)));
    Ok(())
}
