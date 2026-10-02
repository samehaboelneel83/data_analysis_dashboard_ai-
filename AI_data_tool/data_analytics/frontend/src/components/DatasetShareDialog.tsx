import { useEffect, useMemo, useState } from 'react'
import { adminRolesApi, adminUsersApi, datasetSharesApi, orgUnitsApi } from '../services/api'
import type { DatasetShare, User } from '../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from './ui/ConfirmDialog'
import { useModalDialog } from './ui/useModalDialog'

type Kind = 'user' | 'role' | 'org_unit'
type Level = 'view' | 'edit'

/**
 * In-org dataset sharing, managed by org admins.
 *
 * A share is a real grant (`core.capability.readable_dataset_ids` reads it),
 * now with two things the HR evaluation asked for (item 2.5): share with a
 * whole ROLE or an ORG UNIT (and everyone placed under it) instead of one
 * person at a time, and choose VIEW (look only) or EDIT (may also re-model
 * the data). Rows are still filtered by each viewer's own row rules.
 */
export default function DatasetShareDialog({ datasetId, onClose }: {
  datasetId: number
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const confirm = useConfirm()
  const [shares, setShares] = useState<DatasetShare[]>([])
  const [orgUsers, setOrgUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<{ id: number; name: string; is_org_admin?: boolean }[]>([])
  const [units, setUnits] = useState<{ id: number; name: string }[]>([])
  const [kind, setKind] = useState<Kind>('user')
  const [picked, setPicked] = useState<number | ''>('')
  const [level, setLevel] = useState<Level>('view')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([datasetSharesApi.list(datasetId), adminUsersApi.list()])
      .then(([s, u]) => { setShares(s); setOrgUsers(u) })
      .catch(() => toast.error('Failed to load shares'))
      .finally(() => setLoading(false))
    // Roles and units are optional extras: a failure leaves user sharing working.
    adminRolesApi?.list?.().then(r => setRoles(r as never)).catch(() => {})
    orgUnitsApi?.list?.().then(u => setUnits(u as never)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const kindOf = (s: DatasetShare): Kind => s.kind ?? 'user'
  const taken = useMemo(() => new Set(shares.map(s =>
    `${kindOf(s)}:${kindOf(s) === 'user' ? s.user_id : kindOf(s) === 'role' ? s.role_id : s.org_unit_id}`)), [shares])
  const options: { id: number; label: string }[] = kind === 'user'
    ? orgUsers.filter(u => !taken.has(`user:${u.id}`)).map(u => ({ id: u.id, label: u.email }))
    : kind === 'role'
      ? roles.filter(r => !r.is_org_admin && !taken.has(`role:${r.id}`)).map(r => ({ id: r.id, label: r.name }))
      : units.filter(u => !taken.has(`org_unit:${u.id}`)).map(u => ({ id: u.id, label: u.name }))
  const nameOf = (s: DatasetShare) => s.name ?? s.email ?? ''

  const handleShare = async () => {
    if (picked === '') return
    setSaving(true)
    try {
      const share = kind === 'user'
        ? await datasetSharesApi.create(datasetId, picked as number, level)
        : await datasetSharesApi.createGroup(datasetId, {
            ...(kind === 'role' ? { role_id: picked as number } : { org_unit_id: picked as number }), level })
      setShares(prev => [share, ...prev])
      setPicked('')
      toast.success('Dataset shared')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Failed to share dataset')
    } finally {
      setSaving(false)
    }
  }

  const handleRemove = async (share: DatasetShare) => {
    // Naming who loses access: the row is one of several, and a mis-click here
    // silently cuts off a colleague rather than the person intended.
    if (!await confirm({
      title: `Stop sharing with ${nameOf(share)}?`,
      body: kindOf(share) === 'user'
        ? 'They lose access to this dataset immediately. You can share it with them again later.'
        : 'Everyone who had access only through this share loses it immediately.',
      confirmLabel: 'Remove access',
    })) return
    try {
      if (kindOf(share) === 'user') await datasetSharesApi.delete(datasetId, share.id)
      else await datasetSharesApi.deleteGroup(datasetId, share.id)
      setShares(prev => prev.filter(s => !(s.id === share.id && kindOf(s) === kindOf(share))))
      toast.success('Share removed')
    } catch {
      toast.error('Failed to remove share')
    }
  }

  const sel: React.CSSProperties = { fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
    border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }
  const KIND_LABEL: Record<Kind, string> = { user: 'Person', role: 'Role', org_unit: 'Org unit' }

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Share dataset"
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 500, maxWidth: '92vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>Share dataset</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
          Gives a person, a role or an org unit (and everyone placed under it) access to this
          dataset — its rows are otherwise visible only to whoever created it, your admins, and
          anyone opening a dashboard built on it. They see it filtered by <strong>their own</strong>{' '}
          row-security rules, not yours. <em>View</em> lets them read it; <em>Edit</em> also lets
          them change its calculations and model.
        </p>

        {loading ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap' }}>
              <select aria-label="Share with" value={kind} style={sel}
                onChange={e => { setKind(e.target.value as Kind); setPicked('') }}>
                <option value="user">Person</option>
                <option value="role">Role</option>
                <option value="org_unit">Org unit</option>
              </select>
              <select aria-label={kind === 'user' ? 'User to share with' : kind === 'role' ? 'Role to share with' : 'Org unit to share with'}
                value={picked}
                onChange={e => setPicked(e.target.value ? Number(e.target.value) : '')}
                style={{ ...sel, flex: 1, minWidth: 160 }}>
                <option value="">{kind === 'user' ? 'Select a user…' : kind === 'role' ? 'Select a role…' : 'Select an org unit…'}</option>
                {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select aria-label="Access level" value={level} style={sel}
                onChange={e => setLevel(e.target.value as Level)}>
                <option value="view">View</option>
                <option value="edit">Edit</option>
              </select>
              <button className="btn btn-primary btn-sm" onClick={handleShare} disabled={picked === '' || saving}
                title={picked === '' ? 'Choose who to share with first' : undefined}>
                {saving ? 'Sharing…' : 'Share'}
              </button>
            </div>

            {shares.length === 0 ? (
              <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '8px 0' }}>
                Not shared with anyone yet.
              </p>
            ) : (
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 220, overflowY: 'auto' }}>
                {shares.map(s => (
                  <li key={`${kindOf(s)}-${s.id}`} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
                    border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <span style={{ fontSize: 10, color: 'var(--muted)', minWidth: 54 }}>{KIND_LABEL[kindOf(s)]}</span>
                    <span style={{ flex: 1 }}>{nameOf(s)}</span>
                    <span style={{ fontSize: 10, color: 'var(--muted)' }}>{(s.level ?? 'edit') === 'view' ? 'View' : 'Edit'}</span>
                    <button aria-label={`Remove share for ${nameOf(s)}`} className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11, color: 'var(--danger)' }}
                      onClick={() => handleRemove(s)}>Remove</button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  )
}
