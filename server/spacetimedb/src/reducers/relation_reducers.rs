use spacetimedb::{reducer, ReducerContext, Table};
use super::{now_ms, make_id};

use crate::queries::*;
use crate::tables::*;

// ── Related Task Links (#21) ──────────────────────────────────────

#[reducer]
pub fn add_task_relation(ctx: &ReducerContext, task_id: String, related_task_id: String, relation_type: String) -> Result<(), String> {
    // Verify both tasks exist
    find_task(ctx, &task_id).ok_or_else(|| "Task not found".to_string())?;
    find_task(ctx, &related_task_id).ok_or_else(|| "Related task not found".to_string())?;

    // Validate relation type
    let valid_types = ["blocks", "blocked_by", "relates_to", "duplicates", "is_duplicated_by"];
    if !valid_types.contains(&relation_type.as_str()) {
        return Err(format!("Invalid relation type: {}. Valid: {}", relation_type, valid_types.join(", ")));
    }

    // Check not self-referencing
    if task_id == related_task_id {
        return Err("Cannot relate a task to itself".to_string());
    }

    // Check not duplicate
    let exists = ctx.db.task_relations().iter()
        .any(|r| r.task_id == task_id && r.related_task_id == related_task_id);
    if exists {
        return Err("Relation already exists".to_string());
    }

    let now = now_ms(ctx);
    let rel_id = make_id("rel", ctx);
    ctx.db.task_relations().insert(TaskRelation {
        id: rel_id,
        task_id,
        related_task_id,
        relation_type,
        created_at: now,
    });
    Ok(())
}

#[reducer]
pub fn remove_task_relation(ctx: &ReducerContext, relation_id: String) -> Result<(), String> {
    let old: Vec<TaskRelation> = ctx.db.task_relations().iter()
        .filter(|r| r.id == relation_id)
        .map(|r| r.clone())
        .collect();
    for r in old {
        ctx.db.task_relations().delete(r);
    }
    Ok(())
}
