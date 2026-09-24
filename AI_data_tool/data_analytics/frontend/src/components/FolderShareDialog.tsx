import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { workspaceApi } from '../services/api'
import type { WorkspaceGrant, WorkspaceGrantEntry, WorkspaceShareOptions } from '../services/api'
import type { WorkspaceNode } from '../types/report'
import { useModalDialog } from './ui/useModalDialog'

/**
 * Share a workspace folder — live, never a snapshot.
 *
 * Three kinds of audience, one row each: a MEMBER (typed by email — a
 * non-admin author may share, and sharing must not hand every member a
 * browsable directory of the org), a ROLE, or a UNIT OF THE ORG CHART.
 * Each at 'view' (open, filter, interact) or 'edit' (redesign too). The
 * people shared with see the dashboards against live data with their OWN
 * row/column security applied — which is why the copy under the title says
 * so instead of leaving them to assume it is a frozen copy.
 *
 * A unit is ANY TIER, not just the bottom one: the chart runs Country >
 * Region > Department > Team, each unit carrying the org's own word for its
 * tier in `level_name`. Sharing with "Egypt" or with "Engineering" is the
 * same act as sharing with one team — it reaches everyone placed anywhere
 * beneath it, because membership climbs (see `folder_grant_levels`). The
 * first dropdown lists each tier as its own option so picking a country is
 * not buried under "team"; the second list is then only that tier.
 *
 * Every change round-trips through the PUT (replace-the-list, like the
 * roles pair): the server is the only place the list is edited, so the rows
 * shown after a change are the rows the server actually holds.
 */
export default function FolderShareDialog({ node, onClose, onChanged }: {
  node: WorkspaceNode
  onClose: () => void
  /** Called after any successful change, so the tree can refresh badges. */
  onChanged?: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [grants, setGrants] = useState<WorkspaceGrant[]>([])
  const [options, setOptions] = useState<WorkspaceShareOptions>({ roles: [], org_units: [] })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // The composer row: who, and at what level. Org-chart tiers are separate
  // kinds (`unit:Country`, `unit:Team`, …) so the first dropdown names them
  // one by one instead of one "Team, department, region…" dump.
  type Kind = 'user' | 'role' | `unit:${string}`
  const [kind, setKind] = useState<Kind>('user')
  const [email, setEmail] = useState('')
  const [roleId, setRoleId] = useState<number | ''>('')
  const [unitId, setUnitId] = useState<number | ''>('')
  const [level, setLevel] = useState<'view' | 'edit'>('view')
  const selectedTier = kind.startsWith('unit:') ? kind.slice(5) : null

  useEffect(() => {
    Promise.all([workspaceApi.grants(node.id), workspaceApi.shareOptions()])
      .then(([g, o]) => { setGrants(g); setOptions(o) })
      .catch(() => toast.error('Failed to load sharing'))
      .finally(() => setLoading(false))
  }, [node.id])

  // Chart order, deepest tier last: the org names its own tiers, so anything
  // unrecognised keeps its own heading rather than being forced into one.
  const TIER_ORDER = ['Country', 'Region', 'Branch', 'Department', 'Team']
  const tierRank = (level: string | null) => {
    const i = TIER_ORDER.findIndex(t => t.toLowerCase() === (level ?? '').toLowerCase())
    return i === -1 ? TIER_ORDER.length : i
  }
  const unitTiers = (() => {
    const seen = new Map<string, typeof options.org_units>()
    for (const u of options.org_units) {
      const key = u.level_name?.trim() || 'Other units'
      const list = seen.get(key) ?? []
      list.push(u)
      seen.set(key, list)
    }
    return [...seen.entries()].sort((a, b) => tierRank(a[0]) - tierRank(b[0]))
  })()
  const unitsInTier = selectedTier
    ? (unitTiers.find(([tier]) => tier === selectedTier)?.[1] ?? [])
    : []

  /** "Alexandria › Engineering › Software": two teams can share a name in
   *  different regions, and picking the wrong one shares with the wrong
   *  people. */
  const unitPath = (id: number): string => {
    const byId = new Map(options.org_units.map(u => [u.id, u]))
    const parts: string[] = []
    let cur = byId.get(id)
    const seen = new Set<number>()
    while (cur && !seen.has(cur.id)) {
      seen.add(cur.id)
      parts.unshift(cur.name)
      cur = cur.parent_id != null ? byId.get(cur.parent_id) : undefined
    }
    return parts.join(' › ')
  }

  const toEntry = (g: WorkspaceGrant): WorkspaceGrantEntry =>
    g.user_id != null
      ? { user_email: g.user_email ?? '', level: g.level }
      : g.role_id != null
        ? { role_id: g.role_id, level: g.level }
        : { org_unit_id: g.org_unit_id ?? 0, level: g.level }

  const save = async (entries: WorkspaceGrantEntry[]): Promise<boolean> => {
    setSaving(true)
    try {
      setGrants(await workspaceApi.setGrants(node.id, entries))
      onChanged?.()
      return true
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not change sharing')
      return false
    } finally {
      setSaving(false)
    }
  }

  const add = async () => {
    let entry: WorkspaceGrantEntry
    if (kind === 'user') {
      if (!email.trim()) return
      entry = { user_email: email.trim(), level }
    } else if (kind === 'role') {
      if (roleId === '') return
      entry = { role_id: roleId as number, level }
    } else {
      if (unitId === '') return
      entry = { org_unit_id: unitId as number, level }
    }
    if (await save([...grants.map(toEntry), entry])) {
      setEmail(''); setRoleId(''); setUnitId('')
      toast.success('Shared')
    }
  }

  const remove = (g: WorkspaceGrant) =>
    save(grants.filter(x => x.id !== g.id).map(toEntry))

  const changeLevel = (g: WorkspaceGrant, lvl: 'view' | 'edit') =>
    save(grants.map(x => x.id === g.id ? { ...toEntry(x), level: lvl } : toEntry(x)))

  const label = (g: WorkspaceGrant) => {
    if (g.user_email) return g.user_email
    if (g.role_name != null) return `Role: ${g.role_name}`
    const unit = options.org_units.find(u => u.id === g.org_unit_id)
    // The org's own word for the tier -- "Department: Engineering", not a
    // blanket "Team:" over a country.
    const tier = unit?.level_name?.trim() || 'Unit'
    return `${tier}: ${g.org_unit_name ?? g.org_unit_id}`
  }

  const input: React.CSSProperties = {
    fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
    border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)',
  }

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label={`Share ${node.name}`}
        onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          padding: 18, width: 480, maxWidth: '92vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <strong style={{ fontSize: 13 }}>Share “{node.name}”</strong>
          <button onClick={onClose} aria-label="Close"
            style={{ border: 'none', background: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--muted)' }}>✕</button>
        </div>
        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12 }}>
          Everyone you share with sees this workspace’s dashboards <strong>live</strong> — they
          can open, filter and interact, with <strong>their own</strong> data-security rules
          applied. <strong>View</strong> lets them look and explore; <strong>edit</strong> lets
          them redesign too. Unpublished dashboards inside become visible to them.
          Sharing with a department or region reaches <strong>everyone under
          it</strong> in the org chart, teams included.
        </p>

        {loading ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</p>
        ) : (
          <>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
              <select aria-label="Share with" value={kind}
                onChange={e => {
                  setKind(e.target.value as Kind)
                  setUnitId('')
                  setRoleId('')
                }}
                style={input}>
                <option value="user">Member</option>
                <option value="role">Role</option>
                {unitTiers.map(([tier]) => (
                  <option key={tier} value={`unit:${tier}`}>{tier}</option>
                ))}
              </select>
              {kind === 'user' && (
                <input aria-label="Member email" type="email" placeholder="name@company.com"
                  value={email} onChange={e => setEmail(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') void add() }}
                  style={{ ...input, flex: 1, minWidth: 140 }} />
              )}
              {kind === 'role' && (
                <select aria-label="Role to share with" value={roleId}
                  onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')}
                  style={{ ...input, flex: 1 }}>
                  <option value="">Select a role…</option>
                  {options.roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
              )}
              {selectedTier && (
                <select aria-label={`${selectedTier} to share with`} value={unitId}
                  onChange={e => setUnitId(e.target.value ? Number(e.target.value) : '')}
                  style={{ ...input, flex: 1 }}>
                  <option value="">{`Select a ${selectedTier.toLowerCase()}…`}</option>
                  {unitsInTier.map(u => (
                    <option key={u.id} value={u.id}>{unitPath(u.id)}</option>
                  ))}
                </select>
              )}
              <select aria-label="Access level" value={level}
                onChange={e => setLevel(e.target.value as 'view' | 'edit')} style={input}>
                <option value="view">View</option>
                <option value="edit">Edit</option>
              </select>
              <button className="btn btn-primary btn-sm" onClick={() => void add()} disabled={saving}>
                {saving ? 'Sharing…' : 'Share'}
              </button>
            </div>

            {grants.length === 0 ? (
              <p style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', padding: '8px 0' }}>
                Not shared with anyone yet.
              </p>
            ) : (
              <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex',
                flexDirection: 'column', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
                {grants.map(g => (
                  <li key={g.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11,
                    border: '1px solid var(--border)', borderRadius: 6, padding: '6px 8px' }}>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap' }}>{label(g)}</span>
                    <select aria-label={`Access level for ${label(g)}`} value={g.level}
                      disabled={saving}
                      onChange={e => void changeLevel(g, e.target.value as 'view' | 'edit')}
                      style={{ ...input, fontSize: 11, padding: '3px 6px' }}>
                      <option value="view">View</option>
                      <option value="edit">Edit</option>
                    </select>
                    <button aria-label={`Stop sharing with ${label(g)}`} className="btn btn-ghost btn-sm"
                      disabled={saving} style={{ fontSize: 10, color: 'var(--danger)' }}
                      onClick={() => void remove(g)}>Remove</button>
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
