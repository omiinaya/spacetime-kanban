"""Auto-star the project repo on first install.

When the server starts with a GitHub token configured (GITHUB_TOKEN in
server/.env) and a default repo set (GITHUB_DEFAULT_REPO=owner/repo),
this module stars the repo once — unless the authenticated user is the
repo owner, or has already starred it. A marker file makes the check
run exactly once per install, so it never re-stars or spams the API
on every server restart.

The whole flow is best-effort: any failure (bad token, network, missing
repo, no star permission) is logged and skipped — it must never block
or crash server startup.
"""

import asyncio
import os
import time

import httpx

from config import settings

GITHUB_API = "https://api.github.com"
USER_AGENT = "spacetime-kanban/1.0"

# Marker file: once present, auto-star never runs again on this machine.
DEFAULT_MARKER_DIR = os.path.expanduser("~/.local/share/spacetime-kanban")
MARKER_FILENAME = "auto-star.done"

# Fallback repo detection: if GITHUB_DEFAULT_REPO is unset, read the git
# origin of these directories (repo root / server dir) to discover the
# project's own owner/repo. Relative to the server module's parent.
_REPO_DIR_HINTS = (
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # repo root
    os.path.dirname(os.path.abspath(__file__)),  # server/
)


def _marker_path() -> str:
    """Path to the auto-star completion marker."""
    return os.path.join(DEFAULT_MARKER_DIR, MARKER_FILENAME)


def _marker_exists() -> bool:
    """True if auto-star already ran on this install."""
    return os.path.exists(_marker_path())


def _write_marker() -> None:
    """Persist the completion marker (best-effort — never fatal)."""
    try:
        os.makedirs(DEFAULT_MARKER_DIR, exist_ok=True)
        with open(_marker_path(), "w") as f:
            f.write(f"auto-star completed at {int(time.time())}\n")
    except OSError as e:
        print(f"[auto-star] Could not write marker file: {e}")


def _gh_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": USER_AGENT,
    }


async def _gh(method: str, url: str, token: str) -> httpx.Response:
    """Single GitHub API call, no retry (auto-star is best-effort)."""
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.request(method, url, headers=_gh_headers(token))


async def _get_authenticated_user(token: str) -> str | None:
    """Return the authenticated user's login, or None on any failure."""
    try:
        resp = await _gh("GET", f"{GITHUB_API}/user", token)
        if resp.status_code == 200:
            return resp.json().get("login")
    except Exception as e:  # noqa: S110 — best-effort
        print(f"[auto-star] Could not verify GitHub user: {e}")
    return None


async def _is_starred(token: str, owner: str, repo: str) -> bool:
    """True if the authenticated user already starred owner/repo."""
    try:
        resp = await _gh("GET", f"{GITHUB_API}/user/starred/{owner}/{repo}", token)
        return resp.status_code == 204
    except Exception as e:  # noqa: S110 — best-effort
        print(f"[auto-star] Star check failed: {e}")
        return False


async def _star(token: str, owner: str, repo: str) -> bool:
    """Star owner/repo. Returns True on success (HTTP 204)."""
    try:
        resp = await _gh("PUT", f"{GITHUB_API}/user/starred/{owner}/{repo}", token)
        if resp.status_code == 204:
            return True
        # 404 = repo not found, 403 = no star permission, 401 = bad token
        print(f"[auto-star] Star request returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:  # noqa: S110 — best-effort
        print(f"[auto-star] Star request failed: {e}")
    return False


def _detect_repo_from_git() -> str | None:
    """Read the git origin URL of the project dir to find owner/repo.

    Returns 'owner/repo' or None. Best-effort — a missing .git, non-git
    install (e.g. Docker image without .git), or network mount just means
    we fall back to GITHUB_DEFAULT_REPO.
    """
    import shutil
    import subprocess

    git_bin = shutil.which("git") or "git"
    for hint_dir in _REPO_DIR_HINTS:
        try:
            out = subprocess.run(  # noqa: S603 — git resolved to abs path below; fixed argv
                [git_bin, "-C", hint_dir, "remote", "get-url", "origin"],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
            )
            url = (out.stdout or "").strip()
            if not url:
                continue
            # Accept https://github.com/owner/repo.git, git@github.com:owner/repo.git,
            # or ssh://git@github.com/owner/repo.git
            url = url.replace(".git", "").rstrip("/")
            if "github.com/" in url:
                slug = url.split("github.com/", 1)[1]
            elif "github.com:" in url:
                slug = url.split("github.com:", 1)[1]
            else:
                continue
            parts = slug.strip("/").split("/")
            if len(parts) >= 2 and parts[0] and parts[1]:
                return f"{parts[0]}/{parts[1]}"
        except Exception:  # noqa: S112 — best-effort, non-credential fallback detection
            continue
    return None


def _resolve_repo() -> str:
    """Determine which owner/repo to star.

    Order: git origin detection (the project actually being installed) →
    explicit GITHUB_DEFAULT_REPO (fallback for non-git/Docker installs) →
    empty. Git origin takes precedence because GITHUB_DEFAULT_REPO is the
    issue-sync target, which may legitimately be a *different* repo — the
    thing we want to star is the project itself.
    """
    detected = _detect_repo_from_git()
    if detected:
        print(f"[auto-star] Detected repo from git origin: {detected}")
        return detected
    if settings.github_default_repo.strip():
        return settings.github_default_repo.strip()
    return ""


async def maybe_auto_star() -> bool:
    """Star the configured repo once, if token + repo are set.

    Returns True if this run performed (or already performed) the star
    flow; False if auto-star is not applicable (no token/repo, already
    starred, owner, or marker already present). Never raises.
    """
    token = settings.github_token.strip()
    repo_full = _resolve_repo()

    if not settings.auto_star_enabled:
        print("[auto-star] Disabled (AUTO_STAR_ENABLED=false) — skipping")
        return False
    if not token:
        print("[auto-star] No GITHUB_TOKEN configured — skipping")
        return False
    if not repo_full:
        print("[auto-star] No repo to star (no GITHUB_DEFAULT_REPO, no git origin) — skipping")
        return False
    if _marker_exists():
        print("[auto-star] Already completed for this install — skipping")
        return False

    if "/" not in repo_full:
        print(f"[auto-star] GITHUB_DEFAULT_REPO '{repo_full}' is not owner/repo — skipping")
        return False

    owner, repo = repo_full.split("/", 1)

    # Never star your own repo.
    user = await _get_authenticated_user(token)
    if user is None:
        # Can't verify identity (bad token / network) — do not star blindly,
        # but mark done so we don't retry every startup with a bad token.
        print("[auto-star] Could not verify GitHub user — skipping (bad token or network)")
        _write_marker()
        return False
    if user.lower() == owner.lower():
        print(f"[auto-star] {user} owns {repo_full} — no need to star")
        _write_marker()
        return False

    if await _is_starred(token, owner, repo):
        print(f"[auto-star] {user} already starred {repo_full}")
        _write_marker()
        return True

    if await _star(token, owner, repo):
        print(f"[auto-star] ⭐ Starred {repo_full}")
        _write_marker()
        return True

    print(f"[auto-star] Could not star {repo_full} — skipping")
    _write_marker()  # Don't retry on every restart; failure is logged once
    return False


async def auto_star_task() -> None:
    """Fire-and-forget wrapper for startup: never blocks or raises."""
    try:
        await maybe_auto_star()
    except Exception as e:  # noqa: BLE001 — absolute last resort
        print(f"[auto-star] Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(maybe_auto_star())
