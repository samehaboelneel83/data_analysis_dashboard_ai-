import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useT } from '../../i18n'
import { mapSettingsApi, type MapSettings } from '../../services/api'
import { setTileSettings } from '../report/geo/tiles'
import LoadError from '../ui/LoadError'
import LoadingState from '../ui/LoadingState'

/**
 * The organization's basemap tile server: one form, shown on Admin -> Maps and
 * on Admin -> Settings.
 *
 * No basemap by default. The platform runs air-gapped, so there is no public
 * tile service to fall back to: an org that wants streets and terrain under its
 * maps points this at its own XYZ tile server.
 */
export default function BasemapSettings({ headingLevel = 2 }: { headingLevel?: 2 | 3 }) {
  const t = useT()
  const [form, setForm] = useState<MapSettings>({ tile_url: '', attribution: '', contrast_tile_url: '' })
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true); setLoadError(null)
    mapSettingsApi.get()
      .then(s => setForm({ tile_url: s.tile_url ?? '', attribution: s.attribution ?? '', contrast_tile_url: s.contrast_tile_url ?? '' }))
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
      toast.success(saved.tile_url ? t('pg.adminPlatform.basemap.saved') : t('pg.adminPlatform.basemap.off'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('pg.adminPlatform.basemap.saveFailed'))
    } finally { setSaving(false) }
  }

  const Heading = headingLevel === 3 ? 'h3' : 'h2'
  const field = (key: keyof MapSettings, label: string, placeholder: string, hint: string, ltr = true) => (
    <label style={{ display: 'block', marginBottom: 12, fontSize: 13 }}>
      <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{label}</span>
      <input value={form[key] ?? ''} placeholder={placeholder} style={{ width: '100%', maxWidth: 560 }} dir={ltr ? 'ltr' : undefined}
        onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
      <span style={{ display: 'block', fontSize: 11.5, color: 'var(--muted)', marginTop: 3 }}>{hint}</span>
    </label>
  )
  return (
    <section className="card" style={{ padding: 16, marginTop: 16 }}>
      <Heading style={{ fontSize: 15, marginTop: 0 }}>{t('pg.adminPlatform.basemap.title')}</Heading>
      {loading ? <LoadingState /> : loadError ? <LoadError what={t('pg.adminPlatform.maps.loadWhat')}
        title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.maps.loadWhat') })} retryLabel={t('pg.adminPlatform.retry')}
        error={loadError} onRetry={load} /> : (
        <>
          <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>
            {t('pg.adminPlatform.basemap.intro')}
          </p>
          {/* The hints show {z}/{x}/{y} literally: no vars are passed, so t() leaves them. */}
          {field('tile_url', t('pg.adminPlatform.basemap.tileUrl'), 'https://tiles.example.local/{z}/{x}/{y}.png',
            t('pg.adminPlatform.basemap.tileHint'))}
          {field('attribution', t('pg.adminPlatform.basemap.attribution'), '© OpenStreetMap contributors',
            t('pg.adminPlatform.basemap.attributionHint'), false)}
          {field('contrast_tile_url', t('pg.adminPlatform.basemap.contrastUrl'), 'https://tiles.example.local/contrast/{z}/{x}/{y}.png',
            t('pg.adminPlatform.basemap.contrastHint'))}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" disabled={saving} onClick={() => void save(form)}>
              {saving ? t('pg.adminPlatform.saving') : t('pg.adminPlatform.save')}
            </button>
            {form.tile_url && (
              <button className="btn btn-sm" disabled={saving}
                onClick={() => void save({ tile_url: '', attribution: '', contrast_tile_url: '' })}>{t('pg.adminPlatform.basemap.turnOff')}</button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
