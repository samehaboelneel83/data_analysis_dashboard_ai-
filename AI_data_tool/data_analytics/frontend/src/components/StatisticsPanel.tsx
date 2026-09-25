import { useEffect, useMemo, useState } from 'react'
import {
  analysisCatalogueApi, type AnalysisSpec, type DatasetColumn,
} from '../services/api'
import LoadError from './ui/LoadError'
import { FlaskConical } from 'lucide-react'
import { useT } from '../i18n'
import { ResultFor } from './analysis/analysisResults'

/**
 * One screen for every runnable analysis, driven by the registry.
 *
 * Eight statistical analyses shipped with working endpoints and no frontend
 * entry point at all — half the registry was reachable only by the agent, which
 * can mention them but not invoke them.
 *
 * They got ONE screen rather than eight because two facts made that correct:
 * every endpoint took a flat body of column names, and every one returned the
 * same `TestResult` envelope. Eight bespoke forms would be eight copies of the
 * same logic drifting apart.
 *
 * But both facts were true only of the statistical tests, and this screen was
 * built to their shape: it filtered the catalogue to `result_kind ===
 * 'statistical_test'`, posted through a hand-written name→slug map, rendered
 * one envelope, and treated every non-enum, non-array parameter as a column
 * name. So it stayed at eight while eleven other analyses — two of them
 * (`explain_response`, `goal_seek`) finished and already shipping behind their
 * own dialog — stayed unreachable from here.
 *
 * What it takes instead: the catalogue says which entries are `runnable`; one
 * endpoint runs any of them; the schema says which parameters are columns; and
 * a `result_kind` this file has never heard of falls through to a renderer that
 * shows the numbers anyway. A newly registered analysis now appears here with
 * no change to this file — which is what a registry was for.
 */

type Value = string | string[] | number
type Params = Record<string, Value>
type Prop = AnalysisSpec['params_schema']['properties'][string]

/**
 * A registry property, narrowed to the shapes a form can render.
 *
 * `format: "column"` is what separates a column reference from free text or a
 * number to type. Without it, everything that was not an enum or an array
 * became a dropdown of the dataset's columns — right for eight analyses, and
 * wrong the moment a ninth wanted a target VALUE rather than a column.
 */
function fieldKind(prop: Prop) {
  if (prop.enum) return 'enum' as const
  const types = Array.isArray(prop.type) ? prop.type : [prop.type]
  if (types.includes('array')) return 'multi' as const
  if (prop.format === 'column') return 'column' as const
  if (types.includes('number') || types.includes('integer')) return 'number' as const
  return 'text' as const
}

/** Not `!!v`: a required target of zero is an ordinary goal, and a truthiness
 *  check would leave Run disabled with the field visibly filled in. */
function answered(v: Value | undefined) {
  if (Array.isArray(v)) return v.length > 0
  return v !== undefined && v !== ''
}

export default function StatisticsPanel({ datasetId, columns, mode }: {
  datasetId: number
  columns: DatasetColumn[]
  /** The dataset's mode. These analyses read the whole frame, so they are
   *  import-only — and a picker that cannot run anything must say so rather
   *  than refuse after the parameters are filled in. */
  mode?: string
}) {
  const t = useT()
  const [specs, setSpecs] = useState<AnalysisSpec[] | null>(null)
  const [specError, setSpecError] = useState<unknown>(null)
  const [chosen, setChosen] = useState<string>('')
  const [params, setParams] = useState<Params>({})
  const [ran, setRan] =
    useState<{ kind: string; result: unknown; params: Params } | null>(null)
  const [runError, setRunError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const loadSpecs = () => {
    setSpecError(null)
    analysisCatalogueApi.registry()
      // `runnable`, not a result kind: an entry with no handler behind it is
      // real and documented, but choosing it could only ever produce a 400.
      .then(all => setSpecs(all.filter(a => a.runnable)))
      .catch(e => setSpecError(e ?? new Error('failed')))
  }
  useEffect(loadSpecs, [])

  const spec = useMemo(
    () => specs?.find(s => s.name === chosen) ?? null, [specs, chosen])

  // Reset between analyses: carrying `predictors` into a test that has no such
  // field would post a parameter the endpoint rejects.
  const pick = (name: string) => {
    setChosen(name); setParams({}); setRan(null); setRunError(null)
  }

  const required = spec?.params_schema.required ?? []
  const complete = required.every(k => answered(params[k]))

  const run = async () => {
    if (!spec || !complete) return
    setRunning(true); setRunError(null); setRan(null)
    // A blank optional field is one the user did not answer: posting `""`
    // against a number schema is a 400, and posting nothing is what the
    // catalogue means by optional.
    const body = Object.fromEntries(
      Object.entries(params).filter(([, v]) => answered(v)))
    try {
      const res = await analysisCatalogueApi.run(datasetId, spec.name, body)
      setRan({ kind: res.result_kind, result: res.result, params })
    } catch (e: unknown) {
      // The backend's own messages name the actual problem ("Only 3 event(s);
      // Cox regression needs about 10 per predictor"), which is far more
      // useful than anything generic.
      setRunError((e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? 'The analysis could not be run')
    } finally {
      setRunning(false)
    }
  }

  if (specError) {
    return <LoadError what="the analysis catalogue" error={specError} onRetry={loadSpecs} />
  }
  if (!specs) return <p style={{ color: 'var(--muted)' }}>Loading…</p>

  return (
    <>
    {mode === 'directquery' && (
      // Said before the form rather than after the button, and it is an
      // ACCOUNT rather than a refusal: these analyses read the source live,
      // bounded, and the result will say how much of it it saw. A person
      // choosing between two datasets deserves to know one was measured over
      // every row and the other over a sample.
      <p data-testid="directquery-analysis-notice"
        style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 12px', maxWidth: 680,
          border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
        This dataset is queried at its source. Analyses read it live, up to a
        row limit, and each result says how many rows it measured — so a figure
        drawn from a sample is never presented as if it came from everything.
      </p>
    )}
    <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', flexWrap: 'wrap' }}>
      {/* ── Picker ─────────────────────────────────────────────────────── */}
      <div style={{ flex: '0 1 260px', minWidth: 220 }}>
        <label htmlFor="stat-analysis" style={{
          display: 'block', fontSize: 12, fontWeight: 600,
          color: 'var(--muted)', marginBottom: 4,
        }}>
          Analysis
        </label>
        <select id="stat-analysis" value={chosen} onChange={e => pick(e.target.value)}
          style={{ width: '100%' }}>
          <option value="">— choose —</option>
          {specs.map(s => (
            <option key={s.name} value={s.name}>{s.name.replace(/_/g, ' ')}</option>
          ))}
        </select>

        {/* The registry's descriptions are already written as questions a user
            would ask, so they are used verbatim rather than paraphrased. */}
        {spec && (
          <p style={{ fontSize: 12, color: 'var(--muted)', marginTop: 8 }}>
            {spec.description}
          </p>
        )}

        {spec && Object.entries(spec.params_schema.properties).map(([key, prop]) => {
          const kind = fieldKind(prop)
          const label = key.replace(/_/g, ' ')
          const isRequired = required.includes(key)
          return (
            <div key={key} style={{ marginTop: 10 }}>
              <label htmlFor={`stat-${key}`} style={{
                display: 'block', fontSize: 12, color: 'var(--muted)', marginBottom: 2,
              }}>
                {label}{isRequired ? '' : ' (optional)'}
              </label>

              {kind === 'enum' ? (
                <select id={`stat-${key}`} value={(params[key] as string) ?? ''}
                  onChange={e => setParams(p => ({ ...p, [key]: e.target.value }))}
                  style={{ width: '100%' }}>
                  {prop.enum!.map(v => <option key={v} value={v}>{v}</option>)}
                </select>
              ) : kind === 'multi' ? (
                <div id={`stat-${key}`} style={{
                  maxHeight: 120, overflowY: 'auto', display: 'flex',
                  flexDirection: 'column', gap: 3, background: 'var(--bg)',
                  padding: 6, borderRadius: 4,
                }}>
                  {columns.map(c => {
                    const list = (params[key] as string[]) ?? []
                    return (
                      <label key={c.name} style={{
                        display: 'flex', alignItems: 'center', gap: 6,
                        fontSize: 12, cursor: 'pointer',
                      }}>
                        <input type="checkbox" checked={list.includes(c.name)}
                          aria-label={`${label} ${c.name}`}
                          onChange={() => setParams(p => {
                            const cur = (p[key] as string[]) ?? []
                            return {
                              ...p,
                              [key]: cur.includes(c.name)
                                ? cur.filter(x => x !== c.name)
                                : [...cur, c.name],
                            }
                          })} />
                        <span>{c.name}</span>
                      </label>
                    )
                  })}
                </div>
              ) : kind === 'column' ? (
                <select id={`stat-${key}`} value={(params[key] as string) ?? ''}
                  onChange={e => setParams(p => ({ ...p, [key]: e.target.value }))}
                  style={{ width: '100%' }}>
                  <option value="">— choose —</option>
                  {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
                </select>
              ) : kind === 'number' ? (
                // Held as a NUMBER in state, not the input's string: the schema
                // types it as a number, and posting "500" would leave the
                // request depending on the server to coerce it.
                <input id={`stat-${key}`} type="number" style={{ width: '100%' }}
                  value={params[key] === undefined ? '' : String(params[key])}
                  onChange={e => setParams(p => ({
                    ...p,
                    [key]: e.target.value === '' ? '' : Number(e.target.value),
                  }))} />
              ) : (
                <input id={`stat-${key}`} type="text" style={{ width: '100%' }}
                  value={(params[key] as string) ?? ''}
                  onChange={e => setParams(p => ({ ...p, [key]: e.target.value }))} />
              )}

              {prop.description && (
                <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>
                  {prop.description}
                </div>
              )}
            </div>
          )
        })}

        {spec && (
          <button className="btn btn-primary btn-sm" disabled={!complete || running} title={!complete ? 'Choose every required column first' : undefined}
            onClick={() => void run()} style={{ marginTop: 12, width: '100%' }}>
            {running ? 'Running…' : 'Run'}
          </button>
        )}
      </div>

      {/* ── Result ─────────────────────────────────────────────────────── */}
      <div style={{ flex: '1 1 320px', minWidth: 0 }}>
        {/* The first thing on the tab, so it has to say what the tab is FOR
            and offer a way in -- a sentence beside an empty select was a
            dead end nobody read. The chips are the same list as the select. */}
        {!spec && (
          <div className="card dl-analysis-intro">
            <FlaskConical size={28} color="var(--muted)" aria-hidden />
            <p className="dl-analysis-intro__title">{t('analysis.introTitle')}</p>
            <p className="dl-analysis-intro__text">
              {t('analysis.introBody')}
            </p>
            <div className="dl-analysis-intro__chips">
              {specs.slice(0, 8).map(sp => (
                <button key={sp.name} type="button" className="btn btn-sm" onClick={() => pick(sp.name)}
                  title={sp.description}>
                  {sp.name.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>
        )}
        {runError && (
          <div role="alert" className="card" style={{ padding: 16 }}>
            <p style={{ margin: 0, fontSize: 13 }}>{runError}</p>
          </div>
        )}
        {ran && <ResultFor kind={ran.kind} result={ran.result} params={ran.params} />}
      </div>
    </div>
    </>
  )
}
