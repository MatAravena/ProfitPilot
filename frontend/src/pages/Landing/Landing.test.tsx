import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Landing } from './Landing'

function renderLanding() {
  return render(<MemoryRouter><Landing /></MemoryRouter>)
}

describe('Landing page', () => {
  it('shows the brand name', () => {
    renderLanding()
    expect(screen.getByText('PROFITPILOT')).toBeInTheDocument()
  })

  it('shows the main headline', () => {
    renderLanding()
    expect(screen.getByText('Algorithmic trading')).toBeInTheDocument()
  })

  it('renders the Sign in button', () => {
    renderLanding()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('renders the Get started button', () => {
    renderLanding()
    expect(screen.getByRole('button', { name: /get started/i })).toBeInTheDocument()
  })
})
