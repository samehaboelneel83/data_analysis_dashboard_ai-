import { describe, it, expect } from 'vitest'
import { pageFrame, pageSizeChoice, parsePageDim } from './pageSize'

describe('C-21 page size', () => {
  it('a page made before page sizes were applied keeps flowing', () => {
    expect(pageFrame({ page_size: '16:9' })).toBeNull()
    expect(pageFrame({ page_size: '4:3', custom_width: null, custom_height: null })).toBeNull()
    expect(pageSizeChoice({ page_size: '16:9' })).toBe('fit')
  })
  it('a stored size is a fixed frame', () => {
    expect(pageFrame({ page_size: '4:3', custom_width: 960, custom_height: 720 })).toEqual({ w: 960, h: 720 })
    expect(pageFrame({ page_size: 'custom', custom_width: 1600, custom_height: 1200 })).toEqual({ w: 1600, h: 1200 })
    expect(pageSizeChoice({ page_size: 'custom', custom_width: 1600, custom_height: 1200 })).toBe('custom')
  })
  it('"fit" never has a frame', () => {
    expect(pageFrame({ page_size: 'fit', custom_width: 1600, custom_height: 1200 })).toBeNull()
  })
  it('accepts only whole numbers in range', () => {
    expect(parsePageDim('1600')).toBe(1600)
    expect(parsePageDim('100')).toBeNull()
    expect(parsePageDim('20000')).toBeNull()
    expect(parsePageDim('12.5')).toBeNull()
    expect(parsePageDim('')).toBeNull()
  })
})
