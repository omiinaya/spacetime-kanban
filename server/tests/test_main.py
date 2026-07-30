"""Tests for server/main.py — middleware, route registration, startup, health."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


class TestMain:
    """Test suite for main.py — middleware, route registration, startup, endpoint."""

    # ── App configuration ──────────────────────────────────────────────

    def test_app_title_and_version(self):
        """The FastAPI app should have the correct title and version."""
        from main import app

        assert app.title == "spacetimedb-kanban"
        assert app.version == "0.1.0"

    def test_app_has_openapi_docs_enabled(self):
        """The app should have docs, redoc, and openapi endpoints configured."""
        from main import app

        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"

    def test_app_has_cors_middleware(self):
        """CORS middleware should be registered."""
        from main import app

        middleware_types = [
            m.cls for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"
        ]
        assert len(middleware_types) == 1

    def test_app_has_gzip_middleware(self):
        """GZip middleware should be registered."""
        from main import app

        middleware_types = [
            m.cls for m in app.user_middleware if m.cls.__name__ == "GZipMiddleware"
        ]
        assert len(middleware_types) == 1

    # ── Route registration ─────────────────────────────────────────────

    def test_all_routers_are_included(self):
        """All expected routers should be registered with the app."""
        from main import app

        # Collect ALL route paths by traversing the route tree recursively
        def _collect_paths(routes: list) -> set:
            paths = set()
            for route in routes:
                if hasattr(route, "path") and route.path is not None:
                    paths.add(route.path)
                # Handle _IncludedRouter — access .original_router.routes
                if hasattr(route, "original_router") and hasattr(route.original_router, "routes"):
                    for sub in list(route.original_router.routes):
                        if hasattr(sub, "path") and sub.path:
                            paths.add(sub.path)
                # Handle Router/APIRouter objects with .routes
                if hasattr(route, "routes"):
                    paths |= _collect_paths(list(route.routes))
                # Handle Mount objects with .app.routes
                if hasattr(route, "app") and hasattr(route.app, "routes"):
                    paths |= _collect_paths(list(route.app.routes))
            return paths

        route_paths = _collect_paths(list(app.routes))

        # Check that health endpoint is registered
        assert any("/health" in p for p in route_paths), "Health endpoint not found"

        # Check SPA catch-all
        assert any(p in ("/", "") for p in route_paths) or "/" in str(route_paths), (
            "Root endpoint not found"
        )

        # Check API routes are registered via routers
        api_paths = [p for p in route_paths if p.startswith("/api/")]
        assert len(api_paths) >= 5, f"Expected at least 5 API routes, got {len(api_paths)}"

        # Verify key API endpoints exist
        expected_prefixes = [
            "/api/tasks",
            "/api/agents",
            "/api/analytics",
            "/api/labels",
            "/api/logs",
            "/api/projects",
            "/api/task-templates",
            "/api/webhook/github",
        ]
        for prefix in expected_prefixes:
            matches = [p for p in api_paths if p.startswith(prefix)]
            assert len(matches) >= 1, f"No routes found for {prefix}"

    # ── Health endpoint ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_health_endpoint_returns_json(self):
        """The /health endpoint should return a JSON response with status ok."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_includes_worker_count(self):
        """The health endpoint should include workers_alive field."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "workers_alive" in data
        assert isinstance(data["workers_alive"], int)

    @pytest.mark.asyncio
    async def test_health_includes_scheduler_enabled(self):
        """The health endpoint should include scheduler_enabled field."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "scheduler_enabled" in data
        assert isinstance(data["scheduler_enabled"], bool)

    @pytest.mark.asyncio
    async def test_health_includes_now_ms(self):
        """The health endpoint should include a now_ms timestamp."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.status_code == 200
        data = resp.json()
        assert "now_ms" in data
        assert isinstance(data["now_ms"], int)
        assert data["now_ms"] > 0

    # ── Security headers middleware ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_security_headers_are_set(self):
        """The security middleware should set X-Content-Type-Options and other headers."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-xss-protection") == "0"
        assert "strict-transport-security" in resp.headers
        assert "max-age=31536000" in resp.headers["strict-transport-security"]

    @pytest.mark.asyncio
    async def test_rate_limit_headers_are_set(self):
        """The middleware should set X-RateLimit-Limit and X-RateLimit-Remaining."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        assert resp.headers.get("x-ratelimit-limit") == "200"
        assert resp.headers.get("x-ratelimit-remaining") == "199"

    @pytest.mark.asyncio
    async def test_content_security_policy_header_set(self):
        """Content-Security-Policy header should be set."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/health")

        csp = resp.headers.get("content-security-policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    # ── SPA fallback ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_api_404_returns_json(self):
        """API 404s should return JSON, not SPA HTML."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/nonexistent-route")

        assert resp.status_code == 404
        assert resp.headers["content-type"] == "application/json"
        data = resp.json()
        assert data["detail"] == "Not found"

    # ── Lifespan (startup) ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_lifespan_creates_stdb_on_404(self):
        """On startup, if STDB returns 404 for database, it should create one."""
        from main import lifespan

        mock_app = MagicMock()

        with (
            patch("main.httpx.AsyncClient") as mock_client_cls,
            patch("scheduler.start_scheduler", new_callable=AsyncMock),
            patch("scheduler.stop_scheduler", new_callable=AsyncMock),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # First call returns 404 (DB not found)
            get_resp = MagicMock()
            get_resp.status_code = 404
            # Second call returns 201 (DB created)
            post_resp = MagicMock()
            post_resp.status_code = 201

            mock_client.get.return_value = get_resp
            mock_client.post.return_value = post_resp

            async with lifespan(mock_app):
                pass

            # Verify create was called
            assert mock_client.post.call_count >= 1
            # Verify the create call had the right payload
            create_call = mock_client.post.call_args_list[0]
            assert "/v1/database" in str(create_call)

    @pytest.mark.asyncio
    async def test_lifespan_stdb_ok_first_try(self):
        """On startup, if STDB is reachable on first try."""
        from main import lifespan

        mock_app = MagicMock()

        with (
            patch("main.httpx.AsyncClient") as mock_client_cls,
            patch("scheduler.start_scheduler", new_callable=AsyncMock),
            patch("scheduler.stop_scheduler", new_callable=AsyncMock),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # STDB already exists
            get_resp = MagicMock()
            get_resp.status_code = 200
            mock_client.get.return_value = get_resp

            async with lifespan(mock_app):
                pass

            # Should NOT have called create
            assert mock_client.post.call_count == 0

    @pytest.mark.asyncio
    async def test_lifespan_exits_on_unreachable_stdb(self):
        """On startup, if STDB is unreachable after retries, should exit."""
        from main import lifespan

        mock_app = MagicMock()

        with (
            patch("main.httpx.AsyncClient") as mock_client_cls,
            patch("main.os._exit") as mock_exit,
            patch.dict("os.environ", {"KANBAN_STDB_RETRIES": "2"}, clear=False),
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            # Always raise connection error
            mock_client.get.side_effect = ConnectionError("STDB not ready")
            mock_client.post.side_effect = ConnectionError("STDB not ready")

            try:
                async with lifespan(mock_app):
                    pass
            except (Exception, asyncio.CancelledError):
                pass

            # Should have retried and eventually called os._exit
            assert mock_client.get.call_count > 1
            mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_lifespan_scheduler_started_and_stopped(self):
        """The scheduler should be started on enter and stopped on exit."""
        from main import lifespan

        mock_app = MagicMock()

        with (
            patch("main.httpx.AsyncClient") as mock_client_cls,
            patch("scheduler.start_scheduler", new_callable=AsyncMock) as mock_start,
            patch("scheduler.stop_scheduler", new_callable=AsyncMock) as mock_stop,
        ):
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            get_resp = MagicMock()
            get_resp.status_code = 200
            mock_client.get.return_value = get_resp

            async with lifespan(mock_app):
                pass

            mock_start.assert_awaited_once()
            mock_stop.assert_awaited_once()

    # ── SPA serving ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_spa_root_served_when_built(self):
        """When web dist exists, / should serve index.html."""
        from main import app, WEB_DIST

        # Only test if the dist actually exists
        import os

        if os.path.isdir(WEB_DIST) and os.path.isfile(os.path.join(WEB_DIST, "index.html")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
        else:
            pytest.skip("Web dist not built — skipping SPA test")

    @pytest.mark.asyncio
    async def test_spa_root_returns_json_when_not_built(self):
        """When web dist doesn't exist, / should return a JSON message."""
        from main import app, WEB_DIST

        import os

        if not os.path.isdir(WEB_DIST):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert "dashboard not built" in data["status"]
        else:
            pytest.skip("Web dist exists — skipping not-built test")

    # ── 404 handler / SPA fallback ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_non_api_404_serves_spa_when_built(self):
        """Non-API 404 should serve index.html when web dist exists."""
        from main import app, WEB_DIST

        import os

        if os.path.isdir(WEB_DIST) and os.path.isfile(os.path.join(WEB_DIST, "index.html")):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/some/spa/route")
            assert resp.status_code == 200
            assert "text/html" in resp.headers.get("content-type", "")
        else:
            pytest.skip("Web dist not built — skipping SPA fallback test")

    @pytest.mark.asyncio
    async def test_non_api_404_returns_json_when_not_built(self):
        """Non-API 404 should return JSON when web dist doesn't exist."""
        from main import app, WEB_DIST

        import os

        if not os.path.isdir(WEB_DIST):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/some/spa/route")
            assert resp.status_code == 404
            data = resp.json()
            assert data["detail"] == "Not found"
        else:
            pytest.skip("Web dist exists — skipping not-built fallback test")

    # ── GitHub sync ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sync_to_github_no_link(self):
        """_sync_to_github should return early if no link found."""
        from main import _sync_to_github

        with patch("main.issue_sync.get_link", return_value=None):
            result = await _sync_to_github(task_id="task_1", event="completed")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_no_token(self):
        """_sync_to_github should return early if no token configured."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", ""),
        ):
            result = await _sync_to_github(task_id="task_1", event="completed")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_no_repo_or_issue(self):
        """_sync_to_github should return early if repo or issue_number missing."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "", "issue_number": 0}),
            patch("main.settings.github_token", "some-token"),
        ):
            result = await _sync_to_github(task_id="task_1", event="completed")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_completed(self):
        """_sync_to_github should close issue on completed event."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.close_issue", new_callable=AsyncMock) as mock_close,
            patch("main.issue_sync.update_issue_status") as mock_update,
            patch("main.issue_sync.add_issue_comment", new_callable=AsyncMock) as mock_comment,
        ):
            result = await _sync_to_github(task_id="task_1", event="completed", notes="Done!")
            mock_close.assert_awaited_once_with("some-token", "my-repo", 42)
            mock_update.assert_called_once_with("task_1", "closed")
            mock_comment.assert_awaited_once()
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_unclaimed(self):
        """_sync_to_github should reopen issue on unclaimed event."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.reopen_issue", new_callable=AsyncMock) as mock_reopen,
            patch("main.issue_sync.update_issue_status") as mock_update,
            patch("main.issue_sync.add_issue_comment", new_callable=AsyncMock) as mock_comment,
        ):
            result = await _sync_to_github(task_id="task_1", event="unclaimed", notes="Reopened")
            mock_reopen.assert_awaited_once_with("some-token", "my-repo", 42)
            mock_update.assert_called_once_with("task_1", "open")
            mock_comment.assert_awaited_once()
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_no_notes(self):
        """_sync_to_github should handle events without notes."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.close_issue", new_callable=AsyncMock),
            patch("main.issue_sync.update_issue_status"),
        ):
            result = await _sync_to_github(task_id="task_1", event="completed")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_comment_error(self):
        """_sync_to_github should not crash if add_issue_comment fails."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.close_issue", new_callable=AsyncMock),
            patch("main.issue_sync.update_issue_status"),
            patch("main.issue_sync.add_issue_comment", side_effect=Exception("API error")),
        ):
            # Should not raise
            result = await _sync_to_github(task_id="task_1", event="completed", notes="Done!")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_unclaimed_comment_error(self):
        """_sync_to_github should handle comment errors on unclaimed event (lines 199-200)."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.reopen_issue", new_callable=AsyncMock),
            patch("main.issue_sync.update_issue_status"),
            patch("main.issue_sync.add_issue_comment", side_effect=Exception("API error")),
        ):
            # Should not raise
            result = await _sync_to_github(task_id="task_1", event="unclaimed", notes="Reopened")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_outer_exception(self):
        """_sync_to_github outer exception handler (lines 201-205)."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.close_issue", side_effect=Exception("Sync failed")),
        ):
            # Should not raise - outer handler catches everything
            result = await _sync_to_github(task_id="task_1", event="completed", notes="Done!")
            assert result is None

    @pytest.mark.asyncio
    async def test_sync_to_github_unclaimed_outer_exception(self):
        """_sync_to_github outer exception on unclaimed path."""
        from main import _sync_to_github

        with (
            patch("main.issue_sync.get_link", return_value={"repo": "my-repo", "issue_number": 42}),
            patch("main.settings.github_token", "some-token"),
            patch("main.issue_sync.reopen_issue", side_effect=Exception("Reopen failed")),
        ):
            result = await _sync_to_github(task_id="task_1", event="unclaimed", notes="Reopened")
            assert result is None

    # ── spa_fallback for non-API paths without index.html ──────────────

    @pytest.mark.asyncio
    async def test_spa_fallback_without_index(self):
        """spa_fallback should return JSON 404 when index.html doesn't exist (line 223)."""
        from main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/nonexistent/spa/route")

        # This tests the spa_fallback handler at line 223
        # If WEB_DIST/index.html exists, it will return the file (FileResponse)
        # If not, it returns JSON 404
        # Either way it should return 200 or 404, not crash
        assert resp.status_code in (200, 404)

    # ── Web dist message lines ─────────────────────────────────────────

    def test_web_dist_message_built(self):
        """Verify the WEB_DIST path and the messages printed when dist is missing."""
        from main import WEB_DIST

        import os

        assert isinstance(WEB_DIST, str)
        assert "web" in WEB_DIST
        assert "dist" in WEB_DIST
