import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Loader from './Loader'

/**
 * The animation is CSS, and jsdom applies no stylesheet — so these pin the
 * things the stylesheet DEPENDS ON rather than the motion itself.
 *
 * The one that matters is the element count. The shadows are paired to the
 * balls by `:nth-child(4)` and `:nth-child(5)` in index.css, which is only
 * correct while the markup is exactly three balls followed by three shadows.
 * Drop or reorder one and every shadow lands under the wrong ball — invisible
 * to a type checker, and invisible here too unless something counts them.
 */
describe('Loader', () => {
  it('announces itself as a live status region', () => {
    render(<Loader label="Loading…" />)
    const status = screen.getByRole('status')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })

  it('renders three balls and three shadows, in that order', () => {
    const { container } = render(<Loader />)
    const children = Array.from(container.querySelectorAll('.dl-loader > *'))
    expect(children.map(el => el.className)).toEqual([
      'dl-loader__ball', 'dl-loader__ball', 'dl-loader__ball',
      'dl-loader__shadow', 'dl-loader__shadow', 'dl-loader__shadow',
    ])
  })

  it('hides the animation from assistive tech, leaving only the label', () => {
    const { container } = render(<Loader label="Loading…" />)
    expect(screen.getByText('Loading…')).toBeInTheDocument()
    expect(container.querySelector('.dl-loader')).toHaveAttribute('aria-hidden')
  })

  it('renders no label when none is given, rather than an empty paragraph', () => {
    const { container } = render(<Loader />)
    expect(container.querySelector('.dl-loading__label')).toBeNull()
  })

})
