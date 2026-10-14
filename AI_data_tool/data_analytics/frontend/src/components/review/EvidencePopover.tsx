import { useT } from '../../i18n'
import { rich } from '../../i18n/pages/modelsMaps'
import type { FkEvidence } from '../../services/api'

/**
 * Why inference proposed a relationship.
 *
 * ARCHITECTURE.md: evidence is stored "so the review UI can justify each
 * suggestion rather than asking for blind trust". A user asked to approve a
 * join needs to see what it was based on — 97% of orders.customer_id values
 * appear in customers.id is an argument; "confidence 0.94" is a number they have
 * no way to check.
 */
export function EvidenceSummary({ evidence }: { evidence: FkEvidence | null }) {
  const t9 = useT()
  if (!evidence) return null

  const overlapPct = Math.round((evidence.overlap ?? 0) * 100)

  return (
    <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.6 }}>
      <div>
        {rich(t9, 'evp.overlap', { pct: <strong>{overlapPct}%</strong> })}
        {evidence.child_distinct != null && (
          <> {t9('evp.sampled', { n: evidence.child_distinct })}</>
        )}
      </div>
      <div>
        {rich(t9, 'evp.name', { pct: <strong>{Math.round((evidence.name_score ?? 0) * 100)}%</strong> })}
        {evidence.name_score >= 1 && ` ${t9('evp.convention', { pattern: '<table>_id' })}`}
      </div>
      {evidence.parent_distinct != null && (
        <div>{t9('evp.parent', { n: evidence.parent_distinct })}</div>
      )}
      <div style={{ marginTop: 4, color: '#64748b', fontStyle: 'italic' }}>
        {t9('evp.cached')}
      </div>
    </div>
  )
}

export default EvidenceSummary
