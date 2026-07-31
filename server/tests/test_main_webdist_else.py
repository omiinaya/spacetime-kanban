"""Cover main.py lines 140-141 and workers/run.py line 27 via in-process import manipulation."""

import importlib
import importlib.util
import os
import sys
from unittest.mock import patch as mock_patch

import pytest


class TestMainWebDistElse:
    """Cover main.py lines 140-141: the else branch when WEB_DIST doesn't exist."""

    def test_web_dist_else_branch_in_process(self):
        """Reload main.py with mocked isdir to exercise the else branch in-process."""
        import main as main_mod

        server_dir = os.path.normpath(
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )
        project_root = os.path.normpath(os.path.join(server_dir, ".."))
        web_dist = os.path.join(project_root, "web", "dist")

        if not os.path.isdir(web_dist):
            return

        real_isdir = os.path.isdir
        with mock_patch.object(os.path, "isdir") as mock_isdir:

            def selective_isdir(path):
                normed = os.path.normpath(str(path))
                if normed == os.path.normpath(web_dist):
                    return False
                if normed == os.path.normpath(os.path.join(web_dist, "assets")):
                    return False
                return real_isdir(path)

            mock_isdir.side_effect = selective_isdir

            # Reload main — re-executes module-level code including the else branch
            importlib.reload(main_mod)

        assert hasattr(main_mod, "app")


class TestWorkersRunPathBranch:
    """Cover workers/run.py line 27: the if-server_dir-not-in-sys.path branch."""

    def test_server_dir_path_branch(self):
        """Load workers/run.py via importlib util with server_dir removed from sys.path."""
        server_dir = os.path.normpath(
            os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        )
        workers_run_path = os.path.join(server_dir, "workers", "run.py")

        # Save original state
        orig_path = sys.path.copy()

        try:
            # Remove all server_dir references from sys.path
            sys.path = [p for p in sys.path if os.path.normpath(p) != server_dir]
            assert server_dir not in sys.path, "server_dir must not be on sys.path"

            # Load the module via its file path — executes module-level code
            spec = importlib.util.spec_from_file_location("workers._run_test", workers_run_path)
            assert spec is not None, f"No spec for {workers_run_path}"
            mod = importlib.util.module_from_spec(spec)

            # Must register in sys.modules so internal imports work
            sys.modules["workers._run_test"] = mod
            spec.loader.exec_module(mod)

            # After module-level code runs, server_dir should be on sys.path
            assert server_dir in sys.path, "Module should have added server_dir to sys.path"
            assert hasattr(mod, "route_task"), "Module should have route_task"
            assert hasattr(mod, "main"), "Module should have main"
        finally:
            sys.path = orig_path
            if "workers._run_test" in sys.modules:
                del sys.modules["workers._run_test"]


class TestWorkersRunMainBranch:
    """Cover workers/run.py main() usage path (line 56)."""

    def test_main_no_args_sys_exit(self):
        """Test that main() with no args calls sys.exit(2)."""
        import contextlib
        import io

        import workers.run as wr_mod

        old_argv = sys.argv
        sys.argv = ["workers/run.py"]

        try:
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                with pytest.raises(SystemExit) as exc_info:
                    wr_mod.main()
            assert exc_info.value.code == 2
            assert "Usage" in stderr.getvalue()
        finally:
            sys.argv = old_argv

    def test_main_with_task_id(self):
        """Test that main() with a task ID calls run_worker."""
        import workers.run as wr_mod

        with (
            mock_patch("workers.run.run_worker") as mock_run,
            mock_patch("workers.run.sys.exit"),
            mock_patch.object(sys, "argv", ["workers/run.py", "task_123"]),
        ):
            wr_mod.main()
            mock_run.assert_called_once_with("task_123", wr_mod.route_task)
