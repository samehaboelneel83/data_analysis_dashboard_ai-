import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { translate, type TranslateFn } from '../../i18n'
import { funcCats } from './calcColumns/catalog'
import PackTermsConfirm from './PackTermsConfirm'
import { candidateBlockReason, type ModelSpec } from '../../lib/modelCompare'
import { geoMatchSentence, type GeoMatchReport } from '../../lib/geoMatch'
import type { BoundaryPack } from '../../services/api'

/** 8-i18n leftovers: the calc-column palette, a pack's terms and two lib sentences in Arabic. */
const AR: TranslateFn = (key, vars) => translate('ar', key, vars)
const EN: TranslateFn = (key, vars) => translate('en', key, vars)

describe('panelsA leftovers in Arabic', () => {
  beforeEach(() => localStorage.setItem('datalytics.language', 'ar'))
  afterEach(() => localStorage.removeItem('datalytics.language'))

  it('translates the palette categories and hints, never the signatures or snippets', () => {
    const ar = funcCats(AR), en = funcCats(EN)
    expect(ar[0].label).toBe('رقمية')
    expect(ar[0].items[0]).toMatchObject({ label: 'abs(x)', snippet: 'abs()', hint: 'القيمة المطلقة' })
    expect(en[0].items[0].hint).toBe('Absolute value')
    expect(ar.map(c => c.items.map(i => `${i.label}|${i.snippet}|${i.back}`)))
      .toEqual(en.map(c => c.items.map(i => `${i.label}|${i.snippet}|${i.back}`)))
    expect(ar.flatMap(c => [c.label, ...c.items.map(i => i.hint)]).filter(s => /[A-Za-z]{4,}/.test(s.replace(/⁦[^⁩]*⁩/g, ''))))
      .toEqual([])
  })

  it('shows a pack’s terms in Arabic', () => {
    const pack = {
      id: 'eu-nuts1', name: 'EU NUTS-1', source: 'Eurostat', license: 'GISCO terms',
      license_url: 'https://example.invalid/l', attribution: '© EuroGeographics', terms: 'Credit the source.',
    } as unknown as BoundaryPack
    render(<DirectionProvider><PackTermsConfirm pack={pack} onAccept={() => {}} onCancel={() => {}} /></DirectionProvider>)
    const group = screen.getByRole('group', { name: 'شروط «⁨EU NUTS-1⁩»' })
    expect(group).toHaveTextContent('شروط استخدام EU NUTS-1')
    expect(group).toHaveTextContent('ستعرض كل خريطة مرسومة منها: © EuroGeographics')
    expect(screen.getByRole('link', { name: 'اقرأ الترخيص' })).toHaveAttribute('href', 'https://example.invalid/l')
    expect(screen.getByRole('button', { name: 'أوافق، ثبّت' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إلغاء' })).toBeInTheDocument()
    expect(screen.queryByText(/terms of use|I accept|Cancel/)).toBeNull()
  })

  it('says why a model cannot be compared, and how well values map, in Arabic', () => {
    const a = { id: 1, response: 'revenue' } as unknown as ModelSpec
    const b = { id: 2, response: 'churned' } as unknown as ModelSpec
    expect(candidateBlockReason(b, [a], AR)).toBe('يتنبأ بـ«⁨churned⁩»، والبقية تتنبأ بـ«⁨revenue⁩»')
    expect(candidateBlockReason({ id: 3 } as unknown as ModelSpec, [], AR)).toBe('ليس له متغير استجابة بعد')
    const r = { pctRows: 86, totalValues: 4, unmatched: [{ name: 'Luxor', count: 2 }, { name: 'Alex', count: 1 }] } as unknown as GeoMatchReport
    expect(geoMatchSentence(r, 3, AR)).toBe('⁨86٪⁩ من الصفوف على الخريطة · ⁨2⁩ من ⁨4⁩ قيمة بلا مطابقة: «⁨Luxor⁩» (صفّان)، «⁨Alex⁩» (صف واحد)')
  })
})
