/**
 * The Insights page's plain summary (guided setup, phase 5d): when the
 * person ran the guided setup on the chosen dataset, what it found -- in
 * words for their work -- sits above the page's own scan.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useT } from '../../i18n'
import { setupApi, type SetupFindings } from '../../services/api'
import PlainSummary from '../ui/PlainSummary'
import { sayText } from '../../lib/readbackText'

export default function SetupInsights({ datasetId }: { datasetId: number }) {
  const t = useT()
  const [found, setFound] = useState<{ findings: SetupFindings; source: number } | null>(null)
  useEffect(() => {
    let alive = true
    setFound(null)
    // Optional: whatever goes wrong here, the page's own scan is unaffected.
    Promise.resolve().then(() => setupApi.findings(datasetId)).then(r => {
      if (alive && r.findings?.insights.length && r.source_id) setFound({ findings: r.findings, source: r.source_id })
    }).catch(() => {})
    return () => { alive = false }
  }, [datasetId])
  if (!found) return null
  return (
    <div style={{ marginBottom: 16 }}>
      <PlainSummary title={t('setup.p.fromSetup')}
        items={found.findings.insights.map(i => ({ id: i.id, tone: 'insight' as const, what: sayText(t, i.what, (i as { what_i18n?: unknown }).what_i18n as never),
                                                   why: sayText(t, i.why ?? '', (i as { why_i18n?: unknown }).why_i18n as never) || undefined, todo: i.todo ?? undefined }))} />
      <p style={{ margin: '8px 0 0', fontSize: 13 }}>
        <Link to={`/setup/${found.source}?step=check`}>{t('setup.p.openCheck')}</Link>
      </p>
    </div>
  )
}
