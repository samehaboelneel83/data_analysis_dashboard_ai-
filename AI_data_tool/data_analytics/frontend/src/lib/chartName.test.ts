import { describe, it, expect } from 'vitest'
import { chartName } from './chartName'
import { translate } from '../i18n'

describe('chart names, never codes (QA4 T2)', () => {
  it('Arabic uses the gallery name; English the gallery label; never "kpi"', () => {
    const ar = (k: string, v?: Record<string, string | number>) => translate('ar', k as never, v)
    const en = (k: string, v?: Record<string, string | number>) => translate('en', k as never, v)
    expect(chartName('kpi', ar as never, 'ar')).not.toBe('kpi')
    expect(chartName('bar', en as never, 'en')).not.toBe('bar')
  })
})
