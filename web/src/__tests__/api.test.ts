import { describe, it, expect, vi } from 'vitest'

// Mock the spacetimedb SDK before importing api
vi.mock('spacetimedb', () => ({
  SpacetimeDBClient: {
    // minimal mock
  },
  DB: {
    // minimal mock
  }
}))

describe('API module', () => {
  it('exists and can be imported', async () => {
    const api = await import('../api')
    expect(api).toBeDefined()
  })
})
