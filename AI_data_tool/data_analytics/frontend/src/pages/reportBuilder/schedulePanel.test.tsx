import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders as render } from '../../test/renderWithProviders'
import { DirectionProvider } from '../../contexts/DirectionContext'
import { SchedulePanel } from './SchedulePanel'
import { schedulesApi, deliveriesApi } from '../../services/api'

/** QA3 Batch C: the Schedule panel's content follows the interface language. */

vi.mock('../../services/api', async orig => ({
  ...(await orig<Record<string, unknown>>()),
  schedulesApi: { list: vi.fn(), create: vi.fn(), delete: vi.fn(), runNow: vi.fn() },
  deliveriesApi: { list: vi.fn() },
}))

const ROWS = [
  { id: 1, interval_minutes: 2880, recipients: ['a@example.com'], timezone: null, calendar: null, last_status: null },
  { id: 2, interval_minutes: 0, recipients: ['b@example.com', 'c@example.com'], timezone: 'Asia/Riyadh',
    calendar: { kind: 'weekly', hour: 9, minute: 5, weekday: 2 }, last_status: null, per_recipient: true },
]

beforeEach(() => {
  localStorage.clear()
  vi.mocked(schedulesApi.list).mockResolvedValue(ROWS as never)
  vi.mocked(deliveriesApi.list).mockResolvedValue([])
})

const renderIt = () => render(<DirectionProvider><SchedulePanel reportId={1} /></DirectionProvider>)

describe('SchedulePanel language', () => {
  it('reads in English as before', async () => {
    renderIt()
    expect((await screen.findAllByRole('button', { name: 'Run now' })).length).toBe(2)
    expect(screen.getByText('Scheduled delivery')).toBeInTheDocument()
    const rows = document.body.textContent ?? ''
    expect(rows).toContain('Every 2 days → a@example.com')
    expect(rows).toContain('Weekly (Wed) at 09:05 Asia/Riyadh → b@example.com, c@example.com')
  })

  it('reads in Arabic, data kept whole in <bdi>', async () => {
    localStorage.setItem('datalytics.language', 'ar')
    renderIt()
    expect((await screen.findAllByRole('button', { name: 'تشغيل الآن' })).length).toBe(2)
    expect(screen.getByText('الإرسال المجدول')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'إضافة جدول' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'نوع الجدول' })).toBeInTheDocument()
    const text = document.body.textContent ?? ''
    expect(text).toContain('كل يومين، إلى a@example.com')
    expect(text).toContain('أسبوعيًا يوم الأربعاء الساعة 09:05 بتوقيت Asia/Riyadh، إلى b@example.com, c@example.com')
    expect(screen.getByText('b@example.com, c@example.com').tagName).toBe('BDI')
    expect(screen.getByText('09:05').tagName).toBe('BDI')
    expect(text).not.toMatch(/Run now|Scheduled delivery|Every|Recipients|each their own view/)
  })
})
