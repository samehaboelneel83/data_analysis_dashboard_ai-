import { useEffect, useMemo, useState } from 'react'
import { useT } from '../../i18n'
import toast from 'react-hot-toast'
import { orgUnitsApi, adminUsersApi, type OrgUnit, type User } from '../../services/api'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { usePrompt } from '../../components/ui/PromptDialog'
import { ChevronDown, ChevronRight, Network, Plus, Trash2, Users } from 'lucide-react'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * The organization's own chart, and who sits where.
 *
 * This is what makes hierarchical RLS work: a rule written ONCE as
 * `branch in MYSCOPE()` scopes every user to their own subtree, because
 * placement is per user and access flows downward. Without this page the
 * capability exists only over the API, which is the "shipped but unreachable"
 * trap this codebase has hit repeatedly.
 *
 * The page authors the tree; it never decides access. Expansion happens
 * server-side in core/rls.py, which is the single place worth auditing.
 */

interface TreeNode extends OrgUnit { children: TreeNode[] }

function nest(units: OrgUnit[]): TreeNode[] {
  const byId = new Map<number, TreeNode>()
  units.forEach(u => byId.set(u.id, { ...u, children: [] }))
  const roots: TreeNode[] = []
  for (const u of units) {
    const node = byId.get(u.id)!
    const parent = u.parent_id != null ? byId.get(u.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  return roots
}

export default function AdminOrgUnits() {
  const t = useT()
  const [units, setUnits] = useState<OrgUnit[]>([])
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [open, setOpen] = useState<Set<number>>(new Set())
  const [placingUser, setPlacingUser] = useState<number | ''>('')
  const [placements, setPlacements] = useState<number[]>([])
  const confirm = useConfirm()
  const prompt = usePrompt()

  const load = () => {
    setLoading(true)
    setLoadError(null)
    Promise.all([orgUnitsApi.list(), adminUsersApi.list()])
      .then(([u, us]) => { setUnits(u); setUsers(us) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  useEffect(() => {
    if (placingUser === '') { setPlacements([]); return }
    orgUnitsApi.forUser(placingUser as number)
      .then(rows => setPlacements(rows.map(r => r.org_unit_id)))
      .catch(() => toast.error('Could not load that user’s placements'))
  }, [placingUser])

  const tree = useMemo(() => nest(units), [units])

  const addUnit = async (parent: OrgUnit | null) => {
    const name = (await prompt({
      title: parent ? `New unit under ${parent.name}` : 'New top-level unit',
      label: 'Unit name', placeholder: 'e.g. Egypt', confirmLabel: 'Next',
    }))?.trim()
    if (!name) return
    const level = (await prompt({
      title: `What kind of unit is ${name}?`,
      body: 'Optional — leave empty to skip.',
      label: 'Level name', placeholder: 'e.g. Country, Region, Branch, Team',
      confirmLabel: 'Add unit', required: false,
    }))?.trim()
    try {
      await orgUnitsApi.create({ name, parent_id: parent?.id ?? null, level_name: level || undefined })
      load()
      toast.success(`Added ${name}`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not add the unit')
    }
  }

  const removeUnit = async (u: OrgUnit) => {
    if (!await confirm({
      title: `Delete “${u.name}”?`,
      // Said plainly: the cascade is not recoverable, and it silently changes
      // what people can see.
      body: `Everything beneath it is deleted too, and anyone placed there loses that access. `
        + `Users placed only here will see no rows at all until they are placed again.`,
    })) return
    try {
      await orgUnitsApi.remove(u.id)
      load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not delete the unit')
    }
  }

  const togglePlacement = (unitId: number) => {
    setPlacements(p => p.includes(unitId) ? p.filter(x => x !== unitId) : [...p, unitId])
  }

  const savePlacements = async () => {
    if (placingUser === '') return
    try {
      await orgUnitsApi.setForUser(placingUser as number, placements)
      toast.success(placements.length
        ? 'Placement saved — access flows down from there'
        : 'Placements cleared — this user now matches no rows where MYSCOPE() is used')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save the placement')
    }
  }

  const row = (n: TreeNode, depth: number): React.ReactNode => {
    const isOpen = open.has(n.id) || depth === 0
    const hasKids = n.children.length > 0
    return (
      <div key={n.id}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px',
          paddingInlineStart: 8 + depth * 18, borderBottom: '1px solid var(--border)' }}>
          <button onClick={() => setOpen(p => {
            const next = new Set(p); next.has(n.id) ? next.delete(n.id) : next.add(n.id); return next
          })}
            aria-label={hasKids ? (isOpen ? `Collapse ${n.name}` : `Expand ${n.name}`) : n.name}
            style={{ border: 'none', background: 'none', cursor: hasKids ? 'pointer' : 'default',
              color: 'var(--muted)', padding: 0, visibility: hasKids ? 'visible' : 'hidden',
              display: 'inline-flex' }}>
            {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>

          {placingUser !== '' && (
            <input type="checkbox" aria-label={`Place at ${n.name}`}
              checked={placements.includes(n.id)} onChange={() => togglePlacement(n.id)} />
          )}

          <span style={{ fontSize: 13, fontWeight: 600 }}>{n.name}</span>
          {n.level_name && (
            <span style={{ fontSize: 10.5, color: 'var(--muted)', border: '1px solid var(--border)',
              borderRadius: 99, padding: '1px 7px', textTransform: 'uppercase' }}>
              {n.level_name}
            </span>
          )}
          {n.match_value !== n.name && (
            <span title="The value this unit takes in your data"
              style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>
              = {n.match_value}
            </span>
          )}

          <span style={{ marginInlineStart: 'auto', display: 'flex', gap: 4 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => addUnit(n)}
              aria-label={`Add a unit under ${n.name}`} style={{ fontSize: 11 }}>
              <Plus size={11} />
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => removeUnit(n)}
              aria-label={`Delete ${n.name}`} style={{ fontSize: 11, color: 'var(--danger)' }}>
              <Trash2 size={11} />
            </button>
          </span>
        </div>
        {isOpen && n.children.map(c => row(c, depth + 1))}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.orgChart')}</h1>
        <button className="btn btn-primary" onClick={() => addUnit(null)}>
          <Plus size={16} aria-hidden /> {t('admin.addTopUnit')}
        </button>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 20, maxWidth: 680 }}>
        Build your hierarchy — Country, Region, Branch, Department, Team, to whatever depth you
        use. Place a person at one node and they automatically see that node and everything
        beneath it. Write the rule once as <code>branch in MYSCOPE()</code> on a Row security
        rule; it then means something different, and correct, for every user.
      </p>

      {loading && <LoadingState />}
      {!loading && loadError != null && (
        <LoadError what="the organization chart" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && (
        <>
          <div className="card" style={{ padding: '10px 12px', marginBottom: 16, display: 'flex',
            gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <Users size={15} aria-hidden style={{ color: 'var(--accent)' }} />
            <label htmlFor="place-user" style={{ fontSize: 12, fontWeight: 600 }}>Place a user</label>
            <select id="place-user" value={placingUser}
              onChange={e => setPlacingUser(e.target.value ? Number(e.target.value) : '')}
              style={{ fontSize: 12, minWidth: 240 }}>
              <option value="">Choose someone…</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
            </select>
            {placingUser !== '' && (
              <>
                <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                  Tick every unit they cover — access includes everything beneath each one.
                </span>
                <button className="btn btn-primary btn-sm" onClick={savePlacements}
                  style={{ marginInlineStart: 'auto' }}>Save placement</button>
              </>
            )}
          </div>

          {units.length === 0 ? (
            <EmptyState icon={Network} title="No hierarchy yet"
              description="Start with a top-level unit — a country or the organization itself — then add regions and branches beneath it." />
          ) : (
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {tree.map(n => row(n, 0))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
