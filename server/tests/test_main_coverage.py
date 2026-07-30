"""Coverage tests for main.py uncovered paths.

Targets:
  - serve_spa() fallback JSON when index.html missing (line 156)
  - spa_fallback 404 JSON for non-/api/ path without index.html (line 223)
  - Import-time warning when WEB_DIST missing (lines 140-141)
  - workers/run.py sys.path.insert at import time (line 27)
"""

import os
import subprocess
import sys
import tempfile

from fastapi.testclient import TestClient

import main as main_module

# Path helpers
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(TESTS_DIR)
PROJECT_ROOT = os.path.dirname(SERVER_DIR)


def test_spa_route_no_index():
    """Line 156: serve_spa returns JSON dict when index.html is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original = main_module.WEB_DIST
        main_module.WEB_DIST = tmpdir
        try:
            client = TestClient(main_module.app)
            resp = client.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert "dashboard not built" in data["status"]
        finally:
            main_module.WEB_DIST = original


def test_spa_fallback_no_index_non_api():
    """Line 223: spa_fallback returns 404 for non-/api/ paths when no index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        original = main_module.WEB_DIST
        main_module.WEB_DIST = tmpdir
        try:
            client = TestClient(main_module.app)
            resp = client.get("/some-unknown-page")
            assert resp.status_code == 404
            assert resp.json() == {"detail": "Not found"}
        finally:
            main_module.WEB_DIST = original


def _run_subprocess(script_lines, cwd):
    """Write a temp script and run it, returning CompletedProcess."""
    with tempfile.TemporaryDirectory(suffix="_subp_test") as tmp:
        script_path = os.path.join(tmp, "_test_script.py")
        with open(script_path, "w") as f:
            f.write("\n".join(script_lines) + "\n")
        result = subprocess.run(  # noqa: S603 — controlled, using sys.executable + temp script
            [sys.executable, "-W", "ignore", script_path],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    return result


def test_main_no_web_dist_warning():
    """Lines 140-141: warning printed when WEB_DIST does not exist at import."""
    web_dist_real = os.path.join(PROJECT_ROOT, "web", "dist")
    script = [
        "import builtins",
        "import os",
        "import sys",
        f"sys.path.insert(0, {SERVER_DIR!r})",
        "",
        "_real_print = builtins.print",
        "_printed = []",
        "",
        "def _capture_print(*args, **kwargs):",
        "    _printed.append(' '.join(str(a) for a in args))",
        "    _real_print(*args, **kwargs)",
        "",
        "builtins.print = _capture_print",
        "",
        "_real_isdir = os.path.isdir",
        f"web_dist_target = {web_dist_real!r}",
        "",
        "def _mock_isdir(p):",
        "    if os.path.abspath(p) == os.path.abspath(web_dist_target):",
        "        return False",
        "    return _real_isdir(p)",
        "",
        "os.path.isdir = _mock_isdir",
        "",
        "from main import WEB_DIST",
        "",
        "print_res = '|'.join(_printed)",
        "print('WEB_DIST=' + repr(WEB_DIST), flush=True)",
        "print('PRINTS=' + print_res, flush=True)",
    ]
    result = _run_subprocess(script, PROJECT_ROOT)
    combined = result.stdout + result.stderr
    if result.returncode != 0:
        print(f"DEBUG stdout: {result.stdout}")
        print(f"DEBUG stderr: {result.stderr}")
    assert result.returncode == 0, f"Subprocess failed:\n{combined}"
    assert "Web dist not found" in combined, f"Expected warning not found in output:\n{combined}"


def test_workers_run_syspath_insert():
    """Line 27: workers/run.py inserts server dir into sys.path at import."""
    script = [
        "import os",
        "import sys",
        f"sys.path.insert(0, {SERVER_DIR!r})",
        "",
        "import workers.run",
        "",
        "script_dir = os.path.dirname(os.path.abspath(workers.run.__file__))",
        "svr_dir = os.path.dirname(script_dir)",
        "assert svr_dir in sys.path, 'server_dir ' + svr_dir + ' not in sys.path'",
        "print('OK server_dir=' + svr_dir)",
    ]
    result = _run_subprocess(script, PROJECT_ROOT)
    assert "OK server_dir=" in result.stdout, (
        f"workers/run.py import failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
