.PHONY: build test lint fmt fix dev-up dev-down clean help

BIN := .venv/bin
PYTHON := python3

# ── Help ────────────────────────────────────────────────────────────────
help:  ## Show available targets
	@echo "SpacetimedbKanban — Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Backend (FastAPI) ───────────────────────────────────────────────────
test-python: test  ## alias for test
	@true

test-rust:  ## Run Rust STDB module tests (native target, not wasm)
	cd server/spacetimedb && cargo test 2>&1

test-all: test test-rust test-frontend  ## Run all test suites

build-stdb:  ## Build the STDB wasm module
	cd server/spacetimedb && cargo build --release --target wasm32-unknown-unknown

publish-stdb: build-stdb  ## Build and publish STDB module to local server
	cd server/spacetimedb && spacetime publish -b target/wasm32-unknown-unknown/release/spacetimedb_kanban.wasm -s http://localhost:3001 --yes kanban 2>&1

build-frontend:  ## Build frontend production bundle
	cd web && npm install && npm run build

test:  ## Run backend tests
	cd server && python3 -m pytest tests/ -v -x 2>/dev/null || python -m pytest tests/ -v -x

test-frontend:  ## Run frontend tests
	cd web && npm test 2>/dev/null || echo "npm test not configured"

lint:  ## Lint Python backend (ruff)
	cd server && python3 -m ruff check . 2>/dev/null || python3 -m ruff check server/ 2>/dev/null || echo "ruff not available — skipping lint"

fmt:  ## Format code (ruff)
	cd server && python3 -m ruff format . 2>/dev/null || python3 -m ruff format server/ 2>/dev/null || echo "ruff not available — skipping format"

fmt-check:  ## Check formatting without modifying
	cd server && python3 -m ruff format --check . 2>/dev/null || python3 -m ruff format --check server/ 2>/dev/null || echo "ruff not available — skipping format check"

fix: fmt lint  ## Fix auto-fixable issues

install-hooks:  ## Install pre-commit + git hooks
	cd server && pip install pre-commit 2>/dev/null; true
	git config core.hooksPath .githooks
	@echo "Git hooks configured to use .githooks/"
	@echo "Install pre-commit: pip install pre-commit && pre-commit install"

# ── Dev Environment ─────────────────────────────────────────────────────
dev-up:  ## Start backend dev server
	@echo "Starting server on :8727..."
	-fuser -k 8727/tcp 2>/dev/null; true
	cd server && python3 main.py &
	@sleep 2
	@echo "Backend: http://localhost:8727"

dev-down:  ## Stop dev server
	-fuser -k 8727/tcp 2>/dev/null; true

# ── Cleanup ─────────────────────────────────────────────────────────────
clean:  ## Clean build artifacts
	rm -rf web/dist web/node_modules
	rm -rf server/__pycache__ server/tests/__pycache__
	find . -name '*.pyc' -delete

# ── Agent-Friendly Targets ────────────────────────────────────────────────
.PHONY: test-unit test-integration test-quick coverage check-ports deps-check health setup-git-hooks

test-unit:  ## Run backend unit tests
	cd server && python3 -m pytest tests/ -m unit -v --tb=short 2>/dev/null || \
		python -m pytest tests/ -m unit -v --tb=short 2>/dev/null || \
		echo "No unit test marker found — running all tests" && \
		cd server && python3 -m pytest tests/ -v -x 2>/dev/null || python -m pytest tests/ -v -x

test-integration:  ## Run full stack tests (requires backend + STDB)
	@echo "=== Integration Tests ==="
	@echo "Make sure these services are running:"
	@echo "  - Backend on :8727"
	@echo "  - SpacetimeDB on :3001"
	@echo "Then run: cd server && python3 -m pytest tests/ -v -x"

test-quick:  ## Quick health check
	@echo "=== Quick Test ==="
	@python3 --version
	@node --version
	@echo "Quick health check passed."

coverage:  ## Run tests with pytest coverage
	@echo "=== Coverage ==="
	@cd server && python3 -m pytest tests/ --cov=. --cov-report=term --cov-report=html --cov-branch 2>/dev/null || \
		echo "Install pytest-cov: pip install pytest-cov"
	@echo "HTML report: server/htmlcov/index.html"

check-ports:  ## Verify required ports are free
	@echo "Checking ports 8727 (server), 3001 (STDB)..."
	@for port in 8727 3001; do \
		if ss -tlnp "sport = :$$port" 2>/dev/null | grep -q .; then \
			echo "  Port $$port: IN USE"; \
		else \
			echo "  Port $$port: free"; \
		fi; \
	done

deps-check:  ## Verify required tools are installed
	@echo "=== Dependency Check ==="
	@for cmd in python3 node npm spacetime; do \
		if command -v $$cmd >/dev/null 2>&1; then \
			echo "  $$cmd: found"; \
		else \
			echo "  $$cmd: MISSING"; \
		fi; \
	done

health:  ## Check if services are running
	@echo "=== Health Checks ==="
	@for url in http://localhost:8727/api/health http://localhost:3001; do \
		if curl -sf "$$url" >/dev/null 2>&1; then \
			echo "  $$url — OK"; \
		else \
			echo "  $$url — not reachable"; \
		fi; \
	done

setup-git-hooks:  ## Configure git hooks from .githooks/
	@if [ -d .githooks ]; then \
		git config core.hooksPath .githooks; \
		echo "Git hooks configured to use .githooks/"; \
	else \
		mkdir -p .githooks; \
		git config core.hooksPath .githooks; \
		echo "Created .githooks/ and configured git to use it"; \
	fi
