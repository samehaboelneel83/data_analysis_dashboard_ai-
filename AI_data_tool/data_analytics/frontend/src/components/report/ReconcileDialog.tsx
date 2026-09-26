import { useState } from 'react'
import { useT } from '../../i18n'
import { useModalDialog } from '../ui/useModalDialog'
import { widgetDataApi, type CalcColumn, type ReconcileMapping, type ReconcileResult } from '../../services/api'

/**
 * E17: does this widget say what the report it replaces said?
 *
 * The owner picks the old report's export of the same table (CSV or Excel);
 * the widget, as they see it, is compared row by row: rows that agree, rows
 * that differ and by how much, rows on one side only, and the totals. Which
 * columns identify a row and which to compare are guessed from the names
 * and can be changed. The server decides agreement (services/reconcile.py):
 * to the decimals the file shows.
 */
export default function ReconcileDialog({ title, datasetId, body, onClose }: {
  title: string
  datasetId: number
  body: { config: Record<string, unknown>; widget_type: string; calculated_columns?: CalcColumn[]
          report_id?: number; parameters?: Record<string, unknown> }
  onClose: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ReconcileResult | null>(null)
  const [mapping, setMapping] = useState<ReconcileMapping | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async (f: File, m?: ReconcileMapping) => {
    setBusy(true); setError(null)
    try {
      const r = await widgetDataApi.reconcile(datasetId, body, f, m)
      setResult(r); setMapping(r.mapping)
    } catch (e) {
      setResult(null)
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('rec.failed'))
    } finally { setBusy(false) }
  }

  const pairEditor = (kind: 'keys' | 'values', label: string) => mapping && result && (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
      <legend style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)' }}>{label}</legend>
      {mapping[kind].map(([a, e], i) => (
        <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4 }}>
          <select aria-label={t('rec.widgetColumn', { n: i + 1, kind: label })} value={a}
            onChange={ev => setMapping(m => m && { ...m, [kind]: m[kind].map((p, j) => j === i ? [ev.target.value, p[1]] : p) })}>
            {result.columns.widget.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <span aria-hidden>↔</span>
          <select aria-label={t('rec.fileColumn', { n: i + 1, kind: label })} value={e}
            onChange={ev => setMapping(m => m && { ...m, [kind]: m[kind].map((p, j) => j === i ? [p[0], ev.target.value] : p) })}>
            {result.columns.file.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      ))}
    </fieldset>
  )

  const fmt = (v: unknown) => v == null ? '—' : typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(v)
  const STATUS: Record<ReconcileResult['rows'][number]['status'], string> = {
    match: t('rec.match'), mismatch: t('rec.mismatch'),
    missing_in_widget: t('rec.onlyInFile'), missing_in_file: t('rec.onlyInWidget'),
  }

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={t('rec.title', { title })} onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(760px, calc(100vw - 32px))', maxHeight: 'calc(100vh - 64px)', overflow: 'auto',
          display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <b>{t('rec.title', { title })}</b>
          <button type="button" className="btn btn-sm" aria-label={t('rec.close')} onClick={onClose}>×</button>
        </div>
        <p style={{ margin: 0, color: 'var(--muted)', fontSize: 12.5 }}>{t('rec.lead')}</p>
        <label style={{ fontSize: 13 }}>
          <span style={{ display: 'block', fontWeight: 600, marginBottom: 4 }}>{t('rec.file')}</span>
          <input type="file" accept=".csv,.txt,.tsv,.xlsx,.xls,.xlsm"
            onChange={e => { const f = e.target.files?.[0] ?? null; setFile(f); if (f) void run(f) }} />
        </label>
        {busy && <p role="status" style={{ margin: 0 }}>{t('rec.working')}</p>}
        {error && <p role="alert" style={{ margin: 0, color: 'var(--danger)' }}>{error}</p>}

        {result && mapping && (
          <>
            <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
              {pairEditor('keys', t('rec.keys'))}
              {pairEditor('values', t('rec.values'))}
              <button className="btn btn-sm" disabled={busy || !file} onClick={() => file && void run(file, mapping)}>
                {t('rec.again')}
              </button>
            </div>
            <div role="status" data-testid="rec-summary"
              style={{ padding: '8px 10px', borderRadius: 6, fontWeight: 600,
                background: result.reconciled ? 'var(--mc-success-soft, #e3f5ea)' : 'var(--mc-warning-soft, #fff3d6)' }}>
              {result.reconciled ? t('rec.allAgree', { n: result.counts.match }) : t('rec.summary', {
                match: result.counts.match, mismatch: result.counts.mismatch,
                onlyFile: result.counts.missing_in_widget, onlyWidget: result.counts.missing_in_file })}
              {(result.duplicate_keys.file > 0 || result.duplicate_keys.widget > 0) &&
                <span style={{ fontWeight: 400 }}> {t('rec.duplicates', { n: result.duplicate_keys.file + result.duplicate_keys.widget })}</span>}
            </div>
            <table className="dl-table" data-testid="rec-totals">
              <caption style={{ textAlign: 'start', fontWeight: 600, fontSize: 12 }}>{t('rec.totals')}</caption>
              <thead><tr><th>{t('rec.column')}</th><th className="dl-table__num">{t('rec.inFile')}</th>
                <th className="dl-table__num">{t('rec.inWidget')}</th><th className="dl-table__num">{t('rec.difference')}</th></tr></thead>
              <tbody>{result.totals.map(tt => (
                <tr key={tt.column}><td>{tt.column}</td><td className="dl-table__num">{fmt(tt.expected)}</td>
                  <td className="dl-table__num">{fmt(tt.actual)}</td><td className="dl-table__num">{fmt(tt.difference)}</td></tr>
              ))}</tbody>
            </table>
            {result.rows.some(r => r.status !== 'match') && (
              <table className="dl-table" data-testid="rec-rows">
                <caption style={{ textAlign: 'start', fontWeight: 600, fontSize: 12 }}>{t('rec.differences')}</caption>
                <thead><tr><th>{t('rec.row')}</th><th>{t('rec.status')}</th><th>{t('rec.column')}</th>
                  <th className="dl-table__num">{t('rec.inFile')}</th><th className="dl-table__num">{t('rec.inWidget')}</th>
                  <th className="dl-table__num">{t('rec.difference')}</th></tr></thead>
                <tbody>
                  {result.rows.filter(r => r.status !== 'match').slice(0, 200).flatMap((r, i) => {
                    const key = Object.values(r.key).map(fmt).join(' · ')
                    const cells = r.values.filter(v => !v.ok)
                    if (!cells.length) return [<tr key={i}><td>{key}</td><td>{STATUS[r.status]}</td><td colSpan={4} /></tr>]
                    return cells.map((v, j) => (
                      <tr key={`${i}-${j}`}><td>{j === 0 ? key : ''}</td><td>{j === 0 ? STATUS[r.status] : ''}</td>
                        <td>{v.column}</td><td className="dl-table__num">{fmt(v.expected)}</td>
                        <td className="dl-table__num">{fmt(v.actual)}</td><td className="dl-table__num">{fmt(v.difference)}</td></tr>
                    ))
                  })}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </div>
  )
}
