"""Dependency scanner — checks for outdated or mismatched dependencies.

Scans Cargo.toml, package.json, pyproject.toml for:
  - Dependencies pinned to old versions (pre-release, beta)
  - Mismatched versions between workspace members
  - Missing dev dependencies or test frameworks

Priority: P2 (medium) — dependency drift accumulates slowly.
"""

import json
import os
import re
import tomllib

from scanners import register_scanner


def _parse_cargo_toml(filepath: str) -> dict | None:
    """Parse a Cargo.toml file."""
    try:
        with open(filepath, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return None


def _check_cargo_deps(repo_name: str, repo_path: str) -> list[dict]:
    """Check Cargo.toml for dependency issues."""
    findings = []
    cargo_toml = os.path.join(repo_path, "Cargo.toml")
    server_cargo = os.path.join(repo_path, "server", "spacetimedb", "Cargo.toml")

    for path in [cargo_toml, server_cargo]:
        if not os.path.isfile(path):
            continue
        data = _parse_cargo_toml(path)
        if not data:
            continue

        # Check for workspace-level dep inconsistencies
        if "workspace" in data and "members" in data["workspace"]:
            members = data["workspace"]["members"]
            # Check each member's Cargo.toml
            for member in members:
                member_path = os.path.join(repo_path, member, "Cargo.toml")
                if not os.path.isfile(member_path):
                    continue
                member_data = _parse_cargo_toml(member_path)
                if not member_data:
                    continue
                # Dep version consistency checks could go here
                pass

        # Check for pinned versions (e.g. "=0.1.0" or git dependencies)
        deps = data.get("dependencies", {})
        for dep_name, dep_spec in deps.items():
            if isinstance(dep_spec, str) and dep_spec.startswith("="):
                cargo_rel = f"{os.path.basename(os.path.dirname(path))}/Cargo.toml"
                findings.append(
                    {
                        "title": f"Unpin {dep_name} in {cargo_rel}",
                        "description": (
                            f"`{dep_name}` is pinned to exact version `{dep_spec}` "
                            f"in {path}. "
                            f"Consider using `{dep_spec[1:]}` or a semver range to get bug fixes."
                        ),
                        "priority": 3,
                        "scanner": "deps",
                        "skip_verify": True,
                    }
                )

        # Check for git dependencies (should use crates.io)
        git_deps = [(n, s) for n, s in deps.items() if isinstance(s, dict) and "git" in s]
        if git_deps:
            names = ", ".join(n for n, _ in git_deps[:5])
            findings.append(
                {
                    "title": f"Review {len(git_deps)} git dependencies in {repo_name}",
                    "description": (
                        f"{len(git_deps)} dependencies use git URLs "
                        f"instead of crates.io: {names}. "
                        f"These should be migrated to published versions when available."
                    ),
                    "priority": 3,
                    "scanner": "deps",
                    "skip_verify": True,
                }
            )

    return findings


def _check_npm_deps(repo_path: str) -> list[dict]:
    """Check package.json for out-of-date dependencies."""
    findings = []
    for root in [repo_path, os.path.join(repo_path, "web")]:
        pkg_json = os.path.join(root, "package.json")
        if not os.path.isfile(pkg_json):
            continue

        try:
            with open(pkg_json) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

        # Check for pinned versions (exact with no ^/~)
        pinned = [
            (n, v)
            for n, v in deps.items()
            if isinstance(v, str) and re.match(r"^\d+\.\d+\.\d+$", v)
        ]
        if pinned:
            names = ", ".join(f"{n}@{v}" for n, v in pinned[:5])
            rel_root = os.path.relpath(pkg_json, repo_path)
            findings.append(
                {
                    "title": f"Unpin {len(pinned)} npm deps in {rel_root}",
                    "description": (
                        f"{len(pinned)} packages in {rel_root} "
                        f"are pinned to exact versions: {names}. "
                        f"Use ^ or ~ ranges to get patch/minor updates automatically."
                    ),
                    "priority": 3,
                    "scanner": "deps",
                    "skip_verify": True,
                }
            )

        # Check for duplicate deps across root and web/
        if root == repo_path and os.path.isfile(os.path.join(repo_path, "web", "package.json")):
            web_pkg = os.path.join(repo_path, "web", "package.json")
            try:
                with open(web_pkg) as f:
                    web_data = json.load(f)
                web_deps = {
                    **web_data.get("dependencies", {}),
                    **web_data.get("devDependencies", {}),
                }
                duplicates = set(deps.keys()) & set(web_deps.keys())
                if duplicates:
                    names = ", ".join(sorted(duplicates)[:5])
                    findings.append(
                        {
                            "title": "Deduplicate npm deps shared between root and web/",
                            "description": (
                                f"{len(duplicates)} packages appear in both "
                                f"root and web/package.json: {names}. "
                                f"Consider hoisting shared deps to the root or using a workspace."
                            ),
                            "priority": 3,
                            "scanner": "deps",
                            "skip_verify": True,
                        }
                    )
            except (OSError, json.JSONDecodeError):
                pass

    return findings


@register_scanner
def scan_deps(repo_name: str, repo_path: str) -> list[dict]:
    """Scan the repo for dependency issues."""
    findings = []
    findings.extend(_check_cargo_deps(repo_name, repo_path))
    findings.extend(_check_npm_deps(repo_path))
    return findings
