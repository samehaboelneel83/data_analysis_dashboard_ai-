import { useEffect, useState } from 'react'
import { discoveryApi, type DatasetHealth as Health, type HealthCheck } from '../services/api'
import { useT } from '../i18n'
import { takeawayText } from '../lib/readbackText'

const MARK = { pass: '✓', warn: '!', fail: '✕' } as const
const TONE = { pass: 'var(--ok, #16a34a)', warn: 'var(--warning, #d68910)', fail: 'var(--danger, #dc2626)' } as const

/** Rows per month as plain bars: what a usual month holds, at a glance. */
function Months({ series }: { series: [string, number][] }) {
  const top = Math.max(...series.map(s => s[1]), 1)
  return (
    <div data-testid="health-volume" aria-hidden="true"
      style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 28, marginTop: 4 }}>
      {series.map(([label, n]) => (
        <div key={label} title={`${label}: ${n.toLocaleString()}`}
          style={{ flex: '1 1 0', maxWidth: 10, height: `${Math.max(n / top * 100, 3)}%`,
            background: 'color-mix(in srgb, var(--muted) 55%, transparent)', borderRadius: 1 }} />
      ))}
    </div>
  )
}

function Check({ c }: { c: HealthCheck }) {
  const t = useT()
  // The server's sentence in the reader's language (rb.health.* in the catalogue).
  const title = takeawayText(t, { takeaway: c.title, takeaway_i18n: c.title_i18n as never }) ?? c.title
  const sentence = takeawayText(t, { takeaway: c.sentence, takeaway_i18n: c.sentence_i18n as never }) ?? c.sentence
  const skipped = c.figures.checked === false
  const series = Array.isArray(c.figures.series) ? c.figures.series : []
  return (
    <li data-testid="health-check" data-status={skipped ? 'skipped' : c.status}
      style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: 8, padding: '6px 0', borderTop: '1px solid var(--border)' }}>
      <span aria-hidden="true" style={{ fontWeight: 700, color: skipped ? 'var(--muted)' : TONE[c.status] }}>
        {skipped ? '–' : MARK[c.status]}
      </span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)' }}>{sentence}</div>
        {c.id === 'volume' && series.length > 1 && <Months series={series} />}
      </div>
    </li>
  )
}

/**
 * A dataset's health: what was checked, what passed, what is worth a look
 * and what failed -- each with one sentence (server:
 * services/discovery/health.py). Read off the stored profile; no AI.
 * Problems first; the checks that passed are behind "Show details".
 */
export default function HealthChecks({ datasetId }: { datasetId: number }) {
  const [h, setH] = useState<Health | null>(null)
  const [open, setOpen] = useState(false)
  const t = useT()
  useEffect(() => {
    let live = true
    setH(null)
    discoveryApi.health(datasetId).then(r => { if (live) setH(r) }).catch(() => { if (live) setH(null) })
    return () => { live = false }
  }, [datasetId])
  if (!h) return null
  const problems = h.checks.filter(c => c.status !== 'pass' && c.figures.checked !== false)
  const rest = h.checks.filter(c => !problems.includes(c))
  const s = h.summary
  return (
    <section className="card" data-testid="dataset-health" style={{ padding: 16, marginTop: 12 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>{t('hchk.title')}</h3>
        <span data-testid="health-summary" style={{ fontSize: 12, color: 'var(--muted)' }}>
          <b style={{ color: TONE.pass }}>{s.pass}</b> {t('hchk.pass')} ·{' '}
          <b style={{ color: s.warn ? TONE.warn : 'var(--muted)' }}>{s.warn}</b> {t('hchk.warn')} ·{' '}
          <b style={{ color: s.fail ? TONE.fail : 'var(--muted)' }}>{s.fail}</b> {t('hchk.fail')}
        </span>
      </div>
      {problems.length === 0
        ? <p style={{ fontSize: 12.5, margin: '8px 0 0' }}>{t('hchk.allGood')}</p>
        : <ul style={{ listStyle: 'none', margin: '8px 0 0', padding: 0 }}>{problems.map(c => <Check key={c.id} c={c} />)}</ul>}
      {rest.length > 0 && (
        <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
          style={{ font: 'inherit', fontSize: 12, marginTop: 8, padding: 0, background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
          {open ? t('hchk.hide') : t('hchk.show', { n: rest.length })}
        </button>
      )}
      {open && <ul style={{ listStyle: 'none', margin: '6px 0 0', padding: 0 }}>{rest.map(c => <Check key={c.id} c={c} />)}</ul>}
      {(h.restricted || s.sampled) && (
        <p style={{ fontSize: 11, color: 'var(--muted)', margin: '8px 0 0' }}>
          {h.restricted ? t('hchk.restricted') : t('hchk.sampled')}
        </p>
      )}
    </section>
  )
}
