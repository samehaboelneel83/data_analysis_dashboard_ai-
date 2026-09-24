import { useEffect, useMemo, useState } from 'react'
import { adminUsersApi, datasetSharesApi } from '../services/api'
import type { DatasetShare, User } from '../services/api'
import toast from 'react-hot-toast'
import { useConfirm } from './ui/ConfirmDialog'
import { useModalDialog } from './ui/useModalDialog'

/**
 * In-org dataset sharing, managed by org admins.
 *
 * SH1 shipped this as a BADGE: every member could already read every dataset
 * in the org, so a share only flagged provenance. Dataset ownership (0020)
 * made it a real grant -- `core.capability.readable_dataset_ids` reads these
 * rows -- so the copy below now describes access being given, not a bookmark
 * being set. Shape still mirrors ShareLinksDialog: a picker to grant, a list
 * to revoke.
 */
export default function DatasetShareDialog({ datasetId, onClose }: {
  datasetId: number
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const confirm = useConfirm()
  const [shares, setShares] = useState<DatasetShare[]>([])
  const [orgUsers, setOrgUsers] = useState<User[]>([])
  const [pickedUserId, setPickedUserId] = useState<number | ''>('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([datasetSharesApi.list(datasetId), adminUsersApi.list()])
      .then(([s, u]) => { setShares(s); setOrgUsers(u) })
      .catch(() => toast.error('Failed to load shares'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const sharedUserIds = useMemo(() => new Set(shares.map(s => s.user_id)), [shares])
  const shareable = orgUsers.filter(u => !sharedUserIds.has(u.id))

  const handleShare = async () => {
    if (pickedUserId === '') return
    setSaving(true)
    try {
      const share = await datasetSharesApi.create(datasetId, pickedUserId as number)
      setShares(prev => [share, ...prev])
      setPickedUserId('')
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
      title: `Stop sharing with ${share.email}?`,
      body: 'They lose access to this dataset immediately. You can share it with them again later.',
      confirmLabel: 'Remove access',
    })) return
    try {
      await datasetSharesApi.delete(datasetId, share.id)
      setShares(prev => prev.filter(s => s.id !== share.id))
      toast.success('Share removed')
    } catch {
      toast.error('Failed to remove share')
    }
  }

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Share dataset"
          onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 440, maxWidth: '92vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>Share dataset</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
          Gives a teammate access to this dataset — its rows are otherwise visible only to
          whoever uploaded it, your admins, and anyone opening a dashboard built on it.
          They see it filtered by <strong>their own</strong> row-security rules, not yours.
        </p>

        {loading ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              <select aria-label="User to share with" value={pickedUserId}
                onChange={e => setPickedUserId(e.target.value ? Number(e.target.value) : '')}
                style={{ flex: 1, fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
                  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' }}>
                <option value="">Select a user…</option>
                {shareable.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
              </select>
              <button className="btn btn-primary btn-sm" onClick={handleShare} disabled={pickedUserId === '' || saving} title={pickedUserId === '' ? 'Choose a person to share with first' : undefined}>
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
                  <li key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
                    border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <span style={{ flex: 1 }}>{s.email}</span>
                    <button aria-label={`Remove share for ${s.email}`} className="btn btn-ghost btn-sm"
                      style={{ fontSize: 10, color: 'var(--danger)' }}
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
