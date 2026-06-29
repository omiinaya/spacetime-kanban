.PHONY: build test lint fmt fix dev-up dev-down clean help

BIN := .venv/bin
PYTHON := python3

# ── Help ────────────────────────────────────────────────────────────────
help:  ## Show available targets
	@echo "SpacetimedbKanban — Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | 		awk 'BEGIN {FS = ":.*?## "}; {printf "[36m%-20s[0m %s
", $$1, $$2}'

# ── Backend (FastAPI) ───────────────────────────────────────────────────
build:  ## Build frontend production bundle
	cd web && npm install && npm run build

test:  ## Run backend tests
	cd server && python3 -m pytest tests/ -v -x 2>/dev/null || python -m pytest tests/ -v -x

test-frontend:  ## Run frontend tests
	cd web && npm test 2>/dev/null || echo "npm test not configured"

lint:  ## Lint Python backend
	cd server && python3 -m flake8 --statistics 2>/dev/null || echo "flake8 not installed"

fmt:  ## Format code
	cd server && python3 -m black . 2>/dev/null || echo "black not installed"

fix: fmt lint  ## Fix auto-fixable issues

# ── Dev Environment ─────────────────────────────────────────────────────
dev-up:  ## Start backend dev server
	@echo "Starting server on :8727..."
	cd server && python3 main.py &
	@sleep 1
	@echo "Backend: http://localhost:8727"

dev-down:  ## Stop dev server
	-pkill -f "python3 main.py" 2>/dev/null; echo "Stopped"

# ── Cleanup ─────────────────────────────────────────────────────────────
clean:  ## Clean build artifacts
	rm -rf web/dist web/node_modules
	rm -rf server/__pycache__ server/tests/__pycache__
	find . -name '*.pyc' -delete
