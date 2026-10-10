/**
 * One column's whole journey (docs/pipeline/PLAN.md, P5), as numbered steps:
 * where it comes from -> how the dataset loads it (and how the last load
 * went) -> each transformation step that touches it -> the formula that makes
 * it -> the checks run on it -> everything that uses it. "Where does this
 * number come from?" and "what breaks if this changes?" in one place.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { datasetsApi, type ColumnLineage as Lineage, type LineageStage } from '../../services/api'
import { useT, type MessageKey } from '../../i18n'
import { formatDate } from '../../lib/dateFormat'

const SHOW = 8

export default function ColumnLineage({ datasetId, name }: { datasetId: number; name: string }) {
  const t = useT()
  const [data, setData] = useState<Lineage | null>(null)
  const [failed, setFailed] = useState(false)
  const [sql, setSql] = useState(false)
  useEffect(() => {
    setData(null); setFailed(false)
    datasetsApi.columnLineage(datasetId, name).then(setData).catch(() => setFailed(true))
  }, [datasetId, name])
  if (failed) return null
  if (!data) return <div className="dl-cols__muted" style={{ fontSize: 12 }}>{t('lin.loading')}</div>
  const word = (prefix: string, k: string) => { const key = `${prefix}.${k}` as MessageKey; const v = t(key); return v !== key ? v : k }

  const origin = (o: LineageStage & { stage: 'source' } | ({ name: string } & Record<string, unknown>)): ReactNode => {
    const x = o as Record<string, any>
    switch (x.kind) {
      case 'source': return <span dir="auto">{t('lin.source', { source: x.source, table: x.table, column: x.column })}
        {x.native_type && <span className="dl-cols__muted"> ({x.native_type})</span>}</span>
      case 'upload': return t('lin.upload')
      case 'query': return t('lin.query')
      case 'derived': return t('lin.derived', { names: (x.datasets as { name: string }[]).map(d => d.name).join(', ') || '—' })
      case 'inputs': return <>{t('lin.inputsFrom')}{' '}{(x.inputs as Record<string, any>[]).map((i, k) => (
        <span key={k}>{k > 0 && '; '}<strong dir="auto">{i.name}</strong>: {origin(i as never)}</span>))}</>
      default: return t('lin.unknown')
    }
  }

  const stage = (s: LineageStage): ReactNode => {
    switch (s.stage) {
      case 'source': return (<>
        {origin(s)}
        {s.arrives_as && <span className="dl-cols__muted"> — {t('lin.arrivesAs', { col: s.arrives_as })}</span>}
      </>)
      case 'load': {
        const r = s.last_run
        return (<>
          {t(s.mode === 'directquery' ? 'lin.live' : s.strategy === 'incremental' ? 'lin.incremental' : 'lin.full',
            { cursor: s.cursor_column ?? '', key: s.key_column ?? '' })}
          {s.reconcile_deletes && <span> {t('lin.deletes')}</span>}
          {r ? (
            <div className="dl-cols__muted">
              {t('lin.lastRun', { status: word('jobs.status', r.status), when: r.started_at ? formatDate(r.started_at) : '—',
                rows: r.rows != null ? r.rows.toLocaleString() : '—',
                secs: r.duration_ms != null ? (r.duration_ms / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) : '—' })}
              {r.error && <div style={{ color: 'var(--danger)' }}>{r.error}</div>}
            </div>
          ) : s.last_refreshed_at ? <div className="dl-cols__muted">{t('lin.loaded', { when: formatDate(s.last_refreshed_at) })}</div> : null}
          {s.query && (<>
            <button type="button" onClick={() => setSql(v => !v)}
              style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, padding: 0 }}>
              {sql ? t('lin.hideSql') : t('lin.showSql')}
            </button>
            {sql && <pre dir="ltr" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: '4px 0 0' }}>{s.query}</pre>}
          </>)}
        </>)
      }
      case 'steps': return (
        <ol style={{ margin: 0, paddingInlineStart: 18 }}>
          {s.steps.map(st => (
            <li key={st.index} value={st.index}>
              <strong>{word('lin.step', st.kind)}</strong>
              {st.dataset && <> — <bdi>{st.dataset}</bdi></>}
              <span className="dl-cols__muted"> · {t(`lin.role.${st.role}` as MessageKey)}</span>
            </li>
          ))}
          {s.total_steps > s.steps.length && (
            <div className="dl-cols__muted">{t('lin.otherSteps', { n: s.total_steps - s.steps.length })}</div>
          )}
        </ol>
      )
      case 'formula': return (<>
        {t(s.kind === 'measure' ? 'lin.measure' : 'lin.calculated')} <code dir="ltr">{s.expression}</code>
      </>)
      case 'checks': return s.checks.map((c, i) => (
        <span key={i} style={{ marginInlineEnd: 8 }}>
          {word('checks.kind', c.kind)}{c.column ? '' : ` (${t('lin.wholeDataset')})`}
          <span className="dl-cols__muted"> · {t(c.severity === 'block' ? 'rules3.block' : 'rules3.warn')}{!c.enabled && ` · ${t('lin.off')}`}</span>
        </span>
      ))
    }
  }

  const steps: { title: string; body: ReactNode }[] = [
    ...data.process.map(s => ({ title: t(`lin.stage.${s.stage}` as MessageKey), body: stage(s) })),
    { title: t('lin.stage.used', { n: data.used_by.length }), body: data.used_by.length === 0
      ? <span className="dl-cols__muted">{t('lin.unused')}</span>
      : (<span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 4 }}>
          {data.used_by.slice(0, SHOW).map((u, i) => (
            <span key={i} style={{ border: '1px solid var(--border)', borderRadius: 99, padding: '1px 8px' }} title={u.where}>
              <span className="dl-cols__muted">{word('lin.kind', u.kind)}:</span> <bdi>{u.label}</bdi>
            </span>
          ))}
          {data.used_by.length > SHOW && <span className="dl-cols__muted">{t('lin.more', { n: data.used_by.length - SHOW })}</span>}
        </span>) },
  ]
  return (
    <div data-testid="column-lineage" style={{ fontSize: 12, marginTop: 8, width: '100%' }}>
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{t('lin.title', { col: name })}</div>
      <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 6 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ display: 'grid', gridTemplateColumns: '22px 1fr', gap: 6 }}>
            <span aria-hidden style={{ width: 20, height: 20, borderRadius: 99, background: 'var(--surface2)',
              border: '1px solid var(--border)', display: 'grid', placeItems: 'center', fontSize: 11 }}>{i + 1}</span>
            <div><div style={{ fontWeight: 600 }}>{s.title}</div><div>{s.body}</div></div>
          </li>
        ))}
      </ol>
    </div>
  )
}
