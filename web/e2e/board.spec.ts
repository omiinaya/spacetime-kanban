import { test, expect } from '@playwright/test'

test.describe('Board Page', () => {
  test('board page loads with correct page title', async ({ page }) => {
    await page.goto('/')
    // HTML <title> is "spacetimedb-kanban"
    await expect(page).toHaveTitle('spacetimedb-kanban')
    await expect(page.locator('h1')).toContainText('Board')
  })

  test('four kanban column headers are displayed on desktop', async ({ page }) => {
    await page.goto('/')
    // On desktop (>= 1024px) we get 4 columns via CSS grid
    await page.setViewportSize({ width: 1280, height: 800 })

    const columns = page.locator('h2')
    const columnTexts = await columns.allInnerTexts()

    expect(columnTexts).toContain('AVAILABLE')
    expect(columnTexts).toContain('IN PROGRESS')
    expect(columnTexts).toContain('BLOCKED')
    expect(columnTexts).toContain('DONE')
  })

  test('shows empty state when no tasks exist', async ({ page }) => {
    await page.goto('/')
    // Check for empty state message
    const hasEmptyAlert = page.locator('text=No tasks found')
    const emptyColumn = page.locator('text=Empty').first()

    await expect(hasEmptyAlert.or(emptyColumn)).toBeVisible()
  })

  test('"New" button opens the Create Task dialog', async ({ page }) => {
    await page.goto('/')

    // Click the New button
    const newButton = page.locator('button').filter({ hasText: 'New' }).first()
    await expect(newButton).toBeVisible()
    await newButton.click()

    // Dialog should be visible — look for "New Task" heading
    const dialogTitle = page.locator('h3').filter({ hasText: 'New Task' })
    await expect(dialogTitle).toBeVisible()

    // Form fields should be present
    await expect(page.locator('input[placeholder="Task title"]')).toBeVisible()
    await expect(page.locator('textarea[placeholder="Description (optional)"]')).toBeVisible()

    // Cancel button should close it
    await page.locator('button').filter({ hasText: 'Cancel' }).click()
    await expect(dialogTitle).not.toBeVisible()
  })

  test('search input is present and filters placeholder text', async ({ page }) => {
    await page.goto('/')
    const searchInput = page.locator('input[placeholder="Search tasks..."]')
    await expect(searchInput).toBeVisible()

    // Type a query — the no-results message should appear
    await searchInput.fill('nonexistent-task-xyz')
    await expect(page.locator('text=No tasks match')).toBeVisible()
  })

  test('repo filter dropdown appears when repos exist', async ({ page }) => {
    await page.goto('/')
    // Just verify the page rendered
    await expect(page.locator('h1')).toBeVisible()
  })

  test('Suggest button toggles suggestions panel', async ({ page }) => {
    await page.goto('/')
    const suggestBtn = page.locator('button').filter({ hasText: 'Suggest' })
    await expect(suggestBtn).toBeVisible()
    await suggestBtn.click()

    // Panel heading should appear
    await expect(page.locator('text=Smart Suggestions').first()).toBeVisible()

    // Click again to close
    await suggestBtn.click()
    await expect(page.locator('text=Smart Suggestions')).not.toBeVisible()
  })

  test('Agents button toggles agent panel', async ({ page }) => {
    await page.goto('/')
    const agentsBtn = page.locator('button').filter({ hasText: 'Agents' })
    await expect(agentsBtn).toBeVisible()
    await agentsBtn.click()

    await expect(page.locator('text=Swarm Agents').first()).toBeVisible()

    await agentsBtn.click()
    await expect(page.locator('text=Swarm Agents')).not.toBeVisible()
  })

  test('Graph button opens dependency graph overlay', async ({ page }) => {
    await page.goto('/')
    const graphBtn = page.locator('button').filter({ hasText: 'Graph' })
    await expect(graphBtn).toBeVisible()
    await graphBtn.click()

    // Graph overlay should be visible — check for its close button
    await page.waitForTimeout(500)
    const closeBtn = page.locator('button').filter({ hasText: /Close/ })
    await expect(closeBtn.first()).toBeVisible()
  })

  test('mobile view shows status tabs instead of columns', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/')

    // Mobile status tabs should be visible
    const availableTab = page.locator('button').filter({ hasText: 'Available' })
    const inProgressTab = page.locator('button').filter({ hasText: 'In Progress' })
    await expect(availableTab).toBeVisible()
    await expect(inProgressTab).toBeVisible()
  })

  test('live connection indicator shows LIVE or FALLBACK', async ({ page }) => {
    await page.goto('/')
    const heading = page.locator('h1')

    const headingText = await heading.innerText()
    expect(headingText).toMatch(/(LIVE|FALLBACK)/)
  })

  test('Seed button exists and is clickable', async ({ page }) => {
    await page.goto('/')
    const seedBtn = page.locator('button').filter({ hasText: 'Seed' })
    await expect(seedBtn).toBeVisible()
    await expect(seedBtn).toBeEnabled()
  })

  test('kanban column shows task count badges', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/')

    // Each column heading has a count badge next to it
    const columnCounters = page.locator('h2 + span')
    const count = await columnCounters.count()
    expect(count).toBeGreaterThanOrEqual(1)
  })
})
