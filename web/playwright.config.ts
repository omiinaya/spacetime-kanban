import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 2,
  // Single-worker uvicorn serves the SPA + API + STDB subscription traffic.
  // 4 parallel browsers overload it (health probes time out, requests queue).
  timeout: 60000,
  // Live board renders 1,000+ tasks via STDB subscription — 5s default is not enough
  expect: { timeout: 15000 },
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['list'],
  ],
  use: {
    // E2E runs against the PRODUCTION server (built SPA + real API on :8727).
    // The vite dev server was previously used (:4444) but its esbuild service
    // crashes under Playwright-spawned processes ("The service is no longer
    // running"), and testing prod is closer to what users actually see.
    baseURL: 'http://localhost:8727',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        browserName: 'chromium',
      },
    },
  ],
  // No webServer — expects the kanban server on :8727 (already running in dev/CI).
})
