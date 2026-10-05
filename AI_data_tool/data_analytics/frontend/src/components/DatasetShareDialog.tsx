import { useEffect, useMemo, useState } from 'react'
import { adminRolesApi, adminUsersApi, datasetSharesApi, lineageApi, orgUnitsApi } from '../services/api'
import { Shield, X } from 'lucide-react'
import '../pages/datasetDetail/share.css'
import { useT } from '../i18n'
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
export default function DatasetShareDialog({ datasetId, onClose, datasetName, createdByMe }: {
  datasetId: number
  onClose: () => void
  /** For the title: Share "Demo — Sales". */
  datasetName?: string
  /** Whether the viewer created it, for the "Can also open it" list. */
  createdByMe?: boolean
}) {
  const t = useT()
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
  // Dashboards built on it, for "anyone who can open its N dashboards".
  const [boards, setBoards] = useState<number | null>(null)

  useEffect(() => {
    Promise.all([datasetSharesApi.list(datasetId), adminUsersApi.list()])
      .then(([s, u]) => { setShares(s); setOrgUsers(u) })
      .catch(() => toast.error('Failed to load shares'))
      .finally(() => setLoading(false))
    // Roles and units are optional extras: a failure leaves user sharing working.
    adminRolesApi?.list?.().then(r => setRoles(r as never)).catch(() => {})
    orgUnitsApi?.list?.().then(u => setUnits(u as never)).catch(() => {})
    Promise.resolve().then(() => lineageApi?.graph?.())
      .then(g => { if (g) setBoards(g.reports.filter(r => r.dataset_ids.includes(datasetId)).length) }).catch(() => {})
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

  const KIND_LABEL: Record<Kind, string> = { user: t('share3.person'), role: t('share3.role'), org_unit: t('share3.unit') }
  const initials = (n: string) => (n.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('') || '?').toUpperCase()
  const subOf = (s: DatasetShare) => kindOf(s) === 'user' ? (s.email && s.email !== nameOf(s) ? s.email : t('share3.person'))
    : kindOf(s) === 'role' ? t('share3.role') : t('share3.unitBelow')

  return (
    <div onClick={onClose} className="dl-share__backdrop">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="Share dataset"
        onClick={e => e.stopPropagation()} className="dl-share">
        <header className="dl-share__head">
          <h2>{datasetName ? t('share3.title', { name: datasetName }) : t('share3.titlePlain')}</h2>
          <button onClick={onClose} aria-label="Close" className="dl-share__close"><X size={16} aria-hidden /></button>
        </header>

        {loading ? (
          <p className="dl-share__muted">Loading…</p>
        ) : (
          <>
            <div className="dl-share__add">
              <span role="radiogroup" aria-label="Share with" className="dl-share__seg">
                {(['user', 'role', 'org_unit'] as Kind[]).map(k => (
                  <button key={k} type="button" role="radio" aria-checked={kind === k}
                    onClick={() => { setKind(k); setPicked('') }}>{KIND_LABEL[k]}</button>
                ))}
              </span>
              <select aria-label={kind === 'user' ? 'User to share with' : kind === 'role' ? 'Role to share with' : 'Org unit to share with'}
                value={picked} className="dl-share__pick"
                onChange={e => setPicked(e.target.value ? Number(e.target.value) : '')}>
                <option value="">{kind === 'user' ? t('share3.addPerson') : kind === 'role' ? t('share3.addRole') : t('share3.addUnit')}</option>
                {options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
              </select>
              <select aria-label="Access level" value={level} className="dl-share__level"
                onChange={e => setLevel(e.target.value as Level)}>
                <option value="view">{t('share3.view')}</option>
                <option value="edit">{t('share3.edit')}</option>
              </select>
              <button className="btn btn-primary btn-sm" onClick={handleShare} disabled={picked === '' || saving}
                title={picked === '' ? 'Choose who to share with first' : undefined}>
                {saving ? 'Sharing…' : 'Share'}
              </button>
            </div>

            <h3 className="dl-share__label">{t('share3.direct')}</h3>
            {shares.length === 0 ? (
              <p className="dl-share__muted dl-share__none">Not shared with anyone yet.</p>
            ) : (
              <ul className="dl-share__list">
                {shares.map(s => (
                  <li key={`${kindOf(s)}-${s.id}`}>
                    <span className={`dl-share__avatar dl-share__avatar--${kindOf(s)}`} aria-hidden>{initials(nameOf(s))}</span>
                    <span className="dl-share__who"><strong dir="auto">{nameOf(s)}</strong><span>{subOf(s)}</span></span>
                    <span className="dl-share__lvl">{(s.level ?? 'edit') === 'view' ? t('share3.view') : t('share3.edit')}</span>
                    <button aria-label={`Remove share for ${nameOf(s)}`} className="dl-share__remove"
                      onClick={() => handleRemove(s)}><X size={14} aria-hidden /></button>
                  </li>
                ))}
              </ul>
            )}

            {/* Static on purpose (N9): who else can open it, in words, with no
                counts of admins or viewers the server does not report. */}
            <h3 className="dl-share__label">{t('share3.also')}</h3>
            <ul className="dl-share__list">
              <li>
                <span className="dl-share__avatar" aria-hidden>{createdByMe ? 'YOU' : 'CR'}</span>
                <span className="dl-share__who"><strong>{createdByMe ? t('share3.you') : t('share3.creator')}</strong>
                  <span>{createdByMe ? t('share3.youMade') : t('share3.creatorBody')}</span></span>
                <span className="dl-share__lvl dl-share__muted">{t('share3.creatorTag')}</span>
              </li>
              <li>
                <span className="dl-share__avatar dl-share__avatar--role" aria-hidden>AD</span>
                <span className="dl-share__who"><strong>{t('share3.admins')}</strong><span>{t('share3.adminsBody')}</span></span>
                <span className="dl-share__lvl dl-share__muted">{t('share3.edit')}</span>
              </li>
              {boards != null && boards > 0 && (
                <li>
                  <span className="dl-share__avatar dl-share__avatar--role" aria-hidden>{boards}</span>
                  <span className="dl-share__who"><strong>{t(boards === 1 ? 'share3.boardsOne' : 'share3.boards', { n: boards })}</strong>
                    <span>{t('share3.boardsBody')}</span></span>
                  <span className="dl-share__lvl dl-share__muted">{t('share3.viaBoards')}</span>
                </li>
              )}
            </ul>

            <p className="dl-share__rls">
              <Shield size={15} aria-hidden />
              <span>{t('share3.rls')}</span>
            </p>
            <p className="dl-share__muted dl-share__foot">{t('share3.foot')}</p>
          </>
        )}
      </div>
    </div>
  )
}
