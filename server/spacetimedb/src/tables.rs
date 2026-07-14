// ── Task ────────────────────────────────────────────────────────────

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
    pub subtasks: Option<String>, // JSON array of child task IDs
    // Deadline / due date — epoch ms, None = no deadline
    pub due_by: Option<u64>,
}

// ── Task Log ────────────────────────────────────────────────────────

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

// ── Swarm Agent Registry ────────────────────────────────────────────

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

// ── Kanban Project ──────────────────────────────────────────────────

#[spacetimedb::table(accessor = kanban_projects, public)]
#[derive(Debug, Clone)]
pub struct KanbanProject {
    #[primary_key]
    pub id: String,           // repo slug — matches Task.repo
    pub name: String,         // display name
    pub description: String,
    pub color: String,        // hex colour e.g. "#0ea5e9"
    pub priority: u8,         // 0=most important … 255=lowest (same scale as Task.priority)
    pub active: bool,
    pub created_at: u64,
    pub updated_at: u64,
}

// ── Webhook Subscription ────────────────────────────────────────────

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

// ── Issue Link (GitHub sync) ────────────────────────────────────────

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

// ── Kanban Label ────────────────────────────────────────────────────

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

// ── Task–Label Assignment (junction table) ──────────────────────────

#[spacetimedb::table(accessor = task_label_assignments, public)]
#[derive(Debug, Clone)]
pub struct TaskLabelAssignment {
    #[primary_key]
    pub id: String,              // composite: "task_id:label_id"
    pub task_id: String,
    pub label_id: String,
}

// ── Dispatcher State (key-value store) ──────────────────────────────

#[spacetimedb::table(accessor = dispatcher_state, public)]
#[derive(Debug, Clone)]
pub struct DispatcherStateRow {
    #[primary_key]
    pub key: String,
    pub value: String,  // JSON-serialized value
    pub updated_at: u64,
}

// ── Webhook Delivery Log ────────────────────────────────────────────

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

// ── Task Comment ────────────────────────────────────────────────────

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

// ── Task Checklist Item ─────────────────────────────────────────────

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

// ── Task Template (Recurring / Cron-Based) ──────────────────────────

#[spacetimedb::table(accessor = task_templates, public)]
#[derive(Debug, Clone)]
pub struct TaskTemplate {
    #[primary_key]
    pub id: String,
    pub title: String,
    pub description: String,
    pub priority: u8,
    pub repo: String,
    pub roadmap_item: String,
    pub required_skills: Option<String>,
    pub cron_schedule: String, // human-readable like "weekly mon 9am"
    pub created_by: String,
    pub created_at: u64,
    pub last_triggered_at: u64,
    pub active: bool,
}
