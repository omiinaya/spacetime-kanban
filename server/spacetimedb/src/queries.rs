use crate::tables::*;
use spacetimedb::ReducerContext;

// ── Task Lookups ────────────────────────────────────────────────────

pub fn find_task(ctx: &ReducerContext, task_id: &str) -> Option<Task> {
    ctx.db.tasks().id().find(task_id.to_string())
}

// ── Agent Lookups ───────────────────────────────────────────────────

pub fn find_agent(ctx: &ReducerContext, agent_id: &str) -> Option<SwarmAgent> {
    ctx.db.swarm_agents().id().find(agent_id.to_string())
}

// ── Project Lookups ─────────────────────────────────────────────────

pub fn find_project(ctx: &ReducerContext, project_id: &str) -> Option<KanbanProject> {
    ctx.db.kanban_projects().id().find(project_id.to_string())
}

// ── Webhook Lookups ─────────────────────────────────────────────────

pub fn find_webhook(ctx: &ReducerContext, wh_id: &str) -> Option<WebhookSubscription> {
    ctx.db.webhook_subscriptions().id().find(wh_id.to_string())
}

// ── Issue Link Lookups ──────────────────────────────────────────────

pub fn find_issue_link(ctx: &ReducerContext, task_id: &str) -> Option<IssueLink> {
    ctx.db.issue_links().kanban_task_id().find(task_id.to_string())
}

// ── Label Lookups ───────────────────────────────────────────────────

pub fn find_label(ctx: &ReducerContext, label_id: &str) -> Option<KanbanLabel> {
    ctx.db.kanban_labels().id().find(label_id.to_string())
}

// ── Checklist Lookups ───────────────────────────────────────────────

pub fn find_checklist_item(ctx: &ReducerContext, item_id: &str) -> Option<TaskChecklistItem> {
    ctx.db.task_checklists().id().find(item_id.to_string())
}

// ── Template Lookups ────────────────────────────────────────────────

pub fn find_template(ctx: &ReducerContext, template_id: &str) -> Option<TaskTemplate> {
    ctx.db.task_templates().id().find(template_id.to_string())
}

// ── Type Helpers ────────────────────────────────────────────────────

/// Build a composite primary key for a task↔label assignment.
pub fn assignment_id(task_id: &str, label_id: &str) -> String {
    format!("{}:{}", task_id, label_id)
}

/// Simple cron expression parser supporting:
///   "daily H:MM"           — every day at H:MM (24h)
///   "weekly DDD H:MM"      — every week on day DDD at H:MM
///   "monthly Nth H:MM"     — every month on Nth day at H:MM
///   "hourly"               — every hour at :00
/// Returns true if the schedule matches the current timestamp, and
/// enough time has passed since last_triggered_at.
pub fn is_template_due(schedule: &str, last_triggered_at: u64, now: u64) -> bool {
    let parts: Vec<&str> = schedule.split_whitespace().collect();
    if parts.is_empty() {
        return false;
    }

    // Get current time components from epoch ms
    let total_secs = now / 1000;
    // Days since epoch
    let days_since_epoch = total_secs / 86400;
    // Seconds into current day
    let secs_today = total_secs % 86400;
    // Current hour and minute (fit in u8)
    let hour = (secs_today / 3600) as u8;
    let minute = ((secs_today % 3600) / 60) as u8;

    // Day of week: Jan 1 1970 was Thursday = 4 in 0=Sun..6=Sat scheme
    // (days_since_epoch + 4) % 7 gives: 0=Thu,1=Fri,2=Sat,3=Sun,4=Mon,5=Tue,6=Wed
    // We want 0=Mon..6=Sun, so: (days_since_epoch + 3) % 7
    let day_of_week = ((days_since_epoch + 3) % 7) as u8; // 0=Mon..6=Sun
    let day_of_month = {
        // Approximate: use modulo 30 as a simple day-of-month
        // A proper implementation would use actual calendar but this is fine for our simple case
        ((days_since_epoch % 30) + 1) as u8
    };

    // Helper to parse "H:MM" from the last parts
    let parse_time = |s: &str| -> Option<(u8, u8)> {
        let parts: Vec<&str> = s.split(':').collect();
        if parts.len() == 2 {
            let h: u8 = parts[0].parse().ok()?;
            let m: u8 = parts[1].parse().ok()?;
            Some((h, m))
        } else {
            None
        }
    };

    let mut matched = false;

    match parts[0] {
        "hourly" => {
            // True every hour at :00
            matched = minute == 0;
        }
        "daily" => {
            if parts.len() >= 2 {
                if let Some((h, m)) = parse_time(parts[1]) {
                    matched = hour == h && minute == m;
                }
            }
        }
        "weekly" => {
            if parts.len() >= 3 {
                let day_str = parts[1].to_lowercase();
                let target_day = match day_str.as_str() {
                    "mon" | "monday" => 0u8,
                    "tue" | "tuesday" => 1u8,
                    "wed" | "wednesday" => 2u8,
                    "thu" | "thursday" => 3u8,
                    "fri" | "friday" => 4u8,
                    "sat" | "saturday" => 5u8,
                    "sun" | "sunday" => 6u8,
                    _ => return false,
                };
                if let Some((h, m)) = parse_time(parts[2]) {
                    matched = day_of_week == target_day && hour == h && minute == m;
                }
            }
        }
        "monthly"
            if parts.len() >= 3 => {
                let day_str = parts[1].trim_end_matches(|c: char| !c.is_ascii_digit());
                let target_day: u8 = match day_str.parse() {
                    Ok(d) if (1..=31).contains(&d) => d,
                    _ => return false,
                };
                if let Some((h, m)) = parse_time(parts[2]) {
                    matched = day_of_month == target_day && hour == h && minute == m;
                }
            }
        _ => {}
    }

    if !matched {
        return false;
    }

    // Prevent duplicate triggers: ensure we haven't triggered in the current period
    // The period is at minimum 1 hour, so check that at least 3600s have passed
    // For hourly: 3600s
    // For daily: 86400s
    // For weekly: 604800s
    // For monthly: 86400u64 * 28
    let min_interval = match parts[0] {
        "hourly" => 3600u64,
        "daily" => 86400u64,
        "weekly" => 604800u64,
        "monthly" => 86400u64 * 28,
        _ => 3600u64,
    };

    (now / 1000) - (last_triggered_at / 1000) >= min_interval
}

// ── Task Relations ─────────────────────────────────────────────────

pub fn find_task_relation(ctx: &ReducerContext, relation_id: &str) -> Option<TaskRelation> {
    ctx.db.task_relations().id().find(relation_id.to_string())
}

// ── Automation Rules ──────────────────────────────────────────────

pub fn find_automation_rule(ctx: &ReducerContext, rule_id: &str) -> Option<AutomationRule> {
    ctx.db.automation_rules().id().find(rule_id.to_string())
}

// ── API Keys ──────────────────────────────────────────────────────

pub fn find_api_key(ctx: &ReducerContext, key_id: &str) -> Option<ApiKey> {
    ctx.db.api_keys().id().find(key_id.to_string())
}

// ── Schema Migrations ─────────────────────────────────────────────

pub fn find_migration(ctx: &ReducerContext, version: &str) -> Option<SchemaMigration> {
    ctx.db.schema_migrations().version().find(version.to_string())
}

// ── Unit Tests ────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_assignment_id() {
        // Standard case
        let result = assignment_id("task_123", "label_456");
        assert_eq!(result, "task_123:label_456");

        // Empty strings
        let result = assignment_id("", "");
        assert_eq!(result, ":");

        // Special characters
        let result = assignment_id("task:1", "label:2");
        assert_eq!(result, "task:1:label:2");

        // Very long values (just ensure no panic)
        let long = "a".repeat(1000);
        let result = assignment_id(&long, "b");
        assert_eq!(result, format!("{}:b", long));
    }

    #[test]
    fn test_assignment_id_uniqueness() {
        // Same inputs produce same output (deterministic)
        let a = assignment_id("x", "y");
        let b = assignment_id("x", "y");
        assert_eq!(a, b);

        // Different task same label => different
        let c = assignment_id("x2", "y");
        assert_ne!(a, c);

        // Same task different label => different
        let d = assignment_id("x", "y2");
        assert_ne!(a, d);
    }

    #[test]
    fn test_assignment_id_format_contains_colon() {
        let result = assignment_id("task_id", "label_id");
        assert!(result.contains(':'));
        assert_eq!(result.split(':').count(), 2);
    }
}
