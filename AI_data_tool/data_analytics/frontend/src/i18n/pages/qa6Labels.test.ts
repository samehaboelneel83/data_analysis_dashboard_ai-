import { describe, it, expect } from 'vitest'
import { translate } from '..'
import { boundarySetName, connectorOptionLabel, packText } from './adminPlatform'
import { templateWidgetTitle } from '../../lib/builtinTemplates'

const ar = ((k: string, v?: Record<string, string | number>) => translate('ar', k as never, v)) as never
const en = ((k: string, v?: Record<string, string | number>) => translate('en', k as never, v)) as never

describe('QA6 labels', () => {
  it('A5: an installed starter-pack set reads as Admin → Maps names the pack', () => {
    expect(boundarySetName(ar, 'ar', 'Egypt governorates')).toBe(packText(ar, 'ar', 'egypt-governorates', 'name', 'Egypt governorates'))
    expect(boundarySetName(ar, 'ar', 'Egypt governorates')).toBe('محافظات مصر')
    expect(boundarySetName(ar, 'ar', 'Our sales regions')).toBe('Our sales regions')
    expect(boundarySetName(en, 'en', 'Egypt governorates')).toBe('Egypt governorates')
  })

  it('A6: a TLS mode is named in Arabic with its code kept; the code is unchanged in English', () => {
    expect(connectorOptionLabel(ar, 'ar', 'ssl_mode', 'require')).toBe('مطلوب (⁦require⁩)')
    expect(connectorOptionLabel(en, 'en', 'ssl_mode', 'require')).toBe('require')
    expect(connectorOptionLabel(ar, 'ar', 'ssl_mode', 'prefer')).toBe('prefer')
    expect(connectorOptionLabel(ar, 'ar', 'method', 'GET')).toBe('GET')
  })

  it("A10: a built-in template's widget titles in the author's language; others left alone", () => {
    expect(templateWidgetTitle(ar, 'By category')).toBe('حسب الفئة')
    expect(templateWidgetTitle(ar, 'KPI 3')).toBe('مؤشر 3')
    expect(templateWidgetTitle(ar, 'Revenue by region')).toBeNull()
    expect(templateWidgetTitle(en, 'Over time')).toBe('Over time')
  })
})
