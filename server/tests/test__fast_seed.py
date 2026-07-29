"""Tests for server/_fast_seed.py."""


def test_module_importable():
    import server._fast_seed  # noqa: F401


def test_main_function():
    from server._fast_seed import main

    assert callable(main)


def test_create_task_exists():
    from server._fast_seed import create_task

    assert callable(create_task)
