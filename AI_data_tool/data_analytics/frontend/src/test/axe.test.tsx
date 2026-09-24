import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { axeViolations } from './axe'

/** The helper must actually catch problems, or every "no violations" test
 *  that uses it passes over nothing. */
describe('axeViolations', () => {
  it('catches a nameless button and a control nested in another', async () => {
    const { container } = render(
      <div>
        <button type="button"></button>
        <div role="button" tabIndex={0}><a href="/x">link</a></div>
      </div>)
    const found = (await axeViolations(container)).join('\n')
    expect(found).toMatch(/^button-name/m)
    expect(found).toMatch(/^nested-interactive/m)
  })

  it('passes clean markup', async () => {
    const { container } = render(<button type="button">Save</button>)
    expect(await axeViolations(container)).toEqual([])
  })
})
