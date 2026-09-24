import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LoadingState from './LoadingState'

describe('LoadingState', () => {
  it('shows "Loading…" by default, matching the wording every page already used', () => {
    render(<LoadingState />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
  })

  it('shows a custom label when one is given', () => {
    render(<LoadingState label="Scanning columns…" />)
    expect(screen.getByText('Scanning columns…')).toBeInTheDocument()
  })
})
