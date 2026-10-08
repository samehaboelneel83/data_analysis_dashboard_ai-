import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { packText, richNodes } from '../../i18n/pages/adminPlatform'
import { useDirection } from '../../contexts/DirectionContext'
import toast from 'react-hot-toast'
import { boundarySetsApi, type BoundaryPack, type BoundarySetSummary } from '../../services/api'
import BasemapSettings from '../../components/admin/BasemapSettings'
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
/** A block line inside a pack's entry; `isolate` keeps a dir="auto" line's punctuation its own. */
const PACK_LINE = { display: 'block', unicodeBidi: 'isolate' } as const

export default function AdminMaps() {
  const t = useT()
  const { language } = useDirection()
  const pack = (p: BoundaryPack, field: 'name' | 'description' | 'license') => packText(t, language, p.id, field, p[field])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [sets, setSets] = useState<BoundarySetSummary[]>([])
  const [packs, setPacks] = useState<BoundaryPack[]>([])

  const load = () => {
    setLoading(true); setLoadError(null)
    Promise.all([boundarySetsApi.list(), boundarySetsApi.packs().catch(() => [])])
      .then(([bs, p]) => { setSets(bs); setPacks(p) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const [pendingTerms, setPendingTerms] = useState<string | null>(null)
  const install = async (p: BoundaryPack, accepted = false) => {
    if (p.requires_acceptance && !accepted) { setPendingTerms(p.id); return }
    try {
      await boundarySetsApi.installPack(p.id, accepted)
      setPendingTerms(null)
      toast.success(t('pg.adminPlatform.maps.installed', { name: pack(p, 'name') }))
      load()
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('pg.adminPlatform.maps.installFailed'))
    }
  }

  if (loading) return <LoadingState />
  if (loadError) return <LoadError what={t('pg.adminPlatform.maps.loadWhat')} title={t('pg.adminPlatform.loadErr', { what: t('pg.adminPlatform.maps.loadWhat') })}
    retryLabel={t('pg.adminPlatform.retry')} error={loadError} onRetry={load} />
  const installable = packs.filter(p => !sets.some(s => s.name === p.name))
  return (
    <div style={{ maxWidth: 820 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.maps')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>
        {t('pg.adminPlatform.maps.intro')}
      </p>

      <BasemapSettings />

      <section className="card" style={{ padding: 16, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, marginTop: 0 }}>{t('pg.adminPlatform.maps.sets')}</h2>
        {sets.length === 0 ? <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('pg.adminPlatform.maps.none')}</p> : (
          <ul style={{ fontSize: 13, paddingInlineStart: 18 }}>
            {sets.map(s => <li key={s.id}><bdi>{s.name}</bdi> <span style={{ color: 'var(--muted)' }}>{t('pg.adminPlatform.maps.regions', { n: s.feature_count })}</span></li>)}
          </ul>
        )}
        {installable.length > 0 && (
          <>
            <h3 style={{ fontSize: 13, marginBottom: 6 }}>{t('pg.adminPlatform.maps.packs')}</h3>
            <ul style={{ fontSize: 13, paddingInlineStart: 18 }}>
              {installable.map(p => (
                <li key={p.id} style={{ marginBottom: 6 }}>
                  {/* QA5 L7: the description and the source/licence line are
                      blocks of their own: server prose that wraps inside an
                      Arabic sentence scattered its punctuation. Any English the
                      server sends is isolated with dir="auto". */}
                  <b><bdi>{pack(p, 'name')}</bdi></b> <span style={{ color: 'var(--muted)' }}>
                    {t('pg.adminPlatform.maps.packCount', { n: p.feature_count })}
                    {p.description && <> <span dir="auto" style={PACK_LINE}>{pack(p, 'description')}</span></>}
                    {' '}<span style={PACK_LINE}>{richNodes(t('pg.adminPlatform.maps.packSource'), {
                      source: <bdi dir="ltr">{p.source}</bdi>,
                      license: <bdi dir="auto">{pack(p, 'license')}</bdi>,
                    })}</span>
                  </span>{' '}
                  <button className="btn btn-sm" onClick={() => void install(p)}>
                    {p.requires_acceptance ? t('pg.adminPlatform.maps.reviewInstall') : t('pg.adminPlatform.maps.install')}
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
        <p style={{ fontSize: 11.5, color: 'var(--muted)' }}>{t('pg.adminPlatform.maps.customFiles')}</p>
      </section>
    </div>
  )
}
