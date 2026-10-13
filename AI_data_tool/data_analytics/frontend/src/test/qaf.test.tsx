import { describe, it, expect } from 'vitest'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { hardcodedStrings } from './hardcodedStrings'
import { en, ar } from '../i18n/pages/qaf'
import { translate, type TranslateFn } from '../i18n'
import { statusCounts, statusOf } from '../pages/reports/model'
import { impactText } from '../pages/lineage/SidePanel'
import { nameFromFile } from '../pages/upload/readFile'
import { auditDetail } from '../pages/admin/AdminAudit'

/** FIX-QAF: the fixes from the final QA that are pure logic, and the guard. */
const tr = (lang: 'en' | 'ar'): TranslateFn => (k, v) => translate(lang, k, v)

describe('M2: one status count, and the parts add up', () => {
  const rs = [
    { created_by: null, published: false }, { created_by: null, published: false },
    { created_by: 4, published: false }, { created_by: 4, published: true },
  ]
  it('an unowned (legacy) dashboard is open to everyone, never a draft', () => {
    expect(statusOf(rs[0])).toBe('open')
    expect(statusOf(rs[2])).toBe('draft')
    expect(statusOf(rs[3])).toBe('pub')
  })
  it('drafts + published + everyone = all', () => {
    const c = statusCounts(rs)
    expect(c).toEqual({ all: 4, draft: 1, pub: 1, open: 2 })
    expect(c.draft + c.pub + c.open).toBe(c.all)
  })
})

describe('M4: the impact sentence never reads as "nothing"', () => {
  const cases: [number, number][] = [[0, 1], [0, 2], [0, 9], [1, 0], [2, 3], [5, 12]]
  it('English names only the non-zero parts', () => {
    const t = tr('en')
    expect(impactText(t, 'Sales', 0, 9)).toBe('If Sales changes, 9 reports are affected.')
    expect(impactText(t, 'Sales', 1, 0)).toBe('If Sales changes, 1 dataset is affected.')
    expect(impactText(t, 'Sales', 2, 1)).toBe('If Sales changes, 2 datasets and 1 report are affected.')
    for (const [d, r] of cases) expect(impactText(t, 'S', d, r)).not.toMatch(/\b0 |\bno /)
  })
  it('Arabic has no zero part and says what is affected', () => {
    const t = tr('ar')
    expect(impactText(t, 'Sales', 0, 9)).toBe('تغيير «⁨Sales⁩» يؤثر في 9 تقارير.')
    expect(impactText(t, 'Sales', 0, 1)).toBe('تغيير «⁨Sales⁩» يؤثر في تقرير واحد.')
    expect(impactText(t, 'Sales', 0, 2)).toBe('تغيير «⁨Sales⁩» يؤثر في تقريرين.')
    expect(impactText(t, 'Sales', 2, 12)).toBe('تغيير «⁨Sales⁩» يؤثر في مجموعتي بيانات و12 تقريرًا.')
    for (const [d, r] of cases) expect(impactText(t, 'S', d, r)).not.toMatch(/لا |0 /)
  })
})

describe('21: the suggested name keeps hyphens', () => {
  it('drops only the extension; underscores become spaces', () => {
    expect(nameFromFile('QAF-upload.csv')).toBe('QAF-upload')
    expect(nameFromFile('enrolments_2025.csv')).toBe('Enrolments 2025')
    expect(nameFromFile('sales-q3_final.xlsx')).toBe('Sales-q3 final')
  })
})

describe('26: audit details in words where the shape is known', () => {
  it('names an expiry and a link id; anything else stays as sent, with a tooltip', () => {
    const t = tr('en')
    expect(auditDetail({ action: 'share_link.create', detail: '1d' }, t)).toBe('Expires after 1 day')
    expect(auditDetail({ action: 'share_link.create', detail: '7d' }, t)).toBe('Expires after 7 days')
    expect(auditDetail({ action: 'share_link.revoke', detail: '3' }, t)).toBe('Link #3')
    expect(auditDetail({ action: 'x', detail: null }, t)).toBe('—')
    render(<>{auditDetail({ action: 'org.update', detail: '?' }, t)}</>)
    expect(screen.getByText('?')).toHaveAttribute('title', 'Recorded by the server as is')
  })
})

describe('QAF strings', () => {
  it('both languages hold the same keys and placeholders', () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort())
    const names = (s: string) => [...new Set([...s.matchAll(/\{(\w+)/g)].map(m => m[1]))].sort().join()
    expect((Object.keys(en) as (keyof typeof en)[]).filter(k => names(en[k]) !== names(ar[k]))).toEqual([])
  })
  const FILES = ['pages/connections/ConnectionModal.tsx', 'pages/reports/DashCard.tsx', 'pages/reports/FolderNav.tsx',
    'pages/home/DashboardsSection.tsx', 'components/chat/Pending.tsx', 'pages/lineage/SidePanel.tsx', 'pages/lineage/ListView.tsx',
    'pages/lineage/Graph.tsx', 'pages/datasetDetail/Overview.tsx', 'components/analysis/KeyInfluencersResult.tsx',
    'components/dataset/PredictionModelsPanel.tsx', 'pages/ask/DataPicker.tsx', 'pages/admin/AdminSso.tsx', 'pages/admin/AdminAudit.tsx',
    'components/admin/LlmEndpointsPanel.tsx']
  for (const f of FILES) {
    it(`no hard-coded English: ${f}`, () => {
      expect(hardcodedStrings(path.join(__dirname, '..', f)).map(h => `${h.line} ${h.text}`)).toEqual([])
    })
  }
})
