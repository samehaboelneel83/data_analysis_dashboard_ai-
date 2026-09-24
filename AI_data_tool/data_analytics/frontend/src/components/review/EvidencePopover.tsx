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
  if (!evidence) return null

  const overlapPct = Math.round((evidence.overlap ?? 0) * 100)

  return (
    <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.6 }}>
      <div>
        <strong>{overlapPct}%</strong> of the child column&apos;s distinct values
        appear in the parent
        {evidence.child_distinct != null && (
          <> ({evidence.child_distinct} distinct values sampled)</>
        )}
      </div>
      <div>
        Name match: <strong>{Math.round((evidence.name_score ?? 0) * 100)}%</strong>
        {evidence.name_score >= 1 && ' — follows the <table>_id convention'}
      </div>
      {evidence.parent_distinct != null && (
        <div>Parent column holds {evidence.parent_distinct} distinct values</div>
      )}
      <div style={{ marginTop: 4, color: '#64748b', fontStyle: 'italic' }}>
        Measured on a cached sample, not the live table.
      </div>
    </div>
  )
}

export default EvidenceSummary
