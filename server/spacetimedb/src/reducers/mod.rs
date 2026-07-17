use std::cell::Cell;

use spacetimedb::{ReducerContext, Table};

use crate::tables::*;

// ── Thread-local Counters ───────────────────────────────────────────

thread_local! {
    pub(crate) static LOG_COUNTER: Cell<u64> = const { Cell::new(0) };
    pub(crate) static ID_COUNTER: Cell<u64> = const { Cell::new(0) };
}

// ── Timestamp Helper ────────────────────────────────────────────────

pub(crate) fn now_ms(ctx: &ReducerContext) -> u64 {
    ctx.timestamp.to_micros_since_unix_epoch() as u64 / 1000
}

// ── ID Generator ────────────────────────────────────────────────────

pub(crate) fn make_id(prefix: &str, ctx: &ReducerContext) -> String {
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

// ── Activity Logger ─────────────────────────────────────────────────

pub(crate) fn log_action(
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

// ── CRUD Helpers ────────────────────────────────────────────────────

pub(crate) fn update_task_in_db(ctx: &ReducerContext, task: &Task) {
    let old: Vec<Task> = ctx
        .db
        .tasks()
        .iter()
        .filter(|t| t.id == task.id)
        .collect();
    for t in old {
        ctx.db.tasks().delete(t);
    }
    ctx.db.tasks().insert(task.clone());
}

pub(crate) fn delete_logs_for_task(ctx: &ReducerContext, task_id: &str) {
    let logs: Vec<TaskLog> = ctx
        .db
        .task_logs()
        .iter()
        .filter(|l| l.task_id == task_id)
        .collect();
    for log in logs {
        ctx.db.task_logs().delete(log);
    }
}

pub(crate) fn update_agent_in_db(ctx: &ReducerContext, agent: &SwarmAgent) {
    let old: Vec<SwarmAgent> = ctx
        .db
        .swarm_agents()
        .iter()
        .filter(|a| a.id == agent.id)
        .collect();
    for a in old {
        ctx.db.swarm_agents().delete(a);
    }
    ctx.db.swarm_agents().insert(agent.clone());
}

pub(crate) fn update_project_in_db(ctx: &ReducerContext, project: &KanbanProject) {
    let old: Vec<KanbanProject> = ctx
        .db
        .kanban_projects()
        .iter()
        .filter(|p| p.id == project.id)
        .collect();
    for p in old {
        ctx.db.kanban_projects().delete(p);
    }
    ctx.db.kanban_projects().insert(project.clone());
}

pub(crate) fn update_template_in_db(ctx: &ReducerContext, template: &TaskTemplate) {
    let old: Vec<TaskTemplate> = ctx
        .db
        .task_templates()
        .iter()
        .filter(|t| t.id == template.id)
        .collect();
    for t in old {
        ctx.db.task_templates().delete(t);
    }
    ctx.db.task_templates().insert(template.clone());
}

// ── Domain Sub-modules ──────────────────────────────────────────────

mod task_reducers;
pub use task_reducers::*;

mod project_reducers;
pub use project_reducers::*;

mod admin_reducers;
pub use admin_reducers::*;

mod automation_reducers;
pub use automation_reducers::*;

mod relation_reducers;
pub use relation_reducers::*;
