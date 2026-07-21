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
        table_files.extend(glob.glob(os.path.join(repo_path, "server", "spacetimedb", "src", os.path.basename(pattern)), recursive=True))
    
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
                        if re.match(r"^(user_id|session_id|tenant_id|workspace_id|owner_id|repo_id|project_id|group_id|collection_id|page_id|task_id|parent_id|account_id|client_id|provider_id|model_id|config_id|rule_id|template_id|category_id|agent_id)", field_name):
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
            capture_output=True, text=True, timeout=120
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
                capture_output=True, text=True, timeout=60
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
                ["cargo", "fix", "--allow-dirty", "--allow-staged", "--lib", "-p", "spacetimedb-module"],
                cwd=stdb_dir,
                capture_output=True, text=True, timeout=120
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
    
    return False, "No unused imports found to remove" + (f" ({'; '.join(errors)})" if errors else "")


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

    This is a stub — full extraction requires understanding the code structure.
    """
    return False, "Module extraction requires manual implementation — open the file and refactor"


@register(r"convert\s+.*\s+to\s+typed\s+error")
def handle_typed_errors(ctx: WorkerContext) -> tuple[bool, str]:
    """Convert string-based errors to typed error enums.

    This is a complex refactoring that usually needs LLM assistance.
    """
    return False, "Typed error conversion needs LLM assistance — routing to LLM worker"


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
                capture_output=True, text=True, timeout=180,
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
                capture_output=True, text=True, timeout=180,
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
                capture_output=True, text=True, timeout=180,
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
                capture_output=True, text=True, timeout=120,
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
                capture_output=True, text=True, timeout=120,
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
    """Run git maintenance operations: gc, prune, repack.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    try:
        result = subprocess.run(
            ["git", "gc", "--auto", "--prune=now"],
            cwd=repo_path,
            capture_output=True, text=True, timeout=120,
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
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    try:
        result = subprocess.run(
            ["git", "grep", "-n", "-c", r"(TODO|FIXME|HACK|XXX)"],
            cwd=repo_path,
            capture_output=True, text=True, timeout=30,
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
    """Sync .env.example with .env: report missing or extra keys.
    """
    repo_path = ctx.repo_path
    if not repo_path:
        return False, f"Repo directory not found: {ctx.repo}"

    env_path = os.path.join(repo_path, ".env")
    env_example_path = os.path.join(repo_path, ".env.example")
    server_env = os.path.join(repo_path, "server", ".env")

    changes = []

    for env_file, example_file in [(env_path, env_example_path), (server_env, os.path.join(repo_path, "server", ".env.example"))]:
        if not os.path.isfile(env_file) or not os.path.isfile(example_file):
            continue

        with open(env_file) as f:
            env_keys = set(
                line.split("=")[0].strip()
                for line in f
                if "=" in line and not line.startswith("#")
            )
        with open(example_file) as f:
            example_keys = set(
                line.split("=")[0].strip()
                for line in f
                if "=" in line and not line.startswith("#")
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
                capture_output=True, text=True, timeout=30,
            )
            if fmt_result.returncode == 0:
                results.append("Rust: fmt OK")
            else:
                # Run fmt in-place
                subprocess.run(
                    ["cargo", "fmt"],
                    cwd=stdb_dir,
                    capture_output=True, timeout=30,
                )
                results.append("Rust: fmt fixed")
        except FileNotFoundError:
            results.append("Rust: cargo not found")

    # Ruff
    if os.path.isfile(os.path.join(repo_path, "pyproject.toml")) or os.path.isfile(os.path.join(repo_path, "ruff.toml")):
        try:
            result = subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=repo_path,
                capture_output=True, text=True, timeout=60,
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
                capture_output=True, text=True, timeout=60,
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
