import { useEffect, useState } from 'react'
import { widgetDataApi } from '../../services/api'
import MiniBarChart from './MiniBarChart'

interface Finding {
  kind: string
  title: string
  columns: string[]
}

/**
 * A finding's own chart, derived the same way InsightsPane's "+ Chart it"
 * button does (category+measure -> bar, single measure -> histogram) but
 * fetched and shown inline instead of waiting for a click. A correlation
 * between two measures has no bar/histogram shape worth a mini chart here,
 * so it -- like a finding with no columns -- stays text-only, same as
 * "+ Chart it" offering nothing for that case.
 */
export default function FindingChart({ datasetId, finding, columnTypes }: {
  datasetId: number
  finding: Finding
  columnTypes: Record<string, string>
}) {
  const [rows, setRows] = useState<{ name: unknown; value?: unknown }[] | null>(null)
  // Which chart the rows belong to. A histogram's bins are a distribution
  // and must stay in range order; a categorical bar is a ranking.
  const [isHistogram, setIsHistogram] = useState(false)
  // What the bars are OF -- the same thing an axis title says on a full-size
  // chart. Each bar here names its own category, but nothing named the
  // measure until this line.
  const [caption, setCaption] = useState<string | undefined>(undefined)

  useEffect(() => {
    setRows(null)
    const cats = finding.columns.filter(c => columnTypes[c] === 'categorical')
    const nums = finding.columns.filter(c => columnTypes[c] === 'numeric')

    let config: Record<string, unknown> | null = null
    let widgetType = 'bar'
    let says: string | undefined
    if (cats.length && nums.length) {
      config = { dimension: cats[0], measure: nums[0], aggregation: 'sum' }
      widgetType = 'bar'
      says = `sum(${nums[0]}) by ${cats[0]}`
    } else if (nums.length === 1) {
      config = { measure: nums[0], bins: 20 }
      widgetType = 'histogram'
      says = `count of rows by ${nums[0]}`
    }
    if (!config) return
    setCaption(says)

    let cancelled = false
    const histogram = widgetType === 'histogram'
    widgetDataApi.query(datasetId, config, [], widgetType)
      .then(r => { if (!cancelled) { setIsHistogram(histogram); setRows(r?.rows ?? []) } })
      .catch(() => { /* a chart that failed to load is still a finding worth reading */ })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId, finding.kind, finding.title, finding.columns.join(',')])

  if (!rows) return null
  return <MiniBarChart rows={rows} ordered={isHistogram} caption={caption} />
}
