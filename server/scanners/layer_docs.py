"""Documentation & CI scanner — finds missing project infrastructure.

Layer 3 checks:
  - Missing README.md (critical for any project)
  - Stale README (last modified > 90 days)
  - Missing LICENSE file
  - Missing CONTRIBUTING.md
  - Missing .github/ directory with CI workflows
  - Missing issue/PR templates
  - Missing CHANGELOG.md

Priority: P3 — project infrastructure, important for contributors.
"""

import os

from scanners import register_scanner

# Files/dirs that indicate documented projects
README_FILES = ["README.md", "README.rst", "README.txt"]
CI_FILES = [".github/workflows/ci.yml", ".github/workflows/test.yml", ".github/workflows/main.yml"]
PR_TEMPLATES = [".github/PULL_REQUEST_TEMPLATE.md", ".github/pull_request_template.md"]
ISSUE_TEMPLATES = [".github/ISSUE_TEMPLATE/", ".github/issue_template.md"]
LINT_CONFIGS = [
    ".ruff.toml",
    "ruff.toml",
    "pyproject.toml",  # Python
    ".rustfmt.toml",
    "rustfmt.toml",
    ".clippy.toml",  # Rust
    ".prettierrc",
    ".prettierrc.json",
    ".eslintrc.js",  # JS/TS
]


def _find_project_files(repo_path: str, filenames: list[str]) -> list[str]:
    """Find which of the given files exist in the repo."""
    found = []
    for name in filenames:
        if os.path.isfile(os.path.join(repo_path, name)):
            found.append(name)
        # Also check for star patterns
        if name.endswith("/") and os.path.isdir(os.path.join(repo_path, name)):
            found.append(name)
    return found


def _check_readme_staleness(repo_path: str) -> int | None:
    """Check how many days since README was last modified. Returns None if no README."""
    import time

    for name in README_FILES:
        path = os.path.join(repo_path, name)
        if os.path.isfile(path):
            age_days = (time.time() - os.path.getmtime(path)) / 86400
            return int(age_days)
    return None


def _has_gitignore(repo_path: str) -> bool:
    """Check for .gitignore file."""
    return os.path.isfile(os.path.join(repo_path, ".gitignore"))


def _has_docker(repo_path: str) -> bool:
    """Check for Dockerfile or docker-compose.yml."""
    return any(
        os.path.isfile(os.path.join(repo_path, f))
        for f in ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"]
    )


@register_scanner
def scan_docs_ci(repo_name: str, repo_path: str) -> list[dict]:
    """Scan for documentation and CI infrastructure gaps."""
    findings = []

    # ── README check ──
    readme_age = _check_readme_staleness(repo_path)
    if readme_age is None:
        findings.append(
            {
                "title": f"Add README.md to {repo_name}",
                "description": (
                    "This project has no README file. A README explains "
                    "what the project does, how to set it up, and how to contribute."
                ),
                "priority": 3,
                "scanner": "docs_ci",
            }
        )
    elif readme_age > 90:
        findings.append(
            {
                "title": f"Update README.md in {repo_name} (last updated {readme_age}d ago)",
                "description": (
                    f"The README hasn't been updated in {readme_age} days. "
                    f"It may be out of date with the current codebase."
                ),
                "priority": 3,
                "scanner": "docs_ci",
            }
        )

    # ── License check ──
    if (
        not os.path.isfile(os.path.join(repo_path, "LICENSE"))
        and not os.path.isfile(os.path.join(repo_path, "LICENSE.md"))
        and not os.path.isfile(os.path.join(repo_path, "LICENSE.txt"))
    ):
        findings.append(
            {
                "title": f"Add LICENSE to {repo_name}",
                "description": (
                    "This project has no license file. Without a license, "
                    "others cannot legally use, modify, or distribute the code."
                ),
                "priority": 3,
                "scanner": "docs_ci",
            }
        )

    # ── .gitignore check ──
    if not _has_gitignore(repo_path):
        findings.append(
            {
                "title": f"Add .gitignore to {repo_name}",
                "description": (
                    "This project has no .gitignore. Temporary files, secrets, "
                    "and build artifacts may be committed to the repository."
                ),
                "priority": 3,
                "scanner": "docs_ci",
            }
        )

    # ── CI check ──
    github_dir = os.path.join(repo_path, ".github")
    has_ci = any(os.path.isfile(os.path.join(repo_path, f)) for f in CI_FILES)

    if os.path.isdir(github_dir):
        # Check for any workflow files
        workflows_dir = os.path.join(github_dir, "workflows")
        has_ci = has_ci or (os.path.isdir(workflows_dir) and len(os.listdir(workflows_dir)) > 0)

    if not has_ci:
        found_linters = _find_project_files(repo_path, LINT_CONFIGS)
        if found_linters:
            findings.append(
                {
                    "title": f"Add CI pipeline to {repo_name}",
                    "description": (
                        f"This project has linter/formatter configs "
                        f"({', '.join(found_linters[:3])}) "
                        f"but no CI workflow (.github/workflows/). "
                        f"CI would auto-run checks on PRs."
                    ),
                    "priority": 3,
                    "scanner": "docs_ci",
                }
            )

    # ── CONTRIBUTING check ──
    if not os.path.isfile(os.path.join(repo_path, "CONTRIBUTING.md")) and readme_age is not None:
        findings.append(
            {
                "title": f"Add CONTRIBUTING.md to {repo_name}",
                "description": (
                    "A CONTRIBUTING guide helps others understand "
                    "how to contribute to this project."
                ),
                "priority": 3,
                "scanner": "docs_ci",
            }
        )

    # ── Issue/PR template check ──
    gh_dir = os.path.join(repo_path, ".github")
    if os.path.isdir(gh_dir):
        has_pr_template = any(os.path.isfile(os.path.join(repo_path, f)) for f in PR_TEMPLATES)
        has_issue_template = any(
            os.path.isdir(os.path.join(repo_path, f)) or os.path.isfile(os.path.join(repo_path, f))
            for f in ISSUE_TEMPLATES
        )

        if not has_pr_template and readme_age is not None:
            findings.append(
                {
                    "title": f"Add PR template to {repo_name}",
                    "description": (
                        "A pull request template standardizes "
                        "PR descriptions and helps reviewers."
                    ),
                    "priority": 3,
                    "scanner": "docs_ci",
                }
            )

        if not has_issue_template and readme_age is not None:
            findings.append(
                {
                    "title": f"Add issue template(s) to {repo_name}",
                    "description": (
                        "Issue templates guide users to provide "
                        "useful bug reports and feature requests."
                    ),
                    "priority": 3,
                    "scanner": "docs_ci",
                }
            )

    # ── CHANGELOG check (for repos with >1 branch/tag) ──
    if not os.path.isfile(os.path.join(repo_path, "CHANGELOG.md")):
        import subprocess

        try:
            tag_count = subprocess.run(
                ["git", "tag", "--list"], cwd=repo_path, capture_output=True, text=True, timeout=10
            )
            if len(tag_count.stdout.strip().split("\n")) >= 3:
                findings.append(
                    {
                        "title": f"Add CHANGELOG.md to {repo_name}",
                        "description": (
                            f"This project has "
                            f"{len(tag_count.stdout.strip().split(chr(10)))} tags "
                            f"but no CHANGELOG. "
                            f"A changelog helps users track what changed between releases."
                        ),
                        "priority": 3,
                        "scanner": "docs_ci",
                    }
                )
        except Exception:
            pass

    return findings
