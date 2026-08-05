# Security Notes

## Authentication model

- **Mutations** (task create/update/delete, agent register/heartbeat, API-key
  create/revoke, webhook subscribe, etc.) require an API key when the
  `API_KEY` env var is set. Auth is **disabled by default** (empty `API_KEY`)
  — suitable for a local/demo deployment; **set `API_KEY` in production**.
- **Reads** (`GET` endpoints) are open by design — the kanban board is meant
  to be viewable. The one exception is `GET /api/api-keys`, which is
  auth-gated because it exposes API-key metadata.
- The STDB `api_keys` table is declared `public` (the backend reads it via
  the unauthenticated SQL endpoint). It stores only **SHA-256 hashes** of
  keys, never plaintext, but key names/scopes/`created_by` metadata is
  world-readable to anyone with access to the STDB module. If you deploy the
  module on a public STDB node, set `API_KEY` and consider that key metadata
  is exposed at the module layer.

## Dependency advisories

### react-router-dom (GHSA-qwww-vcr4-c8h2) — NOT APPLICABLE

`npm audit` reports 2 high-severity findings from `react-router` 7.12.0–8.2.0
(GHSA-qwww-vcr4-c8h2, "RSC Mode CSRF Bypass Allows Action Execution Before 400
Response").

**Why this does not affect this project:**

- The advisory itself states: *"This only affects your application if you are
  using the unstable RSC APIs."*
- This project is a **client-only SPA** (Vite build → static `dist/`). It uses
  only stable client-side APIs: `BrowserRouter`, `Routes`, `Route`, `Link`,
  `useLocation`, `useNavigate`, `MemoryRouter` (tests).
- There are **zero** imports of `react-router` RSC/SSR APIs (`createStaticRouter`,
  `createStaticHandler`, `RouterProvider`, `unstable_*`).

**Why we do not downgrade to silence the report:**

- No patched version exists yet (`7.18.2` is the latest; the patched `8.3.0`
  range has not been published).
- The only "fix" npm offers is a downgrade to `7.11.0`, which falls back below
  the range that fixed the *original* CVE-2026-22030 — a downgrade would trade
  one advisory for the other and lose 7 minor versions of fixes.

**Decision:** keep `react-router-dom@^7.18.2` (latest). Revisit when a patched
release (`>= 8.3.0`) is published.

## Verification method

- `npm audit` — reviewed per-advisory, exceptions documented here.
- Python deps — checked via `pip-audit` in CI/release prep.
- Rust/STDB module — `cargo audit` in release prep.
