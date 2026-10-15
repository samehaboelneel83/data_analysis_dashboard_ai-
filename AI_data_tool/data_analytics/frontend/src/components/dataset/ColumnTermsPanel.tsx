import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { metadataApi, type GlossaryTerm } from '../../services/api'
import { useT } from '../../i18n'

/**
 * B-21: the business terms this dataset's columns stand for, on the Columns
 * tab. Each linked column shows its term, linked to the term in the Glossary;
 * an admin gets "Link a business term" per column, which opens the dataset's
 * glossary with that column chosen. The list is the server's: terms the
 * reader may not see (another dataset's, a denied column's) never arrive.
 */
export default function ColumnTermsPanel({ datasetId, columns, canEdit }: {
  datasetId: number
  columns: string[]
  /** Only an org admin may write a glossary term. */
  canEdit: boolean
}) {
  const t = useT()
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null)

  useEffect(() => {
    let live = true
    Promise.resolve().then(() => metadataApi.datasetGlossary(datasetId))
      .then(rows => { if (live) setTerms(rows) })
      // Extra context on the tab, never a blocker: nothing shown when unreadable.
      .catch(() => { if (live) setTerms(null) })
    return () => { live = false }
  }, [datasetId])

  if (terms === null) return null
  const own = new Set(columns)
  const byColumn = new Map<string, GlossaryTerm[]>()
  for (const term of terms) {
    const col = term.maps_to_column
    if (!col || !own.has(col)) continue
    // A connection's term names a column of one of ITS tables; on a dataset
    // only the dataset's own terms and untabled ones describe its columns.
    if (term.dataset_id == null && term.maps_to_object) continue
    byColumn.set(col, [...(byColumn.get(col) ?? []), term])
  }
  const linked = columns.filter(c => byColumn.has(c))

  return (
    <section className="card" style={{ padding: 14, margin: '12px 0' }} aria-label={t('pg.dataPages.gl.colTermsTitle')}>
      <h3 style={{ margin: '0 0 4px', fontSize: 14 }}>{t('pg.dataPages.gl.colTermsTitle')}</h3>
      <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--muted)' }}>{t('pg.dataPages.gl.colTermsIntro')}</p>
      {linked.length === 0 && (
        <p style={{ margin: '0 0 8px', fontSize: 12, color: 'var(--muted)' }}>{t('pg.dataPages.gl.colTermsNone')}</p>
      )}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 4, fontSize: 12.5 }}>
        {(canEdit ? columns : linked).map(col => (
          <li key={col} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 8 }}>
            <bdi dir="ltr" style={{ fontFamily: 'var(--mono)', minWidth: 120 }}>{col}</bdi>
            {(byColumn.get(col) ?? []).map(term => (
              <Link key={term.id} to={`/glossary?dataset=${datasetId}#term-${term.id}`}
                title={term.definition ?? undefined} style={{ fontWeight: 600 }}>
                {term.term}
              </Link>
            ))}
            {canEdit && (
              <Link to={`/glossary?dataset=${datasetId}&column=${encodeURIComponent(col)}`}
                aria-label={t('pg.dataPages.gl.colLinkFor', { name: col })}
                style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                {t('pg.dataPages.gl.colLink')}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
