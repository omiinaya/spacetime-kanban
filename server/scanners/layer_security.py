"""Production readiness scanner — finds deployment, security, and ops gaps.

Layer 4 checks:
  - .env committed to git history (leaked secrets)
  - Dockerfile / docker-compose.yml missing
  - No healthcheck or monitoring
  - No Makefile / justfile / Taskfile (build automation)
  - No LICENSE (re-license check from layer_docs)

Priority: P3 — long-term project health.
"""

import os
import subprocess

from scanners import register_scanner


def _check_env_in_git(repo_path: str) -> int:
    """Check if .env file was ever committed to git history."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--diff-filter=A", "--", ".env"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return len([l for l in result.stdout.strip().split("\n") if l.strip()])
    except Exception:
        return 0


def _check_for_build_automation(repo_path: str) -> list[str]:
    """Find build automation files."""
    found = []
    for name in ["Makefile", "justfile", "Taskfile.yml", "Taskfile.yaml", "Rakefile"]:
        if os.path.isfile(os.path.join(repo_path, name)):
            found.append(name)
    return found


def _check_for_commit_hooks(repo_path: str) -> list[str]:
    """Check if git hooks are configured."""
    hooks = []
    hooks_dir = os.path.join(repo_path, ".githooks")
    if os.path.isdir(hooks_dir):
        hooks = os.listdir(hooks_dir)
    return hooks


def _check_branch_protection(repo_path: str) -> bool:
    """Check if there's a main branch and any other branches (team signal)."""
    try:
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        branches = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        return len(branches) > 1  # More than just origin/main
    except Exception:
        return False


@register_scanner
def scan_prod_readiness(repo_name: str, repo_path: str) -> list[dict]:
    """Scan for production readiness and security gaps."""
    findings = []

    # ── .env in git check ──
    env_commits = _check_env_in_git(repo_path)
    if env_commits > 0:
        findings.append(
            {
                "title": f"Remove .env from git history in {repo_name} ({env_commits} commit(s))",
                "description": f"The `.env` file was committed {env_commits} time(s). This may expose secrets "
                f"in git history. Use `git filter-branch` or `bfg` to purge it.",
                "priority": 2,
                "scanner": "prod_readiness",
            }
        )

    # ── Docker check ──
    has_dockerfile = os.path.isfile(os.path.join(repo_path, "Dockerfile"))
    has_compose = any(
        os.path.isfile(os.path.join(repo_path, f))
        for f in ["docker-compose.yml", "docker-compose.yaml"]
    )
    if not has_dockerfile and not has_compose:
        # Check if it's a server project (has main.py, Cargo.toml, etc.)
        has_server = any(
            os.path.isfile(os.path.join(repo_path, f))
            for f in ["server/main.py", "main.py", "Cargo.toml", "pyproject.toml"]
        )
        if has_server:
            findings.append(
                {
                    "title": f"Add Dockerfile to {repo_name}",
                    "description": "This project has server code but no Dockerfile. Containerization "
                    "simplifies deployment and environment consistency.",
                    "priority": 3,
                    "scanner": "prod_readiness",
                }
            )

    # ── Build automation check ──
    build_tools = _check_for_build_automation(repo_path)
    if not build_tools:
        has_cargo = os.path.isfile(os.path.join(repo_path, "Cargo.toml"))
        has_npm = os.path.isfile(os.path.join(repo_path, "package.json"))
        if has_cargo and not has_npm:
            # Rust-only projects should at least have basic commands
            findings.append(
                {
                    "title": f"Add Makefile or justfile to {repo_name}",
                    "description": "This Rust project has no build automation (Makefile, justfile). "
                    "Common commands like `build`, `test`, `lint` should be documented.",
                    "priority": 3,
                    "scanner": "prod_readiness",
                }
            )

    # ── Healthcheck endpoint check ──
    server_dirs = [os.path.join(repo_path, "server"), repo_path]
    has_healthcheck = False
    for sd in server_dirs:
        main_py = os.path.join(sd, "main.py")
        if os.path.isfile(main_py):
            try:
                with open(main_py) as f:
                    content = f.read()
                if "/health" in content or "health" in content.lower():
                    has_healthcheck = True
                    break
            except (OSError, UnicodeDecodeError):
                pass

    (
        any(
            os.path.isfile(os.path.join(d, "main.py"))
            and "FastAPI" in open(os.path.join(d, "main.py")).read()
            for d in server_dirs
            if os.path.isfile(os.path.join(d, "main.py"))
        )
        if False
        else False
    )

    # Simple check for health endpoint
    for sd in server_dirs:
        main_py = os.path.join(sd, "main.py")
        if os.path.isfile(main_py):
            try:
                with open(main_py) as f:
                    content = f.read()
                if '"health"' in content or "'health'" in content or "/health" in content:
                    has_healthcheck = True
                break
            except:
                pass

    # Actually let me use a simpler approach
    for root, _dirs, files in os.walk(repo_path):
        for f in files:
            if f == "main.py":
                filepath = os.path.join(root, f)
                try:
                    with open(filepath) as fh:
                        content = fh.read()
                    if '@app.get("/health")' in content or "def health" in content:
                        has_healthcheck = True
                except:
                    pass

    if not has_healthcheck:
        has_server_code = any(
            os.path.isfile(os.path.join(repo_path, f))
            for f in ["server/main.py", "main.py", "app.py", "server/app.py"]
        )
        if has_server_code:
            findings.append(
                {
                    "title": f"Add health check endpoint to {repo_name}",
                    "description": "This project has a server but no /health endpoint. "
                    "A health endpoint is essential for monitoring and container orchestration.",
                    "priority": 3,
                    "scanner": "prod_readiness",
                }
            )

    # ── Pre-commit hooks check ──
    hooks = _check_for_commit_hooks(repo_path)
    if hooks:
        findings.append(
            {
                "title": f"Enable pre-commit hooks in {repo_name}",
                "description": f"Found {len(hooks)} hook(s) in `.githooks/` but they need to be activated "
                f"with `git config core.hooksPath .githooks`.",
                "priority": 3,
                "scanner": "prod_readiness",
            }
        )

    return findings
