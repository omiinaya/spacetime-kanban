"""Two-way GitHub issue sync for spacetimedb-kanban.

Stores the kanban-task ⟷ GitHub-issue mapping in STDB (issue_links table).
Provides GitHub API helpers for creating, closing, and reopening issues.
"""
import json
import re
from datetime import datetime
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import httpx

from config import settings

STDB_SQL_URL = f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/sql"
STDB_CALL_URL = f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/call"
GITHUB_API = "https://api.github.com"


# ── STDB helpers (synchronous) ───────────────────────────────────────


def _stdb_sql(query: str) -> list[dict]:
    """Execute a synchronous SQL query against STDB."""
    resp = httpx.post(
        STDB_SQL_URL,
        content=query,
        headers={"Content-Type": "application/sql"},
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"SQL query failed: {resp.text[:300]}")
    data = resp.json()
    return _parse_rows(data)


def _parse_rows(resp_json: list[dict]) -> list[dict]:
    """Parse STDB SATS row format into dicts."""
    if not resp_json:
        return []
    entry = resp_json[0]
    schema = entry.get("schema", {})
    elements = schema.get("elements", [])
    col_names: list[str] = []
    for el in elements:
        name = el.get("name", {})
        if isinstance(name, dict):
            name = name.get("some", name)
        col_names.append(str(name) if name else "?")
    rows = entry.get("rows", [])
    result: list[dict] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            if isinstance(val, list) and len(val) == 2:
                if val[0] == 0:
                    val = val[1] if val[1] and val[1] != [] else None
                else:
                    val = None
            row_dict[key] = val
        result.append(row_dict)
    return result


def _call(reducer: str, args: list) -> dict:
    """Call a synchronous STDB reducer."""
    resp = httpx.post(
        f"{STDB_CALL_URL}/{reducer}",
        json=args,
        timeout=10,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Reducer failed: {resp.text[:300]}")
    text = resp.text.strip()
    if text:
        return resp.json()
    return {"status": "ok"}


# ── Public mapping API (STDB-backed) ──────────────────────────────────


def get_link(task_id: str) -> Optional[dict]:
    """Get the GitHub issue link for a kanban task, if any."""
    rows = _sql_param("SELECT * FROM issue_links WHERE kanban_task_id = '{task_id}'", task_id=task_id)
    if not rows:
        return None
    r = rows[0]
    return {
        "issue_number": r.get("issue_number", 0),
        "repo": r.get("repo", ""),
        "issue_url": r.get("issue_url", ""),
        "html_url": r.get("html_url", ""),
        "status": r.get("status", "open"),
        "linked_at": r.get("linked_at", 0),
    }


def get_task_id_for_issue(repo: str, issue_number: int) -> Optional[str]:
    """Reverse lookup: find kanban task ID by GitHub issue."""
    rows = _stdb_sql(
        f"SELECT kanban_task_id FROM issue_links "
        f"WHERE repo = '{repo}' AND issue_number = {issue_number}"
    )
    if rows:
        return rows[0].get("kanban_task_id")
    return None


def link_issue(task_id: str, repo: str, issue_number: int, issue_url: str, html_url: str) -> dict:
    """Record a kanban ⟷ GitHub issue link in STDB."""
    _call("link_issue", [task_id, issue_number, repo, issue_url, html_url])
    return get_link(task_id) or {
        "issue_number": issue_number,
        "repo": repo,
        "issue_url": issue_url,
        "html_url": html_url,
        "status": "open",
        "linked_at": int(datetime.utcnow().timestamp() * 1000),
    }


def unlink_issue(task_id: str) -> bool:
    """Remove a kanban ⟷ GitHub issue link. Returns True if existed."""
    try:
        _call("unlink_issue", [task_id])
        return True
    except RuntimeError as e:
        if "not found" in str(e).lower():
            return False
        raise


def update_issue_status(task_id: str, status: str) -> Optional[dict]:
    """Update the cached GH issue status (open/closed) in STDB."""
    try:
        _call("update_issue_link_status", [task_id, status])
    except RuntimeError as e:
        if "not found" in str(e).lower():
            return None
        raise
    return get_link(task_id)


def list_links(repo: Optional[str] = None) -> list[dict]:
    """List all linked issues, optionally filtered by repo."""
    if repo:
        rows = _sql_param("SELECT * FROM issue_links WHERE repo = '{repo}'", repo=repo)
    else:
        rows = _stdb_sql("SELECT * FROM issue_links")
    results = []
    for r in rows:
        results.append({
            "kanban_task_id": r.get("kanban_task_id", ""),
            "issue_number": r.get("issue_number", 0),
            "repo": r.get("repo", ""),
            "issue_url": r.get("issue_url", ""),
            "html_url": r.get("html_url", ""),
            "status": r.get("status", "open"),
            "linked_at": r.get("linked_at", 0),
        })
    results.sort(key=lambda x: -x.get("linked_at", 0))
    return results


# ── GitHub API helpers (unchanged) ────────────────────────────────────


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "spacetimedb-kanban/1.0",
    }


def _gh_request(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    """Make a GitHub API request and return parsed JSON."""
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, method=method, headers=_gh_headers(token))
    try:
        with urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        err_body = e.read().decode()[:300]
        raise RuntimeError(f"GitHub API HTTP {e.code}: {err_body}")


def create_issue(
    token: str,
    repo: str,
    title: str,
    body: str = "",
    labels: Optional[list[str]] = None,
    assignee: Optional[str] = None,
) -> dict:
    """Create a GitHub issue and return {number, html_url, issue_url, ...}."""
    payload = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignee:
        payload["assignees"] = [assignee]

    url = f"{GITHUB_API}/repos/{repo}/issues"
    result = _gh_request("POST", url, token, payload)
    return {
        "issue_number": result["number"],
        "html_url": result["html_url"],
        "issue_url": result["url"],
        "state": result.get("state", "open"),
    }


def close_issue(token: str, repo: str, issue_number: int) -> dict:
    """Close a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return _gh_request("PATCH", url, token, {"state": "closed"})


def reopen_issue(token: str, repo: str, issue_number: int) -> dict:
    """Re-open a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return _gh_request("PATCH", url, token, {"state": "open"})


def get_issue(token: str, repo: str, issue_number: int) -> dict:
    """Fetch GitHub issue details."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return _gh_request("GET", url, token)


def get_issue_comments(token: str, repo: str, issue_number: int) -> list[dict]:
    """Get comments on a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    result = _gh_request("GET", url, token)
    return result if isinstance(result, list) else []


def add_issue_comment(token: str, repo: str, issue_number: int, body: str) -> dict:
    """Add a comment to a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    return _gh_request("POST", url, token, {"body": body})
