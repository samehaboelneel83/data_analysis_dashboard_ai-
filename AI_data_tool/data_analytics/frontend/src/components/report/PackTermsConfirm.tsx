import type { BoundaryPack } from '../../services/api'

/**
 * The terms of a starter pack whose source requires them, shown BEFORE it is
 * installed.
 *
 * Some boundary data (the EU NUTS regions, from Eurostat/GISCO) is free to use
 * only on conditions: the source must be credited on every map, and some uses
 * are excluded. A button that installs it on one click would accept those
 * terms on the org's behalf without anybody reading them, so packs flagged
 * `requires_acceptance` go through this panel first. It is inline rather than
 * a `window.confirm`, which cannot show a link or keep the text readable.
 */
export default function PackTermsConfirm({ pack, busy, onAccept, onCancel }: {
  pack: BoundaryPack
  busy?: boolean
  onAccept: () => void
  onCancel: () => void
}) {
  return (
    <div role="group" aria-label={`Terms for ${pack.name}`} data-testid="pack-terms"
      style={{
        marginTop: 6, padding: 8, border: '1px solid var(--border)', borderRadius: 6,
        fontSize: 11, background: 'var(--surface-2, transparent)',
      }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>
        {pack.name}: terms of use
      </div>
      {pack.terms && <p style={{ margin: '0 0 4px' }}>{pack.terms}</p>}
      {pack.attribution && (
        <p style={{ margin: '0 0 4px' }}>
          Every map drawn from it will show: <em>{pack.attribution}</em>
        </p>
      )}
      <p style={{ margin: '0 0 6px', color: 'var(--muted)' }}>
        Source: {pack.source}. Licence: {pack.license}
        {pack.license_url && (
          <> (<a href={pack.license_url} target="_blank" rel="noreferrer">read the licence</a>)</>
        )}.
      </p>
      <div style={{ display: 'flex', gap: 6 }}>
        <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={onAccept}>
          I accept, install
        </button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
