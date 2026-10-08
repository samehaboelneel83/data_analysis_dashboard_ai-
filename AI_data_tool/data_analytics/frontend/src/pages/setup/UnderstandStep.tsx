/**
 * Guided setup, step 1: Understand (docs/guided-setup/PLAN.md, 1b).
 *
 * "What does this database hold, and where do I start?" The facts the sync
 * measured show at once; the AI's plain words fill in when written (the page
 * asks again while `ai.pending`). Most useful tables first; plumbing folded
 * away but never hidden. The full catalog stays one click away on the
 * review page (decision D6: plain first, details never removed).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { ChevronDown, Pencil, RefreshCw, Sparkles, Table2 } from 'lucide-react'
import { useT, type TranslateFn } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { metadataApi, setupApi, type SetupSample, type SetupSummary, type SetupTable } from '../../services/api'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/** How often to ask again while the AI is writing, and for how long at most. */
const POLL_MS = 4000
const POLL_LIMIT = 45

const num = (n: number | null | undefined) => localDigits((n ?? 0).toLocaleString())

/** "Feb 2024" / "فبراير 2024": month names in the reader's language, digits
 *  Western unless the reader chose Arabic-Indic (localDigits decides). */
function month(iso: string | null, language: string): string {
  if (!iso) return ''
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  if (Number.isNaN(d.getTime())) return iso
  const locale = language === 'ar' ? 'ar-u-nu-latn' : undefined
  return localDigits(d.toLocaleDateString(locale, { month: 'short', year: 'numeric' }))
}

function period(t: TranslateFn, language: string, from: string | null, to: string | null,
                exact: boolean): string | null {
  if (!from) return null
  const range = t('setup.u.period', { from: month(from, language), to: month(to, language) })
  return exact ? range : `${range} ${t('setup.u.approx')}`
}

export default function UnderstandStep({ sourceId, onNext }: { sourceId: number; onNext: () => void }) {
  const t = useT()
  const { language } = useDirection()
  const [data, setData] = useState<SetupSummary | null>(null)
  const [error, setError] = useState<unknown>(null)
  const polls = useRef(0)
  // Set when the page stops asking while the AI is still writing: a model
  // that is down can take many minutes to fail over, and "still reading"
  // must not stay on screen forever.
  const [gaveUp, setGaveUp] = useState(false)
  // Bumped on every answer, so polling continues even when an answer is
  // identical to the last one (React skips a render for the same object).
  const [answers, setAnswers] = useState(0)

  const load = useCallback(async (fresh = false) => {
    try {
      setError(null)
      const s = fresh ? await setupApi.refreshSummary(sourceId, language) : await setupApi.summary(sourceId, language)
      setData(s)
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language])

  useEffect(() => { polls.current = 0; setGaveUp(false); load() }, [load])

  // Ask again while the AI is still writing, or the sync still running.
  const waiting = data?.status === 'syncing' || !!data?.ai?.pending || !!data?.ranges_pending
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  if (error) return <LoadError what={t('setup.u.what')} error={error} onRetry={() => load()} />
  if (!data) return <LoadingState label={t('setup.u.loading')} />

  if (data.status !== 'ready') {
    const key = data.status === 'syncing' ? 'setup.u.syncing' : data.status === 'failed' ? 'setup.u.syncFailed' : 'setup.u.empty'
    return (
      <section className="card setup-card" aria-live="polite">
        <p className="setup-card__lead">{t(key)}</p>
        {data.status !== 'syncing' && (
          <Link className="btn btn-sm" to={`/connections/${sourceId}/review`}>{t('setup.u.openReview')}</Link>
        )}
      </section>
    )
  }

  const tables = data.tables ?? []
  const main = tables.filter(x => x.group === 'main')
  const lists = tables.filter(x => x.group === 'supporting')
  const system = tables.filter(x => x.group === 'technical')
  const totals = data.totals!

  return (
    <div className="setup-understand">
      <Overview data={data} sourceId={sourceId} slow={gaveUp} onChanged={() => load()}
        onAskAgain={() => { polls.current = 0; setGaveUp(false); load(true) }}
        onCheckAgain={() => { polls.current = 0; setGaveUp(false); load() }} />

      <section aria-labelledby="setup-main" className="setup-section">
        <h2 id="setup-main" className="setup-section__title">{t('setup.u.whereToStart')}</h2>
        <p className="setup-section__sub">
          {t('setup.u.whereToStartSub')}
        </p>
        <ol className="setup-tables">
          {main.map((x, i) => (
            <TableCard key={x.id} table={x} rank={i + 1} sourceId={sourceId} canEdit={data.can_edit}
              onChanged={() => load()} />
          ))}
        </ol>
        {main.length === 0 && <p className="setup-section__sub">{t('setup.u.noMain')}</p>}
      </section>

      {lists.length > 0 && (
        <Group title={t('setup.u.lists', { n: num(lists.length) })} hint={t('setup.u.listsHint')}
          open={main.length === 0}>
          <ul className="setup-tables">
            {lists.map(x => <TableCard key={x.id} table={x} sourceId={sourceId} canEdit={data.can_edit} onChanged={() => load()} />)}
          </ul>
        </Group>
      )}

      {system.length > 0 && (
        <Group title={t('setup.u.system', { n: num(system.length) })} hint={t('setup.u.systemHint')}>
          <ul className="setup-tables">
            {system.map(x => <TableCard key={x.id} table={x} sourceId={sourceId} canEdit={data.can_edit} onChanged={() => load()} />)}
          </ul>
        </Group>
      )}

      {!!data.questions?.length && (
        <section aria-labelledby="setup-questions" className="card setup-card">
          <h2 id="setup-questions" className="setup-section__title">{t('setup.u.questions')}</h2>
          <ul className="setup-questions">
            {data.questions.map(q => <li key={q}>{q}</li>)}
          </ul>
        </section>
      )}

      <div className="setup-footer">
        <Link to={`/connections/${sourceId}/review`} className="setup-details-link">
          <ChevronDown size={14} aria-hidden="true" /> {t('setup.u.details')}
        </Link>
        <button type="button" className="btn btn-primary" onClick={onNext}>
          {t('setup.next', { step: t('setup.step.data') })}
        </button>
      </div>
      <p className="setup-footnote">
        {t('setup.u.factsFootnote', { tables: num(totals.tables), rows: num(totals.rows) })}
      </p>
    </div>
  )
}

function Overview({ data, sourceId, slow, onChanged, onAskAgain, onCheckAgain }: {
  data: SetupSummary; sourceId: number; slow: boolean
  onChanged: () => void; onAskAgain: () => void; onCheckAgain: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const [editing, setEditing] = useState(false)
  const [turningOn, setTurningOn] = useState(false)
  const totals = data.totals!
  const ai = data.ai!
  const when = period(t, language, totals.date_from, totals.date_to, totals.dates_exact)
  const fallback = t('setup.u.factsSentence', {
    name: data.source.name, tables: num(totals.tables), rows: num(totals.rows),
  })

  async function turnOn() {
    setTurningOn(true)
    try {
      await metadataApi.settings(sourceId, { allow_llm_sampling: true })
      onAskAgain()
    } catch { toast.error(t('setup.u.turnOnFailed')) } finally { setTurningOn(false) }
  }

  return (
    <section className="card setup-card setup-overview" aria-labelledby="setup-overview">
      <div className="setup-overview__head">
        <h2 id="setup-overview" className="setup-section__title">{t('setup.u.holds')}</h2>
        {data.overview_source && !editing && (
          <span className={`setup-badge setup-badge--${data.overview_source}`}>
            {data.overview_source === 'you' ? t('setup.u.byYou') : <><Sparkles size={11} aria-hidden="true" /> {t('setup.u.byAi')}</>}
          </span>
        )}
        {/* Asked once and kept; asking again is the reader's choice. */}
        {data.source.allow_ai && !ai.pending && !editing && (ai.used || !ai.reason) && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onAskAgain}
            title={t('setup.u.askAgainHint')}>
            <RefreshCw size={13} aria-hidden="true" /> {t('setup.u.askAgain')}
          </button>
        )}
        {data.can_edit && !editing && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(true)}
            aria-label={t('setup.u.editOverview')}>
            <Pencil size={13} aria-hidden="true" /> {t('setup.u.edit')}
          </button>
        )}
      </div>

      {editing ? (
        <DescriptionEditor initial={data.overview_source === 'you' ? data.overview ?? '' : ''}
          placeholder={data.overview ?? fallback}
          label={t('setup.u.editOverview')}
          onCancel={() => setEditing(false)}
          onSave={async text => {
            await setupApi.editOverview(sourceId, text)
            setEditing(false)
            onChanged()
          }} />
      ) : (
        <p className="setup-card__lead">{data.overview ?? fallback}</p>
      )}

      <ul className="setup-facts" aria-label={t('setup.u.factsLabel')}>
        <li>{t('setup.u.tablesN', { n: num(totals.tables) })}</li>
        {totals.views > 0 && <li>{t('setup.u.viewsN', { n: num(totals.views) })}</li>}
        <li>{t('setup.u.rowsN', { n: num(totals.rows) })}</li>
        {when && <li>{when}</li>}
      </ul>

      <div aria-live="polite">
        {ai.pending && !slow && (
          <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.u.aiWriting')}</p>
        )}
        {ai.pending && slow && (
          <p className="setup-ai">
            {t('setup.u.aiSlow')}{' '}
            <button type="button" className="btn btn-sm" onClick={onCheckAgain}>
              <RefreshCw size={12} aria-hidden="true" /> {t('setup.u.checkAgain')}
            </button>
          </p>
        )}
        {ai.reason === 'off' && (
          <p className="setup-ai">
            {t('setup.u.aiOff')}{' '}
            {data.can_edit && (
              <button type="button" className="btn btn-sm" disabled={turningOn} onClick={turnOn}>
                {t('setup.u.turnOn')}
              </button>
            )}
          </p>
        )}
        {ai.used && (ai.reason === 'failed' || ai.reason === 'unavailable') && (
          <p className="setup-ai">{t('setup.u.aiRefreshFailed')}</p>
        )}
        {!ai.used && (ai.reason === 'failed' || ai.reason === 'unavailable') && (
          <p className="setup-ai">
            {t('setup.u.aiDown')}{' '}
            <button type="button" className="btn btn-sm" onClick={onAskAgain}>
              <RefreshCw size={12} aria-hidden="true" /> {t('setup.u.askAgain')}
            </button>
          </p>
        )}
      </div>
    </section>
  )
}

function TableCard({ table: x, rank, sourceId, canEdit, onChanged }: {
  table: SetupTable; rank?: number; sourceId: number; canEdit: boolean; onChanged: () => void
}) {
  const t = useT()
  const { language } = useDirection()
  const sep = language === 'ar' ? '، ' : ', '
  const [sample, setSample] = useState<SetupSample | null>(null)
  const [showSample, setShowSample] = useState(false)
  const [loadingSample, setLoadingSample] = useState(false)
  const [editing, setEditing] = useState(false)
  const when = period(t, language, x.date_from, x.date_to, x.dates_exact)

  async function toggleSample() {
    const next = !showSample
    setShowSample(next)
    if (next && !sample) {
      setLoadingSample(true)
      try { setSample(await setupApi.sample(sourceId, x.id)) }
      catch { setSample({ columns: [], rows: [], restricted: false, error: 'unreachable' }) }
      finally { setLoadingSample(false) }
    }
  }

  return (
    <li className="card setup-table">
      <div className="setup-table__head">
        {rank !== undefined && <span className="setup-table__rank" aria-hidden="true">{localDigits(String(rank))}</span>}
        <div className="setup-table__names">
          <h3 className="setup-table__title">{x.title ?? x.name}</h3>
          {x.title && <code className="setup-table__name">{x.name}</code>}
        </div>
        {x.canonical && <span className="setup-badge setup-badge--you">{t('setup.u.canonical')}</span>}
      </div>

      {editing ? (
        <DescriptionEditor initial={x.what_source === 'you' ? x.what ?? '' : ''} placeholder={x.what ?? ''}
          label={t('setup.u.editTable', { name: x.title ?? x.name })}
          onCancel={() => setEditing(false)}
          onSave={async text => {
            await setupApi.editTable(sourceId, x.id, text)
            setEditing(false)
            onChanged()
          }} />
      ) : (
        <>
          {x.what && <p className="setup-table__what">{x.what}</p>}
          {x.useful_for && <p className="setup-table__good"><strong>{t('setup.u.goodFor')}</strong> {x.useful_for}</p>}
        </>
      )}

      <ul className="setup-facts">
        <li>{t('setup.u.rowsN', { n: num(x.rows) })}</li>
        {x.measures.length > 0 && <li>{t('setup.u.numbers', { cols: x.measures.slice(0, 4).join(sep) })}</li>}
        {when && <li>{when}</li>}
        {x.related.length > 0 && <li>{t('setup.u.linksTo', { tables: x.related.join(sep) })}</li>}
      </ul>

      <div className="setup-table__actions">
        <button type="button" className="btn btn-ghost btn-sm" aria-expanded={showSample} onClick={toggleSample}>
          <Table2 size={13} aria-hidden="true" /> {showSample ? t('setup.u.hideSample') : t('setup.u.showSample')}
        </button>
        {canEdit && !editing && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(true)}>
            <Pencil size={13} aria-hidden="true" /> {t('setup.u.edit')}
          </button>
        )}
      </div>

      {showSample && (
        <div className="setup-sample">
          {loadingSample ? <p className="setup-section__sub">{t('setup.u.loadingSample')}</p>
            : <SampleTable sample={sample} />}
        </div>
      )}
    </li>
  )
}

function SampleTable({ sample }: { sample: SetupSample | null }) {
  const t = useT()
  if (!sample || sample.error === 'unreachable') return <p className="setup-section__sub">{t('setup.u.sampleFailed')}</p>
  if (sample.error === 'restricted' || !sample.rows.length) {
    return <p className="setup-section__sub">{sample.restricted ? t('setup.u.sampleRestricted') : t('setup.u.sampleEmpty')}</p>
  }
  return (
    <>
      <div className="setup-sample__scroll">
        <table>
          <thead><tr>{sample.columns.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
          <tbody>
            {sample.rows.map((r, i) => (
              <tr key={i}>{sample.columns.map(c => (
                <td key={c}>{r[c] === null || r[c] === undefined || r[c] === '' ? <em>{t('setup.u.emptyValue')}</em> : String(r[c])}</td>
              ))}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {sample.restricted && <p className="setup-section__sub">{t('setup.u.sampleRestricted')}</p>}
    </>
  )
}

function DescriptionEditor({ initial, placeholder, label, onSave, onCancel }: {
  initial: string; placeholder: string; label: string
  onSave: (text: string) => Promise<void>; onCancel: () => void
}) {
  const t = useT()
  const [text, setText] = useState(initial)
  const [saving, setSaving] = useState(false)
  return (
    <form className="setup-editor" onSubmit={async e => {
      e.preventDefault()
      setSaving(true)
      try { await onSave(text) } catch { toast.error(t('setup.u.saveFailed')) } finally { setSaving(false) }
    }}>
      <textarea aria-label={label} value={text} placeholder={placeholder} rows={3}
        onChange={e => setText(e.target.value)} autoFocus />
      <p className="setup-section__sub">{t('setup.u.editHint')}</p>
      <div className="setup-editor__actions">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>{t('common.cancel')}</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>{t('setup.u.save')}</button>
      </div>
    </form>
  )
}

function Group({ title, hint, open = false, children }: {
  title: string; hint: string; open?: boolean; children: React.ReactNode
}) {
  return (
    <details className="setup-group" open={open}>
      <summary><span className="setup-section__title">{title}</span> <span className="setup-section__sub">{hint}</span></summary>
      {children}
    </details>
  )
}
