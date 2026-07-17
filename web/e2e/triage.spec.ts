import { test, expect } from '@playwright/test'

test.describe('Triage Page', () => {
  test('renders with heading and description', async ({ page }) => {
    await page.goto('/triage')
    await expect(page.locator('h1')).toContainText('Blocked Triage')
    await expect(page.locator('text=Blocked tasks grouped by failure reason')).toBeVisible()
  })

  test('shows either clusters or the clean-board state', async ({ page }) => {
    await page.goto('/triage')
    // Either there are blocked-task clusters with Retry/Archive actions,
    // or the "board is clean" celebration shows.
    const clusterAction = page.locator('button').filter({ hasText: 'Retry all' }).first()
    const cleanState = page.locator('text=the board is clean')
    await expect(clusterAction.or(cleanState)).toBeVisible()
  })

  test('cluster expands to show task list', async ({ page }) => {
    await page.goto('/triage')
    const firstClusterToggle = page.locator('button:has(svg.lucide-chevron-right)').first()
    if (await firstClusterToggle.isVisible()) {
      await firstClusterToggle.click()
      // Expanded rows expose per-task Retry buttons
      await expect(page.locator('button').filter({ hasText: 'Retry' }).first()).toBeVisible()
    }
  })

  test('refresh button reloads data', async ({ page }) => {
    await page.goto('/triage')
    const refreshBtn = page.locator('button').filter({ hasText: 'Refresh' })
    await expect(refreshBtn).toBeVisible()
    await refreshBtn.click()
    // Page still shows the heading after refresh
    await expect(page.locator('h1')).toContainText('Blocked Triage')
  })

  test('navigates from sidebar', async ({ page }) => {
    await page.goto('/')
    await page.locator('aside').first().getByText('Triage').click()
    await expect(page).toHaveURL('/triage')
    await expect(page.locator('h1')).toContainText('Blocked Triage')
  })
})
