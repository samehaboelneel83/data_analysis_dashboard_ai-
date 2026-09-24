export interface AnalyticsLineConfig {
  referenceValue?: number
  referenceLabel?: string
  referenceColor?: string
  showAverageLine?: boolean
}

export interface AnalyticsLine {
  value: number
  label: string
  color: string
}

const DEFAULT_REFERENCE_COLOR = '#f59e0b'
const AVERAGE_COLOR = '#8b5cf6'

export function computeAnalyticsLines(rows: { value?: unknown; [key: string]: unknown }[], analytics: AnalyticsLineConfig | undefined): AnalyticsLine[] {
  if (!analytics) return []
  const lines: AnalyticsLine[] = []

  if (analytics.referenceValue != null && !isNaN(analytics.referenceValue)) {
    lines.push({
      value: analytics.referenceValue,
      label: analytics.referenceLabel || 'Reference',
      color: analytics.referenceColor || DEFAULT_REFERENCE_COLOR,
    })
  }

  if (analytics.showAverageLine) {
    const nums = rows.filter(r => r.value != null).map(r => Number(r.value)).filter(n => !isNaN(n))
    if (nums.length > 0) {
      const avg = nums.reduce((a, b) => a + b, 0) / nums.length
      lines.push({ value: avg, label: 'Average', color: AVERAGE_COLOR })
    }
  }

  return lines
}
