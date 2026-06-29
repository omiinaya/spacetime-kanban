"""Two-way GitHub issue sync for spacetimedb-kanban.

Stores the kanban-task ⟷ GitHub-issue mapping in ~/.kanban/issue_map.json.
Provides GitHub API helpers for creating, closing, and reopening issues.
"""
import json
import os
import uuid
from datetime import datetime
from typing import Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urljoin

ISSUE_MAP_FILE = os.path.expanduser("~/.kanban/issue_map.json")
GITHUB_API = "https://api.github.com"


# ── Mapping Store ────────────────────────────────────────────────────

def _ensure_file():
    os.makedirs(os.path.dirname(ISSUE_MAP_FILE), exist_ok=True)
    if not os.path.exists(ISSUE_MAP_FILE):
        with open(ISSUE_MAP_FILE, "w") as f:
            json.dump({}, f)


def _load_map() -> dict:
    """Return {kanban_task_id: mapping_dict, ...}"""
    _ensure_file()
    try:
        with open(ISSUE_MAP_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def _save_map(m: dict):
    _ensure_file()
    with open(ISSUE_MAP_FILE, "w") as f:
        json.dump(m, f, indent=2)


# ── Public mapping API ────────────────────────────────────────────────

def get_link(task_id: str) -> Optional[dict]:
    """Get the GitHub issue link for a kanban task, if any."""
    return _load_map().get(task_id)


def get_task_id_for_issue(repo: str, issue_number: int) -> Optional[str]:
    """Reverse lookup: find kanban task ID by GitHub issue."""
    m = _load_map()
    for tid, info in m.items():
        if info.get("repo") == repo and info.get("issue_number") == issue_number:
            return tid
    return None


def link_issue(task_id: str, repo: str, issue_number: int, issue_url: str, html_url: str) -> dict:
    """Record a kanban ⟷ GitHub issue link."""
    m = _load_map()
    m[task_id] = {
        "issue_number": issue_number,
        "repo": repo,
        "issue_url": issue_url,
        "html_url": html_url,
        "status": "open",
        "linked_at": int(datetime.utcnow().timestamp() * 1000),
    }
    _save_map(m)
    return m[task_id]


def unlink_issue(task_id: str) -> bool:
    """Remove a kanban ⟷ GitHub issue link. Returns True if existed."""
    m = _load_map()
    if task_id in m:
        del m[task_id]
        _save_map(m)
        return True
    return False


def update_issue_status(task_id: str, status: str) -> Optional[dict]:
    """Update the cached GH issue status (open/closed)."""
    m = _load_map()
    if task_id in m:
        m[task_id]["status"] = status
        _save_map(m)
        return m[task_id]
    return None


def list_links(repo: Optional[str] = None) -> list[dict]:
    """List all linked issues, optionally filtered by repo."""
    m = _load_map()
    results = []
    for tid, info in m.items():
        if repo and info.get("repo") != repo:
            continue
        results.append({"kanban_task_id": tid, **info})
    results.sort(key=lambda r: -r.get("linked_at", 0))
    return results


# ── GitHub API helpers ────────────────────────────────────────────────

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
