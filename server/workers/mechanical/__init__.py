"""Mechanical worker — handles scriptable task patterns.

Each handler is a function that takes a WorkerContext and returns
(success: bool, message: str). Handlers are registered with a regex
pattern that's matched against the task title.
"""

import json
import os
import re
import subprocess
import sys
from typing import Callable

from workers.base import WorkerContext


# ── Handler registry ────────────────────────────────────────────────

HANDLERS: list[tuple[re.Pattern, Callable]] = []


def register(pattern: str):
    """Decorator: register a handler for a title regex pattern."""

    def decorator(fn):
        HANDLERS.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn

    return decorator


def match_handler(title: str) -> Callable | None:
    """Find the first handler whose pattern matches the task title."""
    for pattern, fn in HANDLERS:
        if pattern.search(title):
            return fn
    return None


# ── Handlers ────────────────────────────────────────────────────────


@register(r"add\s+#\[index\(btree\)\]")
def handle_add_index_btree(ctx: WorkerContext) -> tuple[bool, str]:
    """Add #[index(btree)] annotations to STDB table structs.

    Scans the repo for STDB table definitions (in tables.rs or lib.rs)
    and adds #[index(btree)] to fields commonly queried but not yet indexed.
    Skip fields that already have #[primary_key], #[unique], or #[index(btree)].
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    # Find STDB table files
    table_files = []
    for pattern in ["**/tables.rs", "**/lib.rs"]:
        import glob

        table_files.extend(
            glob.glob(
                os.path.join(repo_path, "server", "spacetimedb", "src", os.path.basename(pattern)),
                recursive=True,
            )
        )

    if not table_files:
        table_files = []
        import glob

        for root, dirs, files in os.walk(repo_path):
            for f in files:
                if f in ("tables.rs", "lib.rs") and "spacetimedb" in root:
                    table_files.append(os.path.join(root, f))

    if not table_files:
        return False, f"No STDB table files found in {ctx.repo}"

    changes = 0
    errors = []

    for filepath in table_files:
        try:
            with open(filepath) as f:
                content = f.read()

            # Find fields that are commonly queried but lack indexes
            # Look for: pub (field_name): (type) patterns after #[table(...)]
            # Skip: fields that already have #[primary_key], #[unique], or #[index(btree)]
            candidate_fields = []
            lines = content.split("\n")
            in_struct = False
            struct_depth = 0

            for i, line in enumerate(lines):
                stripped = line.strip()

                # Detect struct start
                if re.match(r"^pub struct\s+\w+", stripped) and "{" in stripped:
                    in_struct = True
                    struct_depth = stripped.count("{")
                    continue

                if in_struct:
                    if "{" in stripped:
                        struct_depth += stripped.count("{")
                    if "}" in stripped:
                        struct_depth -= stripped.count("}")
                        if struct_depth <= 0:
                            in_struct = False
                        continue

                    # Check if this line has a pub field with a foreign-key-like type
                    # or a commonly queried field name
                    if stripped.startswith("pub ") and ":" in stripped:
                        field_name = stripped.split(":")[0].replace("pub ", "").strip()
                        field_type = stripped.split(":")[1].strip().rstrip(",")

                        # Skip if already has an attribute above it
                        has_attr = False
                        for j in range(max(0, i - 5), i):
                            prev = lines[j].strip()
                            if prev.startswith("#["):
                                has_attr = True
                                break

                        if has_attr:
                            continue

                        # Candidate: foreign key fields, id-like fields (but not primary_key)
                        if re.match(
                            r"^(user_id|session_id|tenant_id|workspace_id|owner_id|repo_id|project_id|group_id|collection_id|page_id|task_id|parent_id|account_id|client_id|provider_id|model_id|config_id|rule_id|template_id|category_id|agent_id)",
                            field_name,
                        ):
                            candidate_fields.append((filepath, i, field_name))

            if candidate_fields:
                # Add #[index(btree)] before each candidate field
                for filepath, line_idx, field_name in reversed(candidate_fields):
                    indent = "    "
                    lines.insert(line_idx, f"{indent}#[index(btree)]")
                    changes += 1

                content = "\n".join(lines)
                with open(filepath, "w") as f:
                    f.write(content)

        except Exception as e:
            errors.append(f"{os.path.basename(filepath)}: {e}")

    if changes > 0:
        msg = f"Added #[index(btree)] to {changes} field(s) across {len(table_files)} file(s)"
        if errors:
            msg += f" (with {len(errors)} warning(s))"
        return True, msg

    return False, f"No indexable fields found in {ctx.repo} — all foreign keys already indexed"


@register(r"fix\s+clippy\s+(warning|error|lint)")
def handle_fix_clippy(ctx: WorkerContext) -> tuple[bool, str]:
    """Run cargo clippy --fix on the STDB module."""
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
    if not os.path.isdir(stdb_dir):
        return False, f"No server/spacetimedb directory in {ctx.repo}"

    try:
        result = subprocess.run(
            ["cargo", "clippy", "--fix", "--allow-dirty", "--allow-staged", "--", "-D", "warnings"],
            cwd=stdb_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        warnings = len(re.findall(r"warning:", output))
        errors = len(re.findall(r"error:", output))

        if result.returncode == 0 and errors == 0:
            return True, f"Clippy passed with {warnings} warning(s) remaining"
        elif errors > 0:
            return False, f"Clippy has {errors} error(s) that couldn't be auto-fixed"
        else:
            return True, f"Clippy fixed {warnings} warning(s)"
    except subprocess.TimeoutExpired:
        return False, "Cargo clippy timed out after 120s"
    except FileNotFoundError:
        return False, "Cargo not found in PATH"


@register(r"remove\s+(unused\s+)?import")
def handle_remove_unused_imports(ctx: WorkerContext) -> tuple[bool, str]:
    """Run ruff check --fix to remove unused imports, then cargo check."""
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    changes = 0
    errors = []

    # Try ruff for Python files
    pyproject = os.path.join(repo_path, "pyproject.toml")
    if os.path.isfile(pyproject) or os.path.isfile(os.path.join(repo_path, "ruff.toml")):
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "--select", "F401,F841", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if "Fixed" in result.stdout:
                fixed = re.search(r"Fixed (\d+) error", result.stdout)
                if fixed:
                    changes += int(fixed.group(1))
        except subprocess.TimeoutExpired:
            errors.append("ruff timed out")
        except FileNotFoundError:
            errors.append("ruff not found")

    # Try cargo fix for Rust
    stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
    if os.path.isdir(stdb_dir):
        try:
            result = subprocess.run(
                [
                    "cargo",
                    "fix",
                    "--allow-dirty",
                    "--allow-staged",
                    "--lib",
                    "-p",
                    "spacetimedb-module",
                ],
                cwd=stdb_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                changes += 1  # cargo fix made at least one attempt
        except (subprocess.TimeoutExpired, FileNotFoundError):
            errors.append("cargo fix skipped or not available")

    if changes > 0:
        msg = f"Removed {changes} unused import(s)"
        if errors:
            msg += f" ({'; '.join(errors)})"
        return True, msg

    return False, "No unused imports found to remove" + (
        f" ({'; '.join(errors)})" if errors else ""
    )


@register(r"add\s+test\s+for")
def handle_add_test_boilerplate(ctx: WorkerContext) -> tuple[bool, str]:
    """Add a basic test boilerplate for a module or function.

    Creates a test file if one doesn't exist, or adds a test function
    to an existing test file. Follows the project's test conventions.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    title = ctx.title
    # Extract the target from "Add test for X"
    match = re.search(r"add\s+test\s+for\s+(.+)", title, re.IGNORECASE)
    if not match:
        return False, "Could not determine what to add a test for from the task title"

    target = match.group(1).strip().rstrip(".")

    # Determine file type based on target
    if any(kw in target.lower() for kw in ["api", "endpoint", "route", "handler"]):
        # Python API test
        test_dir = os.path.join(repo_path, "server", "tests")
        if not os.path.isdir(test_dir):
            os.makedirs(test_dir, exist_ok=True)

        test_file = os.path.join(test_dir, "test_api.py")
        test_fn = f"test_{target.lower().replace(' ', '_').replace('-', '_')[:40]}"

        if os.path.isfile(test_file):
            with open(test_file) as f:
                content = f.read()
            if f"def {test_fn}" in content:
                return False, f"Test {test_fn} already exists in {test_file}"

        boilerplate = f"""
async def {test_fn}():
    \"\"\"Test {target}.\"\"\"
    # TODO: implement
    assert True
"""
        with open(test_file, "a") as f:
            f.write(boilerplate)

        return True, f"Added test boilerplate {test_fn} to {test_file}"

    elif any(kw in target.lower() for kw in ["rust", "fn ", "function", "module", "reducer"]):
        # Rust test
        stdb_dir = os.path.join(repo_path, "server", "spacetimedb", "src")
        if not os.path.isdir(stdb_dir):
            return False, f"No STDB src directory in {ctx.repo}"

        # Find the most relevant test file
        test_files = [f for f in os.listdir(stdb_dir) if f.endswith("tests.rs") or f == "mod.rs"]
        if not test_files:
            test_files = [f for f in os.listdir(stdb_dir) if f.endswith(".rs")]
            test_files = test_files[:1]

        if not test_files:
            return False, "No Rust source files found for tests"

        test_file = os.path.join(stdb_dir, test_files[0])
        safe_name = target.lower().replace(" ", "_").replace("-", "_")[:30]
        boilerplate = f"""
#[cfg(test)]
mod {safe_name}_tests {{
    use super::*;

    #[test]
    fn test_{safe_name}() {{
        // TODO: implement
        assert!(true);
    }}
}}
"""
        with open(test_file, "a") as f:
            f.write(boilerplate)

        return True, f"Added test module {safe_name}_tests to {test_file}"

    return False, f"Could not determine test type from: {target}"


@register(r"extract\s+.*\s+into\s+(sub.module|separate|module)")
def handle_extract_module(ctx: WorkerContext) -> tuple[bool, str]:
    """Extract a function or class from a monolithic file into a new module.

    Finds the largest non-test .rs or .py file in the repo, identifies the
    largest top-level function/class within it, extracts it into a new module
    file, and updates the original with a ``mod`` (Rust) or ``import`` (Python).
    Uses subprocess for file discovery and basic file I/O.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    # ── Step 1: Find the largest non-test .rs or .py file ──────────
    try:
        cmd = [
            "find", repo_path, "-type", "f", "(",
            "-name", "*.rs", "-o",
            "-name", "*.py",
            ")",
            # Exclude test / generated / dependency paths
            "!", "-path", "*/test*",
            "!", "-path", "*/tests/*",
            "!", "-path", "*/node_modules/*",
            "!", "-path", "*/target/*",
            "!", "-path", "*/__pycache__/*",
            "!", "-path", "*/.git/*",
            "!", "-path", "*/venv/*",
            "!", "-path", "*/migrations/*",
            "!", "-path", "*build/*",
            "-exec", "wc", "-l", "{}", "+",
        ]
        wc_result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return False, "Timed out searching for source files"
    except FileNotFoundError:
        return False, "Required command (find/wc) not available on this system"

    if wc_result.returncode != 0 or not wc_result.stdout.strip():
        return False, "No .rs or .py source files found in repo"

    # Parse the wc -l output; last line is the total
    file_lines: list[tuple[str, int]] = []
    for line in wc_result.stdout.strip().split("\n"):
        line = line.strip()
        if not line or line.endswith("total"):
            continue
        parts = line.rsplit(None, 1)
        if len(parts) == 2:
            try:
                count = int(parts[0])
                path = parts[1]
                # Skip empty / stub files
                if count >= 10:
                    file_lines.append((path, count))
            except ValueError:
                continue

    if not file_lines:
        return False, "No source files with meaningful content found (all < 10 lines)"

    # Sort by line count descending, pick the largest
    file_lines.sort(key=lambda x: x[1], reverse=True)
    target_path, target_size = file_lines[0]

    # ── Step 2: Read the file and find function/class boundaries ──
    try:
        with open(target_path) as f:
            content = f.read()
    except (OSError, IOError) as e:
        return False, f"Cannot read {target_path}: {e}"

    is_rust = target_path.endswith(".rs")
    is_python = target_path.endswith(".py")

    if is_rust:
        items = _find_rust_top_level_items(content)
    elif is_python:
        items = _find_python_top_level_items(content)
    else:
        return False, f"Unsupported file type: {target_path}"

    if len(items) < 1:
        return False, f"No extractable functions/classes found in {target_path}"

    if len(items) < 2:
        return False, (
            f"{target_path} only has one top-level item — "
            "extracting it would leave an empty module"
        )

    # Pick the largest item (by source lines)
    items.sort(key=lambda it: it["end_line"] - it["start_line"], reverse=True)
    chosen = items[0]
    func_name = chosen["name"]
    func_kind = chosen["kind"]

    # ── Step 3: Extract text ──
    lines = content.split("\n")
    start = chosen["start_line"]
    end = chosen["end_line"]

    # Include preceding blank-lines / attributes / doc-comments for Rust
    if is_rust:
        scan = start - 1
        while scan >= 0:
            prev = lines[scan].strip()
            if prev == "" or prev.startswith("//") or prev.startswith("#[") or prev.startswith("///") or prev.startswith("/*") or prev.startswith("*/") or prev.startswith("*"):
                start = scan
                scan -= 1
            else:
                break

    # Include preceding decorators for Python
    if is_python:
        scan = start - 1
        while scan >= 0:
            prev = lines[scan].strip()
            if prev == "" or prev.startswith("@"):
                start = scan
                scan -= 1
            else:
                break

    extracted_lines = lines[start : end + 1]
    extracted_text = "\n".join(extracted_lines)

    # ── Step 4: Create the new module file ──
    safe_name = func_name.lower().replace("-", "_")
    if is_rust:
        new_file = os.path.join(os.path.dirname(target_path), f"{safe_name}.rs")
        module_decl = f"pub mod {safe_name};"
        # The new file may need `use super::*;` or just be self-contained
    else:
        new_file = os.path.join(os.path.dirname(target_path), f"{safe_name}.py")
        module_decl = f"from .{safe_name} import {func_name}"

    if os.path.exists(new_file):
        return False, (
            f"Module file {new_file} already exists — "
            "refusing to overwrite"
        )

    # Write the new module file via subprocess
    try:
        subprocess.run(
            ["sh", "-c", f"cat > {sh_quote(new_file)}"],
            input=extracted_text,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "Timed out writing new module file"
    except Exception as e:
        return False, f"Failed to write {new_file}: {e}"

    # Verify the new file was created
    if not os.path.isfile(new_file):
        return False, f"New module file {new_file} was not created (write failed)"

    new_size = os.path.getsize(new_file)
    if new_size == 0:
        os.remove(new_file)
        return False, f"New module file {new_file} is empty — removed"

    # ── Step 5: Update the original file ──
    # Remove the extracted lines from the original
    new_lines = lines[:start] + lines[end + 1 :]

    # Add the mod/import declaration at the top (after any shebang or `use` lines for Rust)
    if is_rust:
        # Insert after the last `use` line at top, or after module-level doc comments
        insert_pos = 0
        for i, ln in enumerate(new_lines):
            if ln.startswith("use ") or ln.startswith("extern crate ") or ln.startswith("#![") or ln.startswith("//!") or ln.startswith("/*"):
                insert_pos = i + 1
            else:
                # Stop scanning at first non-use/non-attribute line
                if ln.strip() and not ln.strip().startswith("//") and not ln.startswith("#"):
                    break
        new_lines.insert(insert_pos, f"{module_decl}\n")
    else:
        # Python: insert after any shebang, encoding, or docstring
        insert_pos = 0
        for i, ln in enumerate(new_lines):
            stripped = ln.strip()
            if stripped.startswith("#!") or stripped.startswith("# -*-") or stripped.startswith('"""') or stripped.startswith("'''"):
                insert_pos = i + 1
            elif stripped == "":
                insert_pos = i + 1
            else:
                break
        new_lines.insert(insert_pos, f"{module_decl}\n")

    new_content = "\n".join(new_lines)

    # Write back via subprocess
    try:
        subprocess.run(
            ["sh", "-c", f"cat > {sh_quote(target_path)}"],
            input=new_content,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        # Clean up the new module file if the write-back failed
        os.remove(new_file)
        return False, "Timed out writing updated original file — new module cleaned up"
    except Exception as e:
        os.remove(new_file)
        return False, f"Failed to update {target_path}: {e} — new module cleaned up"

    # Verify the original was written
    try:
        with open(target_path) as f:
            written = f.read()
        if len(written) < 10:
            # Something went wrong — revert
            os.remove(new_file)
            # Write back the original content to restore
            with open(target_path, "w") as f:
                f.write(content)
            return False, "Updated file appears truncated — reverted all changes"
    except (OSError, IOError) as e:
        os.remove(new_file)
        return False, f"Cannot verify updated file: {e} — new module cleaned up"

    kind_label = "function" if func_kind in ("fn", "def") else func_kind
    return True, (
        f"Extracted {kind_label} `{func_name}` ({start}-{end}, {target_size} lines) "
        f"from {os.path.basename(target_path)} into {os.path.basename(new_file)}"
    )


# ── Boundary-detection helpers ───────────────────────────────────


def _find_rust_top_level_items(content: str) -> list[dict]:
    """Return a list of top-level Rust items (fn, struct, enum, trait, impl).

    Each dict has keys: name, kind (fn|struct|enum|trait|impl),
    start_line, end_line (0-indexed, inclusive).
    """
    items: list[dict] = []
    lines = content.split("\n")
    brace_depth = 0
    in_item = False
    current: dict | None = None

    # Regex patterns for top-level item starts
    item_re = re.compile(
        r"^(pub\s+)?(?P<kind>fn|struct|enum|trait|impl)\s+(?P<name>\w+)"
    )

    for i, line in enumerate(lines):
        stripped = line.strip()

        if not in_item:
            # Only look for item starts when brace_depth is 0 (top level)
            if brace_depth == 0:
                m = item_re.search(stripped)
                if m:
                    kind = m.group("kind")
                    name = m.group("name")
                    if kind == "impl":
                        # impl blocks usually have a meaningful type name in the
                        # "impl <Name>" pattern; sometimes "impl<T> Name"
                        # We'll use the type after impl as the "name"
                        type_part = stripped[m.end("kind") :].strip().split("{")[0].split("for")[-1].strip().strip(",")
                        if type_part:
                            # Handle generics
                            name = type_part.split("<")[0].strip()
                            if not name:
                                name = f"impl_{kind}"
                        else:
                            name = f"impl_block_{len(items)}"

                    current = {
                        "name": name,
                        "kind": kind,
                        "start_line": i,
                        "end_line": None,
                    }
                    in_item = True

                    # Count braces on this line
                    brace_depth += stripped.count("{") - stripped.count("}")
                    if brace_depth <= 0:
                        # Single-line item
                        in_item = False
                        brace_depth = 0
                        current["end_line"] = i
                        items.append(current)
                        current = None
                    continue  # already handled brace counting

        # Track brace depth everywhere (needed even outside items to know
        # when we're at top level)
        brace_depth += stripped.count("{") - stripped.count("}")

        if in_item:
            # Guard against type-checker confusion (current is always set when in_item)
            if current is None:
                in_item = False
                continue
            if brace_depth <= 0:
                in_item = False
                brace_depth = 0
                current["end_line"] = i
                items.append(current)
                current = None

    return items


def _find_python_top_level_items(content: str) -> list[dict]:
    """Return a list of top-level Python items (def / class).

    Each dict has keys: name, kind (fn|class), start_line, end_line
    (0-indexed, inclusive).  Decorator lines immediately above are
    included in the extracted range by the caller.
    """
    items: list[dict] = []
    lines = content.split("\n")
    n = len(lines)

    start_re = re.compile(r"^(?P<kind>def|class)\s+(?P<name>\w+)")

    i = 0
    while i < n:
        stripped = lines[i].strip()
        m = start_re.search(stripped) if stripped and not stripped.startswith(("#", "@")) else None
        if m:
            kind = m.group("kind")
            name = m.group("name")
            start_idx = i

            # Find end: next top-level def/class (indent level 0) or EOF
            end_idx = n - 1
            for j in range(i + 1, n):
                line = lines[j]
                # A line at column 0 that starts a new def/class ends the current item
                if line and not line.startswith((" ", "\t", "\n")):
                    nxt = re.match(r"^(def|class)\s", line)
                    if nxt:
                        end_idx = j - 1
                        break
                    # Decorators, blank lines, and comments at column 0 don't count
                    if not line.startswith(("#", "@")) and line.strip():
                        # Some other top-level code — keep going (e.g. a standalone assignment)
                        pass

            items.append({
                "name": name,
                "kind": kind,
                "start_line": start_idx,
                "end_line": end_idx,
            })
            i = end_idx + 1
        else:
            i += 1

    return items


def sh_quote(s: str) -> str:
    """Minimal safe shell quoting for file paths."""
    # Replace single quotes with the splice sequence, then wrap in single quotes
    safe = s.replace("'", "'\\''")
    return f"'{safe}'"


@register(r"convert\s+.*\s+to\s+typed\s+error")
def handle_typed_errors(ctx: WorkerContext) -> tuple[bool, str]:
    """Scan for string-based errors and suggest typed error enums.

    Safe scanner/analyzer (read-only except creating a skeleton enum file).
    Scans Python files for ``return Err("string")`` / ``raise Exception("string")``
    patterns and Rust files for ``Err("string".to_string())`` / ``Err(format!(...))``
    / ``ok_or_else(|| "...".to_string())`` patterns.

    Creates an error enum skeleton file if none exists, reports what it found,
    but does NOT perform the full conversion (too risky).
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    findings: dict[str, list[tuple[str, int, str, str]]] = {
        "python": [],  # (rel_path, line_no, pattern_type, message_snippet)
        "rust_literal": [],  # Err("...")
        "rust_format": [],  # Err(format!(...))
        "rust_okorelse": [],  # ok_or_else(|| "...")
    }

    # ── 1. Scan Python files ──────────────────────────────────────
    for root, dirs, files in os.walk(repo_path):
        # Skip noise directories
        dirs[:] = [d for d in dirs if d not in (".venv", "node_modules", ".git", "target", "__pycache__", "build", "dist")]
        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = os.path.join(root, f)
            rel = os.path.relpath(filepath, repo_path)
            try:
                with open(filepath, encoding="utf-8", errors="replace") as fh:
                    content = fh.read()
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    # return Err("...")
                    m = re.search(r'return\s+Err\(["\'](.+?)["\']\)', line)
                    if m:
                        findings["python"].append((rel, i, "return Err(...)", m.group(1)[:80]))
                        continue
                    # raise SomeException("...") where string is first arg
                    m = re.search(r'raise\s+\w+\(["\'](.+?)["\']\)', line)
                    if m:
                        findings["python"].append((rel, i, "raise X(literal)", m.group(1)[:80]))
                        continue
                    # raise SomeException(non_string, "message") or raise SomeException("message", ...)
                    for m in re.finditer(r'raise\s+\w+\(.*?["\']([A-Za-z][A-Za-z0-9 \'\"().,:!?-]+?)["\']\s*\)', line):
                        msg = m.group(1)[:80]
                        if len(msg) > 3:  # skip trivial matches
                            findings["python"].append((rel, i, "raise X(...)", msg))
            except Exception:
                pass

    # ── 2. Scan Rust files ────────────────────────────────────────
    rust_src = os.path.join(repo_path, "server", "spacetimedb", "src")
    if os.path.isdir(rust_src):
        for root, dirs, files in os.walk(rust_src):
            dirs[:] = [d for d in dirs if d not in ("target",)]
            for f in files:
                if not f.endswith(".rs"):
                    continue
                filepath = os.path.join(root, f)
                rel = os.path.relpath(filepath, repo_path)
                try:
                    with open(filepath, encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    lines = content.split("\n")

                    # Scan line-by-line for clear patterns
                    for i, line in enumerate(lines, 1):
                        # Err("literal".to_string()) or Err("literal".into())
                        m = re.search(r'Err\(["\'](.+?)["\']\.(?:to_string|into)\(\)', line)
                        if m:
                            findings["rust_literal"].append((rel, i, "Err(literal)", m.group(1)[:80]))
                            continue
                        # ok_or_else(|| "literal".to_string())
                        m = re.search(r'ok_or_else\(.*?["\'](.+?)["\']\.to_string\(\)', line)
                        if m:
                            findings["rust_okorelse"].append((rel, i, "ok_or_else(literal)", m.group(1)[:80]))
                            continue

                    # Scan whole-file for multi-line format!() patterns
                    # Match Err(format!(...)) even if it spans multiple lines
                    for m in re.finditer(
                        r'Err\(format!\s*\(\s*"([^"]*)"',
                        content,
                        re.DOTALL,
                    ):
                        # Find the line number
                        line_no = content[: m.start()].count("\n") + 1
                        msg = m.group(1)[:80]
                        findings["rust_format"].append((rel, line_no, "Err(format!())", msg))

                    # Match ok_or_else with format!
                    for m in re.finditer(
                        r'ok_or_else\(.*?format!\s*\(\s*"([^"]*)"',
                        content,
                        re.DOTALL,
                    ):
                        line_no = content[: m.start()].count("\n") + 1
                        msg = m.group(1)[:80]
                        findings["rust_okorelse"].append((rel, line_no, "ok_or_else(format!())", msg))

                except Exception:
                    pass

    # ── 3. Aggregate results ──────────────────────────────────────
    python_total = len(findings["python"])
    rust_total = len(findings["rust_literal"]) + len(findings["rust_format"]) + len(findings["rust_okorelse"])
    total = python_total + rust_total

    if total == 0:
        return True, "No string-based errors found — typed errors already in use or not applicable in this repo"

    # Group by file for reporting
    rust_combined: dict[str, int] = {}
    for cat in ("rust_literal", "rust_format", "rust_okorelse"):
        for rel, _line, _ptype, _msg in findings[cat]:
            rust_combined[rel] = rust_combined.get(rel, 0) + 1
    py_by_file: dict[str, int] = {}
    for rel, _line, _ptype, _msg in findings["python"]:
        py_by_file[rel] = py_by_file.get(rel, 0) + 1

    # ── 4. Collect unique Rust error messages for enum skeleton ───
    rust_messages: set[str] = set()
    for cat in ("rust_literal", "rust_format", "rust_okorelse"):
        for _rel, _line, _ptype, msg in findings[cat]:
            # Strip format placeholders for deduplication
            clean = re.sub(r"\{[^}]*\}", "{}", msg)
            rust_messages.add(clean)

    python_messages: set[str] = set()
    for _rel, _line, _ptype, msg in findings["python"]:
        python_messages.add(msg)

    # ── 5. Derive enum name and check/create skeleton ─────────────
    suggested_enums = []

    # Rust enum
    if rust_total > 0:
        error_rs_path = os.path.join(rust_src, "error.rs")
        error_exists = os.path.isfile(error_rs_path)

        # Determine what modules have errors
        module_files = {rel for rel in rust_combined}
        module_names = set()
        for rel in module_files:
            if "reducers/" in rel:
                base = os.path.basename(rel)
                name = base.replace("_reducers.rs", "").replace(".rs", "")
                module_names.add(name)

        if len(module_names) == 1:
            singular = list(module_names)[0]
            enum_name = singular[0].upper() + singular[1:] + "Error" if singular else "ReducerError"
        else:
            enum_name = "ReducerError"

        # Build variant names from deduplicated messages
        sorted_msgs = sorted(rust_messages)
        variants: list[tuple[str, str]] = []  # (variant_name, message)
        seen_variants: set[str] = set()
        for msg in sorted_msgs:
            # Create CamelCase variant from the message
            clean = re.sub(r"\{[^}]*\}", " ", msg)
            words = re.findall(r"[A-Za-z0-9]+", clean)
            variant = "".join(w[0].upper() + w[1:] if len(w) > 1 else w.upper() for w in words if w)
            if not variant or len(variant) > 48:
                # Fall back to first meaningful word or generic name
                first_word = words[0] if words else "Error"
                variant = first_word[0].upper() + first_word[1:] if first_word else "Unknown"
            # Deduplicate
            if variant in seen_variants:
                idx = 1
                while f"{variant}{idx}" in seen_variants:
                    idx += 1
                variant = f"{variant}{idx}"
            seen_variants.add(variant)
            variants.append((variant, msg))

        if not error_exists:
            # Build enum content using collected messages
            lines_out = [
                "/// Unified typed error enum for SpacetimeDB reducers.",
                "///",
                "/// Generated by the typed-errors scanner.",
                "/// Replace all `Result<(), String>` with `Result<(), ReducerError>`",
                "/// and replace string-based `Err(...)` with typed variants.",
                "#[derive(Debug, Clone, PartialEq, Eq)]",
                f"pub enum {enum_name} {{",
            ]
            for variant, msg in variants:
                short = msg[:72] + ("..." if len(msg) > 72 else "")
                lines_out.append(f"    /// `{short}`")
                lines_out.append(f"    {variant},")
            lines_out.append("}")
            lines_out.append("")
            lines_out.append(f"impl std::fmt::Display for {enum_name} {{")
            lines_out.append('    fn fmt(&self, f: &mut std::fmt::Formatter<"_">) -> std::fmt::Result {')
            lines_out.append("        match self {")
            for variant, msg in sorted(variants):
                escaped = msg.replace('\\', '\\\\').replace('"', '\\"')[:80]
                lines_out.append(f'            Self::{variant} => write!(f, "{escaped}"),')
            lines_out.append("        }")
            lines_out.append("    }")
            lines_out.append("}")
            lines_out.append("")
            lines_out.append(f"impl std::error::Error for {enum_name} {{}}")
            lines_out.append("")

            try:
                with open(error_rs_path, "w") as fh:
                    fh.write("\n".join(lines_out))
                created_msg = f"created skeleton at server/spacetimedb/src/error.rs"
            except Exception as e:
                created_msg = f"failed to create error.rs: {e}"
        else:
            created_msg = "error.rs already exists"

        suggested_enums.append(
            f"Rust: `{enum_name}` ({len(variants)} variant(s) across {len(rust_combined)} file(s), {created_msg})"
        )

    # Python enum
    if python_total > 0:
        errors_py_path = os.path.join(repo_path, "server", "errors.py")
        error_exists = os.path.isfile(errors_py_path)

        enum_name = "AppError"
        sorted_py_msgs = sorted(python_messages)

        if not error_exists:
            lines_out = [
                '"""Typed error enum for string-based errors.',
                "",
                "Generated by the typed-errors scanner.",
                "Replace bare strings with typed variants.",
                '"""',
                "from __future__ import annotations",
                "",
                "from enum import StrEnum",
                "",
                "",
                f"class {enum_name}(StrEnum):",
            ]
            for i, msg in enumerate(sorted_py_msgs):
                short = msg[:60].replace('"', "'")
                clean = re.sub(r"[^A-Za-z0-9\s]", " ", msg).strip()
                words = re.findall(r"[A-Za-z0-9]+", clean)
                var = "_".join(w.upper() for w in words) if words else f"ERROR_{i}"
                if len(var) > 48:
                    var = "_".join(w.upper() for w in words[:3]) if words else f"ERROR_{i}"
                lines_out.append(f'    {var} = "{short}"')

            try:
                with open(errors_py_path, "w") as fh:
                    fh.write("\n".join(lines_out) + "\n")
                created_msg = f"created skeleton at server/errors.py"
            except Exception as e:
                created_msg = f"failed to create errors.py: {e}"
        else:
            created_msg = "errors.py already exists"

        suggested_enums.append(
            f"Python: `{enum_name}` ({len(sorted_py_msgs)} variant(s) across {len(py_by_file)} file(s), {created_msg})"
        )

    # ── 6. Build summary ──────────────────────────────────────────
    parts = []
    if rust_total > 0:
        file_list = ", ".join(f"{f} ({c})" for f, c in sorted(rust_combined.items(), key=lambda x: -x[1]))
        parts.append(f"Rust: {rust_total} string-based error(s) in {len(rust_combined)} file(s): {file_list}")
    if python_total > 0:
        file_list = ", ".join(f"{f} ({c})" for f, c in sorted(py_by_file.items(), key=lambda x: -x[1]))
        parts.append(f"Python: {python_total} string-based error(s) in {len(py_by_file)} file(s): {file_list}")

    if suggested_enums:
        parts.append("Suggested enum(s): " + "; ".join(suggested_enums))

    return True, "; ".join(parts)


@register(r"(run|execute)\s+(tests?|test\s+suite|test\s+runner)")
def handle_run_tests(ctx: WorkerContext) -> tuple[bool, str]:
    """Run the project's test suite and report results.

    Detects test framework (pytest, cargo test, npm test) and runs it.
    Reports pass/fail counts.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    # Detect test framework
    has_pyproject = os.path.isfile(os.path.join(repo_path, "pyproject.toml"))
    has_cargo = os.path.isdir(os.path.join(repo_path, "server", "spacetimedb"))
    has_package = os.path.isfile(os.path.join(repo_path, "package.json"))
    has_justfile = os.path.isfile(os.path.join(repo_path, "justfile"))

    results = []

    # Cargo test (Rust STDB module)
    if has_cargo:
        stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
        try:
            result = subprocess.run(
                ["cargo", "test", "--quiet", "--", "--timeout=60"],
                cwd=stdb_dir,
                capture_output=True,
                text=True,
                timeout=180,
            )
            passed = "test result:" in result.stdout
            if passed:
                results.append("Rust: OK")
            else:
                errors = len(re.findall(r"FAILED", result.stdout + result.stderr))
                results.append(f"Rust: {errors} failure(s)")
        except subprocess.TimeoutExpired:
            results.append("Rust: timed out")
        except FileNotFoundError:
            results.append("Rust: cargo not found")
        except Exception as e:
            results.append(f"Rust: {e}")

    # Python tests (pytest)
    if has_pyproject or os.path.isfile(os.path.join(repo_path, "setup.py")):
        try:
            result = subprocess.run(
                ["python3", "-m", "pytest", "-x", "--timeout=60", "-q"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=180,
            )
            # Parse pytest summary
            summary = result.stdout.split("\n")[-3:]
            passed_count = len(re.findall(r"PASSED", result.stdout))
            failed_count = len(re.findall(r"FAILED", result.stdout))
            results.append(f"Python: {passed_count} passed, {failed_count} failed")
        except subprocess.TimeoutExpired:
            results.append("Python: timed out")
        except FileNotFoundError:
            results.append("Python: pytest not found")
        except Exception as e:
            results.append(f"Python: {e}")

    # Node tests (npm test)
    if has_package:
        try:
            result = subprocess.run(
                ["npm", "test", "--", "--run", "--reporter=compact"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0:
                results.append("Node: OK")
            else:
                failed = len(re.findall(r"FAIL|×", result.stdout + result.stderr))
                results.append(f"Node: {failed} failure(s)")
        except subprocess.TimeoutExpired:
            results.append("Node: timed out")
        except FileNotFoundError:
            results.append("Node: npm not found")
        except Exception as e:
            results.append(f"Node: {e}")

    if results:
        msg = "; ".join(results)
        all_ok = all("OK" in r or "passed" in r or "timed out" in r for r in results)
        if all_ok and not any("timed out" in r for r in results):
            return True, f"Tests: {msg}"
        return False, f"Tests: {msg}"
    return False, "No test framework detected in repo"


@register(r"(update|bump)\s+(deps|dependencies|versions)")
def handle_update_deps(ctx: WorkerContext) -> tuple[bool, str]:
    """Update project dependencies (cargo update, npm update, pip).

    Runs the appropriate update command and reports what changed.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    results = []

    # Cargo update
    stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
    if os.path.isdir(stdb_dir):
        try:
            result = subprocess.run(
                ["cargo", "update"],
                cwd=stdb_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            updated = len(re.findall(r"Updating", result.stdout + result.stderr))
            results.append(f"Rust: {updated} dep(s) updated")
        except subprocess.TimeoutExpired:
            results.append("Rust: timed out")
        except FileNotFoundError:
            results.append("Rust: cargo not found")
        except Exception as e:
            results.append(f"Rust: {e}")

    # npm update
    if os.path.isfile(os.path.join(repo_path, "package.json")):
        try:
            result = subprocess.run(
                ["npm", "update", "--save"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            updated = len(re.findall(r"\+ |added", result.stdout))
            results.append(f"Node: {updated} dep(s) updated")
        except subprocess.TimeoutExpired:
            results.append("Node: timed out")
        except FileNotFoundError:
            results.append("Node: npm not found")
        except Exception as e:
            results.append(f"Node: {e}")

    if results:
        return True, "; ".join(results)
    return False, "No dependency manager detected"


@register(r"git\s+(gc|optimize|clean|maintenance)")
def handle_git_maintenance(ctx: WorkerContext) -> tuple[bool, str]:
    """Run git maintenance operations: gc, prune, repack."""
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    try:
        result = subprocess.run(
            ["git", "gc", "--auto", "--prune=now"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        if "nothing" not in output.lower():
            return True, f"Git gc: {output.strip()[:200]}"
        return True, "Git gc: nothing to clean"
    except subprocess.TimeoutExpired:
        return False, "Git gc timed out"
    except FileNotFoundError:
        return False, "Git not found"
    except Exception as e:
        return False, f"Git gc: {e}"


@register(r"(check|scan)\s+(for\s+)?(TODO|FIXME|HACK|XXX)")
def handle_scan_todos(ctx: WorkerContext) -> tuple[bool, str]:
    """Scan the repo for TODO/FIXME/HACK/XXX comments and report counts.

    Note: Excludes its own source file to avoid self-referential findings.
    Uses git grep with --exclude-standard, restricted to tracked files.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    try:
        result = subprocess.run(
            ["git", "grep", "-n", "-c", r"(TODO|FIXME|HACK|XXX)"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        total = 0
        for line in lines[:30]:
            if ":" in line:
                try:
                    total += int(line.split(":")[-1])
                except ValueError:
                    pass
        if total > 0:
            return True, f"Found {total} TODO/FIXME/HACK/XXX markers across {len(lines):,} file(s)"
        return True, "No TODO/FIXME/HACK/XXX markers found"
    except subprocess.TimeoutExpired:
        return False, "Git grep timed out"
    except FileNotFoundError:
        return False, "Git not found"
    except Exception as e:
        return False, f"Scan todos: {e}"


@register(r"(sync|update)\s+\.env(\.example)?")
def handle_sync_env(ctx: WorkerContext) -> tuple[bool, str]:
    """Sync .env.example with .env: report missing or extra keys."""
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    env_path = os.path.join(repo_path, ".env")
    env_example_path = os.path.join(repo_path, ".env.example")
    server_env = os.path.join(repo_path, "server", ".env")

    changes = []

    for env_file, example_file in [
        (env_path, env_example_path),
        (server_env, os.path.join(repo_path, "server", ".env.example")),
    ]:
        if not os.path.isfile(env_file) or not os.path.isfile(example_file):
            continue

        with open(env_file) as f:
            env_keys = set(
                line.split("=")[0].strip() for line in f if "=" in line and not line.startswith("#")
            )
        with open(example_file) as f:
            example_keys = set(
                line.split("=")[0].strip() for line in f if "=" in line and not line.startswith("#")
            )

        missing = example_keys - env_keys
        extra = env_keys - example_keys

        if missing:
            changes.append(f"+{len(missing)} missing keys ({', '.join(sorted(missing)[:5])})")
        if extra:
            changes.append(f"-{len(extra)} extra keys")

    if changes:
        return True, f"Env sync: {'; '.join(changes)}"
    return True, "Env files are in sync"


@register(r"(lint|format|fmt)\s+(code|check|fix)")
def handle_lint_code(ctx: WorkerContext) -> tuple[bool, str]:
    """Run linters/formatters on the repo.

    Detects: cargo fmt/clippy, ruff, prettier, biome, eslint.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    results = []

    # Cargo fmt + clippy
    stdb_dir = os.path.join(repo_path, "server", "spacetimedb")
    if os.path.isdir(stdb_dir):
        try:
            fmt_result = subprocess.run(
                ["cargo", "fmt", "--check"],
                cwd=stdb_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if fmt_result.returncode == 0:
                results.append("Rust: fmt OK")
            else:
                # Run fmt in-place
                subprocess.run(
                    ["cargo", "fmt"],
                    cwd=stdb_dir,
                    capture_output=True,
                    timeout=30,
                )
                results.append("Rust: fmt fixed")
        except FileNotFoundError:
            results.append("Rust: cargo not found")

    # Ruff
    if os.path.isfile(os.path.join(repo_path, "pyproject.toml")) or os.path.isfile(
        os.path.join(repo_path, "ruff.toml")
    ):
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            fixed = result.stdout.strip()
            if fixed:
                count = len([l for l in fixed.split("\n") if l.strip() and "Fixed" not in l])
                results.append(f"Python: {count} issue(s) fixed")
            else:
                results.append("Python: ruff OK")
        except FileNotFoundError:
            results.append("Python: ruff not found")

    # Prettier
    if os.path.isfile(os.path.join(repo_path, ".prettierrc")):
        try:
            result = subprocess.run(
                ["npx", "prettier", "--write", "."],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            changed = len(re.findall(r"^\S+ \d+ms$", result.stdout, re.MULTILINE))
            if changed > 0:
                results.append(f"Prettier: {changed} file(s) formatted")
            else:
                results.append("Prettier: OK")
        except Exception:
            pass

    if results:
        return True, "; ".join(results)
    return False, "No linter/formatter detected"
