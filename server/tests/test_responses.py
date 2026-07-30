"""Tests for server/responses.py."""


class TestRowToTask:
    def test_minimal_row(self):
        from server.responses import _row_to_task

        row = {
            "id": "task_1",
            "title": "Test",
            "status": "available",
        }
        task = _row_to_task(row)
        assert task.id == "task_1"
        assert task.title == "Test"
        assert task.status == "available"

    def test_full_row(self):
        from server.responses import _row_to_task

        row = {
            "id": "task_2",
            "title": "Full",
            "description": "Full task",
            "priority": 1,
            "status": "in_progress",
            "assigned_to": "agent-1",
            "repo": "test-repo",
            "roadmap_item": "Phase 1",
            "created_by": "tester",
            "created_at": 1000,
            "updated_at": 2000,
            "score": 5,
            "archived": False,
        }
        task = _row_to_task(row)
        assert task.id == "task_2"
        assert task.priority == 1
        assert task.assigned_to == "agent-1"
        assert task.score == 5

    def test_defaults_for_missing_fields(self):
        from server.responses import _row_to_task

        row = {"id": "t", "title": "T", "status": "available"}
        task = _row_to_task(row)
        assert task.priority == 2
        assert task.description == ""
        assert task.score == 0
        assert task.archived is False
        assert task.assigned_to is None


class TestRowToAgent:
    def test_minimal_agent(self):
        from server.responses import _row_to_agent
        row = {"id": "agent_1"}
        agent = _row_to_agent(row)
        assert agent.id == "agent_1"
        assert agent.host == ""
        assert agent.status == "offline"
        assert agent.last_heartbeat == 0

    def test_full_agent(self):
        from server.responses import _row_to_agent
        row = {
            "id": "agent_2",
            "host": "192.0.2.10",
            "capabilities": "rust,python",
            "repo_focus": "sample-repo-q",
            "current_task_id": "task_42",
            "status": "online",
            "last_heartbeat": 5000,
            "first_seen": 1000,
        }
        agent = _row_to_agent(row)
        assert agent.id == "agent_2"
        assert agent.host == "192.0.2.10"
        assert agent.capabilities == "rust,python"
        assert agent.repo_focus == "sample-repo-q"
        assert agent.status == "online"
        assert agent.last_heartbeat == 5000
        assert agent.first_seen == 1000


class TestRowToTemplate:
    def test_minimal_template(self):
        from server.responses import _row_to_template
        row = {"id": "tmpl_1", "title": "Template", "description": "Test"}
        tmpl = _row_to_template(row)
        assert tmpl.id == "tmpl_1"
        assert tmpl.title == "Template"
        assert tmpl.active is True
        assert tmpl.cron_schedule == ""

    def test_full_template(self):
        from server.responses import _row_to_template
        row = {
            "id": "tmpl_2",
            "title": "Full",
            "description": "Full template",
            "priority": 1,
            "repo": "test-repo",
            "roadmap_item": "Phase 2",
            "required_skills": "python",
            "cron_schedule": "0 9 * * *",
            "created_by": "admin",
            "created_at": 1000,
            "last_triggered_at": 2000,
            "active": False,
        }
        tmpl = _row_to_template(row)
        assert tmpl.id == "tmpl_2"
        assert tmpl.priority == 1
        assert tmpl.cron_schedule == "0 9 * * *"
        assert tmpl.active is False


class TestRowToLog:
    def test_minimal_log(self):
        from server.responses import _row_to_log

        row = {"id": "log_1", "task_id": "task_1", "action": "created"}
        log = _row_to_log(row)
        assert log.id == "log_1"
        assert log.action == "created"

    def test_full_log(self):
        from server.responses import _row_to_log

        row = {
            "id": "log_2",
            "task_id": "task_2",
            "action": "completed",
            "agent_id": "agent-1",
            "notes": "Done",
            "timestamp": 1000,
        }
        log = _row_to_log(row)
        assert log.id == "log_2"
        assert log.agent_id == "agent-1"
        assert log.notes == "Done"
        assert log.timestamp == 1000
