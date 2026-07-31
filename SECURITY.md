# Security Notes

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
