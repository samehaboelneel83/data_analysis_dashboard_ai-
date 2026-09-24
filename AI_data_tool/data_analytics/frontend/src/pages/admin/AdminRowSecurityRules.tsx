import { useEffect, useMemo, useState } from 'react'
import { adminRlsRulesApi, adminRolesApi, datasetsApi } from '../../services/api'
import type { RowSecurityRule, RlsRuleProposal, Role, Dataset, DatasetColumn } from '../../services/api'
import toast from 'react-hot-toast'
import { Z_OVERLAY } from '../../lib/zIndex'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { colRef, literal } from '../../lib/simpleExpr'
import ActionMenu from '../../components/ActionMenu'
import { useModalDialog } from '../../components/ui/useModalDialog'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

// S0b: codeless RLS rule builder. A column is "user-ish" when Layer 1 has
// classified it as an email, or its name reads like one (user/email/owner) —
// these are exactly the columns a "restrict by current user?" rule targets.
function isUserishColumn(col: DatasetColumn): boolean {
  return col.semantic_type === 'email' || /user|email|owner/i.test(col.name)
}

type MatchTarget = 'useremail' | 'userid' | 'orgid' | 'literal'

const MATCH_TARGETS: { value: MatchTarget; label: string; token?: string }[] = [
  { value: 'useremail', label: 'Current user email', token: 'USEREMAIL()' },
  { value: 'userid',    label: 'Current user id',     token: 'USERID()' },
  { value: 'orgid',     label: 'Current organization id', token: 'ORGID()' },
  { value: 'literal',   label: 'Literal value (per role)' },
]

/** `column == <token or quoted literal>` — the whole of S0b's generated shape.
 *  Returns '' when there isn't enough picked yet to mean anything. */
function generateExpression(column: string, target: MatchTarget, literalValue: string): string {
  if (!column) return ''
  const targetDef = MATCH_TARGETS.find(t => t.value === target)
  const rhs = targetDef?.token ?? (literalValue.trim() ? literal(literalValue) : '')
  if (!rhs) return ''
  return `${colRef(column)} == ${rhs}`
}

function RuleModal({ initial, roles, datasets, onSave, onClose }: {
  initial?: RowSecurityRule | null
  roles: Role[]
  datasets: Dataset[]
  onSave: (r: RowSecurityRule) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const isEdit = !!initial
  const [roleId, setRoleId] = useState<number | ''>(initial?.role_id ?? roles[0]?.id ?? '')
  const [datasetId, setDatasetId] = useState<number | ''>(initial?.dataset_id ?? datasets[0]?.id ?? '')
  const [filterExpr, setFilterExpr] = useState(initial?.filter_expr ?? '')
  const [saving, setSaving] = useState(false)
  const [overlap, setOverlap] = useState<string[]>([])

  // S0 ticket 11: a row rule is evaluated over the FULL frame before column
  // security drops the reader's denied columns, so a rule that reads a denied
  // column still selects rows -- the role never sees the column, but the rows
  // it selects. Informational only: never blocks Save (the save validates the
  // expression itself). Debounced and guarded against a stale response landing
  // after a newer keystroke's request.
  useEffect(() => {
    if (roleId === '' || datasetId === '' || !filterExpr.trim()) { setOverlap([]); return }
    let cancelled = false
    const timer = setTimeout(() => {
      adminRlsRulesApi.preflight(roleId as number, datasetId as number, filterExpr)
        .then(r => { if (!cancelled) setOverlap(r.denied) })
        .catch(() => { if (!cancelled) setOverlap([]) })
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [roleId, datasetId, filterExpr])

  // ── S0b: codeless flow ──────────────────────────────────────────────────
  const selectedDataset = datasets.find(d => d.id === datasetId)
  const dsColumns = selectedDataset?.columns ?? []
  const suggestedColumns = dsColumns.filter(isUserishColumn)
  const otherColumns = dsColumns.filter(c => !isUserishColumn(c))
  const [pickedColumn, setPickedColumn] = useState(suggestedColumns[0]?.name ?? dsColumns[0]?.name ?? '')
  const [matchTarget, setMatchTarget] = useState<MatchTarget>('useremail')
  const [literalValue, setLiteralValue] = useState('')

  // Re-derive the picked column whenever the dataset changes — otherwise a column
  // name from the PREVIOUS dataset survives the switch and "Use this expression"
  // can copy in `old_col == USEREMAIL()` referencing a column that doesn't exist
  // on the newly picked dataset.
  useEffect(() => {
    setPickedColumn(suggestedColumns[0]?.name ?? dsColumns[0]?.name ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId])

  const generated = useMemo(
    () => generateExpression(pickedColumn, matchTarget, literalValue),
    [pickedColumn, matchTarget, literalValue],
  )

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
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? "Edit row-security rule" : "New row-security rule"}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? 'Edit Row-Security Rule' : 'New Row-Security Rule'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Role and dataset are fixed once a rule is created (unique per role+dataset pair) — only filter_expr is editable. */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} title={isEdit ? 'Fixed once the rule exists: create a new rule to change it' : undefined} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Dataset *</div>
          <select aria-label="Dataset *" value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} title={isEdit ? 'Fixed once the rule exists: create a new rule to change it' : undefined} {...inp}>
            <option value="">Select a dataset…</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        {dsColumns.length > 0 && (
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 10, marginBottom: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: '.06em', marginBottom: 8 }}>Quick setup — restrict by current user?</div>

            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Column</div>
              <select aria-label="Column" value={pickedColumn} onChange={e => setPickedColumn(e.target.value)} {...inp}>
                <option value="">Select a column…</option>
                {suggestedColumns.length > 0 && (
                  <optgroup label="Suggested (looks like a user/owner column)">
                    {suggestedColumns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </optgroup>
                )}
                {otherColumns.length > 0 && (
                  <optgroup label="Other columns">
                    {otherColumns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </optgroup>
                )}
              </select>
              {pickedColumn && suggestedColumns.some(c => c.name === pickedColumn) && (
                <div style={{ fontSize: 10, color: 'var(--accent)', marginTop: 3 }}>
                  Looks like a user column — restrict rows to the viewer's own?
                </div>
              )}
            </div>

            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Match</div>
              <select aria-label="Match" value={matchTarget} onChange={e => setMatchTarget(e.target.value as MatchTarget)} {...inp}>
                {MATCH_TARGETS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {matchTarget === 'literal' && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Literal value</div>
                <input aria-label="Literal value" value={literalValue} onChange={e => setLiteralValue(e.target.value)} placeholder="e.g. North" {...inp} />
              </div>
            )}

            <div style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '6px 8px',
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 5,
              color: 'var(--muted)', marginBottom: 8, minHeight: 16 }}>
              {generated || <span style={{ opacity: .6 }}>(pick a column and a match target)</span>}
            </div>

            <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
              disabled={!generated} title={!generated ? 'Generate an expression first' : undefined} onClick={() => setFilterExpr(generated)}>
              Use this expression
            </button>
          </div>
        )}

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
        {overlap.length > 0 && (
          <div role="note" style={{ fontSize: 11, padding: '6px 8px', borderRadius: 6, marginBottom: 8,
            background: 'color-mix(in srgb, var(--accent) 12%, transparent)', border: '1px solid var(--border)' }}>
            This rule reads {overlap.join(', ')}, which this role cannot see. The rule still applies:
            the role gets the rows it selects and never the column.
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 20 }}>
          Rows where this expression is false are hidden from every user assigned this role, for this dataset.
          Validated against the dataset's actual data on save.
          <br />
          Use <code style={{ fontFamily: 'var(--mono)' }}>USEREMAIL()</code> (or <code style={{ fontFamily: 'var(--mono)' }}>USERID()</code>)
          to scope each user to their own rows with one rule — e.g. <code style={{ fontFamily: 'var(--mono)' }}>owner == USEREMAIL()</code>.
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

/** S0c: pick a dataset (+ role) → fetch column-derived proposals → check the
 *  ones to apply → one AND-combined rule for that role+dataset. */
function AutoGenerateModal({ roles, datasets, onApplied, onClose }: {
  roles: Role[]
  datasets: Dataset[]
  onApplied: (r: RowSecurityRule) => void
  onClose: () => void
}) {
  const dialogRef = useModalDialog<HTMLDivElement>(onClose)
  const [roleId, setRoleId] = useState<number | ''>(roles[0]?.id ?? '')
  const [datasetId, setDatasetId] = useState<number | ''>(datasets[0]?.id ?? '')
  const [proposals, setProposals] = useState<RlsRuleProposal[]>([])
  const [checked, setChecked] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)

  useEffect(() => {
    if (datasetId === '') { setProposals([]); return }
    setLoading(true)
    adminRlsRulesApi.autoGenerate(datasetId as number)
      .then(r => { setProposals(r.proposals); setChecked(new Set(r.proposals.map(p => p.column))) })
      .catch(() => toast.error('Failed to load proposals'))
      .finally(() => setLoading(false))
  }, [datasetId])

  const toggle = (col: string) => setChecked(prev => {
    const next = new Set(prev)
    if (next.has(col)) next.delete(col); else next.add(col)
    return next
  })

  const handleApply = async () => {
    if (roleId === '' || datasetId === '' || checked.size === 0) return
    setApplying(true)
    try {
      const r = await adminRlsRulesApi.autoGenerate(datasetId as number, {
        role_id: roleId as number, apply: true, columns: Array.from(checked),
      })
      if (r.created) {
        onApplied(r.created)
        toast.success('Rule applied')
      } else {
        toast.error(r.reason ?? 'Nothing to apply — that role already has a hand-edited rule')
      }
      onClose()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Auto-generate failed')
    } finally {
      setApplying(false)
    }
  }

  const inp = {
    style: { width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box' as const,
      background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)' },
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label="Auto-generate row-security rules"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Auto-generate rules</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Dataset *</div>
          <select aria-label="Dataset *" value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a dataset…</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Role *</div>
          <select aria-label="Role *" value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">Select a role…</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        {loading && <p style={{ fontSize: 12, color: 'var(--muted)' }}>Scanning columns…</p>}

        {!loading && datasetId !== '' && proposals.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>
            No user/owner or org-ish columns found on this dataset.
          </p>
        )}

        {!loading && proposals.length > 0 && (
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 10, marginBottom: 16 }}>
            {proposals.map(p => (
              <label key={p.column} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '5px 0', cursor: 'pointer' }}>
                <input type="checkbox" checked={checked.has(p.column)} onChange={() => toggle(p.column)} />
                <span style={{ fontFamily: 'var(--mono)', flex: 1 }}>{p.expression}</span>
              </label>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleApply}
            disabled={applying || roleId === '' || datasetId === '' || checked.size === 0} title={roleId === '' ? 'Choose a role first' : datasetId === '' ? 'Choose a dataset first' : checked.size === 0 ? 'Tick at least one rule' : undefined} style={{ flex: 1 }}>
            {applying ? 'Applying…' : 'Apply selected'}
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
  const [loadError, setLoadError] = useState<unknown>(null)
  const [modal, setModal] = useState<'add' | RowSecurityRule | null>(null)
  const [showAutoGenerate, setShowAutoGenerate] = useState(false)

  // A load failure gets the persistent inline banner below, not a toast: this is
  // the page's whole content going missing, not a transient action result. Falling
  // through to "No rules yet" / "need a role and dataset" here would tell an admin
  // their org has none of these things set up when the server is simply down.
  const load = () => {
    setLoadError(null)
    return Promise.all([adminRlsRulesApi.list(), adminRolesApi.list(), datasetsApi.list()])
      .then(([r, ro, d]) => { setRules(r); setRoles(ro); setDatasets(d) })
      .catch(setLoadError)
  }

  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const roleName = (id: number) => roles.find(r => r.id === id)?.name ?? `Role #${id}`
  const datasetName = (id: number) => datasets.find(d => d.id === id)?.name ?? `Dataset #${id}`

  const handleSaved = (r: RowSecurityRule) => {
    setRules(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (r: RowSecurityRule) => {
    if (!await confirm({ title: 'Delete this row-security rule?', body: `Role "${roleName(r.role_id)}" on dataset "${datasetName(r.dataset_id)}". Rows it was hiding become visible to that role.` })) return
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
        <button className="btn btn-ghost btn-sm" onClick={() => setShowAutoGenerate(true)} disabled={!canCreate} title={!canCreate ? 'Needs at least one role and one dataset' : undefined} style={{ marginInlineEnd: 8 }}>
          ⚡ Auto-generate rules
        </button>
        <button className="btn btn-primary btn-sm" onClick={() => setModal('add')} disabled={!canCreate} title={!canCreate ? 'Needs at least one role and one dataset' : undefined}>
          + New Rule
        </button>
      </div>
      {/* The single most important sentence on this page. These rules narrow a
          DATASET; Ask AI queries the CONNECTION and obeys a different table
          entirely. An admin who sets a rule here and stops has not finished, and
          before this line there was nothing anywhere to tell them so -- a student
          limited to one row here pulled five thousand rows through Ask AI. */}
      <p style={{
        margin: '0 0 20px', padding: '12px 14px', borderRadius: 6, fontSize: 13,
        background: 'var(--surface2)', borderInlineStart: '3px solid var(--warning, #b4232a)',
      }}>
        <strong>These rules do not apply to Ask AI.</strong> They narrow a dataset.
        The assistant queries the connection directly, so the same person can ask
        it for rows this rule hides. Set the matching rule under{' '}
        <a href="/admin/connection-rules">Connection rules (Ask AI)</a>.
      </p>


      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="row security rules" error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && !canCreate && (
        <div style={{ padding: 16, marginBottom: 16, background: 'var(--surface2)', border: '1px solid var(--border)',
          borderRadius: 8, fontSize: 12, color: 'var(--muted)' }}>
          You need at least one role and one dataset before creating a rule.
        </div>
      )}

      {!loading && loadError == null && rules.length === 0 && canCreate && (
        <div className="card" style={{ padding: '56px 24px', textAlign: 'center', color: 'var(--muted)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔒</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No row-security rules yet</div>
          <div style={{ fontSize: 12 }}>Roles with no rule for a dataset see every row within their org.</div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rules.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, padding: '14px 16px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {roleName(r.role_id)} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>on</span> {datasetName(r.dataset_id)}
                {r.auto_generated && (
                  <span title="Generated by Auto-generate rules"
                    style={{ fontSize: 9, fontWeight: 700, color: 'var(--accent)', marginInlineStart: 8,
                      background: 'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius: 99, padding: '2px 7px', textTransform: 'uppercase', letterSpacing: '.04em' }}>
                    auto
                  </span>
                )}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', fontFamily: 'var(--mono)' }}>{r.filter_expr}</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)} style={{ fontSize: 11 }}>Edit</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(r)} style={{ fontSize: 11, color: 'var(--danger)' }}>Delete</button>
            <ActionMenu
              label={`More actions for rule ${roleName(r.role_id)} on ${datasetName(r.dataset_id)}`}
              items={[
                { key: 'edit', label: 'Edit rule', onSelect: () => setModal(r) },
                { key: 'delete', label: 'Delete rule', danger: true, onSelect: () => handleDelete(r) },
              ]}
            />
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

      {showAutoGenerate && (
        <AutoGenerateModal
          roles={roles}
          datasets={datasets}
          onApplied={handleSaved}
          onClose={() => setShowAutoGenerate(false)}
        />
      )}
    </div>
  )
}
