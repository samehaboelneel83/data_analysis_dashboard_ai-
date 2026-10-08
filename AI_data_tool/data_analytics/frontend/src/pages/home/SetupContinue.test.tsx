import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SetupContinue from './SetupContinue'
import type { SetupJourney } from '../../services/api'

const j: SetupJourney = {
  id: 1, source: { id: 37, name: 'Cars DB', type: 'postgresql' }, step: 'data', position: 2, total: 4,
  brief: {}, dataset_ids: [], report_id: null, updated_at: null,
}

describe('Home: continue setting up', () => {
  it('names the connection, the step and where to continue', () => {
    render(<MemoryRouter><SetupContinue journeys={[j]} /></MemoryRouter>)
    expect(screen.getByText('Cars DB: step 2 of 4, Choose data')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Continue: Cars DB' })).toHaveAttribute('href', '/setup/37')
  })

  it('stays away when there is nothing to continue, or the list could not be read', () => {
    const { container, rerender } = render(<MemoryRouter><SetupContinue journeys={[]} /></MemoryRouter>)
    expect(container).toBeEmptyDOMElement()
    rerender(<MemoryRouter><SetupContinue journeys={null} /></MemoryRouter>)
    expect(container).toBeEmptyDOMElement()
  })
})
