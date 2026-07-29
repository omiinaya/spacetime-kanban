"""Tests for server/_task_fountain.py."""


def test_module_importable():
    import server._task_fountain  # noqa: F401


def test_run_function():
    from server._task_fountain import run

    assert callable(run)
