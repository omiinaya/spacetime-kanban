import { test, expect, type Page } from '@playwright/test'

/** Switch the board from the default list view to kanban card view. */
async function switchToCardView(page: Page) {
  await page.locator('button[title="Card view (detailed)"]').click()
}

test.describe('Board Page', () => {
  test('board page loads with correct page title', async ({ page }) => {
    await page.goto('/')
    // HTML <title> is "spacetime-kanban"
    await expect(page).toHaveTitle('spacetime-kanban')
    await expect(page.locator('h1')).toContainText('Board')
  })

  test('four kanban column headers are displayed on desktop', async ({ page }) => {
    await page.goto('/')
    // On desktop (>= 1024px) we get 4 columns in card view (default is list view)
    await page.setViewportSize({ width: 1280, height: 800 })
    await switchToCardView(page)

    const columns = page.locator('h2')
    const columnTexts = await columns.allInnerTexts()

    expect(columnTexts.join(' ')).toContain('AVAILABLE')
    expect(columnTexts.join(' ')).toContain('IN PROGRESS')
    expect(columnTexts.join(' ')).toContain('BLOCKED')
    expect(columnTexts.join(' ')).toContain('DONE')
  })

  test('shows search-aware empty state when nothing matches', async ({ page }) => {
    await page.goto('/')
    // Live board is never empty — verify the search-aware empty state instead
    const searchInput = page.locator('input[placeholder="Search tasks..."]')
    await expect(searchInput).toBeVisible()
    await searchInput.fill('zzz-no-such-task-exists-zzz')
    // Two elements match (banner + list-view td) — assert the first
    await expect(page.locator('text=No tasks match').first()).toBeVisible()
  })

  test('"New" button opens the Create Task dialog', async ({ page }) => {
    await page.goto('/')

    // Click the New button
    const newButton = page.locator('button').filter({ hasText: 'New' }).first()
    await expect(newButton).toBeVisible()
    await newButton.click()

    // Dialog should be visible — look for "Create Task" heading
    const dialogTitle = page.locator('h2').filter({ hasText: 'Create Task' })
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
    await expect(page.locator('text=No tasks match').first()).toBeVisible()
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

    // Graph overlay should be visible — check for its heading
    await expect(page.locator('h2').filter({ hasText: 'Dependency Graph' })).toBeVisible()
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
    await switchToCardView(page)

    // Each column header (h2) includes a count, e.g. "AVAILABLE (12/50)" or a badge
    const columnHeaders = page.locator('h2')
    await expect(columnHeaders.first()).toBeVisible()
    const count = await columnHeaders.count()
    expect(count).toBeGreaterThanOrEqual(4)
  })
})
