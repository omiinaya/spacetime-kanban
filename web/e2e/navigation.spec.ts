import { test, expect } from '@playwright/test'

test.describe('Navigation', () => {
  test('sidebar displays all nav links', async ({ page }) => {
    await page.goto('/')
    // Use .first() to handle both desktop sidebar and mobile drawer
    const navLinks = page.locator('aside nav a')
    await expect(navLinks.first()).toBeVisible()

    // All four nav items should be present
    await expect(navLinks).toHaveCount(4)

    const labels = await navLinks.allInnerTexts()
    expect(labels).toContain('Board')
    expect(labels).toContain('GitHub Issues')
    expect(labels).toContain('Activity Log')
    expect(labels).toContain('Analytics')
  })

  test('navigating to Board shows the kanban board', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h1')).toContainText('Board')
  })

  test('navigating to GitHub Issues page', async ({ page }) => {
    await page.goto('/issues')
    // h1 is rendered immediately even during loading
    await expect(page.locator('h1')).toContainText('GitHub Issue Links')
  })

  test('navigating to Activity Log page', async ({ page }) => {
    await page.goto('/logs')
    // LogsPage renders h1 after loading completes (API call fails quickly)
    await expect(page.locator('h1').or(page.locator('text=Activity Log'))).toBeVisible({ timeout: 10000 })
  })

  test('navigating to Analytics page', async ({ page }) => {
    await page.goto('/analytics')
    // AnalyticsPage shows h1 only when data loads; wait for either heading or error
    await expect(
      page.locator('h1').or(page.locator('text=Analytics error'))
    ).toBeVisible({ timeout: 10000 })
  })

  test('sidebar nav links navigate correctly', async ({ page }) => {
    await page.goto('/')

    // Click "Activity Log" — target the sidebar (first aside) link
    await page.locator('aside').first().getByText('Activity Log').click()
    await expect(page).toHaveURL('/logs')
    await expect(page.locator('h1').or(page.locator('text=Activity Log'))).toBeVisible({ timeout: 10000 })

    // Click "Board"
    await page.locator('aside').first().getByText('Board').click()
    await expect(page).toHaveURL('/')

    // Click "GitHub Issues"
    await page.locator('aside').first().getByText('GitHub Issues').click()
    await expect(page).toHaveURL('/issues')
  })

  test('mobile hamburger menu toggles sidebar', async ({ page }) => {
    // Set viewport to mobile size
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/')

    // Hamburger should be visible on mobile
    const hamburger = page.locator('button').filter({ has: page.locator('.lucide-menu') })
    await expect(hamburger).toBeVisible()

    // The mobile drawer (second aside) should be off-screen initially
    const drawer = page.locator('aside').nth(1)
    await expect(drawer).toHaveClass(/-translate-x-full/)

    // Click hamburger to open
    await hamburger.click()
    await expect(drawer).toHaveClass(/translate-x-0/)

    // Close with the X button inside the drawer
    const closeBtn = drawer.locator('button').filter({ has: page.locator('.lucide-x') })
    await closeBtn.click()
    await expect(drawer).toHaveClass(/-translate-x-full/)
  })
})
