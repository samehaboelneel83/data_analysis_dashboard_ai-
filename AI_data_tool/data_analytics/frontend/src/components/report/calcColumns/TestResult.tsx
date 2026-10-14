/**
 * A calculated column's Test result, plain first: what the whole column looks
 * like (how many rows got each label; lowest / average / highest), or what is
 * wrong with the formula in plain words, with the raw error behind
 * "Show details".
 */
import { useState } from 'react'
import type { CalcPreview } from '../../../services/api'
import { useT, type MessageKey } from '../../../i18n'

const fmt = (v: number | null) => v == null ? '—'
  : Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toLocaleString(undefined, { maximumFractionDigits: 2 })

export default function TestResult({ preview }: { preview: CalcPreview }) {
  const t = useT()
  const [details, setDetails] = useState(false)
  const ok = preview.ok
  const s = preview.summary
  return (
    <div data-testid="calc-test-result" style={{ padding: '8px 12px', borderRadius: 6, fontSize: 12,
      background: ok ? 'rgba(52,211,153,.08)' : 'rgba(248,113,113,.08)',
      border: `1px solid ${ok ? '#34d399' : '#f87171'}` }}>
      {ok ? (<>
        {s?.kind === 'labels' && (<>
          <div style={{ color: '#34d399', fontWeight: 700, marginBottom: 4 }}>
            ✓ {t('pg.panelsA.res.labels', { n: s.distinct, rows: s.rows.toLocaleString() })}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {s.top.map(([label, n]) => (
              <span key={label} style={{ border: '1px solid var(--border)', borderRadius: 99, padding: '1px 8px' }}>
                <bdi>{label}</bdi> · {n.toLocaleString()}
              </span>
            ))}
          </div>
          {s.distinct > s.top.length && <div style={{ color: 'var(--muted)', marginTop: 3 }}>{t('pg.panelsA.res.more', { n: s.distinct - s.top.length })}</div>}
          {s.distinct === 1 && <div style={{ color: '#f59e0b', marginTop: 3 }}>⚠ {t('pg.panelsA.res.oneLabel')}</div>}
        </>)}
        {s?.kind === 'number' && (
          <div style={{ color: '#34d399', fontWeight: 700 }}>
            ✓ {t('pg.panelsA.res.numbers', { min: fmt(s.min), mean: fmt(s.mean), max: fmt(s.max) })}
          </div>
        )}
        {!s && <div style={{ color: '#34d399', fontWeight: 700 }}>✓ {preview.dtype}</div>}
        {s && s.empty > 0 && (
          <div style={{ color: 'var(--muted)', marginTop: 3 }}>{t('pg.panelsA.res.empty', { n: s.empty.toLocaleString(), rows: s.rows.toLocaleString() })}</div>
        )}
        {s?.kind === 'number' && s.infinite > 0 && (
          <div style={{ color: '#f59e0b', marginTop: 3 }}>⚠ {t('pg.panelsA.res.infinite', { n: s.infinite.toLocaleString() })}</div>
        )}
        <div style={{ color: 'var(--muted)', marginTop: 4 }}>
          {t('pg.panelsA.res.sample')} <bdi dir="ltr">{preview.sample?.slice(0, 6).map(v => v == null ? '—' : typeof v === 'number' ? fmt(v) : String(v)).join(', ')}</bdi>
        </div>
      </>) : (<>
        <div style={{ color: '#f87171' }}>✗ {problemText(t, preview)}</div>
        {preview.error && (
          <button type="button" onClick={() => setDetails(d => !d)}
            style={{ border: 'none', background: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: 11, padding: 0, marginTop: 4, textDecoration: 'underline' }}>
            {details ? t('pg.panelsA.res.hideDetails') : t('pg.panelsA.res.showDetails')}
          </button>
        )}
        {details && <pre dir="ltr" style={{ fontSize: 11, whiteSpace: 'pre-wrap', margin: '4px 0 0', color: 'var(--muted)' }}>{preview.error}</pre>}
      </>)}
    </div>
  )
}

/** The problem in the reader's language; the raw error when it is not one we know. */
export function problemText(t: ReturnType<typeof useT>, preview: CalcPreview): string {
  const p = preview.problem
  if (!p || p.code === 'other') return preview.error ?? t('pg.panelsA.previewFailed')
  const key = (p.code === 'unknown_name' && p.suggest ? 'unknown_name_suggest' : p.code)
  const params = Object.fromEntries(Object.entries(p).map(([k, v]) => [k, String(v)]))
  const k = `pg.panelsA.prob.${key}` as MessageKey
  const out = t(k, params)
  return out === k ? (preview.error ?? '') : out
}
