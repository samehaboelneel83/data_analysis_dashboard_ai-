import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { sensitivityApi, type DatasetSensitivity as Sens } from '../services/api'

/**
 * A dataset's sensitivity label (Phase 7.3): its own label, the label in
 * force after lineage (a source or joined dataset can raise it) with the
 * reason, and what the label enforces -- in words, next to the control.
 */
export default function DatasetSensitivity({ datasetId }: { datasetId: number }) {
  const [s, setS] = useState<Sens | null>(null)
  useEffect(() => {
    let live = true
    sensitivityApi.get(datasetId).then(r => { if (live) setS(r) }).catch(() => { if (live) setS(null) })
    return () => { live = false }
  }, [datasetId])
  if (!s) return null
  const inherited = s.effective && s.effective !== s.label
  const enforce = s.effective === 'Restricted'
    ? 'No guest links or embeds; downloads need data-level access; not e-mailed.'
    : s.effective === 'Confidential'
      ? `Guest links need a signed-in member${s.redacted_on_share.length ? `; ${s.redacted_on_share.join(', ')} redacted from links, embeds and files` : ''}.`
      : null
  return (
    <span data-testid="dataset-sensitivity" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11 }}
      title={[inherited ? `In force: ${s.effective} — ${s.reasons[0] ?? ''}` : '', enforce ?? ''].filter(Boolean).join(' · ') || 'Sensitivity label'}>
      <select aria-label="Dataset sensitivity" value={s.label ?? ''} style={{ fontSize: 11, padding: '2px 4px' }}
        onChange={async e => {
          try {
            setS(await sensitivityApi.set(datasetId, e.target.value))
            toast.success(e.target.value ? `Labelled ${e.target.value}` : 'Label cleared')
          } catch (err) {
            toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not label this dataset')
          }
        }}>
        <option value="">— Unlabelled —</option>
        {s.options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
      {inherited && <span style={{ color: 'var(--muted)' }}>in force: <b>{s.effective}</b></span>}
    </span>
  )
}
