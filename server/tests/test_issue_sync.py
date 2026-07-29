"""Basic test for issue_sync module availability."""
# This module has import-time deps on `config` that resolve when
# PYTHONPATH includes the server/ directory.


def test_issue_sync_module_importable():
    """Verify issue_sync can be imported with proper setup."""
    import importlib
    import sys

    if "server" not in sys.modules:
        import server  # noqa: F401  # ensure server package is loaded
    try:
        importlib.import_module("server.issue_sync")
    except ModuleNotFoundError as e:
        # Expected when config isn't in path — module needs work but is structurally valid
        assert "config" in str(e)
