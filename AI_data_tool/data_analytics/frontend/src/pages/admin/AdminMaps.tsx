import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import toast from 'react-hot-toast'
import { boundarySetsApi, mapSettingsApi, type BoundaryPack, type BoundarySetSummary, type MapSettings } from '../../services/api'
import { setTileSettings } from '../../components/report/geo/tiles'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'
import PackTermsConfirm from '../../components/report/PackTermsConfirm'

/**
 * Org map settings: the basemap tile server, and the org's boundary sets and
 * starter packs in one place (they can also be managed from any region map).
 *
 * No basemap by default. The platform runs air-gapped, so there is no public
 * tile service to fall back to: an org that wants streets and terrain under its
 * maps points this at its own XYZ tile server.
 */
export default function AdminMaps() {
  const t = useT()
  const [form, setForm] = useState<MapSettings>({ tile_url: '', attribution: '', contrast_tile_url: '' })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [sets, setSets] = useState<BoundarySetSummary[]>([])
  const [packs, setPacks] = useState<BoundaryPack[]>([])

  const load = () => {
    setLoading(true); setLoadError(null)
    Promise.all([mapSettingsApi.get(), boundarySetsApi.list(), boundarySetsApi.packs().catch(() => [])])
      .then(([s, bs, p]) => {
        setForm({ tile_url: s.tile_url ?? '', attribution: s.attribution ?? '', contrast_tile_url: s.contrast_tile_url ?? '' })
        setSets(bs); setPacks(p)
      })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const save = async (next: MapSettings) => {
    setSaving(true)
    try {
      const saved = await mapSettingsApi.set(next)
      setForm({ tile_url: saved.tile_url ?? '', attribution: saved.attribution ?? '', contrast_tile_url: saved.contrast_tile_url ?? '' })
      setTileSettings(saved)
      toast.success(saved.tile_url ? 'Basemap saved' : 'Basemap turned off')
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not save')
    } finally { setSaving(false) }
  }

  const [pendingTerms, setPendingTerms] = useState<string | null>(null)
  const install = async (p: BoundaryPack, accepted = false) => {
    if (p.requires_acceptance && !accepted) { setPendingTerms(p.id); return }
    try {
      await boundarySetsApi.installPack(p.id, accepted)
      setPendingTerms(null)
      toast.success(`${p.name} installed`)
      load()
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Could not install')
    }
  }

  if (loading) return <LoadingState />
  if (loadError) return <LoadError what="the map settings" error={loadError} onRetry={load} />
  const field = (key: keyof MapSettings, label: string, placeholder: string, hint: string) => (
    <label style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
      <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{label}</span>
      <input value={form[key] ?? ''} placeholder={placeholder} style={{ width: '100%', maxWidth: 560 }}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      <span style={{ display: 'block', fontSize: 11.5, color: 'var(--muted)', marginTop: 3 }}>{hint}</span>
    </label>
  )
  const installable = packs.filter(p => !sets.some(s => s.name === p.name))
  return (
    <div style={{ maxWidth: 820 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.maps')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>
        Basemap tiles and region boundaries for every map in the organisation.
      </p>

      <section className="card" style={{ padding: 16, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, marginTop: 0 }}>Basemap</h2>
        <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>
          Off by default: maps draw country outlines only. Point this at your own XYZ tile server to draw
          streets and terrain under every map; maps then use the tiles' Web Mercator projection.
        </p>
        {field('tile_url', 'Tile address', 'https://tiles.example.local/{z}/{x}/{y}.png',
          'Must contain {z}, {x} and {y}. {s} rotates a/b/c subdomains. Tiles are fetched by each viewer’s browser.')}
        {field('attribution', 'Attribution', '© OpenStreetMap contributors',
          'Shown in the corner of every map with tiles. Required by almost every tile licence.')}
        {field('contrast_tile_url', 'High-contrast tile address (optional)', 'https://tiles.example.local/contrast/{z}/{x}/{y}.png',
          'Used instead for viewers whose system asks for more contrast.')}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => void save(form)}>
            {saving ? 'Saving…' : 'Save'}
          </button>
          {form.tile_url && (
            <button className="btn btn-sm" disabled={saving}
              onClick={() => void save({ tile_url: '', attribution: '', contrast_tile_url: '' })}>Turn basemap off</button>
          )}
        </div>
      </section>

      <section className="card" style={{ padding: 16, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, marginTop: 0 }}>Boundary sets</h2>
        {sets.length === 0 ? <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>None yet.</p> : (
          <ul style={{ fontSize: 13, paddingInlineStart: 18 }}>
            {sets.map(s => <li key={s.id}>{s.name} <span style={{ color: 'var(--muted)' }}>— {s.feature_count} regions</span></li>)}
          </ul>
        )}
        {installable.length > 0 && (
          <>
            <h3 style={{ fontSize: 13, marginBottom: 6 }}>Starter packs</h3>
            <ul style={{ fontSize: 13, paddingInlineStart: 18 }}>
              {installable.map(p => (
                <li key={p.id} style={{ marginBottom: 6 }}>
                  <b>{p.name}</b> <span style={{ color: 'var(--muted)' }}>— {p.feature_count} regions. {p.description} Source: {p.source}; licence: {p.license}.</span>{' '}
                  <button className="btn btn-sm" onClick={() => void install(p)}>
                    {p.requires_acceptance ? 'Review terms & install' : 'Install'}
                  </button>
                  {pendingTerms === p.id && (
                    <PackTermsConfirm pack={p}
                      onAccept={() => void install(p, true)}
                      onCancel={() => setPendingTerms(null)} />
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        <p style={{ fontSize: 11.5, color: 'var(--muted)' }}>Custom boundary files are uploaded from any region map’s Boundaries picker.</p>
      </section>
    </div>
  )
}
