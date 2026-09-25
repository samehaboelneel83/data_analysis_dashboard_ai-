/**
 * "Can I trust this data?" in one place (requested 2026-09-25): missing
 * values, duplicate rows, type problems, outliers, and the author's own rules
 * -- computed over the rows THIS viewer's charts use (their row and column
 * security, the saved prep pipeline). Run on demand: a full scan is not free,
 * and an Overview that opens instantly matters more than one that is prefilled.
 */
import { useState } from 'react'
import { datasetsApi, type QualityReport } from '../../services/api'

const card = { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: 12 } as const

export default function DataQualityPanel({ datasetId }: { datasetId: number }) {
  const [report, setReport] = useState<QualityReport | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [rules, setRules] = useState('')

  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      const list = rules.split('\n').map(r => r.trim()).filter(Boolean)
      setReport(await datasetsApi.quality(datasetId, list))
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Could not check this dataset')
    } finally {
      setBusy(false)
    }
  }

  const flagged = report?.column_report.filter(c => c.issues.length) ?? []
  return (
    <section aria-label="Data quality" style={{ ...card, marginTop: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <h2 style={{ fontSize: 14, margin: 0, flex: 1 }}>Data quality</h2>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => void run()} disabled={busy}>
          {busy ? 'Checking…' : report ? 'Check again' : 'Check data quality'}
        </button>
      </div>
      <label style={{ display: 'block', fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
        Your rules (optional) — one per line, each describing a GOOD row, e.g. <code>amount &gt;= 0</code>
        <textarea value={rules} onChange={e => setRules(e.target.value)} rows={2} aria-label="Quality rules"
          style={{ display: 'block', width: '100%', marginTop: 4, fontFamily: 'var(--mono)', fontSize: 11 }} />
      </label>
      {error && <p role="alert" style={{ color: 'var(--danger)', fontSize: 12 }}>{error}</p>}
      {report && (
        <div data-testid="quality-report" style={{ marginTop: 10, fontSize: 12 }}>
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <span><b>{report.rows.toLocaleString()}</b> rows × <b>{report.columns}</b> columns</span>
            <span><b>{report.missing_pct}%</b> of cells empty</span>
            <span><b>{report.duplicate_rows.toLocaleString()}</b> duplicate row{report.duplicate_rows === 1 ? '' : 's'}</span>
            <span><b>{report.columns_with_issues}</b> column{report.columns_with_issues === 1 ? '' : 's'} with issues</span>
          </div>
          {flagged.length > 0 && (
            <table style={{ width: '100%', marginTop: 8, fontSize: 11, borderCollapse: 'collapse' }}>
              <thead><tr><th style={{ textAlign: 'start' }}>Column</th><th style={{ textAlign: 'start' }}>Issues</th></tr></thead>
              <tbody>
                {flagged.map(c => (
                  <tr key={c.column}>
                    <td style={{ padding: '2px 8px 2px 0', fontWeight: 600 }}>{c.column}</td>
                    <td style={{ color: 'var(--muted)' }}>{c.issues.join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {report.duplicate_rows > 0 && (
            <div style={{ marginTop: 8, color: 'var(--muted)' }}>
              Duplicate rows, e.g. {report.duplicate_examples.slice(0, 2)
                .map(r => Object.values(r).slice(0, 4).map(v => String(v ?? '—')).join(', ')).join(' | ')}.
              A “Remove duplicates” prep step drops them.
            </div>
          )}
          {report.rules.map(r => (
            <div key={r.rule} style={{ marginTop: 6, color: r.error ? 'var(--danger)' : (r.failing_rows ? 'var(--warning, #d68910)' : 'var(--muted)') }}>
              <code>{r.rule}</code>: {r.error
                ? `could not check (${r.error})`
                : r.failing_rows ? `${r.failing_rows.toLocaleString()} row${r.failing_rows === 1 ? '' : 's'} fail` : 'every row passes'}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
