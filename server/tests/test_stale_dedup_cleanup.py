"""Test stale-worker alert dedup — cleanup coverage."""
from scheduler import _should_alert_stale, _stale_alerted_tasks


def test_cleanup_old_entries():
    """Periodic cleanup removes entries older than 2x cooldown."""
    _stale_alerted_tasks.clear()
    # Use large timestamps to keep cutoff positive
    start = 100_000_000_000  # Far future so cutoff is positive

    # Add an old entry well before cutoff
    old_ts = start - 100 * 3600_000  # 100 hours ago
    _should_alert_stale("old_task", old_ts)
    assert "old_task" in _stale_alerted_tasks

    # Add a new entry at 'start' — triggers cleanup
    # Cutoff = start - 2 * cooldown = start - 12h
    # old_ts (100h ago) < cutoff (12h ago) → should be removed
    _should_alert_stale("new_task", start)
    assert "old_task" not in _stale_alerted_tasks, "Old entry should be cleaned up"
    assert "new_task" in _stale_alerted_tasks
