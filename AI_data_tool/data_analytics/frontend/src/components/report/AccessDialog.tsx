import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { pageVisibilityApi, reportCapabilityApi } from '../../services/api'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useModalDialog } from '../ui/useModalDialog'

const LEVELS = [
  { value: 'data', label: 'Full (view + edit + data)' },
  { value: 'edit', label: 'Edit (structure, no data model)' },
  { value: 'view', label: 'View only' },
] as const

/**
 * Per-report viewer capability levels, SAS's three additive tiers assigned per
 * role. Admin-only. A role left at "Full" stores no restriction (the default),
 * so this dialog only ever writes the roles an admin deliberately narrows.
 * Org-admin roles are always full and are not listed.
 */
export default function AccessDialog({ reportId, onClose }: { reportId: number; onClose: () => void }) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [roles, setRoles] = useState<{ id: number; name: string }[]>([])
  const [levels, setLevels] = useState<Record<number, string>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([pageVisibilityApi.roles(), reportCapabilityApi.get(reportId)])
      .then(([rs, lv]) => {
        setRoles(rs)
        setLevels(Object.fromEntries(Object.entries(lv).map(([k, v]) => [Number(k), v])))
      })
      .catch(() => toast.error('Could not load access settings'))
      .finally(() => setLoading(false))
  }, [reportId])

  const setRole = async (roleId: number, level: string) => {
    const next = { ...levels }
    if (level === 'data') delete next[roleId]
    else next[roleId] = level
    setLevels(next)
    try {
      const saved = await reportCapabilityApi.set(reportId, next)
      setLevels(Object.fromEntries(Object.entries(saved).map(([k, v]) => [Number(k), v])))
      toast.success('Access updated')
    } catch {
      toast.error('Could not save access')
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }} onClick={onClose}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Report access"
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
          padding: 24, width: 480, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Report access by role</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
          Each role's capability on this report. Full is the default; narrowing a role restricts
          what its members can do — enforced on the server, not just hidden. Admins always have full access.
        </p>
        {loading && <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>}
        {!loading && roles.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>No roles to configure.</p>
        )}
        {roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span style={{ flex: 1, fontSize: 13 }}>{r.name}</span>
            <select aria-label={`Access level for ${r.name}`}
              value={levels[r.id] ?? 'data'} onChange={e => setRole(r.id, e.target.value)}
              style={{ fontSize: 12, width: 240 }}>
              {LEVELS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
            </select>
          </div>
        ))}
      </div>
    </div>
  )
}
