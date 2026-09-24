import { useEffect, useState } from 'react'
import { adminRlsRulesApi, adminRolesApi, datasetsApi } from '../../services/api'
import type { RowSecurityRule, Role, Dataset } from '../../services/api'
import toast from 'react-hot-toast'

function RuleModal({ initial, roles, datasets, onSave, onClose }: {
  initial?: RowSecurityRule | null
  roles: Role[]
  datasets: Dataset[]
  onSave: (r: RowSecurityRule) => void
  onClose: () => void
}) {
  const isEdit = !!initial
  const [roleId, setRoleId] = useState<number | ''>(initial?.role_id ?? roles[0]?.id ?? '')
  const [datasetId, setDatasetId] = useState<number | ''>(initial?.dataset_id ?? datasets[0]?.id ?? '')
  const [filterExpr, setFilterExpr] = useState(initial?.filter_expr ?? '')
  const [saving, setSaving] = useState(false)

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  const handleSave = async () => {
    if (!isEdit && (roleId === '' || datasetId === '')) { toast.error('Role and dataset are required'); return }
    if (!filterExpr.trim()) { toast.error('Filter expression is required'); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRlsRulesApi.update(initial!.id, { filter_expr: filterExpr })
        : await adminRlsRulesApi.create({ role_id: roleId as number, dataset_id: datasetId as number, filter_expr: filterExpr })
      onSave(result)
      toast.success(isEdit ? 'Updated' : 'Rule created')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Save failed — check the filter expression syntax')
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Row-Security Rule' : 'New Row-Security Rule'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Role and dataset are fixed once a rule is created (unique per role+dataset pair) — only filter_expr is editable. */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Dataset *</div>
          <select value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} {...inp}>
            <option value="">Select a dataset…</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Filter Expression *</div>
          <textarea
            value={filterExpr}
            onChange={e => setFilterExpr(e.target.value)}
            placeholder="region == 'North'"
            rows={3}
            style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12, padding: '6px 8px',
              background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
              color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </label>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 20 }}>
          Rows where this expression is false are hidden from every user assigned this role, for this dataset.
          Validated against the dataset's actual data on save.
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create'}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRowSecurityRules() {
  const [rules, setRules] = useState<RowSecurityRule[]>([])
  const [roles, setRoles] = useState<Role[]>([])
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'add' | RowSecurityRule | null>(null)

  useEffect(() => {
    Promise.all([adminRlsRulesApi.list(), adminRolesApi.list(), datasetsApi.list()])
      .then(([r, ro, d]) => { setRules(r); setRoles(ro); setDatasets(d) })
      .catch((e: any) => toast.error(e?.response?.data?.detail ?? 'Failed to load row security rules'))
      .finally(() => setLoading(false))
  }, [])

  const roleName = (id: number) => roles.find(r => r.id === id)?.name ?? `Role #${id}`
  const datasetName = (id: number) => datasets.find(d => d.id === id)?.name ?? `Dataset #${id}`

  const handleSaved = (r: RowSecurityRule) => {
    setRules(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const handleDelete = async (r: RowSecurityRule) => {
    if (!confirm(`Delete this rule for "${roleName(r.role_id)}" on "${datasetName(r.dataset_id)}"?`)) return
    try {
      await adminRlsRulesApi.delete(r.id)
      setRules(prev => prev.filter(x => x.id !== r.id))
      toast.success('Deleted')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Delete failed')
    }
  }

  const canCreate = roles.length > 0 && datasets.length > 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, flex: 1 }}>Row Security Rules</h1>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')} disabled={!canCreate}>
          + New Rule
        </button>
      </div>

      {loading && <p style={{ color: 'var(--muted)' }}>Loading…</p>}

      {!loading && !canCreate && (
        <div style={{ padding: 16, marginBottom: 16, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 8, fontSize: 12, color: 'var(--muted)' }}>
          You need at least one role and one dataset before creating a rule.
        </div>
      )}

      {!loading && rules.length === 0 && canCreate && (
        <div style={{ padding: 60, textAlign: 'center', background: 'var(--surface)',
          border: '1px solid var(--border)', borderRadius: 12, color: 'var(--muted)' }}>
          No row-security rules yet — roles with no rule for a dataset see every row within their org.
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rules.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14,
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {roleName(r.role_id)} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>on</span> {datasetName(r.dataset_id)}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>{r.filter_expr}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
          </div>
        ))}
      </div>

      {modal && (
        <RuleModal
          initial={modal === 'add' ? null : modal}
          roles={roles}
          datasets={datasets}
          onSave={handleSaved}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
