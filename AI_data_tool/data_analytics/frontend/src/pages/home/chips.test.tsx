import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Hero } from './parts'

/** QA2 B8 (Home): a chip opens Ask AI, a route loaded on demand; until it
 *  arrives the page used to look as if the click did nothing. */
describe('Home question chips (QA2 B8)', () => {
  it('a pressed chip says it is opening, and the others wait', () => {
    render(<MemoryRouter><Hero name="Sam" firstRun={false} noData={false} offline={false} loading={false}
      chips={{ datasetId: 7, datasetName: 'Sales', questions: ['Total revenue?', 'Top region?'] }} /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: /Total revenue\?/ }))
    expect(screen.getByRole('button', { name: /Total revenue\?/ })).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('button', { name: /Top region\?/ })).toBeDisabled()
  })
})
