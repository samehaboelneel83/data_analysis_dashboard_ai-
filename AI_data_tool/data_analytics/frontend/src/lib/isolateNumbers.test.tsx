import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { isolateNumbers } from './isolateNumbers'

describe('numbers keep their order in any direction (QA3 D5)', () => {
  it('a range is one left-to-right isolate', () => {
    const { container } = render(<p dir="rtl">{isolateNumbers('Values ran 7.61–30.21 last month')}</p>)
    const bdis = [...container.querySelectorAll('bdi[dir="ltr"]')].map(b => b.textContent)
    expect(bdis).toEqual(['7.61–30.21'])
    expect(container.textContent).toBe('Values ran 7.61–30.21 last month')
  })

  it('a leading number, a percentage and money are each isolated', () => {
    const { container } = render(<p dir="rtl">{isolateNumbers('51 rows rose by 30% to $1,204.5')}</p>)
    expect([...container.querySelectorAll('bdi')].map(b => b.textContent)).toEqual(['51', '30%', '$1,204.5'])
  })

  it('text without numbers is left alone', () => {
    expect(isolateNumbers('No outliers')).toEqual(['No outliers'])
    expect(isolateNumbers('')).toBe('')
  })
})
