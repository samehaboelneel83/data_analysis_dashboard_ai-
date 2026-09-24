import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { datasetsApi, insightsApi } from '../services/api'
import type { Dataset } from '../services/api'
import { useListFilter } from '../components/ui/ListFilter'
import EmptyState from '../components/ui/EmptyState'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import FindingChart from '../components/insights/FindingChart'
import { Database } from 'lucide-react'
import { useT } from '../i18n'

/**
 * Pick a dataset, see what stands out in it.
 *
 * This was a grid of six cards linking into DatasetDetail's sections, with the
 * scan preview added later on top. The cards are gone: the preview answers the
 * question people actually came with ("is there anything in this data?"), and
 * six links into a page you can reach from the rail were six ways of saying
 * "go and look somewhere else".
 *
 * What remains is the preview and the dataset it runs on. Every analysis
 * capability still lives where it always did -- as a section or tab of
 * /datasets/:id -- and "View full scan →" is this page's way through to it.
 */

/**
 * The interest score below which a finding is not worth showing here.
 *
 * The scan already ranks -- six deterministic detectors, each scoring 0-1,
 * sorted and capped at 12 (services/insights.py). What the preview did NOT do
 * was ask whether the top three were any GOOD: it sliced the first three
 * whatever they scored, so a 0.05 finding earned a place purely by being third
 * on a quiet dataset.
 *
 * 0.3 rather than something higher: the detectors already multiply a weak
 * signal by 0.4, so this clears that class without touching the merely
 * moderate. The full scan keeps everything -- this governs the PREVIEW, which
 * is a claim that these are worth your attention.
 */
const MIN_PREVIEW_SCORE = 0.3

export default function InsightsHub() {
  const t = useT()
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [loading, setLoading] = useState(true)
  // A failed load is this page's whole content going missing -- a persistent,
  // retry-capable banner, not a message that would sit there with no way out.
  const [loadError, setLoadError] = useState<unknown>(null)
  const [selected, setSelected] = useState<number | null>(null)

  const load = () => {
    setLoadError(null)
    return datasetsApi.list()
      .then(ds => {
        setDatasets(ds)
        // The API's own order is not a recency guarantee, and there is no
        // "last opened" signal anywhere in the app (Home.tsx's own Recents
        // falls back to created_at for the identical reason) -- this is the
        // one honest default available without inventing new backend state.
        // A user landing on the hub almost always wants to know something
        // about the dataset they were just working with, not dataset #1.
        if (ds.length > 0) {
          const mostRecent = [...ds].sort((a, b) =>
            new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime())[0]
          setSelected(mostRecent.id)
        }
      })
      .catch(setLoadError)
  }
  useEffect(() => { load().finally(() => setLoading(false)) }, [])

  const { filtered, input, noMatches } = useListFilter(
    datasets, d => [d.name], 'Search datasets…')

  const current = datasets.find(d => d.id === selected) ?? null
  const isDirectQuery = current?.mode === 'directquery'

  // The inline "top insights" preview: fires the moment a dataset is
  // selected (auto or manual), so seeing whether there is anything worth
  // looking at never requires clicking into the Insight scan card first.
  // runShared, not run: DatasetDetail's own #insights section may fire the
  // identical scan moments later if the author clicks through, and sharing
  // the in-flight request is the whole reason that variant exists.
  interface ScanResult {
    narrative: string
    findings: { kind: string; title: string; detail: string; score: number; columns: string[] }[]
  }
  const [scan, setScan] = useState<ScanResult | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState<unknown>(null)

  const runScan = () => {
    if (selected == null || isDirectQuery) return
    setScan(null)
    setScanError(null)
    setScanLoading(true)
    insightsApi.runShared(selected)
      .then(r => setScan(r as ScanResult))
      .catch(setScanError)
      .finally(() => setScanLoading(false))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(runScan, [selected, isDirectQuery])

  return (
    <div style={{ padding: 24, maxWidth: 1000 }}>
      <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{t('nav.insights')}</h1>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16 }}>
        {t('insights.subtitle')}
      </p>

      {loading && <LoadingState label={t('common.loading')} />}

      {!loading && loadError != null && (
        <LoadError what="datasets" error={loadError}
          onRetry={() => { setLoading(true); load().finally(() => setLoading(false)) }} />
      )}

      {!loading && loadError == null && datasets.length === 0 && (
        <EmptyState icon={Database} title={t('insights.empty')} />
      )}

      {!loading && loadError == null && datasets.length > 0 && (
        <>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <label htmlFor="insights-hub-dataset" style={{ fontSize: 12, color: 'var(--muted)' }}>{t('insights.dataset')}</label>
            <select id="insights-hub-dataset" value={selected ?? ''}
              onChange={e => setSelected(Number(e.target.value))}
              style={{ fontSize: 12, padding: '6px 8px', background: 'var(--surface2)',
                border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', minWidth: 240 }}>
              {(noMatches ? datasets : filtered).map(d => (
                <option key={d.id} value={d.id}>
                  {d.name}{d.mode === 'directquery' ? ' · live' : ''}
                </option>
              ))}
            </select>
            {input}
          </div>

          {isDirectQuery && current && (
            <div style={{ marginBottom: 16, padding: 14, background: 'var(--surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius, 8px)' }}>
              <p style={{ fontSize: 13, margin: 0 }}>
                {t('insights.live')}
              </p>
              <Link to={`/datasets/${current.id}`} style={{ fontSize: 12, display: 'inline-block', marginTop: 8 }}>
                {t('insights.openDataset')}
              </Link>
            </div>
          )}

          {!isDirectQuery && scanLoading && (
            <div style={{ marginBottom: 16 }}><LoadingState label="Scanning for insights…" /></div>
          )}

          {!isDirectQuery && scanError != null && (
            <div style={{ marginBottom: 16 }}>
              <LoadError what="insights" error={scanError} onRetry={runScan} />
            </div>
          )}

          {!isDirectQuery && !scanLoading && scanError == null && scan
            && (scan.narrative || scan.findings.length > 0) && (() => {
            // Filtered for the PREVIEW only. The panel itself still renders
            // whenever the scan returned anything, so "View full scan →"
            // survives even when nothing clears the bar -- otherwise a quiet
            // dataset would lose its only route into the full results.
            const strong = scan.findings.filter(f => (f.score ?? 0) >= MIN_PREVIEW_SCORE)
            return (
            <div style={{ marginBottom: 16, padding: 14, background: 'var(--surface)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius, 8px)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: scan.narrative || strong.length ? 8 : 0 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>
                  Top insights
                </span>
                <Link to={`/datasets/${selected}#insights`} style={{ fontSize: 12 }}>View full scan →</Link>
              </div>
              {/* The narrative earns its place by CONNECTING findings. With
                  exactly one, it restates the bullet directly beneath it --
                  live, the paragraph and the bullet said the same sentence
                  about the same outlying row. Two or more, and it is the only
                  thing saying how they relate. */}
              {scan.narrative && strong.length !== 1 && (
                <p style={{ fontSize: 13, marginBottom: strong.length ? 8 : 0 }}>{scan.narrative}</p>
              )}
              {strong.length > 0 && (
                <ul style={{ margin: 0, paddingInlineStart: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {/* Top 3 -- the backend already returns findings sorted by score. */}
                  {strong.slice(0, 3).map((f, i) => (
                    <li key={i} style={{ fontSize: 12 }}>
                      <strong>{f.title}</strong>
                      {f.detail && <span style={{ color: 'var(--muted)' }}> — {f.detail}</span>}
                      {current && (
                        <FindingChart datasetId={current.id} finding={f}
                          columnTypes={Object.fromEntries(current.columns.map(c => [c.name, c.dtype ?? '']))} />
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            )
          })()}

        </>
      )}
    </div>
  )
}
