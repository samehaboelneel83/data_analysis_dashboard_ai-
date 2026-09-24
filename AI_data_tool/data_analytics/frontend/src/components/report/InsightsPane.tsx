import { useState } from 'react'
import toast from 'react-hot-toast'
import { findingKey, insightsApi, pinsApi, suggestApi } from '../../services/api'
import IconLabel from '../ui/IconLabel'
import { RefreshCw, Sparkles, Pin } from 'lucide-react'
import type { Suggestion } from './SuggestionsPane'

interface Finding {
  kind: string; score: number; title: string; detail: string; columns: string[]
  novelty?: 'new' | 'changed' | 'unchanged'
  p_value?: number | null; p_adjusted?: number | null; significant?: boolean | null
  evidence?: { test: string; n: number; effect: string } | null
}

/**
 * The insights engine inside the builder, made actionable: every finding can
 * land on the page — as a text widget carrying its sentence, or as the chart
 * that shows it (category+measure → bar, measure pair → scatter, single
 * measure → histogram). An insight you can only read is a dead end; one that
 * becomes a widget is the start of a report.
 */
export default function InsightsPane({ datasetId, columnTypes, onAdd, reportId, onComposed }: {
  datasetId: number | null
  columnTypes: Record<string, string>          // column -> dtype
  onAdd: (s: Suggestion) => void
  /** Enables "Build a report" — composing writes a page, so it needs the report. */
  reportId?: number
  /** Called after a page is written, so the builder can reload and show it. */
  onComposed?: (pageId: number) => void
}) {
  const [result, setResult] = useState<{ findings: Finding[]; narrative: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [composing, setComposing] = useState(false)
  const [error, setError] = useState('')

  // Adding findings one at a time is the slow path this removes: the engine
  // already ranked them and already knows which chart shows each, so the whole
  // page can be built in one call.
  const compose = async () => {
    if (!reportId || composing) return
    setComposing(true)
    try {
      const out = await suggestApi.autoCompose(reportId)
      toast.success(`Built a page with ${out.widget_count} widgets`)
      onComposed?.(out.page_id)
    } catch (e: unknown) {
      toast.error((e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'Could not build a report')
    } finally {
      setComposing(false)
    }
  }

  const run = () => {
    if (!datasetId) return
    setBusy(true); setError('')
    insightsApi.run(datasetId).then(setResult)
      .catch(e => setError(e?.response?.data?.detail || 'Could not generate insights'))
      .finally(() => setBusy(false))
  }

  const chartFor = (f: Finding): Suggestion | null => {
    const cats = f.columns.filter(c => columnTypes[c] === 'categorical')
    const nums = f.columns.filter(c => columnTypes[c] === 'numeric')
    if (cats.length && nums.length) {
      return { widget_type: 'bar', title: f.title, reason: '',
        config: { dimension: cats[0], measure: nums[0], aggregation: 'sum' } }
    }
    if (nums.length >= 2) {
      // shape_series semantics: dimension = x numeric, measure = y, averaged.
      // The previous x_column/y_column keys exist in no shaper — every
      // correlation "Chart it" rendered empty until now.
      return { widget_type: 'scatter', title: f.title, reason: '',
        config: { dimension: nums[0], measure: nums[1], aggregation: 'avg',
                  limit: 250, sort: 'asc', sort_by: 'name' } }
    }
    if (nums.length === 1) {
      return { widget_type: 'histogram', title: f.title, reason: '',
        config: { measure: nums[0], bins: 20 } }
    }
    return null
  }

  return (
    <div style={{ padding: 12, overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
          Insights
        </span>
        <button className="btn" style={{ fontSize: 10, marginInlineStart: 'auto' }} disabled={busy || !datasetId} title={!datasetId ? 'Attach a dataset to this report first' : undefined} onClick={run}>
          {busy ? 'Scanning…'
          : result ? <IconLabel icon={RefreshCw}>Re-scan</IconLabel>
          : <IconLabel icon={Sparkles}>Generate</IconLabel>}
        </button>
      </div>
      {!datasetId && <p style={{ fontSize: 11, color: 'var(--muted)' }}>Attach a dataset to this report first.</p>}
      {error && <p role="alert" style={{ fontSize: 11, color: 'var(--danger)' }}>{error}</p>}
      {result && (
        <>
          <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10 }}>{result.narrative}</p>
          {reportId != null && result.findings.length > 0 && (
            <button className="btn btn-primary" disabled={composing}
              onClick={() => void compose()}
              style={{ fontSize: 10, width: '100%', marginBottom: 10 }}>
              {composing ? 'Building…' : '<IconLabel icon={Sparkles}>Build a report from these</IconLabel>'}
            </button>
          )}
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {result.findings.map((f, i) => {
              const chart = chartFor(f)
              return (
                <li key={i} data-testid={`rb-insight-${f.kind}`}
                  style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '8px 10px' }}>
                  <div style={{ fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.06em',
                    color: f.kind === 'data_quality' ? '#e6a03c' : 'var(--accent)', marginBottom: 3,
                    display: 'flex', gap: 6, alignItems: 'center' }}>
                    {f.kind.replace('_', ' ')}
                    {/* What changed since the last scan. Only new/changed get a
                        badge: labelling `unchanged` too would give every card a
                        chip and the badge would stop meaning anything. */}
                    {(f.novelty === 'new' || f.novelty === 'changed') && (
                      <span style={{ background: 'var(--accent)', color: 'var(--surface)',
                        borderRadius: 3, padding: '0 4px', fontSize: 8 }}>
                        {f.novelty === 'new' ? 'NEW' : 'CHANGED'}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{f.title}</div>
                  <div style={{ fontSize: 10, color: 'var(--muted)', margin: '2px 0 6px' }}>{f.detail}</div>
                  {f.evidence && f.p_value != null && (
                    // The evidence chip: a tested claim carries its test, population
                    // and effect -- and the adjusted p when several were run.
                    <div data-testid="insight-evidence" style={{ fontSize: 9.5, color: 'var(--muted)', margin: '-2px 0 6px',
                      display: 'inline-block', padding: '1px 7px', borderRadius: 99,
                      border: `1px solid ${f.significant ? 'var(--accent)' : 'var(--border)'}` }}>
                      {f.evidence.test} · {f.evidence.effect} · n = {f.evidence.n.toLocaleString()} ·{' '}
                      {f.p_value < 0.001 ? 'p < 0.001' : `p = ${f.p_value.toPrecision(2)}`}
                      {f.p_adjusted != null ? ` (adjusted ${f.p_adjusted < 0.001 ? '< 0.001' : f.p_adjusted.toPrecision(2)})` : ''}
                      {f.significant ? '' : ' · not significant'}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn" style={{ fontSize: 10 }}
                      onClick={() => onAdd({ widget_type: 'text', title: '', reason: '',
                        config: { content: `${f.title}. ${f.detail}` } })}>
                      + Add as text
                    </button>
                    {datasetId != null && (
                      <button className="btn" style={{ fontSize: 10 }}
                        aria-label={`Pin finding: ${f.title}`}
                        title="Pin to your dashboard — re-evaluated live on every visit"
                        onClick={() => void pinsApi
                          .create({ dataset_id: datasetId, finding_key: findingKey(f) })
                          .then(r => toast.success(r.already_pinned
                            ? 'Already on your dashboard' : 'Pinned to your dashboard'))
                          .catch(() => toast.error('Could not pin this finding'))}>
                        <IconLabel icon={Pin} size={11}>Pin</IconLabel>
                      </button>
                    )}
                    {chart && (
                      <button className="btn btn-primary" style={{ fontSize: 10 }} onClick={() => onAdd(chart)}>
                        + Chart it
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </>
      )}
    </div>
  )
}
