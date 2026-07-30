"""Tests for server/_task_fountain.py."""


def test_module_importable():
    import _task_fountain as m  # noqa: F401

    assert callable(m.run)


def test_run_function():
    from _task_fountain import run

    assert callable(run)
