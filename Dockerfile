# =============================================================================
# Multi-stage Dockerfile for SpacetimeDB Kanban
# Builds: frontend (React/Vite), STDB module (Rust WASM), Python backend
# =============================================================================

# Stage 1: Build frontend (React / Vite)
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY web/ .
RUN npm run build

# Stage 2: Build SpacetimeDB WASM module
FROM rust:1.93 AS module-builder
RUN rustup target add wasm32-unknown-unknown
WORKDIR /app/module
COPY server/spacetimedb/Cargo.toml server/spacetimedb/Cargo.lock* ./
COPY server/spacetimedb/src/ ./src/
RUN cargo build --release --target wasm32-unknown-unknown && \
    cp target/wasm32-unknown-unknown/release/spacetime_kanban.wasm /tmp/module.wasm

# Stage 3: Runtime — Python server
FROM python:3.12-slim

WORKDIR /app

# Runtime OS dependencies + spacetime CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ARG STDB_VERSION=2.6.1
RUN curl -fsSL "https://github.com/spacetimedb/spacetimedb/releases/download/v${STDB_VERSION}/spacetime-linux-x86_64.tar.gz" \
    | tar xz -C /usr/local/bin/ && \
    chmod +x /usr/local/bin/spacetime

# Install Python dependencies
COPY server/requirements.txt server/
RUN pip install --no-cache-dir -r server/requirements.txt

# Copy application code
COPY server/ server/
# .env.example is gitignored/dockerignored — create a placeholder so the
# build never depends on an ignored file (config comes from env at runtime).
COPY server/.env.example server/.env.example
RUN cp server/.env.example ./.env.example 2>/dev/null || true

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/web/dist/ web/dist/

# Copy only the compiled WASM module (not the entire target directory)
COPY --from=module-builder /tmp/module.wasm server/spacetimedb/module.wasm

# Copy and set up entrypoint
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create non-root user
RUN addgroup --system kanban && adduser --system --ingroup kanban kanban && \
    chown -R kanban:kanban /app

USER kanban

EXPOSE 8727

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8727/api/health')" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
