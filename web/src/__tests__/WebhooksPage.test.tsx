import { describe, it, expect, vi, beforeEach } from 'vitest'
import type React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { Webhook, WebhookDelivery } from '../api'

// ──────────────────────────────────────────────
// Mock api module
// ──────────────────────────────────────────────
const mockList = vi.hoisted(() => vi.fn())
const mockCreate = vi.hoisted(() => vi.fn())
const mockDelete = vi.hoisted(() => vi.fn())
const mockTest = vi.hoisted(() => vi.fn())
const mockDeliveries = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  api: {
    webhooks: {
      list: mockList,
      create: mockCreate,
      delete: mockDelete,
      test: mockTest,
      deliveries: mockDeliveries,
    },
  },
}))

// ──────────────────────────────────────────────
// Mock Skeleton — use a testable data-testid
// ──────────────────────────────────────────────
vi.mock('../components/Skeleton', () => ({
  PageSkeleton: ({ rows = 6 }: { rows?: number }) => (
    <div data-testid="page-skeleton" data-rows={rows} />
  ),
}))

// ──────────────────────────────────────────────
// Mock useToast hook
// ──────────────────────────────────────────────
vi.mock('../hooks/useToast', () => ({
  useToast: vi.fn(() => ({
    addToast: vi.fn(),
  })),
}))

// Mock ConfirmDialog — useConfirm resolves to true by default (accepted)
const mockConfirm = vi.hoisted(() => vi.fn().mockResolvedValue(true))
vi.mock('../components/ConfirmDialog', () => ({
  useConfirm: () => ({ confirm: mockConfirm }),
  ConfirmProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { api } from '../api'
import WebhooksPage from '../pages/WebhooksPage'

// ──────────────────────────────────────────────
// Helpers — factory functions for test data
// ──────────────────────────────────────────────

function makeWebhook(overrides: Partial<Webhook> = {}): Webhook {
  return {
    id: 'wh-1',
    url: 'https://discord.com/api/webhooks/abc123',
    type: 'discord',
    events: ['created', 'claimed', 'completed'],
    label: 'Discord Alerts',
    created_at: Date.now() - 86400000,
    ...overrides,
  }
}

function makeDelivery(overrides: Partial<WebhookDelivery> = {}): WebhookDelivery {
  return {
    id: 'del-1',
    webhook_id: 'wh-1',
    event: 'created',
    url: 'https://discord.com/api/webhooks/abc123',
    status_code: 200,
    response_body: 'OK',
    success: true,
    delivered_at: Date.now() - 3600000,
    ...overrides,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <WebhooksPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // Default: window.confirm returns true (accepted)
  vi.stubGlobal('confirm', vi.fn(() => true))
})

// ──────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────

describe('WebhooksPage', () => {
  // ── 1. Loading skeleton ──────────────────────────────
  it('renders PageSkeleton while data is loading', () => {
    // Never-resolving promise keeps the component in loading state
    api.webhooks.list.mockReturnValue(new Promise<Webhook[]>(() => {}))
    renderPage()
    expect(screen.getByTestId('page-skeleton')).toBeInTheDocument()
    expect(screen.getByTestId('page-skeleton')).toHaveAttribute('data-rows', '4')
  })

  // ── 2. Webhook list ──────────────────────────────────
  it('renders webhook cards after data loads', async () => {
    const webhooks = [
      makeWebhook({ id: 'wh-1', label: 'Discord Alerts' }),
      makeWebhook({
        id: 'wh-2',
        label: 'Slack Notifications',
        url: 'https://hooks.slack.com/services/xyz',
        type: 'slack',
      }),
    ]
    api.webhooks.list.mockResolvedValue(webhooks)
    renderPage()

    // Wait for the list to appear
    expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()
    expect(screen.getByText('Slack Notifications')).toBeInTheDocument()

    // The header badge shows the webhook count
    expect(screen.getByText('2')).toBeInTheDocument()

    // Skeleton should no longer be shown
    expect(screen.queryByTestId('page-skeleton')).not.toBeInTheDocument()
  })

  it('renders webhook URL and type badge for each webhook', async () => {
    const webhooks = [
      makeWebhook({ id: 'wh-1', label: 'GitHub Hook', url: 'https://github.com/hooks/test' }),
    ]
    api.webhooks.list.mockResolvedValue(webhooks)
    renderPage()

    expect(await screen.findByText('GitHub Hook')).toBeInTheDocument()
    // URL should be visible
    expect(screen.getByText('https://github.com/hooks/test')).toBeInTheDocument()
    // Type badge
    expect(screen.getByText('discord')).toBeInTheDocument()
  })

  // ── 3. Empty state ───────────────────────────────────
  it('shows empty state when no webhooks exist', async () => {
    api.webhooks.list.mockResolvedValue([])
    renderPage()

    expect(await screen.findByText('No webhooks configured.')).toBeInTheDocument()

    // Helper description text is also present
    expect(
      screen.getByText(/Add a webhook to receive task notifications/),
    ).toBeInTheDocument()

    // Error alert should NOT appear
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  // ── 4. Error state ───────────────────────────────────
  it('shows error alert when API call fails', async () => {
    api.webhooks.list.mockRejectedValue(new Error('Failed to fetch webhooks'))
    renderPage()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByText(/Failed to fetch webhooks/)).toBeInTheDocument()

    // Empty state should NOT appear when there's an error
    expect(screen.queryByText('No webhooks configured.')).not.toBeInTheDocument()

    // Skeleton should not be shown after error
    expect(screen.queryByTestId('page-skeleton')).not.toBeInTheDocument()
  })

  // ── 5. Delete webhook confirmation flow ──────────────
  describe('delete webhook', () => {
    it('calls delete API and reloads when confirm is accepted', async () => {
      const webhooks = [makeWebhook({ id: 'wh-1' })]
      api.webhooks.list.mockResolvedValue(webhooks)
      api.webhooks.delete.mockResolvedValue({ status: 'deleted' })
      renderPage()

      expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()

      // Click the delete button
      fireEvent.click(screen.getByTitle('Delete'))

      await waitFor(() => {
        expect(api.webhooks.delete).toHaveBeenCalledWith('wh-1')
      })

      // The component reloads the list after deletion
      await waitFor(() => {
        expect(api.webhooks.list).toHaveBeenCalledTimes(2)
      })
    })

    it('does not delete when confirm is cancelled', async () => {
      mockConfirm.mockResolvedValueOnce(false)
      const webhooks = [makeWebhook({ id: 'wh-1' })]
      api.webhooks.list.mockResolvedValue(webhooks)
      renderPage()

      expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()

      fireEvent.click(screen.getByTitle('Delete'))

      // Since confirm returned false, the delete should not be called
      await new Promise(r => setTimeout(r, 50))
      expect(api.webhooks.delete).not.toHaveBeenCalled()

      // List should NOT have been called again
      expect(api.webhooks.list).toHaveBeenCalledTimes(1)
    })
  })

  // ── 6. Create webhook form ───────────────────────────
  describe('create webhook', () => {
    it('submits the create webhook form with correct data', async () => {
      api.webhooks.list.mockResolvedValue([])
      api.webhooks.create.mockResolvedValue({
        id: 'wh-new',
        url: 'https://hooks.slack.com/services/new',
        type: 'slack',
        events: ['created'],
        label: '',
        created_at: Date.now(),
      })
      renderPage()

      expect(await screen.findByText('No webhooks configured.')).toBeInTheDocument()

      // Open the create form
      fireEvent.click(screen.getByText('Add Webhook'))

      // Fill in the webhook URL
      const urlInput = screen.getByPlaceholderText(
        'https://discord.com/api/webhooks/...',
      )
      fireEvent.change(urlInput, {
        target: { value: 'https://hooks.slack.com/services/new' },
      })

      // Change type to slack (default is 'Discord')
      const typeSelect = screen.getByDisplayValue('Discord')
      fireEvent.change(typeSelect, { target: { value: 'slack' } })

      // Submit the form
      fireEvent.click(screen.getByText('Create Webhook'))

      // Verify the API call
      expect(api.webhooks.create).toHaveBeenCalledTimes(1)
      expect(api.webhooks.create).toHaveBeenCalledWith({
        url: 'https://hooks.slack.com/services/new',
        type: 'slack',
        events: ['created', 'claimed', 'completed', 'blocked'],
      })

      // Form should reset and list should reload
      await waitFor(() => {
        expect(api.webhooks.list).toHaveBeenCalledTimes(2)
      })

      // The create form should be closed after submission
      expect(screen.queryByPlaceholderText('https://discord.com/api/webhooks/...')).not.toBeInTheDocument()
    })

    it('disables the create button when URL is empty', async () => {
      api.webhooks.list.mockResolvedValue([])
      renderPage()

      expect(await screen.findByText('No webhooks configured.')).toBeInTheDocument()

      // Open the form
      fireEvent.click(screen.getByText('Add Webhook'))

      // Button should be disabled when URL is empty
      const createBtn = screen.getByText('Create Webhook')
      expect(createBtn.closest('button')).toBeDisabled()

      // Type a URL and button should become enabled
      const urlInput = screen.getByPlaceholderText(
        'https://discord.com/api/webhooks/...',
      )
      fireEvent.change(urlInput, {
        target: { value: 'https://example.com/hook' },
      })
      expect(createBtn.closest('button')).not.toBeDisabled()
    })

    it('shows create form when Add Webhook is clicked and hides on Cancel', async () => {
      api.webhooks.list.mockResolvedValue([])
      renderPage()

      expect(await screen.findByText('No webhooks configured.')).toBeInTheDocument()

      // Open
      fireEvent.click(screen.getByText('Add Webhook'))
      expect(
        screen.getByPlaceholderText('https://discord.com/api/webhooks/...'),
      ).toBeInTheDocument()

      // Cancel
      fireEvent.click(screen.getByText('Cancel'))
      expect(
        screen.queryByPlaceholderText('https://discord.com/api/webhooks/...'),
      ).not.toBeInTheDocument()
    })
  })

  // ── 7. View deliveries for a webhook ─────────────────
  describe('delivery history', () => {
    it('fetches and displays deliveries when expanded', async () => {
      const webhooks = [makeWebhook({ id: 'wh-1' })]
      const deliveries = [
        makeDelivery({
          id: 'del-1',
          event: 'created',
          status_code: 200,
          success: true,
        }),
        makeDelivery({
          id: 'del-2',
          event: 'claimed',
          status_code: 500,
          success: false,
          response_body: 'Internal server error',
        }),
      ]
      api.webhooks.list.mockResolvedValue(webhooks)
      api.webhooks.deliveries.mockResolvedValue(deliveries)
      renderPage()

      expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()

      // Click the delivery history toggle
      fireEvent.click(screen.getByText('Show delivery history'))

      // API should be called with correct params
      expect(api.webhooks.deliveries).toHaveBeenCalledWith('wh-1', 10)

      // Wait for delivery items to render
      await waitFor(() => {
        expect(screen.getByText('HTTP 200')).toBeInTheDocument()
      })
      expect(screen.getByText('HTTP 500')).toBeInTheDocument()
      expect(screen.getByText(/Internal server error/)).toBeInTheDocument()

      // Toggle label changes
      expect(screen.getByText('Hide delivery history')).toBeInTheDocument()
    })

    it('shows empty delivery message when there are no deliveries', async () => {
      const webhooks = [makeWebhook({ id: 'wh-1' })]
      api.webhooks.list.mockResolvedValue(webhooks)
      api.webhooks.deliveries.mockResolvedValue([])
      renderPage()

      expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()

      fireEvent.click(screen.getByText('Show delivery history'))

      await waitFor(() => {
        expect(screen.getByText('No delivery history yet.')).toBeInTheDocument()
      })
    })

    it('hides delivery history when toggled closed', async () => {
      const webhooks = [makeWebhook({ id: 'wh-1' })]
      api.webhooks.list.mockResolvedValue(webhooks)
      api.webhooks.deliveries.mockResolvedValue([])
      renderPage()

      expect(await screen.findByText('Discord Alerts')).toBeInTheDocument()

      // Open
      fireEvent.click(screen.getByText('Show delivery history'))
      await waitFor(() => {
        expect(screen.getByText('Hide delivery history')).toBeInTheDocument()
      })

      // Close
      fireEvent.click(screen.getByText('Hide delivery history'))
      expect(screen.queryByText('No delivery history yet.')).not.toBeInTheDocument()
      expect(screen.getByText('Show delivery history')).toBeInTheDocument()
    })
  })
})
