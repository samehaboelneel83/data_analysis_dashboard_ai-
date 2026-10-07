import { useEffect, useMemo, useState } from 'react'
import { fieldStyle } from '../../components/ui/fieldStyle'
import { useT, type MessageKey } from '../../i18n'
import { nodesT } from '../../i18n/pages/adminSecurity'
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
import EmptyState from '../../components/ui/EmptyState'
import { Lock, Plus, Wand2 } from 'lucide-react'

// S0b: codeless RLS rule builder. A column is "user-ish" when Layer 1 has
// classified it as an email, or its name reads like one (user/email/owner) —
// these are exactly the columns a "restrict by current user?" rule targets.
function isUserishColumn(col: DatasetColumn): boolean {
  return col.semantic_type === 'email' || /user|email|owner/i.test(col.name)
}

type MatchTarget = 'useremail' | 'userid' | 'orgid' | 'myscope' | 'literal'

const MATCH_TARGETS: { value: MatchTarget; labelKey: MessageKey; token?: string }[] = [
  { value: 'useremail', labelKey: 'pg.adminSecurity.rls.match.useremail', token: 'USEREMAIL()' },
  { value: 'userid',    labelKey: 'pg.adminSecurity.rls.match.userid', token: 'USERID()' },
  { value: 'orgid',     labelKey: 'pg.adminSecurity.rls.match.orgid', token: 'ORGID()' },
  // One rule for every manager: each sees the org-chart units they are placed
  // in and everything below them (Admin -> Organization chart). HR evaluation,
  // item 2.6: "each department manager sees only their department".
  { value: 'myscope',   labelKey: 'pg.adminSecurity.rls.match.myscope', token: 'MYSCOPE()' },
  { value: 'literal',   labelKey: 'pg.adminSecurity.rls.match.literal' },
]

/** `column == <token or quoted literal>` — the whole of S0b's generated shape.
 *  Returns '' when there isn't enough picked yet to mean anything. */
function generateExpression(column: string, target: MatchTarget, literalValue: string): string {
  if (!column) return ''
  const targetDef = MATCH_TARGETS.find(t => t.value === target)
  const rhs = targetDef?.token ?? (literalValue.trim() ? literal(literalValue) : '')
  if (!rhs) return ''
  if (target === 'myscope') return `${colRef(column)} in ${rhs}`
  return `${colRef(column)} == ${rhs}`
}

function RuleModal({ initial, roles, datasets, onSave, onClose }: {
  initial?: RowSecurityRule | null
  roles: Role[]
  datasets: Dataset[]
  onSave: (r: RowSecurityRule) => void
  onClose: () => void
}) {
  const t = useT()
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

  const inp = { style: fieldStyle }

  const handleSave = async () => {
    if (!isEdit && (roleId === '' || datasetId === '')) { toast.error(t('pg.adminSecurity.c.roleAndDatasetRequired')); return }
    if (!filterExpr.trim()) { toast.error(t('pg.adminSecurity.rls.filterRequired')); return }
    setSaving(true)
    try {
      const result = isEdit
        ? await adminRlsRulesApi.update(initial!.id, { filter_expr: filterExpr })
        : await adminRlsRulesApi.create({ role_id: roleId as number, dataset_id: datasetId as number, filter_expr: filterExpr })
      onSave(result)
      toast.success(isEdit ? t('pg.adminSecurity.c.updated') : t('pg.adminSecurity.c.ruleCreated'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.rls.saveFailed'))
    } finally { setSaving(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={isEdit ? t('pg.adminSecurity.rls.editAria') : t('pg.adminSecurity.rls.newAria')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{isEdit ? t('pg.adminSecurity.rls.editTitle') : t('pg.adminSecurity.rls.newTitle')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        {/* Role and dataset are fixed once a rule is created (unique per role+dataset pair) — only filter_expr is editable. */}
        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.c.roleReq')}</div>
          <select value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} title={isEdit ? t('pg.adminSecurity.rls.fixed') : undefined} {...inp}>
            <option value="">{t('pg.adminSecurity.c.selectRole')}</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.c.datasetReq')}</div>
          <select aria-label={t('pg.adminSecurity.c.datasetReq')} value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} disabled={isEdit} title={isEdit ? t('pg.adminSecurity.rls.fixed') : undefined} {...inp}>
            <option value="">{t('pg.adminSecurity.c.selectDataset')}</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        {dsColumns.length > 0 && (
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 10, marginBottom: 12 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase',
              letterSpacing: '.06em', marginBottom: 8 }}>{t('pg.adminSecurity.rls.quickSetup')}</div>

            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.rls.column')}</div>
              <select aria-label={t('pg.adminSecurity.rls.column')} value={pickedColumn} onChange={e => setPickedColumn(e.target.value)} {...inp}>
                <option value="">{t('pg.adminSecurity.rls.selectColumn')}</option>
                {suggestedColumns.length > 0 && (
                  <optgroup label={t('pg.adminSecurity.rls.suggested')}>
                    {suggestedColumns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </optgroup>
                )}
                {otherColumns.length > 0 && (
                  <optgroup label={t('pg.adminSecurity.rls.otherColumns')}>
                    {otherColumns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                  </optgroup>
                )}
              </select>
              {pickedColumn && suggestedColumns.some(c => c.name === pickedColumn) && (
                <div style={{ fontSize: 11, color: 'var(--accent)', marginTop: 3 }}>
                  {t('pg.adminSecurity.rls.looksUser')}
                </div>
              )}
            </div>

            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.rls.match')}</div>
              <select aria-label={t('pg.adminSecurity.rls.match')} value={matchTarget} onChange={e => setMatchTarget(e.target.value as MatchTarget)} {...inp}>
                {MATCH_TARGETS.map(m => <option key={m.value} value={m.value}>{t(m.labelKey)}</option>)}
              </select>
            </div>

            {matchTarget === 'myscope' && (
              <div data-testid="myscope-hint" style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
                {nodesT(t, 'pg.adminSecurity.rls.myscopeHint', {
                  link: <a href="/admin/org-units">{t('pg.adminSecurity.rls.orgChart')}</a>,
                  code: <code dir="ltr">Sales</code>, // i18n-ok: an example match value
                })}
              </div>
            )}

            {matchTarget === 'literal' && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.rls.literalValue')}</div>
                <input aria-label={t('pg.adminSecurity.rls.literalValue')} value={literalValue} onChange={e => setLiteralValue(e.target.value)} placeholder={t('pg.adminSecurity.rls.literalPlaceholder')} {...inp} />
              </div>
            )}

            <div style={{ fontFamily: 'var(--mono)', fontSize: 11, padding: '6px 8px',
              background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 5,
              color: 'var(--muted)', marginBottom: 8, minHeight: 16 }}>
              {generated ? <bdi dir="ltr">{generated}</bdi> : <span style={{ opacity: .6 }}>{t('pg.adminSecurity.rls.pickFirst')}</span>}
            </div>

            <button type="button" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}
              disabled={!generated} title={!generated ? t('pg.adminSecurity.rls.generateFirst') : undefined} onClick={() => setFilterExpr(generated)}>
              {t('pg.adminSecurity.rls.useExpression')}
            </button>
          </div>
        )}

        <label style={{ display: 'block', marginBottom: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.rls.filterLabel')}</div>
          <textarea
            value={filterExpr}
            onChange={e => setFilterExpr(e.target.value)}
            placeholder="region == 'North'" // i18n-ok: an expression
            dir="ltr"
            rows={3}
            style={{ width: '100%', fontFamily: 'var(--mono)', fontSize: 12, padding: '6px 8px',
              background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 6,
              color: 'var(--text)', resize: 'vertical', boxSizing: 'border-box' }}
          />
        </label>
        {overlap.length > 0 && (
          <div role="note" style={{ fontSize: 11, padding: '6px 8px', borderRadius: 6, marginBottom: 8,
            background: 'color-mix(in srgb, var(--accent) 12%, transparent)', border: '1px solid var(--border)' }}>
            {t('pg.adminSecurity.rls.overlap', { cols: overlap.join(', ') })}
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 20 }}>
          {t('pg.adminSecurity.rls.help1')}
          <br />
          {nodesT(t, 'pg.adminSecurity.rls.help2', {
            a: <code style={{ fontFamily: 'var(--mono)' }} dir="ltr">USEREMAIL()</code>, // i18n-ok: code
            b: <code style={{ fontFamily: 'var(--mono)' }} dir="ltr">USERID()</code>, // i18n-ok: code
            c: <code style={{ fontFamily: 'var(--mono)' }} dir="ltr">owner == USEREMAIL()</code>, // i18n-ok: code
          })}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ flex: 1 }}>
            {saving ? t('pg.adminSecurity.c.saving') : isEdit ? t('pg.adminSecurity.c.saveChanges') : t('pg.adminSecurity.c.create')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('common.cancel')}</button>
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
  const t = useT()
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
      .catch(() => toast.error(t('pg.adminSecurity.rls.loadProposalsFailed')))
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
        toast.success(t('pg.adminSecurity.rls.applied'))
      } else {
        toast.error(r.reason ?? t('pg.adminSecurity.rls.nothingToApply'))
      }
      onClose()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.rls.autoFailed'))
    } finally {
      setApplying(false)
    }
  }

  const inp = { style: fieldStyle }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.5)', display: 'flex',
      alignItems: 'center', justifyContent: 'center', zIndex: Z_OVERLAY }}>
      <div ref={dialogRef} role="dialog" aria-modal="true"
        aria-label={t('pg.adminSecurity.rls.autoAria')}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12,
        padding: 24, width: 460, maxWidth: '90vw', maxHeight: '85vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>{t('pg.adminSecurity.rls.autoTitle')}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, color: 'var(--muted)' }}>×</button>
        </div>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.c.datasetReq')}</div>
          <select aria-label={t('pg.adminSecurity.c.datasetReq')} value={datasetId} onChange={e => setDatasetId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">{t('pg.adminSecurity.c.selectDataset')}</option>
            {datasets.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>{t('pg.adminSecurity.c.roleReq')}</div>
          <select aria-label={t('pg.adminSecurity.c.roleReq')} value={roleId} onChange={e => setRoleId(e.target.value ? Number(e.target.value) : '')} {...inp}>
            <option value="">{t('pg.adminSecurity.c.selectRole')}</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>

        {loading && <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('pg.adminSecurity.rls.scanning')}</p>}

        {!loading && datasetId !== '' && proposals.length === 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)' }}>
            {t('pg.adminSecurity.rls.noProposals')}
          </p>
        )}

        {!loading && proposals.length > 0 && (
          <div style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 8,
            padding: 10, marginBottom: 16 }}>
            {proposals.map(p => (
              <label key={p.column} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, padding: '5px 0', cursor: 'pointer' }}>
                <input type="checkbox" checked={checked.has(p.column)} onChange={() => toggle(p.column)} />
                <span style={{ fontFamily: 'var(--mono)', flex: 1 }}><bdi dir="ltr">{p.expression}</bdi></span>
              </label>
            ))}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" onClick={handleApply}
            disabled={applying || roleId === '' || datasetId === '' || checked.size === 0} title={roleId === '' ? t('pg.adminSecurity.c.chooseRoleFirst') : datasetId === '' ? t('pg.adminSecurity.c.chooseDatasetFirst') : checked.size === 0 ? t('pg.adminSecurity.rls.tickOne') : undefined} style={{ flex: 1 }}>
            {applying ? t('pg.adminSecurity.rls.applying') : t('pg.adminSecurity.rls.applySelected')}
          </button>
          <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: 12, padding: '6px 14px' }}>{t('common.cancel')}</button>
        </div>
      </div>
    </div>
  )
}

export default function AdminRowSecurityRules() {
  const t = useT()
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

  const roleName = (id: number) => roles.find(r => r.id === id)?.name ?? t('pg.adminSecurity.c.roleFallback', { id })
  const datasetName = (id: number) => datasets.find(d => d.id === id)?.name ?? t('pg.adminSecurity.c.datasetFallback', { id })

  const handleSaved = (r: RowSecurityRule) => {
    setRules(prev => {
      const idx = prev.findIndex(x => x.id === r.id)
      return idx >= 0 ? prev.map(x => x.id === r.id ? r : x) : [r, ...prev]
    })
    setModal(null)
  }

  const confirm = useConfirm()
  const handleDelete = async (r: RowSecurityRule) => {
    if (!await confirm({ title: t('pg.adminSecurity.rls.deleteTitle'), body: t('pg.adminSecurity.rls.deleteBody', { role: roleName(r.role_id), dataset: datasetName(r.dataset_id) }) })) return
    try {
      await adminRlsRulesApi.delete(r.id)
      setRules(prev => prev.filter(x => x.id !== r.id))
      toast.success(t('pg.adminSecurity.c.deleted'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? t('pg.adminSecurity.c.deleteFailed'))
    }
  }

  const canCreate = roles.length > 0 && datasets.length > 0

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24 }}>
        <h1 className="dl-page-title" style={{ flex: 1 }}>{t('nav.rowSecurity')}</h1>
        <button className="btn btn-ghost" onClick={() => setShowAutoGenerate(true)} disabled={!canCreate} title={!canCreate ? t('pg.adminSecurity.c.needsRoleAndDataset') : undefined} style={{ marginInlineEnd: 8 }}>
          <Wand2 size={16} aria-hidden /> {t('admin.autoGenerate')}
        </button>
        <button className="btn btn-primary" onClick={() => setModal('add')} disabled={!canCreate} title={!canCreate ? t('pg.adminSecurity.c.needsRoleAndDataset') : undefined}>
          <Plus size={16} aria-hidden /> {t('admin.newRule')}
        </button>
      </div>
      {/* What these rules reach, said accurately. The old banner said "these
          rules do not apply to Ask AI" -- true once, false since E01 placed
          dataset rules on the connection's tables too -- and the HR evaluation
          read it as "a manager can ask the AI for every department's pay". */}
      <p data-testid="rls-ask-note" style={{
        margin: '0 0 20px', padding: '12px 14px', borderRadius: 6, fontSize: 13,
        background: 'var(--surface2)', borderInlineStart: '3px solid var(--accent)',
      }}>
        {nodesT(t, 'pg.adminSecurity.rls.askNote', {
          strong: <strong>{t('pg.adminSecurity.rls.askNoteStrong')}</strong>,
          link: <a href="/admin/connection-rules">{t('pg.adminSecurity.rls.askNoteLink')}</a>,
        })}
      </p>


      {loading && <LoadingState />}

      {!loading && loadError != null && (
        <LoadError what="row security rules" title={t('pg.adminSecurity.rls.loadErr')} retryLabel={t('pg.adminSecurity.c.retry')} error={loadError} onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && !canCreate && (
        <div className="dl-conn-notice">
          {t('pg.adminSecurity.c.needRoleAndDatasetNotice')}
        </div>
      )}

      {!loading && loadError == null && rules.length === 0 && canCreate && (
        <EmptyState icon={Lock} title={t('pg.adminSecurity.rls.emptyTitle')}
          description={t('pg.adminSecurity.rls.emptyBody')} />
      )}

      <div className="dl-rows">
        {rules.map(r => (
          <div key={r.id} className="dl-rows__row">
            <div className="dl-rows__main">
              <div className="dl-rows__title">
                {nodesT(t, 'pg.adminSecurity.c.ruleTitle', {
                  role: <bdi>{roleName(r.role_id)}</bdi>,
                  on: <span style={{ color: 'var(--muted)', fontWeight: 400 }}>{t('pg.adminSecurity.c.on')}</span>,
                  dataset: <bdi>{datasetName(r.dataset_id)}</bdi>,
                })}
                {r.auto_generated && (
                  <span title={t('pg.adminSecurity.rls.autoBadgeTitle')}
                    style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--accent)', marginInlineStart: 8,
                      background: 'color-mix(in srgb, var(--accent) 15%, transparent)', borderRadius: 99, padding: '2px 7px', textTransform: 'uppercase', letterSpacing: '.04em' }}>
                    {t('pg.adminSecurity.rls.autoBadge')}
                  </span>
                )}
              </div>
              <div className="dl-rows__meta dl-rows__meta--mono"><bdi dir="ltr">{r.filter_expr}</bdi></div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setModal(r)}>{t('admin.edit')}</button>
            <button className="btn btn-ghost btn-sm dl-danger-item" onClick={() => handleDelete(r)}>{t('admin.delete')}</button>
            <ActionMenu
              label={t('pg.adminSecurity.rls.moreActions', { role: roleName(r.role_id), dataset: datasetName(r.dataset_id) })}
              items={[
                { key: 'edit', label: t('pg.adminSecurity.rls.editRule'), onSelect: () => setModal(r) },
                { key: 'delete', label: t('pg.adminSecurity.rls.deleteRule'), danger: true, onSelect: () => handleDelete(r) },
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
