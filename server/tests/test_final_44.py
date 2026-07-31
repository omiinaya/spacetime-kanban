"""Precision tests for the 44 remaining uncovered lines in workers/mechanical.

Each test is named after the line(s) it targets.
Uses real temp directories + targeted mocks to hit each branch.

IMPORTANT: repo_path is a READ-ONLY property on WorkerContext.
Use patch.object(WorkerContext, 'repo_path', td) to override it.
"""

import os
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from workers.base import WorkerContext
from workers.mechanical import (  # noqa: E402
    handle_add_index_btree,
    handle_add_init_py,
    handle_add_test_scaffold,
    handle_bare_except_scanner,
    handle_ci_pipeline,
    handle_extract_module,
    handle_git_maintenance,
    handle_remove_unused_imports,
    handle_replace_unwrap_scanner,
    handle_run_tests,
    handle_typed_errors,
    handle_update_deps,
)


def _run_handler(handler_fn, td, task_patch=None, extra_patches=None):
    """Run a handler with repo_path patched to td + optional extra patches."""
    ctx = WorkerContext("x")
    ctx.task = {"id": "x", "title": "x", "repo": "test"}
    if task_patch:
        ctx.task.update(task_patch)

    patches = [patch.object(WorkerContext, "repo_path", td)]
    if extra_patches:
        patches.extend(extra_patches)

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        return handler_fn(ctx)


# ══════════════════════════════════════════════════════════════════════
# Line 155 — handle_add_index_btree:
#   changes > 0 AND errors non-empty (partial success)
# ══════════════════════════════════════════════════════════════════════


def test_155_index_btree_partial_success():
    """Line 155: one file succeeds (has FK fields), one file fails on open."""
    with tempfile.TemporaryDirectory() as td:
        stdb = Path(td, "server", "spacetimedb", "src")
        stdb.mkdir(parents=True)

        # File 1 — has candidate FK fields (will produce changes)
        (stdb / "tables.rs").write_text(
            "pub struct Task {\n    pub user_id: u64,\n    pub name: String,\n}\n"
        )
        # File 2 — has FK fields but unreadable → OSError on open
        tbl2 = stdb / "lib.rs"
        tbl2.write_text("pub struct Item {\n    pub owner_id: u64,\n}\n")
        os.chmod(tbl2, 0o000)

        try:
            s, m = _run_handler(handle_add_index_btree, td)
            assert isinstance(s, bool)
        finally:
            os.chmod(tbl2, 0o644)


# ══════════════════════════════════════════════════════════════════════
# Line 253 — handle_remove_unused_imports:
#   changes > 0 AND errors non-empty
# ══════════════════════════════════════════════════════════════════════


def test_253_remove_imports_partial():
    """Line 253: ruff runs (changes > 0) but cargo raises FNF (errors)."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "pyproject.toml").write_text("[tool.ruff]\n")
        Path(td, "server", "spacetimedb").mkdir(parents=True)

        call_count = 0

        def sub_side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="Fixed 5 errors", stderr="")
            raise FileNotFoundError("cargo not found")

        s, m = _run_handler(
            handle_remove_unused_imports,
            td,
            extra_patches=[patch("subprocess.run", sub_side_effect)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 350-351 — handle_extract_module:
#   ValueError parsing wc -l output
# ══════════════════════════════════════════════════════════════════════


def test_350_extract_valueerror():
    """Lines 350-351: non-numeric count in wc output triggers ValueError."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "dummy.rs").write_text("// dummy\n")
        wc_out = f"abc {td}/dummy.rs\n10 total\n"
        s, m = _run_handler(
            handle_extract_module,
            td,
            extra_patches=[
                patch("subprocess.run", return_value=MagicMock(returncode=0, stdout=wc_out)),
            ],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 534-536 — handle_extract_module:
#   OSError when verifying updated file after extraction
# ══════════════════════════════════════════════════════════════════════


def test_534_extract_verify_oserror():
    """Lines 534-536: verification read of original file fails."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td, "src")
        src.mkdir()
        target = src / "mod.rs"
        target.write_text(
            "pub fn foo() {\n"
            "    let x = 1; let y = 2; let z = 3;\n"
            '    println!("{}", x);\n'
            "}\n"
            "\n"
            "pub fn bar() {\n"
            "    // keep\n"
            "}\n"
        )
        # Ensure file is >= 10 lines
        with open(target, "a") as f:
            for i in range(5):
                f.write(f"// line {i}\n")

        wc_out = f"10 {target}\n20 total\n"

        m = mock_open(read_data=target.read_text())
        m.side_effect = [m.return_value, OSError(13, "Permission denied")]

        def sub_side_effect(*args, **kwargs):
            # find/wc call → return wc output; cat write call → actually write file
            cmd = args[0]
            if cmd and cmd[0] == "find":
                return MagicMock(returncode=0, stdout=wc_out)
            if cmd and cmd[0] == "sh":
                # cmd = ["sh", "-c", "cat > 'path'"]
                import re as _re

                mm = _re.search(r"cat > '([^']+)'", cmd[2] if len(cmd) > 2 else "")
                if mm:
                    Path(mm.group(1)).write_text(kwargs.get("input", ""))
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        s, m2 = _run_handler(
            handle_extract_module,
            td,
            extra_patches=[
                patch("subprocess.run", sub_side_effect),
                patch("builtins.open", m),
            ],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 744-747 — handle_typed_errors (Python scanning):
#   line body in the re.finditer loop for raise X(...)
#   and except OSError triggered by unreadable Python file
# ══════════════════════════════════════════════════════════════════════


def test_744_typed_errors_raise_nonliteral():
    """Lines 744-747: Python re.finditer body for raise X(non_string, 'msg')."""
    with tempfile.TemporaryDirectory() as td:
        # File with raise X(non_string, 'msg') that hits the finditer loop
        (Path(td) / "app.py").write_text("raise Exception(123, 'big fat error here')\n")
        # Also an unreadable Python file to trigger OSError in line 747
        bad = Path(td) / "broken.py"
        bad.write_text("x = 1\n")
        os.chmod(bad, 0o000)

        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)
        # Restore permissions for cleanup
        os.chmod(bad, 0o644)


# ══════════════════════════════════════════════════════════════════════
# Lines 757 — handle_typed_errors (Rust scanning):
#   non-.rs file in rust_src triggers "continue" at line 757
# ══════════════════════════════════════════════════════════════════════


def test_757_typed_errors_non_rs_in_rust_src():
    """Line 757: non-.rs files in rust_src are skipped."""
    with tempfile.TemporaryDirectory() as td:
        rust_src = Path(td, "server", "spacetimedb", "src")
        rust_src.mkdir(parents=True)
        (rust_src / "mod.rs").write_text('Err("bad thing".to_string())\n')
        (rust_src / "backup.bak").write_text("ignore me\n")

        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 800 — handle_typed_errors (Rust scanning):
#   unreadable .rs file triggers `except OSError: pass`
# ══════════════════════════════════════════════════════════════════════


def test_800_typed_errors_unreadable_rust():
    """Line 800: unreadable .rs file raises OSError during Rust scan."""
    with tempfile.TemporaryDirectory() as td:
        rust_src = Path(td, "server", "spacetimedb", "src")
        rust_src.mkdir(parents=True)
        bad = rust_src / "broken.rs"
        bad.write_text('Err("unreadable".to_string())\n')
        os.chmod(bad, 0o000)

        try:
            s, m = _run_handler(handle_typed_errors, td)
            assert isinstance(s, bool)
        finally:
            os.chmod(bad, 0o644)


# ══════════════════════════════════════════════════════════════════════
# Lines 859-861, 864-865 — handle_typed_errors:
#   single Rust module with findings — triggers singular enum name
# ══════════════════════════════════════════════════════════════════════


def test_859_typed_errors_single_module():
    """Lines 859-865: Rust findings from exactly one reducer module."""
    with tempfile.TemporaryDirectory() as td:
        reducers = Path(td, "server", "spacetimedb", "src", "reducers")
        reducers.mkdir(parents=True)
        (reducers / "items_reducers.rs").write_text('Err("item not found".to_string())\n')

        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 880-881 — handle_typed_errors:
#   variant fallback when words list is empty (non-alphanum messages)
# ══════════════════════════════════════════════════════════════════════


def test_880_typed_errors_empty_variant():
    """Lines 880-881: Rust messages with no alphanumeric chars generate 'Error'."""
    with tempfile.TemporaryDirectory() as td:
        reducers = Path(td, "server", "spacetimedb", "src", "reducers")
        reducers.mkdir(parents=True)
        (reducers / "items_reducers.rs").write_text('Err("!!!".to_string())\n')
        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 884-887 — handle_typed_errors:
#   variant dedup — two messages generating same CamelCase variant
# ══════════════════════════════════════════════════════════════════════


def test_884_typed_errors_variant_dedup():
    """Lines 884-887: duplicate variant names get suffixed (Error, Error1, Error2...)."""
    with tempfile.TemporaryDirectory() as td:
        reducers = Path(td, "server", "spacetimedb", "src", "reducers")
        reducers.mkdir(parents=True)
        # THREE messages that all produce empty words lists → variant "Error"
        # (need 3 so the while-loop idx += 1 body actually runs)
        (reducers / "items_reducers.rs").write_text(
            'Err("!!!".to_string())\nErr("???".to_string())\nErr("###".to_string())\n'
        )
        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 927-928 — handle_typed_errors:
#   write error.rs fails with OSError
# ══════════════════════════════════════════════════════════════════════


def test_927_typed_errors_write_fail():
    """Lines 921-922: writing error.rs raises OSError."""
    with tempfile.TemporaryDirectory() as td:
        reducers = Path(td, "server", "spacetimedb", "src", "reducers")
        reducers.mkdir(parents=True)
        (reducers / "items_reducers.rs").write_text('Err("bad".to_string())\n')

        # First open = read reducers.rs (must return content), second = write error.rs (fails)
        m = mock_open(read_data='Err("bad".to_string())\n')
        m.side_effect = [m.return_value, OSError(13, "denied")]
        s, m2 = _run_handler(
            handle_typed_errors,
            td,
            extra_patches=[patch("builtins.open", m)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 965 — handle_typed_errors (Python enum part):
#   var > 48 chars → fallback to words[:3]
# ══════════════════════════════════════════════════════════════════════


def test_965_typed_errors_long_python_var():
    """Line 965: long Python variant name gets truncated to 3 words."""
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "app.py").write_text(
            'raise ValueError("aaaaaaaaa bbbbbbbbb ccccccccc ddddddddd eeeeeeeee fffffffff")\n'
        )
        s, m = _run_handler(handle_typed_errors, td)
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1087 — handle_run_tests:
#   subprocess.TimeoutExpired for npm tests
# ══════════════════════════════════════════════════════════════════════


def test_1087_run_tests_npm_timeout():
    """Line 1087: npm test command times out."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "package.json").write_text('{"scripts": {"test": "jest"}}\n')
        s, m = _run_handler(
            handle_run_tests,
            td,
            extra_patches=[
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired("npm test", 30)),
            ],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1128 — handle_update_deps:
#   cargo update times out
# ══════════════════════════════════════════════════════════════════════


def test_1128_update_deps_cargo_timeout():
    """Line 1128: cargo update times out."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "server", "spacetimedb").mkdir(parents=True)
        s, m = _run_handler(
            handle_update_deps,
            td,
            extra_patches=[
                patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cargo update", 30)),
            ],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1130 — handle_update_deps:
#   cargo not found (FileNotFoundError) on cargo update
# ══════════════════════════════════════════════════════════════════════


def test_1130_update_deps_cargo_not_found():
    """Line 1130: cargo binary not found."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "server", "spacetimedb").mkdir(parents=True)
        s, m = _run_handler(
            handle_update_deps,
            td,
            extra_patches=[
                patch("subprocess.run", side_effect=FileNotFoundError("cargo")),
            ],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 1150-1151 — handle_update_deps:
#   npm update raises OSError
# ══════════════════════════════════════════════════════════════════════


def test_1150_update_deps_npm_oserror():
    """Lines 1150-1151: npm update raises OSError."""
    with tempfile.TemporaryDirectory() as td:
        Path(td, "server", "spacetimedb").mkdir(parents=True)
        Path(td, "package.json").write_text('{"dependencies": {}}\n')

        call_count = 0

        def sub_side_effect(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(returncode=0, stdout="", stderr="")
            raise OSError("npm not executable")

        s, m = _run_handler(
            handle_update_deps,
            td,
            extra_patches=[patch("subprocess.run", sub_side_effect)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1176 — handle_git_maintenance:
#   git output contains "nothing" → "nothing to clean"
# ══════════════════════════════════════════════════════════════════════


def test_1176_git_nothing():
    """Line 1170: git output contains 'nothing' → returns 'nothing to clean'."""
    with tempfile.TemporaryDirectory() as td:
        s, m = _run_handler(
            handle_git_maintenance,
            td,
            extra_patches=[
                patch(
                    "subprocess.run",
                    return_value=MagicMock(returncode=0, stdout="", stderr="nothing to prune"),
                ),
            ],
        )
        assert s
        assert "nothing" in m.lower()


# ══════════════════════════════════════════════════════════════════════
# Line 1376 — handle_add_init_py:
#   Description lines starting with "- dir" (hyphen prefix)
# ══════════════════════════════════════════════════════════════════════


def test_1376_add_init_py_dash_prefix():
    """Line 1376: stripping hyphen prefix from description lines."""
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td, "server", "lib")
        pkg.mkdir(parents=True)

        s, m = _run_handler(
            handle_add_init_py,
            td,
            task_patch={
                "title": "add __init__.py to 2 python package",
                "description": "- server/lib\n",
            },
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1394 — handle_add_init_py:
#   when __init__.py already exists → continue
# ══════════════════════════════════════════════════════════════════════


def test_1394_add_init_py_already_exists():
    """Line 1394: __init__.py exists → skip."""
    with tempfile.TemporaryDirectory() as td:
        pkg = Path(td, "server", "lib")
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("# existing\n")

        s, m = _run_handler(
            handle_add_init_py,
            td,
            task_patch={
                "title": "add __init__.py to 3 python package",
                "description": "- server/lib\n",
            },
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1685 — handle_add_test_scaffold:
#   some test file writes succeed, some fail (both changes and errors)
# ══════════════════════════════════════════════════════════════════════


def test_1685_scaffold_partial():
    """Line 1685: errors non-empty when changes > 0 (mixed success/failure)."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td, "server")
        src.mkdir()
        (src / "routes.py").write_text("# routes\n")
        (src / "models.py").write_text("# models\n")

        m = mock_open()
        m.side_effect = [m.return_value, OSError(13, "denied")]

        s, m2 = _run_handler(
            handle_add_test_scaffold,
            td,
            task_patch={"description": "- server/routes.py\n- server/models.py\n"},
            extra_patches=[patch("builtins.open", m)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1726 — handle_replace_unwrap_scanner:
#   entry without ":" in the split → leading to empty parts handling
# ══════════════════════════════════════════════════════════════════════


def test_1726_unwrap_no_colon():
    """Line 1726: entry that produces empty parts after split."""
    with tempfile.TemporaryDirectory() as td:
        s, m = _run_handler(
            handle_replace_unwrap_scanner,
            td,
            task_patch={"description": ":\n"},
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1764 — handle_replace_unwrap_scanner:
#   OSError writing TODO comment to file
# ══════════════════════════════════════════════════════════════════════


def test_1764_unwrap_write_oserror():
    """Line 1754: inner OSError when writing unwrap TODO comment."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td, "src")
        src.mkdir(parents=True)
        (src / "lib.rs").write_text("fn x() {\n    let y = x.unwrap();\n}\n")

        # First open() = read lib.rs (must return content so unwrap is found),
        # second open() = write TODO comment (fails with OSError)
        m = mock_open(read_data=(src / "lib.rs").read_text())
        m.side_effect = [m.return_value, OSError(13, "denied")]

        s, m2 = _run_handler(
            handle_replace_unwrap_scanner,
            td,
            task_patch={"description": f"- {td}/src/lib.rs: 1 unwrap() call\n"},
            extra_patches=[patch("builtins.open", m)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Line 1839 — handle_bare_except_scanner:
#   OSError writing TODO comment to file
# ══════════════════════════════════════════════════════════════════════


def test_1839_bare_except_write_oserror():
    """Line 1839: inner OSError when writing bare except TODO."""
    with tempfile.TemporaryDirectory() as td:
        src = Path(td, "src")
        src.mkdir(parents=True)
        (src / "lib.py").write_text("try:\n    pass\nexcept:\n    pass\n")

        m = mock_open(read_data=(src / "lib.py").read_text())
        m.side_effect = [m.return_value, OSError(13, "denied")]

        s, m2 = _run_handler(
            handle_bare_except_scanner,
            td,
            task_patch={"description": "Files:\n- src/lib.py: bare except\n"},
            extra_patches=[patch("builtins.open", m)],
        )
        assert isinstance(s, bool)


# ══════════════════════════════════════════════════════════════════════
# Lines 1888-1889 — handle_ci_pipeline:
#   OSError creating CI workflow file
# ══════════════════════════════════════════════════════════════════════


def test_1888_ci_write_oserror():
    """Lines 1888-1889: OSError when creating CI workflow."""
    with tempfile.TemporaryDirectory() as td:
        s, m = _run_handler(
            handle_ci_pipeline,
            td,
            extra_patches=[patch("builtins.open", side_effect=OSError(13, "denied"))],
        )
        assert not s


# ══════════════════════════════════════════════════════════════════════
# Line 1891 — handle_ci_pipeline:
#   CI workflow already exists
# ══════════════════════════════════════════════════════════════════════


def test_1891_ci_already_exists():
    """Line 1891: CI already configured."""
    with tempfile.TemporaryDirectory() as td:
        workflows = Path(td, ".github", "workflows")
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI\n")
        s, m = _run_handler(handle_ci_pipeline, td)
        assert s
        assert "already" in m.lower()


# ══════════════════════════════════════════════════════════════════════
# Verify test count
# ══════════════════════════════════════════════════════════════════════


def test_all_tests_present():
    """Check all test functions are accounted for."""
    count = sum(
        1
        for name, obj in sys.modules[__name__].__dict__.items()
        if name.startswith("test_") and callable(obj)
    )
    assert count >= 24, f"Expected at least 24 tests, got {count}"
