"""Tests for server/models.py."""

import pytest
from pydantic import ValidationError

from server.models import (
    ClaimRequest,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    WebhookCreateRequest,
)


class TestTaskCreate:
    def test_valid_request(self):
        req = TaskCreate(
            title="Test task",
            description="A test",
            priority=1,
        )
        assert req.title == "Test task"
        assert req.priority == 1

    def test_missing_required_title(self):
        with pytest.raises(ValidationError):
            TaskCreate()

    def test_default_priority(self):
        req = TaskCreate(title="Test")
        assert req.priority == 2


class TestTaskUpdate:
    def test_valid_update(self):
        req = TaskUpdate(
            title="Updated title",
            description="Updated desc",
        )
        assert req.title == "Updated title"

    def test_partial_update(self):
        req = TaskUpdate(title="Only title")
        assert req.title == "Only title"
        assert req.description is None


class TestTaskOut:
    def test_required_fields(self):
        task = TaskOut(
            id="task_123",
            title="Test",
            description="Desc",
            priority=0,
            status="available",
            repo="test-repo",
            roadmap_item="Phase 1",
            created_by="tester",
            created_at=1000,
            updated_at=1000,
        )
        assert task.id == "task_123"
        assert task.archived is False

    def test_optional_defaults(self):
        task = TaskOut(
            id="t",
            title="T",
            description="D",
            priority=0,
            status="available",
            repo="r",
            roadmap_item="r",
            created_by="c",
            created_at=0,
            updated_at=0,
        )
        assert task.assigned_to is None
        assert task.score == 0
        assert task.archived is False


class TestWebhookCreate:
    def test_valid_webhook(self):
        req = WebhookCreateRequest(
            url="https://hooks.example.com/test",
            wh_type="generic",
            events=["task_created"],
        )
        assert req.url.startswith("https://")

    def test_missing_url(self):
        with pytest.raises(ValidationError):
            WebhookCreateRequest(wh_type="discord", events=["task_created"])


class TestClaimRequest:
    def test_valid_claim(self):
        req = ClaimRequest(agent_id="agent-1")
        assert req.agent_id == "agent-1"

    def test_missing_agent(self):
        with pytest.raises(ValidationError):
            ClaimRequest()
