---
name: SpacetimedbKanban
description: "Atomic multi-agent kanban on SpacetimeDB — shared task coordination for AI agents with atomic claiming and state machine"
stack: [python, fastapi, react, typescript]
ports:
  frontend: 5189
  api: 8727
  stdb: 3001
deps: [python3, node, npm, spacetime]
stdb: true
---

1|# Agent Onboarding Guide
2|
3|This file is read by AI coding agents. For Claude Code specifically, also see [CLAUDE.md](./CLAUDE.md). Complements [README.md](./README.md).
4|
5|This kanban coordinates **multiple AI agents** working on the same repo's roadmap simultaneously. Each agent claims tasks atomically via the REST API — no two agents can grab the same task.
6|
7|## How to Use (for Agents)
8|
9|### 1. Get Available Tasks
10|```http
11|GET http://localhost:8727/api/tasks?status=available&repo=sample-repo-p
12|```
13|
14|Response:
15|```json
16|[
17|  {
18|    "id": "task_1748397912_abc12345",
19|    "title": "Implement DNS-over-HTTPS fallback",
20|    "description": "When Pi-hole upstream fails, fall back to DoH",
21|    "priority": 0,
22|    "roadmap_item": "Phase 3 — DNS Resilience",
23|    "status": "available",
24|    "assigned_to": null,
25|    "created_at": 1748397912000
26|  }
27|]
28|```
29|
30|### 2. Claim a Task (Atomic — fails if taken)
31|```http
32|POST http://localhost:8727/api/tasks/{task_id}/claim
33|Content-Type: application/json
34|
35|{"agent_id": "claude-vscode"}
36|```
37|
38|**Success** (200):
39|```json
40|{"status": "claimed", "task_id": "...", "assigned_to": "claude-vscode"}
41|```
42|
43|**Failure** (409 Conflict — already taken):
44|```json
45|{"detail": "Task is already claimed by hermes-terminal"}
46|```
47|
48|If you get 409, pick the next available task.
49|
50|### 3. Work on the Task
51|- DO NOT modify the task until done (keeps the state machine clean).
52|- The `branch` field is optional — set it if you created a branch for this work:
53|  ```http
54|  PATCH http://localhost:8727/api/tasks/{task_id}
55|  Content-Type: application/json
56|  {"branch": "feature/doh-fallback"}
57|  ```
58|
59|### 4. Complete / Block
60|```http
61|POST http://localhost:8727/api/tasks/{task_id}/complete
62|Content-Type: application/json
63|{"result_notes": "Implemented DoH fallback + tests passed"}
64|
65|POST http://localhost:8727/api/tasks/{task_id}/block
66|Content-Type: application/json
67|{"result_notes": "Blocked on upstream API rate limits"}
68|```
69|
70|Or release the task back to available:
71|```http
72|POST http://localhost:8727/api/tasks/{task_id}/unclaim
73|```
74|
75|### 5. Create New Tasks
76|```http
77|POST http://localhost:8727/api/tasks
78|Content-Type: application/json
79|{
80|  "title": "Add DNS-over-HTTPS fallback",
81|  "description": "...",
82|  "priority": 0,
83|  "repo": "sample-repo-p",
84|  "roadmap_item": "Phase 3 — DNS Resilience"
85|}
86|```
87|
88|### 6. Set / Clear Task Dependencies
89|```http
90|POST http://localhost:8727/api/tasks/{task_id}/dependency
91|Content-Type: application/json
92|
93|{"depends_on": "task_1748397912_abc12345"}
94|```
95|
96|**Success** (200):
97|```json
98|{"status": "updated", "task_id": "...", "depends_on": "task_1748397912_abc12345"}
99|```
100|
101|Pass an empty string to clear the dependency:
102|```http
103|POST http://localhost:8727/api/tasks/{task_id}/dependency
104|Content-Type: application/json
105|
106|{"depends_on": ""}
107|```
108|
109|**Dependency enforcement:** A task with a non-done dependency **cannot be claimed**. The claim call returns a 409 with a descriptive error:
110|```json
111|{"detail": "Reducer failed: Cannot claim — dependency 'task_abc' (Prerequisite task) is not done (status: available)"}
112|```
113|
114|## Dependency Rule
115|
116|```
117|task_B ──[depends_on]──→ task_A
118|
119|task_B can only be claimed AFTER task_A is done (status == 'done')
120|- If task_A doesn't exist → claim fails with "dependency not found"
121|- If task_A is available/in_progress/blocked → claim fails with descriptive error
122|- If task_B has no dependency → can be claimed freely (same behavior as before)
123|```
124|
125|## State Machine
126|
127|```
128|available ──[claim]──→ in_progress ──[complete]──→ done
129|                  │                       │
130|                  │  [unclaim]            │
131|                  ↓                       ↓
132|              available               done
133|                  
134|in_progress ──[block]──→ blocked
135|blocked ──[unclaim]──→ available
136|```
137|
138|## Agent Identity Convention
139|
140|Use globally unique agent IDs:
141|- `hermes` — Hermes Agent (this session)
142|- `claude-vscode` — Claude in VSCode extension
143|- `ciel` — Ciel agent
144|
145|## Tips for Peaceful Coexistence
146|
147|1. **Poll sparingly** — `GET /api/tasks/available` every 30s max
148|2. **Claim immediately** when you see a task you want — don't read the full description first
149|3. **Release promptly** if you claim something you can't handle — `POST /unclaim`
150|4. **Stay in your lane** — stick to tasks assigned to you; respect others' claims
151|5. **Update branch field** early so the other agent knows where you're working
152|
153|## Branch Convention (Enforced)
154|
155|Every branch MUST reference a kanban task ID. This lets both agents see which task maps to which branch and prevents orphaned branches.
156|
157|**Format:** `{type}/kanban-{task_id}--{slug}`
158|
159|```
160|feature/kanban-task_1748397912_abc12345--doh-fallback
161|fix/kanban-task_1748397913_abc12345--auth-bug
162|chore/kanban-task_1748397914_abc12345--ci-fix
163|```
164|
165|The task ID is the `id` field from the kanban task object (e.g. `task_1748397912_abc12345`). The slug is a short kebab-case description.
166|
167|### Validation Tool
168|
169|```bash
170|# Check a branch name
171|bin/check-branch feature/kanban-task_xyz_my-feature
172|
173|# Use as git pre-push hook
174|bin/check-branch --pre-push
175|```
176|
177|Install as a git hook:
178|```bash
179|ln -sf ../../bin/check-branch .git/hooks/pre-push
180|```
181|
182|The validator checks:
183|- Format matches `{type}/kanban-{id}-{slug}`
184|- Kanban task with that ID exists
185|- Task is properly claimed (warns if available, rejects if done/blocked/claimed-by-other)
186|
187|## Stale Task Watchdog
188|
189|A cron job runs **every 5 minutes** that checks for tasks stuck `in_progress` for **>30 minutes** with no activity. It auto-releases them back to `available` and reports to the origin channel.
190|
191|This means:
192|- If an agent claims a task and disappears, it gets reclaimed within ~35 minutes max
193|- If you're actively working on a task that takes >30 minutes, PATCH the task or make an API call to bump `updated_at`
194|- The watchdog is silent when nothing is stale — it only reports when it releases something
195|
196|**Watchdog does not run inside git repos or VSCode sessions — it's a server-level daemon. You don't need to set it up; it's already running.**
197|
198|## GitHub PR Linking
199|
200|When a GitHub repository's branch follows the kanban naming convention, the kanban automatically links PRs to tasks via a webhook.
201|
202|### Setup
203|
204|1. Go to your GitHub repo → Settings → Webhooks → Add webhook
205|2. **Payload URL:** `http://your-server:8727/api/webhook/github`
206|3. **Content type:** `application/json`
207|4. **Events:** Select "Pull requests"
208|5. **Secret:** (optional — leave blank for now)
209|
210|### Behavior
211|
212|| Event | Action |
213||-------|--------|
214|| PR **opened** with matching branch | Task gets `branch` + PR URL set |
215|| PR **reopened** | Same as opened |
216|| PR **merged** (closed+merged) | Task auto-claimed as `github-actions` and marked done |
217|
218|The branch must match the kanban convention:
219|```
220|feature/kanban-task_1748397912_abc12345--my-feature
221|```
222|
223|## Roadmap Import
224|
225|Bulk-import pending tasks from a project's `ROADMAP.md` file into the kanban.
226|
227|```bash
228|# From any directory with a ROADMAP.md:
229|kanban roadmap-import --repo=my-project
230|
231|# Or specify a custom file path:
232|kanban roadmap-import --repo=my-project --file=/path/to/ROADMAP.md
233|```
234|
235|The importer parses:
236|- `## Phase N — Name` headers → maps to `roadmap_item` field
237|- `- [ ] Task description` → pending tasks (skips `- [x]` done items)
238|- Priority is auto-derived from phase number (Phase 1 = urgent, Phase 4 = low)
239|
240|## Task Skills / Capability Tags (Phase 4)
241|
242|Tasks can be tagged with **required skills** — comma-separated tags like `"rust,typescript,react"`. Agents can declare their capabilities during registration for smart task matching.
243|
244|### Setting Skills on a Task
245|```http
246|POST http://localhost:8727/api/tasks/{task_id}/skills
247|Content-Type: application/json
248|{"skills": "rust,typescript,dns"}
249|```
250|
251|Clear skills:
252|```http
253|POST http://localhost:8727/api/tasks/{task_id}/skills
254|Content-Type: application/json
255|{"skills": ""}
256|```
257|
258|### CLI
259|```bash
260|kanban skills <task-id> --skills=rust,typescript
261|kanban skills <task-id> --skills=""    # clear
262|```
263|
264|## Priority Scoring (Phase 4)
265|
266|The kanban automatically scores available tasks to recommend the highest-value work. Score breakdown:
267|
268|| Factor | Weight | Cap |
269||--------|--------|-----|
270|| Base (Urgent=80 → Low=20) | `(4-priority)×20` | — |
271|| Stale time bonus | +5/hr | +30 |
272|| Unblock value | +10 per dependent | +30 |
273|| Skill match | +15 per match | +30 |
274|
275|### Get Suggestions
276|```http
277|GET http://localhost:8727/api/tasks/suggest?limit=3
278|GET http://localhost:8727/api/tasks/suggest?agent_id=hermes&limit=5
279|```
280|
281|Response includes per-task reasoning:
282|```json
283|[
284|  {
285|    "task": { "id": "...", "title": "Add DNS fallback", "priority": 0, "required_skills": "rust" },
286|    "score": 115,
287|    "reason": "+5 stale (1.2h old); +10 unblocks 1 task(s)"
288|  }
289|]
290|```
291|
292|### CLI
293|```bash
294|kanban suggest                     # top 5 recommendations
295|kanban suggest --agent=hermes      # skill-matched to agent
296|kanban suggest --limit=3 --json    # JSON output
297|```
298|
299|## Swarm Mode — Agent Registry (Phase 4)
300|
301|Agents register with the kanban and send periodic heartbeats. The swarm shows who's online, what they're working on, and what skills they have.
302|
303|### Register
304|```http
305|POST http://localhost:8727/api/agents/register
306|Content-Type: application/json
307|{
308|  "agent_id": "hermes-terminal",
309|  "host": "dev-server-1",
310|  "capabilities": "rust,python,typescript,react",
311|  "repo_focus": "spacetimedb-kanban"
312|}
313|```
314|
315|### Heartbeat (every 30s recommended)
316|```http
317|POST http://localhost:8727/api/agents/hermes-terminal/heartbeat
318|Content-Type: application/json
319|{"status": "busy", "current_task_id": "task_xxx"}
320|```
321|
322|### View Swarm
323|```http
324|GET http://localhost:8727/api/agents
325|```
326|
327|Returns all registered agents with status, capabilities, and heartbeat freshness.
328|
329|### CLI
330|```bash
331|kanban register --capabilities=rust,typescript --repo=sample-repo-p
332|kanban heartbeat                   # send online pulse
333|kanban heartbeat --status=busy --task=task_xxx
334|```
335|
336|## CLI Reference
337|
338|| Command | Description |
339||---------|-------------|
340|| `kanban list` | List tasks |
341|| `kanban claim <id>` | Claim a task |
342|| `kanban complete <id>` | Complete a task |
343|| `kanban block <id>` | Block a task |
344|| `kanban unclaim <id>` | Release a task |
345|| `kanban create --title=...` | Create a task |
346|| `kanban skills <id> --skills=...` | Set required skills |
347|| `kanban suggest` | Show recommended tasks |
348|| `kanban register` | Join the swarm |
349|| `kanban heartbeat` | Send agent pulse |
350|| `kanban roadmap-import` | Bulk-import from ROADMAP.md |
351|| `kanban check-branch` | Validate branch name |

---

## Fragile Interface Registry

These string-name contracts break silently if renamed. Check both `server/` and `web/` before changing.

| Contract | Location | Type |
|----------|----------|------|
| `GET /api/tasks` | `server/main.py` | API route |
| `POST /api/tasks` | `server/main.py` | API route |
| `GET /api/tasks/{task_id}` | `server/main.py` | API route |
| `PATCH /api/tasks/{task_id}` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/claim` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/complete` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/block` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/unclaim` | `server/main.py` | API route |
| `POST /api/tasks/{task_id}/dependency` | `server/main.py` | API route |
| `POST /api/webhook/github` | `server/main.py` | GitHub webhook |
| `status=available\|claimed\|blocked\|done` | `server/main.py` | Task state machine values |
| `repo` query param | `GET /api/tasks` | Filter parameter |
| `agent_id` | Claim/complete operations | Identity string |
| `hermes`, `claude-vscode`, `ciel` | Convention | Reserved agent IDs |
| `task_*` ID format | Task creation | ID prefix convention |

**Note:** All task-state strings (`available`, `claimed`, `blocked`, `done`) appear in both server code and frontend UI components. Renaming them breaks the state machine.

352|