import { useEffect, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT } from '../../i18n'
import { EyeOff, Plus } from 'lucide-react'
import { columnSecurityApi, adminRolesApi, datasetsApi } from '../../services/api'
import type { ColumnSecurityRuleRow, Role, Dataset } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { useModalDialog } from '../../components/ui/useModalDialog'
import EmptyState from '../../components/ui/EmptyState'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * Authoring UI for column-level security. The enforcement has existed for a
 * while (`resolve_denied_columns` runs on every widget, preview, profile and
 * export path, pinned by its own choke-point test); the three admin endpoints
 * were live too -- but there was no page, so rules could only be created with
 * curl. This page closes that gap and adds nothing else: rule semantics stay
 * entirely the backend's.
 *
 * No edit mode. A rule is role + dataset + denied columns; changing the set
 * is delete-and-recreate (the backend has no PATCH), and pretending otherwise
 * in the UI would fake an operation the API cannot perform.
 */

function RuleModal({ roles, datasets, onSaved, onClose }: {
  roles: Role[]
  datasets: Dataset[]
  onSaved: (r: ColumnSecurityRuleRow) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [roleId, setRoleId] = useState<number | ''>(roles[0]?.id ?? '')
  const [datasetId, setDatasetId] = useState<number | ''>(datasets[0]?.id ?? '')
  const [denied, setDenied] = useState<Set<string>>(new Set())
  const [saving, setSaving] = useState(false)

  const selectedDataset = datasets.find(d => d.id === datasetId)
  const dsColumns = selectedDataset?.columns ?? []

  // A denied set survives a dataset switch only by accident of shared names --
  // clear it instead, so a rule never carries a column the dataset lacks.
  useEffect(() => { setDenied(new Set()) }, [datasetId])

  const toggle = (name: string) => setDenied(prev => {
    const next = new Set(prev)
    if (next.has(name)) next.delete(name); else next.add(name)
    return next
  })

  const inp = { style: fieldStyle }

  const handleSave = async () => {
    if (roleId === '' || datasetId === '') { toast.error('Role and dataset are required'); return }
    if (denied.size === 0) { toast.error('Pick at least one column to hide'); return }
    setSaving(true)
    try {
      const { id } = await columnSecurityApi.create({
        role_id: roleId as number, dataset_id: datasetId as number,
        denied_columns: Array.from(denied),
      })
      onSaved({ id, role_id: roleId as number, dataset_id: datasetId as number,
        denied_columns: Array.from(denied) })
      toast.success('Rule created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-label="New column-security rule"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>New Column-Security Rule</h2>
          <button onClick={onClose} aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select aria-label="Role *" value={roleId}
            onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Dataset *</div>
          <select aria-label="Dataset *" value={datasetId}
            onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a dataset…</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Columns to hide *</div>
        {dsColumns.length === 0 ? (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>Pick a dataset to list its columns.</p>
        ) : (
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 10, marginBottom: 16, maxHeight: 220, overflowY: 'auto' }}>
            {dsColumns.map(c => (
              <label key={c.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12,
                padding: '4px 0', cursor: 'pointer' }}>
                <input type="checkbox" checked={denied.has(c.name)} onChange={() => toggle(c.name)} />
                <span style={{ fontFamily: 'var(--mono)', flex: 1 }}>{c.name}</span>
                <span style={{ color: 'var(--muted)', fontSize: 11 }}>{c.dtype}</span>
              </label>
            ))}
          </div>
        )}

        <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 16 }}>
          For that role, these columns cease to exist — in widgets, previews, profiles,
          expressions and exports alike. There is no "hidden but fetchable".
        </p>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave}
            disabled={saving || roleId === '' || datasetId === '' || denied.size === 0} title={roleId === '' ? 'Choose a role first' : datasetId === '' ? 'Choose a dataset first' : denied.size === 0 ? 'Tick at least one column to hide' : undefined} style={{ flex: 1 }}>
            {saving ? 'Saving…' : 'Create rule'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminColumnSecurityRules() {
  const t = useT()
  const [rules, setRules] = useState<ColumnSecurityRuleRow[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [showModal, setShowModal] = useState(false)

  // Rules, roles and datasets all come from one initial fetch -- losing it is
  // the page's whole content going missing, not a transient action failure a
  // toast can adequately report.
  const load = () => {
    setLoading(true)
    setLoadError(null)
    Promise.all([columnSecurityApi.list(), adminRolesApi.list(), datasetsApi.list()])
      .then(([r, ro, d]) => { setRules(r); setRoles(ro); setDatasets(d) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const roleName = (id: number) => roles.find(r => r.id === id)?.name ?? `Role #${id}`
  const datasetName = (id: number) => datasets.find(d => d.id === id)?.name ?? `Deleted dataset (#${id})`

  const confirm = useConfirm()
  const handleDelete = async (r: ColumnSecurityRuleRow) => {
    if (!await confirm({
      title: 'Delete this column-security rule?',
      body: `Role "${roleName(r.role_id)}" on dataset "${datasetName(r.dataset_id)}". ` +
        `The hidden columns (${r.denied_columns.join(', ')}) become visible to that role.`,
    })) return
    try {
      await columnSecurityApi.remove(r.id)
      setRules(prev => prev.filter(x => x.id !== r.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  const canCreate = roles.length > 0 && datasets.length > 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.columnSecurity')}</h1>
        <button className="btn btn-primary" onClick={() => setShowModal(true)} disabled={!canCreate} title={!canCreate ? 'Needs at least one role and one dataset' : undefined}>
          <Plus size={16} aria-hidden /> {t('admin.newRule')}
        </button>
      </div>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 24, maxWidth: 640 }}>
        A rule hides named columns from one role on one dataset — everywhere: widgets,
        data previews, profiles, expressions and exports. Enforcement is server-side;
        this page only writes the rules.
      </p>

      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="column-security rules" error={loadError} onRetry={load} />
      )}

      {!loading && loadError == null && !canCreate && (
        <div className="dl-conn-notice">
          You need at least one role and one dataset before creating a rule.
        </div>
      )}

      {!loading && loadError == null && rules.length === 0 && canCreate && (
        <EmptyState icon={EyeOff} title="No column-security rules yet"
          description="Roles with no rule for a dataset see every column within their org." />
      )}

      <div className="dl-rows">
        {rules.map(r => (
          <div key={r.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title">
                {roleName(r.role_id)} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>on</span> {datasetName(r.dataset_id)}
              </div>
              <div className="dl-rows__meta dl-rows__meta--mono">
                hides: {r.denied_columns.join(', ')}
              </div>
            </div>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => handleDelete(r)}>{t('admin.delete')}</button>
          </div>
        ))}
      </div>

      {showModal && (
        <RuleModal roles={roles} datasets={datasets}
          onSaved={r => { setRules(prev => [r, ...prev]); setShowModal(false) }}
          onClose={() => setShowModal(false)} />
      )}
    </div>
  )
}
