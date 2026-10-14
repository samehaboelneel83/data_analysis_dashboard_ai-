/**
 * The review page's plain summary (guided setup, phase 5c): what the
 * database holds and where to start, from the Understand step's kept words
 * -- the detailed review (relationships, columns, entities) stays below.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { setupApi, type SetupSummary } from '../../services/api'
import PlainSummary from '../ui/PlainSummary'

export default function SourceSummary({ sourceId }: { sourceId: number }) {
  const t = useT()
  const { language } = useDirection()
  const [data, setData] = useState<SetupSummary | null>(null)
  useEffect(() => {
    let alive = true
    Promise.resolve().then(() => setupApi.summary(sourceId, language)).then(d => { if (alive) setData(d) }).catch(() => {})
    return () => { alive = false }
  }, [sourceId, language])
  if (!data || data.status !== 'ready') return null
  const totals = data.totals!
  const main = (data.tables ?? []).filter(x => x.group === 'main').slice(0, 3)
  const lead = data.overview ?? t('setup.u.factsSentence', {
    name: data.source.name, tables: localDigits(totals.tables.toLocaleString()), rows: localDigits(totals.rows.toLocaleString()) })
  return (
    <div style={{ marginBottom: 16 }}>
      <PlainSummary title={t('setup.u.holds')} lead={lead}
        items={main.map(x => ({ id: String(x.id), tone: 'info' as const,
          what: x.title ? `${x.title} (${x.name})` : x.name,
          why: x.what ?? undefined, todo: x.useful_for ?? undefined }))} />
      <p style={{ margin: '8px 0 0', fontSize: 13 }}>
        <Link to={`/setup/${sourceId}`}>{t('setup.review.cta')}</Link>
      </p>
    </div>
  )
}
