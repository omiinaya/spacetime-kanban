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
