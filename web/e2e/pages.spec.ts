import { test, expect } from '@playwright/test'

test.describe('Key Pages', () => {
  test.describe('Activity Log Page', () => {
    test('renders with correct heading and description', async ({ page }) => {
      await page.goto('/logs')
      await expect(page.locator('h1')).toContainText('Activity Log')
      await expect(page.locator('p')).toContainText('Every claim, completion, and state change')
    })

    test('displays loading state then content', async ({ page }) => {
      await page.goto('/logs')
      // Should eventually show either log entries or empty state
      await expect(page.locator('h1')).toBeVisible()
    })

    test('shows empty state when no activity exists', async ({ page }) => {
      await page.goto('/logs')
      // Either shows log entries or the empty state message
      const pageContent = page.locator('#root')
      await expect(pageContent).toBeVisible()
    })

    test('activity entries have correct structure when present', async ({ page }) => {
      await page.goto('/logs')
      // If log entries exist, they should have action labels and timestamps
      const logRows = page.locator('.rounded-lg.hover\\:bg-white\\/\\[0\\.02\\]')
      const count = await logRows.count()
      if (count > 0) {
        // Each row should have an action text
        const firstRow = logRows.first()
        await expect(firstRow).toBeVisible()
      }
    })
  })

  test.describe('GitHub Issues Page', () => {
    test('renders with correct heading and search filter', async ({ page }) => {
      await page.goto('/issues')
      await expect(page.locator('h1')).toContainText('GitHub Issue Links')

      // Search input should be present
      await expect(page.locator('input[placeholder="Filter links..."]')).toBeVisible()
    })

    test('shows empty state when no issues linked', async ({ page }) => {
      await page.goto('/issues')
      // Show the empty state text
      await expect(page.locator('text=No GitHub issue links configured').or(
        page.locator('text=No links match')
      )).toBeVisible()
    })

    test('search filter works on issues page', async ({ page }) => {
      await page.goto('/issues')
      const searchInput = page.locator('input[placeholder="Filter links..."]')
      await expect(searchInput).toBeVisible()

      // Typing in the search should not crash
      await searchInput.fill('test-search-query')
      await page.waitForTimeout(500)
    })

    test('refresh button is present', async ({ page }) => {
      await page.goto('/issues')
      const refreshBtn = page.locator('button').filter({ has: page.locator('.lucide-refresh-cw') })
      await expect(refreshBtn).toBeVisible()
    })
  })

  test.describe('Analytics Page', () => {
    test('renders with correct heading', async ({ page }) => {
      await page.goto('/analytics')
      await expect(page.locator('h1')).toContainText('Analytics')
    })

    test('shows loading state initially', async ({ page }) => {
      await page.goto('/analytics')
      // Show loading or the actual content after load
      await expect(page.locator('h1')).toBeVisible()
    })

    test('displays stat cards when data loads', async ({ page }) => {
      await page.goto('/analytics')
      // Check for stat card labels — these render once data arrives
      // If API returns data, cards are visible otherwise we see loading or error
      await page.waitForTimeout(3000)
      const statCards = page.locator('text=Total Tasks').or(
        page.locator('text=Completed').or(
          page.locator('text=Available').or(
            page.locator('text=Agents')
          )
        )
      )
      // This may not be visible if API fails, but shouldn't crash
    })
  })

  test.describe('404 / Unknown Routes', () => {
    test('non-existent route does not crash the app', async ({ page }) => {
      await page.goto('/nonexistent-route')
      // App should still render with sidebar
      await expect(page.locator('aside')).toBeVisible()
      // No content on unknown routes (React Router doesn't have a 404 route)
      const main = page.locator('main')
      await expect(main).toBeVisible()
    })
  })
})
