"""
Pydantic models for spacetimedb-kanban.

Extracted from shared.py for cleaner separation of concerns.
"""

from typing import Any

from pydantic import BaseModel

# ── Pydantic models ──────────────────────────────────────────────────


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    priority: int
    status: str
    assigned_to: str | None = None
    repo: str
    branch: str | None = None
    roadmap_item: str
    created_by: str
    created_at: int
    updated_at: int
    depends_on: str | None = None
    required_skills: str | None = None
    score: int = 0
    position: int | None = None
    fail_count: int = 0
    max_attempts: int = 3
    fail_reason: str | None = None
    subtask_of: str | None = None
    subtasks: str | None = None
    due_by: int | None = None
    sprint: str | None = None
    archived: bool = False
    estimated_hours: int | None = None
    spent_hours: int | None = None


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str = ""
    created_by: str = "web-user"
    status: str = ""
    fail_count: int = 0
    max_attempts: int = 3
    fail_reason: str | None = None
    subtask_of: str | None = None
    subtasks: str | None = None
    due_by: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    branch: str | None = None
    required_skills: str | None = None
    due_by: int | None = None
    sprint: str | None = None
    archived: bool | None = None
    estimated_hours: int | None = None
    spent_hours: int | None = None


class ClaimRequest(BaseModel):
    agent_id: str


class PermanentBlockRequest(BaseModel):
    reason: str = ""


class BlockRequest(BaseModel):
    reason: str = ""


class BlockWithReasonRequest(BaseModel):
    reason: str = ""


class SplitTaskRequest(BaseModel):
    child_titles: list[str]


class MaxAttemptsRequest(BaseModel):
    max_attempts: int = 3


class SetDependencyRequest(BaseModel):
    depends_on: str = ""  # empty string to clear


class SetSkillsRequest(BaseModel):
    skills: str = ""


class AgentRegisterRequest(BaseModel):
    agent_id: str
    host: str = ""
    capabilities: str = ""
    repo_focus: str = ""


class AgentHeartbeatRequest(BaseModel):
    agent_id: str
    status: str = "online"
    current_task_id: str = ""


class AgentCapabilitiesRequest(BaseModel):
    capabilities: str = ""
    repo_focus: str = ""


class CompleteRequest(BaseModel):
    result_notes: str = ""


class RoadmapImportRequest(BaseModel):
    content: str  # Raw ROADMAP.md content
    repo: str = ""  # Default repo slug for imported tasks
    created_by: str = "roadmap-import"


class LogOut(BaseModel):
    id: str
    task_id: str
    action: str
    agent_id: str | None = None
    notes: str | None = None
    timestamp: int


class AgentOut(BaseModel):
    id: str
    host: str = ""
    capabilities: str | None = None
    repo_focus: str | None = None
    current_task_id: str | None = None
    status: str = "offline"
    last_heartbeat: int = 0
    first_seen: int = 0


class SuggestResult(BaseModel):
    task: TaskOut
    score: int
    reason: str = ""


class LabelOut(BaseModel):
    id: str
    name: str
    color: str
    description: str = ""
    created_at: int = 0


class LabelCreate(BaseModel):
    id: str = ""
    name: str
    color: str = "#0ea5e9"
    description: str = ""


class LabelUpdate(BaseModel):
    name: str = ""
    color: str = ""
    description: str = ""


# ── Project Models ────────────────────────────────────────────────────


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str = ""
    color: str = "#6b7280"
    priority: int = 2
    active: bool = True
    created_at: int = 0
    updated_at: int = 0


class ProjectCreate(BaseModel):
    id: str  # repo slug
    name: str = ""
    description: str = ""
    color: str = "#0ea5e9"
    priority: int = 2
    active: bool = True


class ProjectUpdate(BaseModel):
    name: str = ""
    description: str = ""
    color: str = ""
    priority: int | None = None  # None = don't change
    active: bool = True


class TaskLabelAssign(BaseModel):
    label_ids: list[str] = []


class CommentOut(BaseModel):
    id: str
    task_id: str
    author: str
    body: str
    created_at: int


class CommentCreate(BaseModel):
    body: str
    author: str = "web-user"


class ChecklistItemOut(BaseModel):
    id: str
    task_id: str
    text: str
    completed: bool = False
    position: int = 0
    created_at: int = 0


class ChecklistItemCreate(BaseModel):
    text: str


# ── Task Template Models ───────────────────────────────────────────────


class TemplateOut(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str | None = None
    cron_schedule: str
    created_by: str = ""
    created_at: int = 0
    last_triggered_at: int = 0
    active: bool = True


class TemplateCreate(BaseModel):
    id: str = ""
    title: str
    description: str = ""
    priority: int = 2
    repo: str = ""
    roadmap_item: str = ""
    required_skills: str = ""
    cron_schedule: str
    created_by: str = "web-user"


class TemplateUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: int | None = None
    repo: str | None = None
    roadmap_item: str | None = None
    required_skills: str | None = None
    cron_schedule: str | None = None
    active: bool | None = None


class ReorderRequest(BaseModel):
    task_id: str
    position: int


class BulkReorderRequest(BaseModel):
    items: list[ReorderRequest]


class BulkRetryRequest(BaseModel):
    task_ids: list[str]
    reset_fails: bool = True


class BulkArchiveRequest(BaseModel):
    task_ids: list[str]


class BulkActionRequest(BaseModel):
    """Bulk action on tasks: claim, complete, block, unclaim, delete."""

    action: str
    task_ids: list[str]
    agent_id: str = "web-user"
    reason: str = ""
    result_notes: str = ""


class WebhookCreateRequest(BaseModel):
    url: str
    type: str = "generic"
    events: list[str] = ["created", "claimed", "unclaimed", "completed", "blocked"]
    label: str = ""


class WebhookUpdateRequest(BaseModel):
    url: str | None = None
    type: str | None = None
    events: list[str] | None = None
    label: str | None = None


class IssueLinkRequest(BaseModel):
    task_id: str
    repo: str
    issue_number: int
    issue_url: str = ""
    html_url: str = ""


class IssueCreateRequest(BaseModel):
    task_id: str
    repo: str = ""
    labels: str = ""
    assignee: str = ""


class BatchLabelsRequest(BaseModel):
    task_ids: list[str]
    label_ids: list[str]


class AddLogRequest(BaseModel):
    task_id: str = ""  # Can also come from URL path
    action: str
    agent_id: str = ""
    notes: str = ""


class DispatcherStateUpdate(BaseModel):
    key: str
    value: Any


# ── Task Sprint ─────────────────────────────────────────────────────


class SprintRequest(BaseModel):
    sprint: str  # sprint name


# ── Time Estimates ──────────────────────────────────────────────────


class TimeEstimatesRequest(BaseModel):
    estimated_hours: int = 0
    spent_hours: int = 0


# ── Task Relations ──────────────────────────────────────────────────


class TaskRelationCreate(BaseModel):
    related_task_id: str
    relation_type: str  # "blocks", "blocked_by", "relates_to", "duplicates", "is_duplicated_by"


class TaskRelationOut(BaseModel):
    id: str
    task_id: str
    related_task_id: str
    relation_type: str
    created_at: int


# ── Automation Rules ────────────────────────────────────────────────


class AutomationRuleOut(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger_event: str
    condition: str | None = None
    action_type: str
    action_config: str
    repo: str | None = None
    active: bool = True
    created_at: int = 0
    updated_at: int = 0


class AutomationRuleCreate(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    trigger_event: str
    condition: str = ""
    action_type: str
    action_config: str
    repo: str = ""
    active: bool = True


class AutomationRuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_event: str | None = None
    condition: str | None = None
    action_type: str | None = None
    action_config: str | None = None
    repo: str | None = None
    active: bool | None = None


# ── API Keys ────────────────────────────────────────────────────────


class ApiKeyOut(BaseModel):
    id: str
    key_hash: str
    name: str
    repo_scope: str | None = None
    permissions: str
    created_by: str
    created_at: int = 0
    last_used_at: int = 0
    active: bool = True


class ApiKeyCreate(BaseModel):
    id: str = ""
    key_hash: str
    name: str
    repo_scope: str = ""
    permissions: str = "read"
    created_by: str = "web-user"


# ── Schema Migrations ───────────────────────────────────────────────


class MigrationOut(BaseModel):
    version: str
    description: str = ""
    applied_at: int = 0
    applied_by: str = ""
    checksum: str | None = None


class MigrationCreate(BaseModel):
    version: str
    description: str = ""
    applied_by: str = "web-user"
    checksum: str = ""
