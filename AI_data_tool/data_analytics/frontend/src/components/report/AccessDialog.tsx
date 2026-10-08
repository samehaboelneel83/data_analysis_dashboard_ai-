import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { pageVisibilityApi, reportCapabilityApi } from '../../services/api'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useModalDialog } from '../ui/useModalDialog'
import { useT, type MessageKey } from '../../i18n'

// '' is "no row": what the server actually does without one -- nothing while
// the report is a draft, look-and-filter once it is published. The dialog used
// to show that state as "Full (view + edit + data)", so a Confidential salary
// report LOOKED open to every role (HR evaluation, item 2.3).
const LEVELS: { value: string; label: MessageKey }[] = [
  { value: '', label: 'pg.panelsA.ad.level.default' },
  { value: 'view', label: 'pg.panelsA.ad.level.view' },
  { value: 'edit', label: 'pg.panelsA.ad.level.edit' },
  { value: 'data', label: 'pg.panelsA.ad.level.data' },
]

/**
 * Per-report viewer capability levels, SAS's three additive tiers assigned per
 * role. Admin-only. A role left at "Default" stores no row: it sees nothing
 * while the report is a draft and can view (not edit) once it is published --
 * `core/capability._resolve`. Any other choice is stored for that role.
 * Org-admin roles are always full and are not listed.
 */
export default function AccessDialog({ reportId, onClose }: { reportId: number; onClose: () => void }) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const t = useT()
  const [roles, setRoles] = useState<{ id: number; name: string }[]>([])
  const [levels, setLevels] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([pageVisibilityApi.roles(), reportCapabilityApi.get(reportId)])
      .then(([rs, lv]) => {
        setRoles(rs)
        setLevels(Object.fromEntries(Object.entries(lv).map(([k, v]) => [Number(k), v])))
      })
      .catch(() => toast.error(t('pg.panelsA.ad.loadFailed')))
      .finally(() => setLoading(false))
  }, [reportId])

  const setRole = async (roleId: number, level: string) => {
    const next = { ...levels }
    if (level === '') delete next[roleId]
    else next[roleId] = level
    setLevels(next)
    try {
      const saved = await reportCapabilityApi.set(reportId, next)
      setLevels(Object.fromEntries(Object.entries(saved).map(([k, v]) => [Number(k), v])))
      toast.success(t('pg.panelsA.ad.updated'))
    } catch {
      toast.error(t('pg.panelsA.ad.saveFailed'))
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }} onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={t('pg.panelsA.ad.aria')}
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
          padding: 24, width: 480, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{t('pg.panelsA.ad.title')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
          {t('pg.panelsA.ad.intro')}
        </p>
        {loading && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('common.loading')}</p>}
        {!loading && roles.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('pg.panelsA.ad.noRoles')}</p>
        )}
        {roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ flex: 1, fontSize: 13 }}><bdi>{r.name}</bdi></span>
            <select aria-label={t('pg.panelsA.ad.levelFor', { name: r.name })}
              value={levels[r.id] ?? ''} onChange={e => setRole(r.id, e.target.value)}
              style={{ fontSize: 12, width: 240 }}>
              {LEVELS.map(l => <option key={l.value} value={l.value}>{t(l.label)}</option>)}
            </select>
          </div>
        ))}
      </div>
    </div>
  )
}
