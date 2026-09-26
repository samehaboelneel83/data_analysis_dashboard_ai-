import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import AdminCalendar from './AdminCalendar'
import { calendarSettingsApi } from '../../services/api'
import { fiscalLabel, monthName } from '../../lib/fiscal'

vi.mock('../../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  calendarSettingsApi: { get: vi.fn(), set: vi.fn() },
}))

const d = (iso: string) => new Date(`${iso}T00:00:00Z`)

describe('fiscal labels (the same as services/fiscal.py makes)', () => {
  it('a July year is named by both calendar years, quarters from July', () => {
    expect(fiscalLabel(d('2024-06-30'), 'fiscal_year', 7)).toBe('FY2023/24')
    expect(fiscalLabel(d('2024-07-01'), 'fiscal_year', 7)).toBe('FY2024/25')
    expect(fiscalLabel(d('2024-07-01'), 'fiscal_quarter', 7)).toBe('FY2024/25-Q1')
    expect(fiscalLabel(d('2025-01-01'), 'fiscal_quarter', 7)).toBe('FY2024/25-Q3')
    expect(fiscalLabel(d('2025-06-30'), 'fiscal_quarter', 7)).toBe('FY2024/25-Q4')
  })
  it('an October year, a January year, and the century', () => {
    expect(fiscalLabel(d('2025-10-01'), 'fiscal_quarter', 10)).toBe('FY2025/26-Q1')
    expect(fiscalLabel(d('2025-09-30'), 'fiscal_quarter', 10)).toBe('FY2024/25-Q4')
    expect(fiscalLabel(d('2025-04-01'), 'fiscal_quarter', 1)).toBe('FY2025-Q2')
    expect(fiscalLabel(d('2099-08-01'), 'fiscal_year', 7)).toBe('FY2099/00')
  })
  it('names months in the reader\'s language', () => {
    expect(monthName(7, 'en')).toBe('July')
    expect(monthName(7, 'ar')).toBe('يوليو')
  })
})

describe('Admin → Calendar', () => {
  it('shows the org\'s month, an example, and saves a new one', async () => {
    vi.mocked(calendarSettingsApi.get).mockResolvedValue({ fiscal_year_start_month: 1 })
    vi.mocked(calendarSettingsApi.set).mockImplementation(async b => b)
    render(<AdminCalendar />)
    const select = await screen.findByLabelText('The fiscal year starts in')
    expect((select as HTMLSelectElement).value).toBe('1')
    const save = screen.getByRole('button', { name: 'Save' })
    expect(save).toBeDisabled()                       // nothing changed yet
    fireEvent.change(select, { target: { value: '7' } })
    const year = new Date().getUTCFullYear()
    expect(screen.getByTestId('fiscal-example').textContent)
      .toContain(`FY${year}/${String((year + 1) % 100).padStart(2, '0')}, quarter 1`)
    fireEvent.click(save)
    await waitFor(() => expect(calendarSettingsApi.set).toHaveBeenCalledWith({ fiscal_year_start_month: 7 }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled())
  })

  it('says why it could not load', async () => {
    vi.mocked(calendarSettingsApi.get).mockRejectedValue(new Error('down'))
    render(<AdminCalendar />)
    expect(await screen.findByText(/calendar settings/i)).toBeTruthy()
  })
})
