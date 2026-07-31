"""Test stale-worker alert dedup."""

from scheduler import _should_alert_stale, _stale_alerted_tasks


def test_first_alert_allowed():
    """First call for a task returns True."""
    _stale_alerted_tasks.clear()
    assert _should_alert_stale("task_x", 1000_000) is True


def test_second_alert_blocked():
    """Second call within cooldown returns False."""
    _stale_alerted_tasks.clear()
    assert _should_alert_stale("task_x", 1000_000) is True
    assert _should_alert_stale("task_x", 1000_001) is False  # 1ms later


def test_after_cooldown_allowed():
    """After cooldown expires, alert is allowed again."""
    _stale_alerted_tasks.clear()
    start = 1000_000
    assert _should_alert_stale("task_x", start) is True
    # 12 hours later (2x cooldown)
    later = start + 12 * 3600_000 + 1
    assert _should_alert_stale("task_x", later) is True


def test_different_tasks_independent():
    """Different tasks don't affect each other."""
    _stale_alerted_tasks.clear()
    assert _should_alert_stale("task_a", 1000_000) is True
    assert _should_alert_stale("task_b", 1000_001) is True
    assert _should_alert_stale("task_a", 1000_002) is False
    assert _should_alert_stale("task_b", 1000_003) is False
