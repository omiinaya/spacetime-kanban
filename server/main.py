import asyncio
import os
import re
import sys
import time
from contextlib import asynccontextmanager

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import issue_sync
from config import settings
from routes.agents import router as agents_router
from routes.analytics import router as analytics_router
from routes.apikeys import router as apikeys_router
from routes.dispatcher import router as dispatcher_router
from routes.github import router as github_router
from routes.health import router as health_router
from routes.labels import router as labels_router
from routes.logs import router as logs_router
from routes.ops import router as ops_router
from routes.projects import router as projects_router
from routes.rules import router as rules_router
from routes.scanner import router as scanner_router
from routes.tasks import router as tasks_router
from routes.templates import router as templates_router
from routes.webhook_subs import router as webhook_subs_router

# ── Lifespan: wait for STDB before accepting requests ──────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: wait for STDB, create DB if missing."""
    import os

    max_retries = int(os.environ.get("KANBAN_STDB_RETRIES", "30"))
    stdb_ok = False
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{settings.stdb_base_url}/v1/database/{settings.stdb_db}")
            if resp.status_code == 404:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.post(
                        f"{settings.stdb_base_url}/v1/database",
                        json={"name": settings.stdb_db},
                    )
                print(f"Created database: {settings.stdb_db} (status={resp.status_code})")
            stdb_ok = True
            break
        except Exception as e:
            if attempt < max_retries:
                wait = min(attempt * 2, 30)
                print(f"Waiting for STDB ({attempt}/{max_retries}): {e} — retrying in {wait}s")
                await asyncio.sleep(wait)
            else:
                print(f"STDB unreachable after {max_retries} attempts: {e}")
    if not stdb_ok:
        print(f"CRITICAL: Could not reach SpacetimeDB at {settings.stdb_base_url} — exiting")
        os._exit(1)

    # ── Start background scheduler ──
    from scheduler import start_scheduler, stop_scheduler

    await start_scheduler()

    # ── Auto-star the project repo (best-effort, fire-and-forget) ──
    # Runs once per install when a GitHub token is configured: stars the
    # default repo unless the user already starred it or owns it. Never
    # blocks or crashes startup.
    try:
        from auto_star import auto_star_task

        asyncio.create_task(auto_star_task())
    except Exception as e:  # noqa: S110 — auto-star is best-effort
        print(f"[startup] Auto-star task failed to schedule: {e}")

    yield

    # ── Stop background scheduler on shutdown ──
    await stop_scheduler()


app = FastAPI(
    title="spacetime-kanban",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Compression ──
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Security headers + rate limit info ──
@app.middleware("http")
async def add_security_and_rate_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'"
    )
    # Static rate-limit headers (actual enforcement via app config)
    response.headers["X-RateLimit-Limit"] = "200"
    response.headers["X-RateLimit-Remaining"] = "199"
    return response


# ── Endpoints ────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint — returns JSON for monitoring."""
    from scheduler import _get_worker_count

    return {
        "status": "ok",
        "now_ms": int(time.time() * 1000),
        "workers_alive": _get_worker_count(),
        "scheduler_enabled": settings.scheduler_enabled,
    }


WEB_DIST = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
if os.path.isdir(WEB_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(WEB_DIST, "assets")), name="assets")
else:
    print(f"⚠ Web dist not found at {WEB_DIST} — dashboard not available")
    print("  Build it: cd web && npm run build")


@app.get("/")
async def serve_spa():
    index = os.path.join(WEB_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"status": "dashboard not built — run 'npm run build' in web/"}


# ── Endpoints start here ──────────────────────────────────────────────


# Priority scoring route must be BEFORE /api/tasks/{task_id} to avoid shadowing


# ── Task Logs ────────────────────────────────────────────────────────


async def _sync_to_github(task_id: str, event: str, notes: str = ""):
    """Push a kanban task state change back to a linked GitHub issue."""
    link = issue_sync.get_link(task_id)
    if not link:
        return  # No GitHub issue linked
    token = settings.github_token
    if not token:
        return  # No token configured
    repo = link.get("repo", "")
    issue_number = link.get("issue_number", 0)
    if not repo or not issue_number:
        return
    try:
        if event == "completed":
            await issue_sync.close_issue(token, repo, issue_number)
            issue_sync.update_issue_status(task_id, "closed")
            if notes:
                try:
                    await issue_sync.add_issue_comment(
                        token, repo, issue_number, f"✅ Kanban task completed: {notes}"
                    )
                except Exception as e:
                    print(f"[warn] Failed to add comment for issue {issue_number}: {e}")
        elif event == "unclaimed":
            await issue_sync.reopen_issue(token, repo, issue_number)
            issue_sync.update_issue_status(task_id, "open")
            if notes:
                try:
                    await issue_sync.add_issue_comment(
                        token, repo, issue_number, f"🔄 Kanban task reopened: {notes}"
                    )
                except Exception as e:
                    print(f"[warn] Failed to add reopen comment for issue {issue_number}: {e}")
    except Exception as e:
        print(f"[warn] Issue sync error: {e}")
        import logging

        logging.getLogger(__name__).warning(f"Failed to sync task {task_id} to GitHub: {e}")


@app.exception_handler(404)
async def spa_fallback(request, exc):
    """Catch-all for SPA client-side routing."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    index = os.path.join(WEB_DIST, "index.html")
    if os.path.isfile(index):
        return FileResponse(
            index,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return JSONResponse(status_code=404, content={"detail": "Not found"})


# ── Branch Validation Pattern ─────────────────────────────────────────

BRANCH_PATTERN = re.compile(
    r"^(?:feature|fix|chore|refactor|docs|test)/"
    r"kanban-([a-zA-Z0-9_]+)--"
    r".+$"
)


# ── Route Modules ────────────────────────────────────────────────────
# Registered after inline endpoints so main.py handlers take priority
# on overlapping paths. Route-module-only endpoints (analytics/burndown,
# analytics/calendar, git webhooks, agent capabilities) become active.

app.include_router(agents_router)
app.include_router(analytics_router)
app.include_router(github_router)
app.include_router(labels_router)
app.include_router(logs_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(templates_router)
app.include_router(apikeys_router)
app.include_router(dispatcher_router)
app.include_router(health_router)
app.include_router(ops_router)
app.include_router(rules_router)
app.include_router(scanner_router)
app.include_router(webhook_subs_router)


# ── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.server_port,
        reload=False,
        workers=1,
    )
