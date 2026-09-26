import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { formatTimeAgo, useT, type MessageKey as TKey } from '../i18n'
import {
  adminUsersApi, migrationApi, reportsApi,
  type MigrationFeature, type MigrationFit, type MigrationItem, type MigrationStatus, type User,
} from '../services/api'
import type { Report } from '../types/report'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { useConfirm } from '../components/ui/ConfirmDialog'

/**
 * Migration (E17): the old estate, item by item, and what becomes of each.
 *
 * An admin imports the inventory (a CSV with one row per report or program)
 * and the SAS programs themselves, which are scanned for what they use and
 * mapped to Datalytics features. Each item's owner links the report that
 * replaces it, compares its widgets with the old exports (⇄ Reconcile on a
 * widget, choosing this item) and signs off. Status is derived by the server
 * from that evidence (services/migration.py); this page only shows it.
 */

const STATUSES: MigrationStatus[] = ['to_map', 'mapped', 'differences', 'reconciled', 'signed_off', 'retired']
const KINDS = ['report', 'program', 'stored_process', 'job', 'dataset', 'other'] as const
const STATUS_TONE: Record<MigrationStatus, string | undefined> = {
  to_map: undefined, mapped: undefined, differences: 'dl-fresh--bad', reconciled: undefined,
  signed_off: 'dl-fresh--ok', retired: undefined,
}
const FIT_TONE: Record<MigrationFit, string | undefined> = {
  native: undefined, partial: 'dl-fresh--warn', manual: 'dl-fresh--bad',
}

const detail = (e: unknown, fallback: string) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? fallback

export default function Migration() {
  const t = useT()
  const confirm = useConfirm()
  const [params, setParams] = useSearchParams()
  const openId = Number(params.get('item')) || null
  const [items, setItems] = useState<MigrationItem[]>([])
  const [summary, setSummary] = useState<Record<MigrationStatus, number> | null>(null)
  const [canManage, setCanManage] = useState(false)
  const [users, setUsers] = useState<User[]>([])
  const [reports, setReports] = useState<Report[]>([])
  const [featureMap, setFeatureMap] = useState<MigrationFeature[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [filter, setFilter] = useState<MigrationStatus | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [newName, setNewName] = useState('')
  const [newKind, setNewKind] = useState<string>('report')
  const [newOwner, setNewOwner] = useState('')

  const load = () => {
    setLoading(true); setLoadError(null)
    Promise.all([migrationApi.list(), reportsApi.list().catch(() => [] as Report[])])
      .then(([m, r]) => {
        setItems(m.items); setSummary(m.summary); setCanManage(m.can_manage); setReports(r)
        if (m.can_manage) adminUsersApi.list().then(u => setUsers(u.filter(x => x.is_active))).catch(() => setUsers([]))
      })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const replace = (it: MigrationItem) => {
    setItems(xs => xs.map(x => x.id === it.id ? it : x))
    // The counts follow the item's new status without another round trip.
    setSummary(s => {
      if (!s) return s
      const old = items.find(x => x.id === it.id)
      if (!old || old.status === it.status) return s
      return { ...s, [old.status]: s[old.status] - 1, [it.status]: s[it.status] + 1 }
    })
  }
  const open = (id: number | null) => setParams(id ? { item: String(id) } : {})
  const shown = useMemo(() => filter ? items.filter(i => i.status === filter) : items, [items, filter])

  const add = async () => {
    if (!newName.trim()) return
    setBusy(true)
    try {
      await migrationApi.create({ name: newName.trim(), kind: newKind, owner_id: newOwner ? Number(newOwner) : null })
      setNewName(''); setNewOwner('')
      load()
    } catch (e) {
      toast.error(detail(e, t('mig.saveFailed')))
    } finally { setBusy(false) }
  }

  const importFiles = async (files: File[]) => {
    if (!files.length) return
    setBusy(true)
    try {
      const r = await migrationApi.import(files)
      toast.success(t('mig.imported', { created: r.created, updated: r.updated }))
      setWarnings(r.warnings)
      load()
    } catch (e) {
      toast.error(detail(e, t('mig.importFailed')))
    } finally { setBusy(false) }
  }

  if (loading) return <LoadingState />
  if (loadError) return <LoadError what={t('mig.loadWhat')} error={loadError} onRetry={load} />
  const current = items.find(i => i.id === openId) ?? null
  const kindLabel = (k: string) => t(`mig.kind.${k}` as TKey)

  return (
    <div style={{ maxWidth: 1200 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.migration')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('mig.lead')}</p>

      {summary && (
        <div role="group" aria-label={t('mig.byStatus')} style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
          <button className={`btn btn-sm${filter === null ? ' btn-primary' : ''}`} aria-pressed={filter === null}
            onClick={() => setFilter(null)}>{t('mig.all', { n: items.length })}</button>
          {STATUSES.map(s => (
            <button key={s} className={`btn btn-sm${filter === s ? ' btn-primary' : ''}`} aria-pressed={filter === s}
              onClick={() => setFilter(f => f === s ? null : s)}>
              {t(`mig.status.${s}` as TKey)} · {summary[s] ?? 0}
            </button>
          ))}
        </div>
      )}

      {canManage && (
        <section className="card" style={{ padding: 16, marginTop: 16 }} aria-labelledby="mig-add">
          <h2 id="mig-add" style={{ fontSize: 15, marginTop: 0 }}>{t('mig.add')}</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <label style={{ fontSize: 13 }}>
              <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.name')}</span>
              <input value={newName} onChange={e => setNewName(e.target.value)} style={{ minWidth: 240 }} />
            </label>
            <label style={{ fontSize: 13 }}>
              <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.kind')}</span>
              <select value={newKind} onChange={e => setNewKind(e.target.value)}>
                {KINDS.map(k => <option key={k} value={k}>{kindLabel(k)}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 13 }}>
              <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.owner')}</span>
              <select value={newOwner} onChange={e => setNewOwner(e.target.value)} style={{ minWidth: 200 }}>
                <option value="">{t('mig.noOwner')}</option>
                {users.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
              </select>
            </label>
            <button className="btn btn-primary btn-sm" disabled={busy || !newName.trim()} onClick={() => void add()}>
              {t('mig.addButton')}
            </button>
          </div>
          <label style={{ display: 'block', fontSize: 13, marginTop: 12 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.import')}</span>
            <input type="file" multiple accept=".csv,.txt,.tsv,.sas" disabled={busy} aria-label={t('mig.import')}
              onChange={e => { void importFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />
            <span style={{ display: 'block', color: 'var(--muted)', fontSize: 12, marginTop: 4 }}>{t('mig.importHint')}</span>
          </label>
          {warnings.length > 0 && (
            <ul role="status" aria-label={t('mig.warnings')} style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 0 }}>
              {warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </section>
      )}

      <section className="card dl-table-card" style={{ marginTop: 16 }}>
        {items.length === 0 ? (
          <p style={{ padding: 16, color: 'var(--muted)', fontSize: 13, margin: 0 }}>
            {canManage ? t('mig.emptyAdmin') : t('mig.empty')}
          </p>
        ) : (
          <table className="dl-table">
            <thead>
              <tr>
                <th>{t('mig.name')}</th><th>{t('mig.owner')}</th><th>{t('mig.replacedBy')}</th>
                <th>{t('mig.fit')}</th><th>{t('mig.evidence')}</th><th>{t('mig.statusCol')}</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(i => (
                <tr key={i.id} data-selected={i.id === openId || undefined} data-testid={`mig-${i.id}`}>
                  <td>
                    <button className="btn btn-ghost btn-sm row-name" style={{ padding: 0 }} onClick={() => open(i.id)}>
                      {i.name}
                    </button>
                    <div className="dl-cell-sub">{kindLabel(i.kind)}{i.source_path ? ` · ${i.source_path}` : ''}</div>
                  </td>
                  <td>{i.owner?.email ?? <span style={{ color: 'var(--muted)' }}>{t('mig.noOwner')}</span>}</td>
                  <td><ReportRef item={i} /></td>
                  <td className={i.fit ? FIT_TONE[i.fit] : undefined}>{i.fit ? t(`mig.fit.${i.fit}` as TKey) : '—'}</td>
                  <td>{evidence(i, t)}</td>
                  <td className={STATUS_TONE[i.status]}>
                    {t(`mig.status.${i.status}` as TKey)}
                    {i.report_changed_since_sign_off && <div className="dl-cell-sub dl-fresh--warn">{t('mig.changedSince')}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {current && (
        <ItemPanel key={current.id} item={current} reports={reports} canManage={canManage} users={users}
          onChanged={replace} onDeleted={() => { open(null); load() }} confirm={confirm} />
      )}

      <details className="card" style={{ padding: 16, marginTop: 16 }}
        onToggle={e => { if ((e.target as HTMLDetailsElement).open && !featureMap) migrationApi.featureMap().then(setFeatureMap).catch(() => setFeatureMap([])) }}>
        <summary style={{ fontWeight: 600, cursor: 'pointer' }}>{t('mig.featureMap')}</summary>
        <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('mig.featureMapLead')}</p>
        {featureMap === null ? <LoadingState /> : <FeatureTable rows={featureMap} />}
      </details>
    </div>
  )
}

function ReportRef({ item }: { item: MigrationItem }) {
  const t = useT()
  if (!item.report) return <span style={{ color: 'var(--muted)' }}>{t('mig.notMapped')}</span>
  if (!item.report.can_open) return <span style={{ color: 'var(--muted)' }}>{t('mig.reportHidden')}</span>
  return <Link to={`/reports/${item.report.id}`}>{item.report.name}</Link>
}

function evidence(i: MigrationItem, t: ReturnType<typeof useT>) {
  if (i.reconciles.length === 0) return <span style={{ color: 'var(--muted)' }}>{t('mig.noEvidence')}</span>
  const off = i.reconciles.filter(r => r.counts.mismatch || r.counts.missing_in_file || r.counts.missing_in_widget).length
  return off ? t('mig.evidenceOff', { n: i.reconciles.length, off }) : t('mig.evidenceOk', { n: i.reconciles.length })
}

function FeatureTable({ rows }: { rows: MigrationFeature[] }) {
  const t = useT()
  if (rows.length === 0) return <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>{t('mig.noFeatures')}</p>
  const counted = rows.some(r => r.count != null)
  return (
    <table className="dl-table" style={{ fontSize: 12.5 }}>
      <thead>
        <tr>
          <th>{t('mig.sasConstruct')}</th>{counted && <th>{t('mig.uses')}</th>}
          <th>{t('mig.inDatalytics')}</th><th>{t('mig.fit')}</th><th>{t('mig.note')}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.key}>
            <td>{r.label}</td>{counted && <td>{r.count}</td>}
            <td>{r.target}</td>
            <td className={FIT_TONE[r.fit]}>{t(`mig.fit.${r.fit}` as TKey)}</td>
            <td style={{ whiteSpace: 'normal', maxWidth: 360 }}>{r.note}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ItemPanel({ item, reports, users, canManage, onChanged, onDeleted, confirm }: {
  item: MigrationItem; reports: Report[]; users: User[]; canManage: boolean
  onChanged: (i: MigrationItem) => void; onDeleted: () => void
  confirm: ReturnType<typeof useConfirm>
}) {
  const t = useT()
  const [reportId, setReportId] = useState(item.report?.id ? String(item.report.id) : '')
  const [owner, setOwner] = useState(item.owner?.id ? String(item.owner.id) : '')
  const [notes, setNotes] = useState(item.notes ?? '')
  const [signNote, setSignNote] = useState('')
  const [accept, setAccept] = useState(false)
  const [busy, setBusy] = useState(false)

  const act = async (fn: () => Promise<MigrationItem>, ok?: string) => {
    setBusy(true)
    try {
      onChanged(await fn())
      if (ok) toast.success(ok)
    } catch (e) {
      toast.error(detail(e, t('mig.saveFailed')))
    } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!await confirm({ title: t('mig.deleteTitle', { name: item.name }), body: t('mig.deleteBody') })) return
    try { await migrationApi.remove(item.id); onDeleted() } catch (e) { toast.error(detail(e, t('mig.saveFailed'))) }
  }

  const so = item.sign_off
  const reportOptions = reports.some(r => String(r.id) === reportId) || !reportId ? reports
    : [...reports, { id: Number(reportId), name: item.report?.name ?? `#${reportId}` } as Report]
  return (
    <section className="card" style={{ padding: 16, marginTop: 16 }} aria-labelledby="mig-item">
      <h2 id="mig-item" style={{ fontSize: 15, marginTop: 0 }}>{item.name}</h2>
      {!item.can_edit && <p role="note" style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('mig.viewOnly')}</p>}

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 420px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.replacedBy')}</span>
            <span style={{ display: 'flex', gap: 6 }}>
              <select value={reportId} disabled={!item.can_edit} onChange={e => setReportId(e.target.value)} style={{ flex: 1 }}
                aria-label={t('mig.replacedBy')}>
                <option value="">{t('mig.notMapped')}</option>
                {reportOptions.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
              </select>
              {item.can_edit && (
                <button className="btn btn-sm" disabled={busy || reportId === String(item.report?.id ?? '')}
                  onClick={() => void act(() => migrationApi.update(item.id, { report_id: reportId ? Number(reportId) : null }))}>
                  {t('mig.link')}
                </button>
              )}
            </span>
          </label>
          {canManage && (
            <label style={{ fontSize: 13 }}>
              <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.owner')}</span>
              <span style={{ display: 'flex', gap: 6 }}>
                <select value={owner} onChange={e => setOwner(e.target.value)} style={{ flex: 1 }} aria-label={t('mig.owner')}>
                  <option value="">{t('mig.noOwner')}</option>
                  {users.map(u => <option key={u.id} value={u.id}>{u.email}</option>)}
                </select>
                <button className="btn btn-sm" disabled={busy || owner === String(item.owner?.id ?? '')}
                  onClick={() => void act(() => migrationApi.update(item.id, { owner_id: owner ? Number(owner) : null }))}>
                  {t('mig.setOwner')}
                </button>
              </span>
            </label>
          )}

          <div>
            <h3 style={{ fontSize: 13, margin: '0 0 6px' }}>{t('mig.comparisons')}</h3>
            {item.reconciles.length === 0 ? (
              <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
                {item.report ? t('mig.howToCompare') : t('mig.linkFirst')}
              </p>
            ) : (
              <ul style={{ fontSize: 12.5, margin: 0, paddingInlineStart: 18 }}>
                {item.reconciles.map(r => {
                  const c = r.counts
                  const clean = !(c.mismatch || c.missing_in_file || c.missing_in_widget)
                  return (
                    <li key={r.widget_key} className={clean ? undefined : 'dl-fresh--bad'}>
                      <b>{r.title ?? r.widget_key}</b>: {t('mig.compareCounts', {
                        match: c.match, mismatch: c.mismatch, onlyFile: c.missing_in_widget, onlyWidget: c.missing_in_file })}
                      <span style={{ color: 'var(--muted)' }}> · {r.file} · {r.by_email} · {formatTimeAgo(r.at, t)}</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div>
            <h3 style={{ fontSize: 13, margin: '0 0 6px' }}>{t('mig.features')}</h3>
            {item.features ? (
              <>
                <FeatureTable rows={item.features.features} />
                {item.features.libnames.length > 0 && (
                  <p style={{ fontSize: 12, color: 'var(--muted)' }}>{t('mig.libnames', { list: item.features.libnames.join(', ') })}</p>
                )}
              </>
            ) : <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>{t('mig.noScan')}</p>}
            {item.can_edit && (
              <label style={{ display: 'block', fontSize: 12.5, marginTop: 6 }}>
                <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.attachProgram')}</span>
                <input type="file" accept=".sas" disabled={busy} aria-label={t('mig.attachProgram')}
                  onChange={e => { const f = e.target.files?.[0]; e.target.value = ''
                    if (f) void act(() => migrationApi.scan(item.id, f)) }} />
              </label>
            )}
          </div>
        </div>

        <div style={{ flex: '0 1 340px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <label style={{ fontSize: 13 }}>
            <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.notes')}</span>
            <textarea value={notes} disabled={!item.can_edit} rows={3} onChange={e => setNotes(e.target.value)} style={{ width: '100%' }} />
          </label>
          {item.can_edit && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <button className="btn btn-sm" disabled={busy || notes === (item.notes ?? '')}
                onClick={() => void act(() => migrationApi.update(item.id, { notes }))}>{t('mig.saveNotes')}</button>
              {item.decision === 'migrate' ? (
                <button className="btn btn-sm" disabled={busy}
                  onClick={() => void act(() => migrationApi.update(item.id, { decision: 'retire', notes }))}>{t('mig.retire')}</button>
              ) : (
                <button className="btn btn-sm" disabled={busy}
                  onClick={() => void act(() => migrationApi.update(item.id, { decision: 'migrate' }))}>{t('mig.unretire')}</button>
              )}
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <h3 style={{ fontSize: 13, margin: '0 0 6px' }}>{t('mig.signOff')}</h3>
            {so ? (
              <div style={{ fontSize: 12.5 }}>
                <p style={{ margin: 0 }}>{t('mig.signedBy', { who: so.by_email, ago: formatTimeAgo(so.at, t) ?? '' })}</p>
                <p style={{ margin: '4px 0 0', color: 'var(--muted)' }}>{t(`mig.basis.${so.basis}` as TKey)}{so.note ? ` — ${so.note}` : ''}</p>
                {item.report_changed_since_sign_off && <p role="note" className="dl-fresh--warn" style={{ margin: '4px 0 0' }}>{t('mig.changedSinceLong')}</p>}
                {item.can_edit && (
                  <button className="btn btn-sm" style={{ marginTop: 8 }} disabled={busy}
                    onClick={() => void act(() => migrationApi.withdrawSignOff(item.id))}>{t('mig.withdraw')}</button>
                )}
              </div>
            ) : item.can_sign_off ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12.5 }}>
                <label>
                  <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('mig.signNote')}</span>
                  <textarea value={signNote} rows={2} onChange={e => setSignNote(e.target.value)} style={{ width: '100%' }} />
                </label>
                {item.status === 'differences' && (
                  <label><input type="checkbox" checked={accept} onChange={e => setAccept(e.target.checked)} /> {t('mig.accept')}</label>
                )}
                <button className="btn btn-primary btn-sm" disabled={busy || item.decision === 'retire'}
                  onClick={() => void act(() => migrationApi.signOff(item.id, { note: signNote, accept_differences: accept }), t('mig.signed'))}>
                  {t('mig.signButton')}
                </button>
              </div>
            ) : (
              <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>
                {item.owner ? t('mig.ownerSigns', { who: item.owner.email }) : t('mig.needsOwner')}
              </p>
            )}
          </div>
          {canManage && <button className="btn btn-sm btn-danger" onClick={() => void remove()}>{t('mig.delete')}</button>}
        </div>
      </div>
    </section>
  )
}
