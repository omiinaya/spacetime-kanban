# STDB Rust Module — Anti-Pattern Audit Report
**Date:** 2026-07-28  
**Scope:** All `.rs` files under `server/spacetimedb/src/`  
**Files audited:** 10 (lib.rs, tables.rs, queries.rs, error.rs, reducers/mod.rs, task_reducers.rs, project_reducers.rs, relation_reducers.rs, admin_reducers.rs, automation_reducers.rs)

---

## 🔴 ANTI-PATTERN 1: Full Table Scans via `.iter().find()` (instead of indexed `.pk_field().find()`)
**Severity: HIGH**

Every single-record lookup function in `queries.rs` uses `.iter().find()`, which performs a full table scan instead of using the primary-key index.

| File | Line(s) | Function | Detail |
|------|---------|----------|--------|
| `queries.rs` | 7 | `find_task` | `ctx.db.tasks().iter().find(\|t\| t.id == task_id)` |
| `queries.rs` | 13 | `find_agent` | `ctx.db.swarm_agents().iter().find(\|a\| a.id == agent_id)` |
| `queries.rs` | 19 | `find_project` | `ctx.db.kanban_projects().iter().find(\|p\| p.id == project_id)` |
| `queries.rs` | 25 | `find_webhook` | `ctx.db.webhook_subscriptions().iter().find(\|w\| w.id == wh_id)` |
| `queries.rs` | 31–34 | `find_issue_link` | `ctx.db.issue_links().iter().find(\|l\| l.kanban_task_id == task_id)` |
| `queries.rs` | 39 | `find_label` | `ctx.db.kanban_labels().iter().find(\|l\| l.id == label_id)` |
| `queries.rs` | 45–47 | `find_checklist_item` | `ctx.db.task_checklists().iter().find(\|i\| i.id == item_id)` |
| `queries.rs` | 53–55 | `find_template` | `ctx.db.task_templates().iter().find(\|t\| t.id == template_id)` |
| `queries.rs` | 180–182 | `find_task_relation` | `ctx.db.task_relations().iter().find(\|r\| r.id == relation_id)` |
| `queries.rs` | 188–190 | `find_automation_rule` | `ctx.db.automation_rules().iter().find(\|r\| r.id == rule_id)` |
| `queries.rs` | 196–198 | `find_api_key` | `ctx.db.api_keys().iter().find(\|k\| k.id == key_id)` |
| `queries.rs` | 204–206 | `find_migration` | `ctx.db.schema_migrations().iter().find(\|m\| m.version == version)` |

**Fix:** Replace all with e.g. `ctx.db.tasks().pk_field().find(task_id)`.

---

## 🔴 ANTI-PATTERN 3: `Result<(), String>` return types (instead of `Result<(), ReducerError>`)
**Severity: HIGH**

An `error.rs` file exists with a fully-defined `ReducerError` enum (128 lines, 32 error variants including `Display` and `Error` impls). However, **no reducer uses it**. All 64 `Result<(), String>` occurrences should be `Result<(), ReducerError>`.

| File | Occurrences | Detail |
|------|-------------|--------|
| `reducers/task_reducers.rs` | 28 | All reducer return types are `Result<(), String>` |
| `reducers/admin_reducers.rs` | 20 | All reducer return types are `Result<(), String>` |
| `reducers/automation_reducers.rs` | 10 | All reducer return types are `Result<(), String>` |
| `reducers/project_reducers.rs` | 3 | All reducer return types are `Result<(), String>` |
| `reducers/relation_reducers.rs` | 2 | All reducer return types are `Result<(), String>` |

**Fix:** Replace `Result<(), String>` with `Result<(), ReducerError>` in all reducers and use typed variants instead of string literals. The `ReducerError` type is defined but never imported (`use crate::error::ReducerError`).

---

## 🔴 ANTI-PATTERN 6: Missing `#[index(btree)]` on Frequently-Queried Fields
**Severity: HIGH**

No `#[index(btree)]` annotations exist anywhere in the codebase. Fields queried by non-primary-key predicates via `.iter().filter()` should have secondary indexes.

| Table | Field | Reason for Index | Used In |
|-------|-------|------------------|---------|
| `TaskLog` | `task_id` | Filtered to delete logs for a task | `mod.rs:80` |
| `SwarmAgent` | `id` | Full-table-scan update pattern | `mod.rs:92` |
| `TaskChecklistItem` | `task_id` | Filtered for max-position queries and cleanup | `task_reducers.rs:572, 419` |
| `TaskLabelAssignment` | `task_id` | Filtered for label unassignment | `admin_reducers.rs:459, 554` |
| `TaskLabelAssignment` | `label_id` | Filtered when removing a label | `admin_reducers.rs:382` |
| `TaskRelation` | `task_id` | Duplicate-check scan | `relation_reducers.rs:28` |
| `WebhookDelivery` | `webhook_id` | Probable query target | (not yet filtered, but likely) |
| `IssueLink` | `kanban_task_id` | Lookup by task ID | `queries.rs:31` |

**Fix:** Add `#[index(btree)]` on the relevant fields.

---

## 🔴 ANTI-PATTERN 7: String Fields That Should Be Enums
**Severity: MEDIUM**

Several string fields with closed value domains are left as free-form `String`.

| Table | Field | Line | Known Values |
|-------|-------|------|-------------|
| `TaskRelation` | `relation_type` | tables.rs:302 | `"blocks"`, `"blocked_by"`, `"relates_to"`, `"duplicates"`, `"is_duplicated_by"` |
| `WebhookSubscription` | `wh_type` | tables.rs:174 | `"discord"`, `"slack"`, `"telegram"`, `"generic"` |
| `AutomationRule` | `trigger_event` | tables.rs:315 | `"task_created"`, `"task_completed"`, `"task_blocked"`, `"task_claimed"` |
| `AutomationRule` | `action_type` | tables.rs:317 | `"move_to_column"`, `"assign_to"`, `"add_label"`, `"notify_webhook"` |
| `AutomationRuleLog` | `result` | tables.rs:337 | `"fired"`, `"condition_failed"`, `"error"` |
| `TaskLog` | `action` | tables.rs:128 | `"created"`, `"claimed"`, `"completed"`, `"blocked"`, etc. |
| `ApiKey` | `permissions` | tables.rs:365 | Comma-separated: `"read"`, `"write"`, `"admin"` (should be `Vec<Permission>` or bitflags) |

**Fix:** Replace with proper Rust enums deriving `SpacetimeType` (pattern already established by `TaskStatus`, `SwarmAgentStatus`, `IssueLinkStatus` in `tables.rs`).

---

## 🔴 ANTI-PATTERN 11: Tables Marked Public That Should Be Private
**Severity: MEDIUM**

All 18 tables are marked `public`. Several serve purely internal infrastructure roles.

| Table | Line | Reason |
|-------|------|--------|
| `DispatcherStateRow` | tables.rs:222 | Internal key-value state store — no client should query this |
| `SchemaMigration` | tables.rs:345 | Internal migration tracking — no client should query this |
| `WebhookDelivery` | tables.rs:233 | Accumulating delivery log — internal |
| `AutomationRuleLog` | tables.rs:328 | Accumulating rule execution log — internal |
| `ApiKey` | tables.rs:358 | Hashed API keys — contains sensitive metadata |

**Fix:** Change `public` to `private` (or remove `public`) for internal tables.

---

## 🔴 ANTI-PATTERN 12: Reducer Result Tables That Accumulate Unboundedly
**Severity: MEDIUM**

| Table | Inserted In | Cleanup? |
|-------|-------------|----------|
| `WebhookDelivery` | `admin_reducers.rs:267` | None |
| `AutomationRuleLog` | (not yet used, but defined in tables.rs:328) | None |
| `TaskLog` | `mod.rs:50` | Only cleaned up when parent task is deleted (`delete_logs_for_task`) |
| `IssueLink` | `admin_reducers.rs:296` | Only cleaned up on explicit `unlink_issue` |

**Fix:** Add TTL-based cleanup or cap on stored records — particularly for `WebhookDelivery` and `AutomationRuleLog` which have no cleanup path at all.

---

## 🔴 ANTI-PATTERN 15: Delete-Then-Insert vs Update Pattern
**Severity: HIGH**

The update functions in `mod.rs` and many inline reducers delete matching rows then re-insert instead of performing a proper update. This doubles write cost and loses any versioning/incremental-update semantics.

| File | Lines | Function/Context |
|------|-------|-----------------|
| `reducers/mod.rs` | 62–73 | `update_task_in_db` — scan, delete all matches, insert |
| `reducers/mod.rs` | 87–98 | `update_agent_in_db` — same pattern |
| `reducers/mod.rs` | 100–111 | `update_project_in_db` — same pattern |
| `reducers/mod.rs` | 113–124 | `update_template_in_db` — same pattern |
| `reducers/admin_reducers.rs` | 234–244 | `update_webhook_subscription` — scan, delete, insert inline |
| `reducers/admin_reducers.rs` | 333–342 | `update_issue_link_status` — scan, delete, insert inline |
| `reducers/admin_reducers.rs` | 407–417 | `update_label` — scan, delete, insert inline |
| `reducers/admin_reducers.rs` | 587–600 | `set_dispatcher_state` — scan, delete, insert inline |
| `reducers/task_reducers.rs` | 595–604 | `toggle_checklist_item` — scan, delete, insert inline |
| `reducers/task_reducers.rs` | 628–637 | `reorder_checklist_items` — scan, delete, insert inline |
| `reducers/automation_reducers.rs` | 242–246 | `update_automation_rule` — scan, delete, insert inline |
| `reducers/automation_reducers.rs` | 291–295 | `revoke_api_key` — scan, delete, insert inline |

**Fix:** Use the STDB v2 `update()` method if available, or use `.pk_field().find()` + mutation instead of delete+reinsert. The combination of full-table-scan + delete + insert is the worst possible write path.

---

## 🔴 ANTI-PATTERN 17: `.iter().filter()` on Non-Indexed Fields
**Severity: HIGH**

28 `.filter()` calls with non-primary-key predicates cause full table scans on every execution.

| File | Line(s) | Predicate | Table |
|------|---------|-----------|-------|
| `reducers/mod.rs` | 67 | `\|t\| t.id == task.id` | Task (is PK — use index!) |
| `reducers/mod.rs` | 80 | `\|l\| l.task_id == task_id` | TaskLog |
| `reducers/mod.rs` | 92 | `\|a\| a.id == agent.id` | SwarmAgent (is PK — use index!) |
| `reducers/mod.rs` | 105 | `\|p\| p.id == project.id` | KanbanProject (is PK — use index!) |
| `reducers/mod.rs` | 118 | `\|t\| t.id == template.id` | TaskTemplate (is PK — use index!) |
| `reducers/task_reducers.rs` | 409 | `\|a\| a.task_id == task_id` | TaskLabelAssignment |
| `reducers/task_reducers.rs` | 419 | `\|i\| i.task_id == task_id` | TaskChecklistItem |
| `reducers/task_reducers.rs` | 538 | `\|c\| c.id == comment_id` | TaskComment (is PK — use index!) |
| `reducers/task_reducers.rs` | 572 | `\|i\| i.task_id == task_id` | TaskChecklistItem |
| `reducers/task_reducers.rs` | 599 | `\|i\| i.id == item.id` | TaskChecklistItem (is PK — use index!) |
| `reducers/task_reducers.rs` | 632 | `\|i\| i.id == item.id` | TaskChecklistItem (is PK — use index!) |
| `reducers/admin_reducers.rs` | 238 | `\|w\| w.id == wh.id` | WebhookSubscription (is PK — use index!) |
| `reducers/admin_reducers.rs` | 337 | `\|l\| l.kanban_task_id == link.kanban_task_id` | IssueLink (is PK — use index!) |
| `reducers/admin_reducers.rs` | 382 | `\|a\| a.label_id == label_id` | TaskLabelAssignment |
| `reducers/admin_reducers.rs` | 411 | `\|l\| l.id == label.id` | KanbanLabel (is PK — use index!) |
| `reducers/admin_reducers.rs` | 459 | `\|a\| a.task_id == task_id && a.label_id == label_id` | TaskLabelAssignment |
| `reducers/admin_reducers.rs` | 554 | `\|a\| a.task_id == *task_id && a.label_id == *label_id` | TaskLabelAssignment |
| `reducers/admin_reducers.rs` | 591 | `\|r\| r.key == key` | DispatcherStateRow (is PK — use index!) |
| `reducers/admin_reducers.rs` | 613 | `\|r\| r.key == key` | DispatcherStateRow (is PK — use index!) |
| `reducers/relation_reducers.rs` | 28 | `\|r\| r.task_id == task_id && r.related_task_id == related_task_id` | TaskRelation |
| `reducers/relation_reducers.rs` | 48 | `\|r\| r.id == relation_id` | TaskRelation (is PK — use index!) |
| `reducers/automation_reducers.rs` | 114 | `\|t\| t.active` | TaskTemplate |
| `reducers/automation_reducers.rs` | 243 | `\|r\| r.id == rule_id` | AutomationRule (is PK — use index!) |
| `reducers/automation_reducers.rs` | 253 | `\|r\| r.id == rule_id` | AutomationRule (is PK — use index!) |
| `reducers/automation_reducers.rs` | 292 | `\|k\| k.id == key_id` | ApiKey (is PK — use index!) |
| `reducers/automation_reducers.rs` | 313 | `\|m\| m.version == version` | SchemaMigration (is PK — use index!) |
| `reducers/admin_reducers.rs` | 436 | `\|a\| a.task_id == task_id && a.label_id == label_id` | TaskLabelAssignment |
| `reducers/admin_reducers.rs` | 500 | `\|a\| a.task_id == *task_id && a.label_id == *label_id` | TaskLabelAssignment |

**Fix:** Where filtering on primary key fields, use `.pk_field().find()` or `.pk_field().filter()`. For non-PK fields, add `#[index(btree)]` annotations. This accounts for ~80% of all data access patterns in the codebase.

---

## 🟡 ANTI-PATTERN 5: Missing `#[derive(Debug, Clone)]`
**Severity: LOW**

All table structs correctly derive `Debug` and `Clone`. The `ReducerError` enum in `error.rs` also has both. **No finding — compliant.** ✅

---

## 🟡 ANTI-PATTERN 2: Remove vs Delete (.remove() vs .delete())
**Severity: LOW**

No instances of `.remove()` found. All table deletion uses `.delete()`. **Compliant.** ✅

---

## 🟡 ANTI-PATTERN 4: Missing `#[primary_key]` on Table id Fields
**Severity: LOW**

All 18 tables have `#[primary_key]` on their identity field. **Compliant.** ✅

---

## 🟡 ANTI-PATTERN 8: Missing Accessor Trait Imports
**Severity: LOW**

All reducer files import `use crate::tables::*` which brings accessor traits into scope. All files that query the database import `use spacetimedb::Table`. **Compliant.** ✅

---

## 🟡 ANTI-PATTERN 9: Missing `reseed_uuid` Before `uuid_v4()` Calls
**Severity: LOW**

No UUID generation is used. The codebase uses a custom `make_id()` function with timestamp + sender + counter instead of `uuid_v4()`. **Not applicable.** ✅

---

## 🟡 ANTI-PATTERN 10: Missing `#[allow(clippy::too_many_arguments)]` on Reducers with 8+ Params
**Severity: LOW**

All reducers with 8+ parameters have the annotation:
- `add_task` (10 params) — line 10 ✅
- `add_task_template` (10 params) — line 10 ✅
- `update_task_template` (10 params) — line 61 ✅
- `create_automation_rule` (10 params) — line 186 ✅
- `update_automation_rule` (11 params) — line 218 ✅
- `log_webhook_delivery` (8 params) — line 250 ✅

**Compliant.** ✅

---

## 🟡 ANTI-PATTERN 13: Missing `#[reducer(init)]` vs Bare `#[reducer]` on Init Function
**Severity: LOW**

No init reducer exists in the codebase. **Not applicable.** ✅

---

## 🟡 ANTI-PATTERN 14: Inverted `is_internal()` Logic in Init Function
**Severity: LOW**

No init function exists. **Not applicable.** ✅

---

## 🟡 ANTI-PATTERN 16: Revision Counters via Full Table Scan
**Severity: LOW**

The codebase uses `thread_local!` Cell counters (`ID_COUNTER`, `LOG_COUNTER`) for ID generation, not table-based revision counters. **Compliant.** ✅

---

## Summary Statistics

| Anti-Pattern | Severity | Count | Status |
|-------------|----------|-------|--------|
| #1 — `.iter().find()` full scan | HIGH | 12 locations | ❌ FAIL |
| #3 — `Result<(), String>` vs typed error | HIGH | 64 occurrences across 5 files | ❌ FAIL |
| #6 — Missing `#[index(btree)]` | HIGH | 0 indexed fields, ~10+ need them | ❌ FAIL |
| #15 — Delete-then-insert | HIGH | 4 helpers + 8 inline = 12 locations | ❌ FAIL |
| #17 — `.iter().filter()` on non-indexed | HIGH | 28 `.filter()` calls, most full-table | ❌ FAIL |
| #7 — String-as-enum | MEDIUM | 7 string fields with closed value domains | ❌ FAIL |
| #11 — Table visibility (public vs private) | MEDIUM | 5 internal tables marked public | ❌ FAIL |
| #12 — Unbounded accumulators | MEDIUM | 4 tables with no cleanup | ❌ FAIL |
| #2 — Remove vs delete | LOW | 0 instances | ✅ PASS |
| #4 — Missing primary_key | LOW | 0 instances | ✅ PASS |
| #5 — Missing Debug/Clone | LOW | 0 instances | ✅ PASS |
| #8 — Accessor trait imports | LOW | 0 instances | ✅ PASS |
| #9 — reseed_uuid | LOW | N/A | ✅ PASS |
| #10 — too_many_arguments | LOW | 0 missing annotations | ✅ PASS |
| #13 — init reducer annotation | LOW | N/A | ✅ PASS |
| #14 — is_internal() logic | LOW | N/A | ✅ PASS |
| #16 — Revision counters | LOW | 0 instances | ✅ PASS |
