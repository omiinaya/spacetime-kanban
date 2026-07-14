use spacetimedb::{reducer, ReducerContext, Table};

use crate::queries::*;
use crate::tables::*;
use super::{now_ms, update_project_in_db};

// ── Project Reducers ────────────────────────────────────────────────

#[reducer]
pub fn add_project(
    ctx: &ReducerContext,
    id: String,
    name: String,
    description: String,
    color: String,
    priority: u8,
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
        priority,
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
    if !name.is_empty() {
        proj.name = name;
    }
    if !description.is_empty() {
        proj.description = description;
    }
    if !color.is_empty() {
        proj.color = color;
    }
    proj.priority = priority;
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
