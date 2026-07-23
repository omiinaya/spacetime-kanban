"""Two-way GitHub issue sync for spacetimedb-kanban.

Stores the kanban-task ⟷ GitHub-issue mapping in STDB (issue_links table).
Provides GitHub API helpers for creating, closing, and reopening issues.
"""

import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from config import settings

# ── Retry config ─────────────────────────────────────────────────────
GH_API_MAX_RETRIES = 3
GH_API_BASE_DELAY = 1.0  # seconds

STDB_SQL_URL = (
    f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/sql"
)
STDB_CALL_URL = (
    f"http://{settings.stdb_host}:{settings.stdb_port}/v1/database/{settings.stdb_db}/call"
)
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
    """Parse STDB SATS row format into dicts using recursive type-aware extraction."""
    if not resp_json:
        return []
    entry = resp_json[0]
    schema = entry.get("schema", {})
    elements = schema.get("elements", [])
    col_names: list[str] = []
    col_types: list[dict] = []
    for el in elements:
        name = el.get("name", {})
        if isinstance(name, dict):
            name = name.get("some", name)
        col_names.append(str(name) if name else "?")
        col_types.append(el.get("algebraic_type", {}))
    from shared import _extract_sats_val

    rows = entry.get("rows", [])
    result: list[dict] = []
    for row in rows:
        row_dict = {}
        for i, val in enumerate(row):
            key = col_names[i] if i < len(col_names) else f"col_{i}"
            atype = col_types[i] if i < len(col_types) else {}
            row_dict[key] = _extract_sats_val(val, atype)
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


def _sanitize(val: str) -> str:
    """Escape single quotes to prevent SQL injection."""
    return val.replace("'", "''")


def _sql_param(query_template: str, **params: str) -> list[dict]:
    """Safe SQL query with named parameters — escapes all string values."""
    escaped = {k: _sanitize(str(v)) for k, v in params.items()}
    query = query_template.format(**escaped)
    return _stdb_sql(query)


# ── Public mapping API (STDB-backed) ──────────────────────────────────


def get_link(task_id: str) -> dict | None:
    """Get the GitHub issue link for a kanban task, if any."""
    rows = _sql_param(
        "SELECT * FROM issue_links WHERE kanban_task_id = '{task_id}'", task_id=task_id
    )
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


def get_task_id_for_issue(repo: str, issue_number: int) -> str | None:
    """Reverse lookup: find kanban task ID by GitHub issue."""
    rows = _sql_param(
        "SELECT kanban_task_id FROM issue_links "
        "WHERE repo = '{repo}' AND issue_number = '{issue_number}'",
        repo=repo,
        issue_number=str(issue_number),
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


def update_issue_status(task_id: str, status: str) -> dict | None:
    """Update the cached GH issue status (open/closed) in STDB."""
    try:
        _call("update_issue_link_status", [task_id, status])
    except RuntimeError as e:
        if "not found" in str(e).lower():
            return None
        raise
    return get_link(task_id)


def list_links(repo: str | None = None) -> list[dict]:
    """List all linked issues, optionally filtered by repo."""
    if repo:
        rows = _sql_param("SELECT * FROM issue_links WHERE repo = '{repo}'", repo=repo)
    else:
        rows = _stdb_sql("SELECT * FROM issue_links")
    results = []
    for r in rows:
        results.append(
            {
                "kanban_task_id": r.get("kanban_task_id", ""),
                "issue_number": r.get("issue_number", 0),
                "repo": r.get("repo", ""),
                "issue_url": r.get("issue_url", ""),
                "html_url": r.get("html_url", ""),
                "status": r.get("status", "open"),
                "linked_at": r.get("linked_at", 0),
            }
        )
    results.sort(key=lambda x: -x.get("linked_at", 0))
    return results


# ── GitHub API helpers (unchanged) ────────────────────────────────────


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "spacetimedb-kanban/1.0",
    }


async def _gh_request(method: str, url: str, token: str, body: dict | None = None) -> dict:
    """Make a GitHub API request with httpx and exponential-backoff retry."""
    headers = _gh_headers(token)
    if body:
        headers["Content-Type"] = "application/json"

    last_error = ""
    for attempt in range(GH_API_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.request(
                    method=method,
                    url=url,
                    json=body,
                    headers=headers,
                )
                if resp.status_code < 500:
                    raw = resp.text
                    return json.loads(raw) if raw.strip() else {}
                # Server error — will retry with backoff
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except httpx.TimeoutException as e:
            last_error = f"timeout: {e}"
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            last_error = str(e)[:200]

        if attempt < GH_API_MAX_RETRIES - 1:
            await asyncio.sleep(GH_API_BASE_DELAY * (2**attempt))

    raise RuntimeError(
        f"GitHub API request failed after {GH_API_MAX_RETRIES} attempts: {last_error}"
    )


async def search_issues(token: str, repo: str, query: str) -> list[dict]:
    """Search GitHub issues in a repo using the GitHub API search.

    Returns a list of matching issues (title, number, html_url, state).
    """
    url = f"{GITHUB_API}/search/issues?q=repo:{repo}+{quote(query)}&per_page=10"
    result = await _gh_request("GET", url, token)
    items = result.get("items", [])
    return [
        {
            "number": i["number"],
            "title": i.get("title", ""),
            "html_url": i.get("html_url", ""),
            "state": i.get("state", "open"),
        }
        for i in items
    ]


async def find_existing_issue(token: str, repo: str, task_id: str) -> dict | None:
    """Search GitHub for an existing issue that already links to a kanban task.

    The kanban stores the task ID in the issue body as:
      _Created from kanban task `{task_id}`_

    Search for this string and return the first open match, or None.
    """
    results = await search_issues(token, repo, f'"kanban task `{task_id}`"+state:open')
    if results:
        return results[0]
    return None


async def create_issue(
    token: str,
    repo: str,
    title: str,
    body: str = "",
    labels: list[str] | None = None,
    assignee: str | None = None,
    task_id: str | None = None,
) -> dict:
    """Create a GitHub issue and return {number, html_url, issue_url, ...}.

    If task_id is provided, first checks GitHub for an existing issue
    that already links to this kanban task (via the body marker). If
    found, returns the existing issue instead of creating a duplicate.
    This is the primary dedup mechanism — survives kanban STDB resets.
    """
    # Dedup: check GitHub for existing issue with this task ID
    if task_id:
        existing = await find_existing_issue(token, repo, task_id)
        if existing:
            return {
                "issue_number": existing["number"],
                "html_url": existing["html_url"],
                "issue_url": f"{GITHUB_API}/repos/{repo}/issues/{existing['number']}",
                "state": existing["state"],
            }

    payload: dict[str, Any] = {"title": title}
    if body:
        payload["body"] = body
    if labels:
        payload["labels"] = labels
    if assignee:
        payload["assignees"] = [assignee]

    url = f"{GITHUB_API}/repos/{repo}/issues"
    result = await _gh_request("POST", url, token, payload)
    return {
        "issue_number": result["number"],
        "html_url": result["html_url"],
        "issue_url": result["url"],
        "state": result.get("state", "open"),
    }


async def close_issue(token: str, repo: str, issue_number: int) -> dict:
    """Close a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return await _gh_request("PATCH", url, token, {"state": "closed"})


async def reopen_issue(token: str, repo: str, issue_number: int) -> dict:
    """Re-open a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return await _gh_request("PATCH", url, token, {"state": "open"})


async def get_issue(token: str, repo: str, issue_number: int) -> dict:
    """Fetch GitHub issue details."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    return await _gh_request("GET", url, token)


async def get_issue_comments(token: str, repo: str, issue_number: int) -> list[dict]:
    """Get comments on a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    result = await _gh_request("GET", url, token)
    return result if isinstance(result, list) else []


async def add_issue_comment(token: str, repo: str, issue_number: int, body: str) -> dict:
    """Add a comment to a GitHub issue."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    return await _gh_request("POST", url, token, {"body": body})
