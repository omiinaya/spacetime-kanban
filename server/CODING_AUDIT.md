# Code Quality Audit — spacetimedb-kanban server/

**Date:** 2026-07-28  
**Tool:** ruff 0.15.21, pytest 9.1.1, coverage 7.15.2  
**Scanned:** 50 source files + 20 test files  
**Total LOC:** 16,852

---

## Executive Summary

| Metric | Value |
|---|---|
| Total issues found | **2,540** |
| Fixable automatically | **282** (plus 409 with `--unsafe-fixes`) |
| Test count | **180 passed, 8 skipped** |
| Code coverage | **51%** overall |
| Format compliance | **71/80 files already formatted** (9 need formatting) |

---

## 1. CRITICAL ISSUES (Security & Correctness)

### 1A. Security (S-class: 106 findings)

| Issue | Count | Severity |
|---|---|---|
| `S310` — `urlopen()` with `file:` or custom schemes | 29 | **HIGH** |
| `S607` — `subprocess` with partial executable path | 32 | **HIGH** |
| `S603` — `subprocess` call without shell=True check | 10 | **MEDIUM** |
| `S104` — Binding to all interfaces (0.0.0.0) | 1 | **MEDIUM** |
| `S110` — `try-except-pass` | 17 | **MEDIUM** |
| `S112` — `try-except-continue` | 3 | **MEDIUM** |
| `S101` — `assert` in non-test code | 14 | **LOW** |

**Key files with security issues:**
- `server/_fast_seed.py` — 6 security issues (urlopen, partial path)
- `server/_task_fountain.py` — 10 security issues (urlopen, subprocess, except-pass)
- `server/mcp_server.py` — 9 S310 urlopen calls
- `server/workers/mechanical/__init__.py` — 29 security issues
- `server/scanners/*.py` — 16 security issues across 3 files

### 1B. Blind Exception Handling (BLE001: 94 findings)

94 instances of bare `except Exception:` across the codebase. **Worst offenders:**

| File | Count |
|---|---|
| `server/scheduler.py` | 28 |
| `server/workers/mechanical/__init__.py` | 17 |
| `server/scheduler_low_backlog.py` | 8 |
| `server/scanners/runner.py` | 6 |
| `server/main.py` | 5 |

These blanket exception handlers can mask real failures, making debugging difficult.

### 1C. Dangling asyncio Tasks (RUF006: 16 findings)

`asyncio.create_task()` / `loop.create_task()` called WITHOUT storing a reference:

| File | Count | Impact |
|---|---|---|
| `server/routes/tasks.py` | 10 | Tasks may be garbage-collected mid-flight |
| `server/routes/github.py` | 5 | Webhook processing tasks may be dropped |
| `server/scheduler.py` | 1 | Background loop task may be collected |

**This is a potential production bug** — un-referenced asyncio tasks can be garbage collected before completion, causing silent failures.

### 1D. Deprecated datetime Usage (DTZ: 12 findings)

| File | Issue |
|---|---|
| `server/issue_sync.py:146` | `utcnow()` — use `now(tz=UTC)` |
| `server/routes/analytics.py` | 7 deprecated datetime calls |
| `server/webhooks.py` | 4 `utcnow()` calls |

`datetime.utcnow()` and `datetime.utcfromtimestamp()` are deprecated since Python 3.12.

---

## 2. CODE COMPLEXITY (C901: 36 findings)

Functions exceeding complexity threshold of 10:

| Complexity | Function | File |
|---|---|---|
| **48** | `handle_typed_errors` | `workers/mechanical/__init__.py` |
| **38** | `handle_extract_module` | `workers/mechanical/__init__.py` |
| **25** | `handle_add_index_btree` | `workers/mechanical/__init__.py` |
| **23** | `handle_add_test_scaffold` | `workers/mechanical/__init__.py` |
| **22** | `github_webhook` | `routes/github.py` |
| **22** | `scan_prod_readiness` | `scanners/layer_security.py` |
| **21** | `stale_watcher` | `scheduler.py` |
| **20** | `run_llm_worker` | `workers/llm.py` |
| **19** | `_generate_improvement_tasks` | `scheduler_low_backlog.py` |
| **19** | `_extract_sats_val` | `shared.py` |
| **18** | `task_archiver` | `scheduler.py` |
| **18** | `handle_run_tests` | `workers/mechanical/__init__.py` |

**Additional complexity issues:**
- 24 `PLR0912` (too many branches)
- 14 `PLR0915` (too many statements)
- 6 `PLR0911` (too many return statements)
- 4 `PLR0913` (too many arguments)

---

## 3. CODE STYLE & MAINTAINABILITY

### 3A. Type Annotations (ANN: 706 findings)

| Rule | Count | Description |
|---|---|---|
| `ANN201` | 352 | Missing return type on public function |
| `ANN001` | 321 | Missing type on function argument |
| `ANN202` | 23 | Missing return type on private function |
| `ANN401` | 10 | Using `Any` type |

**Only 5% of public functions have return type annotations.** This significantly impacts IDE support and static analysis.

### 3B. Print Statements (T201: 125 findings)

125 `print()` calls found outside scripts. These should be `logging.*` calls in production code.

| Worst files | Count |
|---|---|
| `server/workers/mechanical/__init__.py` | 35 |
| `server/scheduler.py` | 14 |
| `server/main.py` | 9 |
| `server/_fast_seed.py` | 9 |
| `server/_task_fountain.py` | 5 |
| `server/scanners/runner.py` | 5 |

### 3C. Import Issues

| Issue | Count | Details |
|---|---|---|
| `PLC0415` — import inside function | 62 | Many `import` statements at function start instead of module top |
| `RUF100` — unused `# noqa` directives | 29 | Suppressions that no longer suppress anything |

### 3D. Subprocess Safety (PLW1510: 34 findings)

34 `subprocess.run()` calls without `check=True`, meaning they won't raise on non-zero exit codes, potentially allowing silent failures.

---

## 4. TEST HEALTH

### 4A. Test Results

| Result | Count |
|---|---|
| Passed | **180** |
| Skipped (integration tests) | **8** |
| Failed | **0** |
| Test coverage | **51%** |

### 4B. Critical Test Issue — Duplicate Test Files

**14 duplicate test files** exist at the root `server/` level that are exact copies of files in `server/tests/`:

| Root-level file | tests/ counterpart | Lines |
|---|---|---|
| `server/test__fast_seed.py` | `server/tests/test__fast_seed.py` | 12 |
| `server/test__task_fountain.py` | `server/tests/test__task_fountain.py` | 12 |
| `server/test_auth.py` | `server/tests/test_auth.py` | 12 |
| `server/test_config.py` | `server/tests/test_config.py` | 12 |
| `server/test_issue_sync.py` | `server/tests/test_issue_sync.py` | 12 |
| `server/test_main.py` | `server/tests/test_main.py` | 12 |
| `server/test_mcp_server.py` | `server/tests/test_mcp_server.py` | 11 |
| `server/test_models.py` | `server/tests/test_models.py` | 12 |
| `server/test_responses.py` | `server/tests/test_responses.py` | 12 |
| `server/test_scheduler.py` | `server/tests/test_scheduler.py` | 12 |
| `server/test_scheduler_low_backlog.py` | `server/tests/test_scheduler_low_backlog.py` | 12 |
| `server/test_shared.py` | `server/tests/test_shared.py` | 12 |
| `server/test_webhook_dispatcher.py` | `server/tests/test_webhook_dispatcher.py` | 12 |
| `server/test_webhooks.py` | `server/tests/test_webhooks.py` | 12 |

These are all trivial `assert True` stubs. The proper tests with real logic live in `tests/test_api.py` (2,135 lines), `tests/test_e2e_http.py` (368 lines), `tests/test_sats_parser.py` (467 lines), and `tests/test_integration_stdb.py` (263 lines).

### 4C. Coverage by Area

| Area | Coverage |
|---|---|
| Models | **100%** |
| Auth | **100%** |
| Config | **100%** |
| API Keys | **100%** |
| Labels | **87%** |
| Rules | **95%** |
| Tasks routes | **69%** |
| Health | **72%** |
| Webhook subs | **71%** |
| Analytics | **53%** |
| Agents | **50%** |
| Shared helpers | **66%** |
| Main/app | **44%** |
| Issue sync | **33%** |
| Webhooks | **28%** |
| Webhook dispatcher | **24%** |
| Scheduler | **6%** (worst) |
| Scheduler low backlog | **9%** |
| Scanners | **~10-50%** |
| _fast_seed / _task_fountain | **8-14%** |

---

## 5. FORMATTING & CONVENTIONS

### 5A. Format check

9 files need reformatting (71 are already compliant):
- `server/_fast_seed.py`
- `server/_task_fountain.py`
- `server/mcp_server.py`
- `server/scanners/layer_architecture.py`
- `server/scanners/layer_docs.py`
- `server/test_mcp_server.py`
- `server/tests/test_api.py`
- `server/tests/test_mcp_server.py`
- `server/workers/mechanical/__init__.py`

### 5B. Missing Trailing Commas (COM812: 215 findings)

215 instances of missing trailing commas in multi-line constructs.

### 5C. Commented-out Code (ERA001: 10 findings)

Found in:
- `server/workers/mechanical/__init__.py` (5 instances)
- `server/scheduler.py` (2 instances)
- `server/routes/tasks.py` (1 instance)
- Others

### 5D. TODO/FIXME Tracking (TD002/TD003/FIX002: 84 findings)

- 28 lines contain TODO/FIXME without an author (`TD002`)
- 28 lines contain TODO/FIXME without a link to an issue (`TD003`)
- 28 line-level markers (`FIX002`)

---

## 6. DEPENDENCY ISSUES

### 6A. Missing Dependencies

- `mcp` package was missing and had to be installed to run MCP server tests
- `pytest-cov` had to be installed for coverage reporting (though listed in pip list earlier)

### 6B. requirements.txt

The `server/requirements.txt` only lists 6 core packages and is missing many runtime dependencies (fastapi, uvicorn, httpx, pydantic, pydantic-settings, python-dotenv). All other dependencies (pytest, ruff, bcrypt, pyyaml, websockets, etc.) are not pinned.

---

## 7. TOP PRIORITY RECOMMENDATIONS

### P0 — Fix Now
1. **Store references to all `asyncio.create_task()` calls** — 16 dangling tasks that may be GC'd
2. **Remove 14 duplicate stub test files** from `server/` root directory
3. **Add `check=True` to `subprocess.run()` calls** — 34 calls that silently ignore failures

### P1 — Security
4. **Replace bare `except Exception:` with specific exception types** — 94 instances
5. **Replace `except: pass` with at least logging** — 17 instances
6. **Review all `urlopen()` calls for scheme restrictions** — 29 instances

### P2 — Maintainability
7. Add type annotations to public functions (706 missing annotations)
8. Replace `print()` with `logging.*` (125 instances)
9. Refactor the 9 most complex functions (complexity > 20)
10. Replace deprecated `datetime.utcnow()` and `utcfromtimestamp()` calls

### P3 — Cleanup
11. Run `ruff format` on the 9 unformatted files
12. Remove commented-out code (10 instances)
13. Move `import` statements to module top level (62 instances)
14. Remove unused `# noqa` directives (29 instances)
15. Fill in missing TODOs with issue references

---

## Top 5 Files with Most Issues

| File | LOC | Critical Issues | Complexity Score | Notes |
|---|---|---|---|---|
| `server/workers/mechanical/__init__.py` | 1,837 | 110+ | Very High | Largest file, 10 complex functions, copious subprocess & exception issues |
| `server/scheduler.py` | 1,255 | 60+ | High | 28 blind excepts, multiple complex coroutines, 0% test coverage on critical paths |
| `server/routes/tasks.py` | 854 | 25+ | Medium | 10 dangling asyncio tasks, many bare excepts |
| `server/mcp_server.py` | 1,334 | 15+ | Medium | 9 urlopen calls, inline import, type annotation gaps |
| `server/_fast_seed.py` | 401 | 20+ | Medium | Security concerns with urlopen & subprocess |

---
*Generated by ruff 0.15.21 static analysis + pytest results*
