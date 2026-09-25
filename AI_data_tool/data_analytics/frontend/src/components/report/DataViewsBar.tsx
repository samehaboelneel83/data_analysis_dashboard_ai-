import { useEffect, useState } from 'react'
import { dataViewsApi } from '../../services/api'

/**
 * Save/apply reusable data views: a named snapshot of a dataset's semantic
 * layer (roles, formats, calc columns, measures, filter, prep, hierarchy),
 * applicable to any other import dataset in the org.
 *
 * The apply result is reported verbatim — what applied, what was skipped and
 * why — because a silent partial apply would leave the author believing
 * formats exist that don't.
 */
export default function DataViewsBar({ datasetId, onApplied, isAdmin }: {
  datasetId: number
  onApplied?: () => void
  /** Only an admin may choose the view applied to every new dataset. The server
   *  refuses either way; hiding the control keeps everyone else from meeting a
   *  403 they could not have predicted. */
  isAdmin?: boolean
}) {
  const [views, setViews] = useState<{ id: number; name: string; pieces: string[]; is_default?: boolean }[]>([])
  const [selected, setSelected] = useState('')
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [status, setStatus] = useState('')

  const refresh = () => dataViewsApi.list().then(setViews).catch(() => setViews([]))
  useEffect(() => { refresh() }, [])

  const save = async () => {
    if (!name.trim()) return
    try {
      await dataViewsApi.save(datasetId, name.trim())
      setStatus(`Saved data view "${name.trim()}"`)
      setSaving(false); setName('')
      refresh()
    } catch {
      setStatus('Could not save the data view')
    }
  }

  const apply = async () => {
    const id = Number(selected)
    if (!id) return
    try {
      const r = await dataViewsApi.apply(datasetId, id)
      const parts = Object.entries(r.applied).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
      setStatus(`Applied ${parts.join(', ') || 'nothing'}${r.skipped.length ? ` — skipped ${r.skipped.length}: ${r.skipped.join('; ')}` : ''}`)
      onApplied?.()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setStatus(detail || 'Could not apply the data view')
    }
  }

  const chosen = views.find(v => String(v.id) === selected)

  const toggleDefault = async (on: boolean) => {
    if (!chosen) return
    try {
      await dataViewsApi.setDefault(chosen.id, on)
      setStatus(on
        ? `"${chosen.name}" will be applied to every dataset uploaded from now on`
        : `"${chosen.name}" is no longer applied to new datasets`)
      refresh()
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setStatus(detail || 'Could not change the default data view')
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        Data views
      </span>
      {saving ? (
        <>
          <input aria-label="Data view name" value={name} onChange={e => setName(e.target.value)}
            placeholder="e.g. Sales semantics" style={{ fontSize: 11, width: 180 }} />
          <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => void save()}>Save</button>
          <button className="btn" style={{ fontSize: 11 }} onClick={() => { setSaving(false); setName('') }}>Cancel</button>
        </>
      ) : (
        <button className="btn" style={{ fontSize: 11 }} onClick={() => setSaving(true)}>Save current as view…</button>
      )}
      <select aria-label="Saved data views" value={selected} onChange={e => setSelected(e.target.value)} style={{ fontSize: 11 }}>
        <option value="">— choose a view —</option>
        {views.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
      </select>
      <button className="btn" style={{ fontSize: 11 }} disabled={!selected} title={!selected ? 'Choose a saved view first' : undefined} onClick={() => void apply()}>Apply to this dataset</button>
      {isAdmin && chosen && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)' }}>
          <input type="checkbox" checked={!!chosen.is_default}
            onChange={e => void toggleDefault(e.target.checked)}
            style={{ margin: 0 }} />
          Default for new datasets
        </label>
      )}
      {isAdmin && chosen && (
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>
          (applied to every dataset uploaded into this organisation, as far as its
          columns match)
        </span>
      )}
      {status && <span data-testid="dataview-status" style={{ fontSize: 11, color: 'var(--muted)', flexBasis: '100%' }}>{status}</span>}
    </div>
  )
}
