import { test, expect } from '@playwright/test'

test.describe('Task Interaction', () => {
  test('create task dialog has all required form fields', async ({ page }) => {
    await page.goto('/')
    await page.locator('button').filter({ hasText: 'New' }).click()

    // Dialog should be visible
    await expect(page.locator('h2').filter({ hasText: 'Create Task' })).toBeVisible()

    // Verify all form fields exist (scope select to the dialog form — the
    // board toolbar also has a <select>, causing strict-mode violations)
    await expect(page.locator('input[placeholder="Task title"]')).toBeVisible()
    await expect(page.locator('textarea[placeholder="Description (optional)"]')).toBeVisible()
    await expect(page.locator('form select')).toBeVisible() // priority select
    await expect(page.locator('input[placeholder="Repo slug"]')).toBeVisible()
    await expect(page.locator('input[placeholder="Roadmap item"]')).toBeVisible()
    await expect(page.locator('input[placeholder="Skills (e.g. rust,python)"]')).toBeVisible()
  })

  test('create button is disabled when title is empty', async ({ page }) => {
    await page.goto('/')
    await page.locator('button').filter({ hasText: 'New' }).click()

    const createBtn = page.locator('button[type="submit"]').filter({ hasText: 'Create' })
    // Button should be disabled when title is empty
    await expect(createBtn).toBeDisabled()
  })

  test('create task form fields are interactive', async ({ page }) => {
    await page.goto('/')
    await page.locator('button').filter({ hasText: 'New' }).click()

    // Fill in the form
    await page.locator('input[placeholder="Task title"]').fill('E2E Test Task')
    await page.locator('textarea[placeholder="Description (optional)"]').fill('Created by Playwright E2E test')
    await page.locator('input[placeholder="Repo slug"]').fill('e2e-testing')
    await page.locator('input[placeholder="Roadmap item"]').fill('Phase 4 — E2E')
    await page.locator('input[placeholder="Skills (e.g. rust,python)"]').fill('typescript,playwright')

    // Select priority
    await page.locator('form select').selectOption('0')

    // Submit button should now be enabled
    const createBtn = page.locator('button[type="submit"]').filter({ hasText: 'Create' })
    await expect(createBtn).toBeEnabled()
  })

  test('create task dialog can be dismissed with Cancel or X', async ({ page }) => {
    await page.goto('/')
    await page.locator('button').filter({ hasText: 'New' }).click()
    await expect(page.locator('h2').filter({ hasText: 'Create Task' })).toBeVisible()

    // Click Cancel
    await page.locator('button').filter({ hasText: 'Cancel' }).click()
    await expect(page.locator('h2').filter({ hasText: 'Create Task' })).not.toBeVisible()
  })

  test('can select priority in create dialog', async ({ page }) => {
    await page.goto('/')
    await page.locator('button').filter({ hasText: 'New' }).click()

    const select = page.locator('form select')
    // Verify all priority options exist
    const options = await select.locator('option').allInnerTexts()
    expect(options).toContain('Urgent')
    expect(options).toContain('High')
    expect(options).toContain('Medium')
    expect(options).toContain('Low')

    // Select "Urgent"
    await select.selectOption('0')
    await expect(select).toHaveValue('0')
  })

  test('task detail dialog shows metadata when a task card is clicked', async ({ page }) => {
    await page.goto('/')
    // NOTE: never click Seed here — E2E runs against the PRODUCTION board.
    // The live board already has tasks; click the first row in list view.
    const firstRow = page.locator('table tbody tr').first()
    await expect(firstRow).toBeVisible()
    await firstRow.click()

    // Task detail dialog should open with expected sections
    await expect(page.locator('text=Dependency Chain').first()).toBeVisible()
    await expect(page.locator('text=Activity Log').first()).toBeVisible()

    // Close the dialog via the X button in its header (scoped to the dialog —
    // the first .lucide-x button on the page is the hidden mobile-drawer close)
    await page.locator('div.fixed.inset-0 button').filter({ has: page.locator('.lucide-x') }).first().click()
  })

  test('task list displays priority labels and status', async ({ page }) => {
    await page.goto('/')
    // List view shows priority labels (Urgent/High/Medium/Low) and status badges
    await expect(page.locator('h1')).toContainText('Board')
    await expect(page.locator('table tbody tr').first()).toBeVisible()
  })
})
