import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CellLink, isWebAddress, shortAddress } from './cellLink'

describe('web addresses in table cells', () => {
  it.each([
    ['https://eg.hatla2ee.com/en/car/audi/q3/7234745', true],
    ['http://example.com', true],
    ['javascript:alert(1)', false],
    ['data:text/html,x', false],
    ['see https://x.com', false],
    [42, false],
  ])('%s is a link: %s', (v, yes) => expect(isWebAddress(v)).toBe(yes))

  it('reads short and opens safely in a new tab', () => {
    const outer = vi.fn()
    render(<div onClick={outer}><CellLink url="https://eg.hatla2ee.com/en/car/audi/q3/7234745" /></div>)
    const a = screen.getByRole('link', { name: 'eg.hatla2ee.com/…/7234745' })
    expect(a).toHaveAttribute('href', 'https://eg.hatla2ee.com/en/car/audi/q3/7234745')
    expect(a).toHaveAttribute('target', '_blank')
    expect(a).toHaveAttribute('rel', 'noopener noreferrer')
    fireEvent.click(a)
    expect(outer).not.toHaveBeenCalled()   // no cross-filter from a link click
    expect(shortAddress('https://site.com/')).toBe('site.com')
  })
})
