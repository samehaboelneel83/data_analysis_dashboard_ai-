/**
 * Fiscal-year labels, as the server makes them (services/fiscal.py) -- used
 * to show an example beside the setting, never to bucket data.
 *
 * January start: `FY2025`, `FY2025-Q1`. Any other: `FY2025/26`,
 * `FY2025/26-Q1`, named by both calendar years the fiscal year spans.
 */
export function fiscalLabel(date: Date, granularity: 'fiscal_year' | 'fiscal_quarter', startMonth: number): string {
  const start = startMonth >= 1 && startMonth <= 12 ? Math.trunc(startMonth) : 1
  const month = date.getUTCMonth() + 1
  const first = date.getUTCFullYear() - (month < start ? 1 : 0)
  const name = start === 1 ? `FY${first}` : `FY${first}/${String((first + 1) % 100).padStart(2, '0')}`
  if (granularity === 'fiscal_year') return name
  const q = Math.floor(((month - start + 12) % 12) / 3) + 1
  return `${name}-Q${q}`
}

/** The month's name in the reader's language (1 = January). */
export function monthName(month: number, locale: string): string {
  return new Intl.DateTimeFormat(locale, { month: 'long', timeZone: 'UTC' })
    .format(new Date(Date.UTC(2024, month - 1, 15)))
}
