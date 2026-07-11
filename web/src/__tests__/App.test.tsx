import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

describe('App', () => {
  it('renders the navigation', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    )
    // Nav items appear multiple times (sidebar + mobile), so use getAllByText
    const boardLinks = screen.getAllByText('Board')
    expect(boardLinks.length).toBeGreaterThan(0)
  })

  it('shows nav items in sidebar', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>
    )
    // The sidebar nav links are rendered as <a> elements
    const links = screen.getAllByRole('link')
    const linkTexts = links.map(link => link.textContent?.trim())
    expect(linkTexts).toContain('Board')
    expect(linkTexts).toContain('Projects')
    expect(linkTexts).toContain('Labels')
    expect(linkTexts).toContain('GitHub Issues')
  })
})
