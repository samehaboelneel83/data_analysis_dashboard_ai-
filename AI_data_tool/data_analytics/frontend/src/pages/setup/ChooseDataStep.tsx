/**
 * Guided setup, step 2: Choose data (docs/guided-setup/PLAN.md, 2a-2e).
 *
 * About you (optional, asked once, reused by every later step) -> the AI
 * proposes 2-3 datasets, each saying what it Includes, Leaves out and Why ->
 * the reader ticks one or more (or datasets already made from this
 * connection), changes a proposal by asking in plain words, or builds one
 * by hand -> the chosen datasets are created and the setup moves on.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import toast from 'react-hot-toast'
import { MessageSquare, RefreshCw, Sparkles, Table2, Wrench } from 'lucide-react'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import { jobsApi, setupApi, type SetupBrief, type SetupDatasetsStep, type SetupProposal } from '../../services/api'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

const POLL_MS = 4000
const POLL_LIMIT = 60
const num = (n: number | null | undefined) => localDigits((n ?? 0).toLocaleString())

type Creating = { name: string; state: 'running' | 'done' | 'failed'; error?: string | null; datasetId?: number | null }

export default function ChooseDataStep({ sourceId, onDone }: {
  sourceId: number
  /** Called with every dataset id the setup now uses, once they exist. */
  onDone: (datasetIds: number[]) => Promise<void>
}) {
  const t = useT()
  const { language } = useDirection()
  const [data, setData] = useState<SetupDatasetsStep | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [answers, setAnswers] = useState(0)
  const [editingBrief, setEditingBrief] = useState(false)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [names, setNames] = useState<Record<string, string>>({})
  const [adopted, setAdopted] = useState<Set<number>>(new Set())
  const [mode, setMode] = useState<'import' | 'directquery'>('import')
  const [creating, setCreating] = useState<Creating[] | null>(null)
  const [gaveUp, setGaveUp] = useState(false)
  const polls = useRef(0)

  const load = useCallback(async () => {
    try {
      setError(null)
      const d = await setupApi.datasets(sourceId, language)
      setData(d)
      setAnswers(n => n + 1)
    } catch (e) { setError(e) }
  }, [sourceId, language])
  useEffect(() => { polls.current = 0; load() }, [load])

  // The datasets already chosen in an earlier visit stay ticked.
  useEffect(() => {
    if (data?.chosen?.length) setAdopted(prev => prev.size ? prev : new Set(data.chosen))
  }, [data?.chosen])

  const waiting = !!data && (data.proposals.pending || data.proposals.items.some(p => p.refining))
  useEffect(() => {
    if (!waiting) return
    if (polls.current >= POLL_LIMIT) { setGaveUp(true); return }
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, answers, load])

  async function suggest(brief?: SetupBrief) {
    try {
      if (brief) await setupApi.update(sourceId, { brief })
      setEditingBrief(false)
      polls.current = 0
      setGaveUp(false)
      await setupApi.suggestDatasets(sourceId, language)
      await load()
    } catch { toast.error(t('setup.d.suggestFailed')) }
  }

  async function refine(p: SetupProposal, message: string) {
    try {
      polls.current = 0
      setGaveUp(false)
      await setupApi.refineDataset(sourceId, p.id, message, language)
      await load()
    } catch { toast.error(t('setup.d.refineFailed')) }
  }

  async function create() {
    if (!data) return
    const chosen = data.proposals.items.filter(p => picked.has(p.id))
    const kept = [...adopted]
    if (!chosen.length) { await onDone(kept); return }
    setCreating(chosen.map(p => ({ name: names[p.id] ?? p.name, state: 'running' })))
    try {
      const res = await setupApi.createDatasets(sourceId, chosen.map(p => ({ id: p.id, name: names[p.id] ?? p.name })), mode)
      const results = await Promise.all(res.items.map(async (item, i): Promise<Creating> => {
        if (item.error) return { name: item.name, state: 'failed', error: item.error }
        if (item.dataset_id) return { name: item.name, state: 'done', datasetId: item.dataset_id }
        const final = await waitForJob(item.job_id!, update => setCreating(prev => prev && prev.map((c, k) => k === i ? { ...c, ...update } : c)))
        return { name: item.name, ...final }
      }))
      setCreating(results)
      const made = results.filter(r => r.state === 'done' && r.datasetId).map(r => r.datasetId!)
      if (made.length === results.length) await onDone([...kept, ...made])
      else if (made.length) toast(t('setup.d.someFailed'))
      else toast.error(t('setup.d.allFailed'))
      if (made.length && made.length < results.length) {
        // Keep what worked; the failed ones stay on screen with their reason.
        await setupApi.update(sourceId, { dataset_ids: [...kept, ...made] })
      }
    } catch (e) {
      setCreating(null)
      toast.error(t('setup.d.createFailed'))
      throw e
    }
  }

  if (error) return <LoadError what={t('setup.d.what')} error={error} onRetry={load} />
  if (!data) return <LoadingState />

  const asked = data.proposals.asked
  const showBrief = !asked || editingBrief
  const count = picked.size + adopted.size

  return (
    <div className="setup-understand">
      {showBrief ? (
        <AboutYou initial={data.brief} first={!asked}
          onSubmit={brief => suggest(brief)}
          onSkip={() => asked ? setEditingBrief(false) : suggest({})} />
      ) : (
        <section className="card setup-card" aria-labelledby="setup-brief">
          <div className="setup-overview__head">
            <h2 id="setup-brief" className="setup-section__title">{t('setup.d.aboutYou')}</h2>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditingBrief(true)}>
              {t('setup.d.changeAnswers')}
            </button>
          </div>
          <BriefSummary brief={data.brief} />
        </section>
      )}

      {asked && (
        <section className="setup-section" aria-labelledby="setup-proposals">
          <div className="setup-overview__head">
            <h2 id="setup-proposals" className="setup-section__title">{t('setup.d.proposals')}</h2>
            {!data.proposals.pending && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => suggest()}>
                <RefreshCw size={13} aria-hidden="true" /> {t('setup.d.suggestAgain')}
              </button>
            )}
          </div>
          <p className="setup-section__sub">{t('setup.d.proposalsSub')}</p>
          <div aria-live="polite">
            {data.proposals.pending && !gaveUp && (
              <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.d.thinking')}</p>
            )}
            {data.proposals.pending && gaveUp && (
              <p className="setup-ai">{t('setup.u.aiSlow')}{' '}
                <button type="button" className="btn btn-sm" onClick={() => { polls.current = 0; setGaveUp(false); load() }}>
                  {t('setup.u.checkAgain')}
                </button></p>
            )}
            {!data.proposals.pending && data.proposals.failed && data.proposals.items.some(p => p.source === 'auto') && (
              <p className="setup-ai">{data.proposals.failed === 'off' ? t('setup.d.autoOff') : t('setup.d.autoDown')}</p>
            )}
            {!data.proposals.pending && data.proposals.items.length > 0 && data.proposals.language
              && data.proposals.language !== language && (
              <p className="setup-ai">{t('setup.langHint')}</p>
            )}
            {!data.proposals.pending && !data.proposals.items.length && (
              <p className="setup-ai">{t('setup.d.none')}</p>
            )}
          </div>
          <ul className="setup-tables">
            {data.proposals.items.map(p => (
              <ProposalCard key={p.id} p={p} checked={picked.has(p.id)} canCreate={data.can_create}
                allowAi={data.allow_ai} name={names[p.id] ?? p.name}
                onName={v => setNames(n => ({ ...n, [p.id]: v }))}
                onToggle={() => setPicked(s => { const n = new Set(s); if (n.has(p.id)) n.delete(p.id); else n.add(p.id); return n })}
                onRefine={m => refine(p, m)} />
            ))}
          </ul>
        </section>
      )}

      {data.existing.length > 0 && (
        <section className="card setup-card" aria-labelledby="setup-existing">
          <h2 id="setup-existing" className="setup-section__title">{t('setup.d.existing')}</h2>
          <p className="setup-section__sub">{t('setup.d.existingSub')}</p>
          <ul className="setup-checklist">
            {data.existing.map(d => (
              <li key={d.id}>
                <label>
                  <input type="checkbox" checked={adopted.has(d.id)}
                    onChange={() => setAdopted(s => { const n = new Set(s); if (n.has(d.id)) n.delete(d.id); else n.add(d.id); return n })} />
                  <span>{d.name}</span>
                  {d.rows != null && <span className="setup-section__sub">{t('setup.u.rowsN', { n: num(d.rows) })}</span>}
                </label>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.can_create && (
        <section className="card setup-card" aria-labelledby="setup-manual">
          <h2 id="setup-manual" className="setup-section__title"><Wrench size={14} aria-hidden="true" /> {t('setup.d.manual')}</h2>
          <p className="setup-section__sub">{t('setup.d.manualSub')}</p>
          <div className="setup-table__actions">
            <Link className="btn btn-sm" to={`/connections?browse=${sourceId}`}>{t('setup.d.browse')}</Link>
            <Link className="btn btn-sm" to={`/connections?build=${sourceId}`}>{t('setup.d.builder')}</Link>
          </div>
        </section>
      )}

      {creating && (
        <section className="card setup-card" aria-live="polite" aria-labelledby="setup-creating">
          <h2 id="setup-creating" className="setup-section__title">{t('setup.d.creating')}</h2>
          <ul className="setup-checklist">
            {creating.map((c, i) => (
              <li key={i} className={`setup-job setup-job--${c.state}`}>
                <span>{c.name}</span>
                <span className="setup-section__sub">
                  {c.state === 'running' ? t('setup.d.jobRunning') : c.state === 'done' ? t('setup.d.jobDone') : `${t('setup.d.jobFailed')} ${c.error ?? ''}`}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="setup-footer">
        <span className="setup-section__sub">
          {!data.can_create && data.proposals.items.length > 0 ? t('setup.d.cannotCreate') : count ? t('setup.d.chosenN', { n: num(count) }) : t('setup.d.chosenNone')}
        </span>
        <div className="setup-table__actions">
          {picked.size > 0 && (
            <label className="setup-mode">
              <span className="setup-section__sub">{t('setup.d.mode')}</span>
              <select value={mode} onChange={e => setMode(e.target.value as 'import' | 'directquery')}>
                <option value="import">{t('setup.d.modeImport')}</option>
                <option value="directquery">{t('setup.d.modeLive')}</option>
              </select>
            </label>
          )}
          <button type="button" className="btn btn-primary" disabled={count === 0 || (!!creating && creating.some(c => c.state === 'running'))}
            onClick={() => { void create() }}>
            {picked.size > 0 ? t('setup.d.createAndNext', { n: num(picked.size) }) : t('setup.next', { step: t('setup.step.check') })}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Poll an import job until it ends. */
async function waitForJob(jobId: number, onUpdate: (u: Partial<Creating>) => void): Promise<Omit<Creating, 'name'>> {
  for (let i = 0; i < 400; i++) {
    const job = await jobsApi.get(jobId)
    if (job.state === 'succeeded') {
      const result = (job.result ?? {}) as { dataset_id?: number }
      return { state: 'done', datasetId: result.dataset_id ?? null }
    }
    if (job.state === 'failed' || job.state === 'cancelled') {
      return { state: 'failed', error: job.error ?? null }
    }
    onUpdate({ state: 'running' })
    await new Promise(r => setTimeout(r, 1500))
  }
  return { state: 'failed', error: null }
}

const BRIEF_FIELDS: { key: keyof SetupBrief; label: 'setup.d.q.work' | 'setup.d.q.focus' | 'setup.d.q.questions' | 'setup.d.q.exclude'
                     ph: 'setup.d.ph.work' | 'setup.d.ph.focus' | 'setup.d.ph.questions' | 'setup.d.ph.exclude' }[] = [
  { key: 'work', label: 'setup.d.q.work', ph: 'setup.d.ph.work' },
  { key: 'focus', label: 'setup.d.q.focus', ph: 'setup.d.ph.focus' },
  { key: 'questions', label: 'setup.d.q.questions', ph: 'setup.d.ph.questions' },
  { key: 'exclude', label: 'setup.d.q.exclude', ph: 'setup.d.ph.exclude' },
]

function AboutYou({ initial, first, onSubmit, onSkip }: {
  initial: SetupBrief; first: boolean; onSubmit: (b: SetupBrief) => void; onSkip: () => void
}) {
  const t = useT()
  const [brief, setBrief] = useState<SetupBrief>(initial)
  const [busy, setBusy] = useState(false)
  return (
    <form className="card setup-card" aria-labelledby="setup-about"
      onSubmit={async e => { e.preventDefault(); setBusy(true); try { await onSubmit(brief) } finally { setBusy(false) } }}>
      <h2 id="setup-about" className="setup-section__title">{t('setup.d.aboutYou')}</h2>
      <p className="setup-section__sub">{t('setup.d.aboutYouSub')}</p>
      <div className="setup-brief">
        {BRIEF_FIELDS.map(f => (
          <label key={f.key} className="setup-brief__field">
            <span>{t(f.label)}</span>
            <textarea rows={2} value={brief[f.key] ?? ''} placeholder={t(f.ph)} maxLength={1000}
              onChange={e => setBrief(b => ({ ...b, [f.key]: e.target.value }))} />
          </label>
        ))}
      </div>
      <div className="setup-editor__actions">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onSkip} disabled={busy}>
          {first ? t('setup.d.skip') : t('common.cancel')}
        </button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
          {first ? t('setup.d.suggest') : t('setup.d.saveAndSuggest')}
        </button>
      </div>
    </form>
  )
}

function BriefSummary({ brief }: { brief: SetupBrief }) {
  const t = useT()
  const said = BRIEF_FIELDS.filter(f => brief[f.key])
  if (!said.length) return <p className="setup-section__sub">{t('setup.d.noAnswers')}</p>
  return (
    <dl className="setup-brief-summary">
      {said.map(f => (
        <div key={f.key}><dt>{t(f.label)}</dt><dd>{brief[f.key]}</dd></div>
      ))}
    </dl>
  )
}

function ProposalCard({ p, checked, canCreate, allowAi, name, onName, onToggle, onRefine }: {
  p: SetupProposal; checked: boolean; canCreate: boolean; allowAi: boolean; name: string
  onName: (v: string) => void; onToggle: () => void; onRefine: (message: string) => void
}) {
  const t = useT()
  const [preview, setPreview] = useState(false)
  const [chat, setChat] = useState(false)
  const [sql, setSql] = useState(false)
  const [message, setMessage] = useState('')
  return (
    <li className={`card setup-table${checked ? ' is-picked' : ''}`}>
      <div className="setup-table__head">
        {canCreate && (
          <input type="checkbox" checked={checked} onChange={onToggle}
            aria-label={t('setup.d.pick', { name: p.name })} />
        )}
        <div className="setup-table__names">
          <h3 className="setup-table__title">{p.name}</h3>
          {p.source === 'ai' && <span className="setup-badge setup-badge--ai"><Sparkles size={11} aria-hidden="true" /> {t('setup.u.byAi')}</span>}
        </div>
      </div>
      {p.purpose && <p className="setup-table__what">{p.purpose}</p>}
      <div className="setup-split">
        <div>
          <h4 className="setup-split__title setup-split__title--in">{t('setup.d.includes')}</h4>
          <ul>{p.includes.map(x => <li key={x}>{x}</li>)}</ul>
        </div>
        <div>
          <h4 className="setup-split__title setup-split__title--out">{t('setup.d.leavesOut')}</h4>
          {p.leaves_out.length ? <ul>{p.leaves_out.map(x => <li key={x}>{x}</li>)}</ul>
            : <p className="setup-section__sub">{t('setup.d.nothingLeftOut')}</p>}
        </div>
      </div>
      {p.why && <p className="setup-table__good"><strong>{t('setup.d.why')}</strong> {p.why}</p>}
      <ul className="setup-facts">
        {p.test.row_count != null && <li>{t('setup.u.rowsN', { n: num(p.test.row_count) })}</li>}
        <li>{t('setup.d.columnsN', { n: num(p.test.columns.length) })}</li>
        {p.tables.length > 0 && <li>{t('setup.d.fromTables', { tables: p.tables.join(', ') })}</li>}
      </ul>
      {checked && (
        <label className="setup-brief__field">
          <span>{t('setup.d.datasetName')}</span>
          <input value={name} onChange={e => onName(e.target.value)} maxLength={120} />
        </label>
      )}
      <div className="setup-table__actions">
        <button type="button" className="btn btn-ghost btn-sm" aria-expanded={preview} onClick={() => setPreview(v => !v)}>
          <Table2 size={13} aria-hidden="true" /> {preview ? t('setup.u.hideSample') : t('setup.u.showSample')}
        </button>
        {allowAi && (
          <button type="button" className="btn btn-ghost btn-sm" aria-expanded={chat} onClick={() => setChat(v => !v)}>
            <MessageSquare size={13} aria-hidden="true" /> {t('setup.d.change')}
          </button>
        )}
        <button type="button" className="btn btn-ghost btn-sm" aria-expanded={sql} onClick={() => setSql(v => !v)}>
          {sql ? t('plain.hideDetails') : t('plain.showDetails')}
        </button>
      </div>
      {preview && (
        <div className="setup-sample">
          {p.test.rows.length ? (
            <div className="setup-sample__scroll">
              <table>
                <thead><tr>{p.test.columns.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
                <tbody>{p.test.rows.map((r, i) => (
                  <tr key={i}>{p.test.columns.map(c => (
                    <td key={c}>{r[c] === null || r[c] === undefined || r[c] === '' ? <em>{t('setup.u.emptyValue')}</em> : String(r[c])}</td>
                  ))}</tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p className="setup-section__sub">{t('setup.u.sampleEmpty')}</p>}
        </div>
      )}
      {sql && <pre className="setup-sql" dir="ltr">{p.sql}</pre>}
      {chat && (
        <div className="setup-chat">
          {p.history.length > 0 && (
            <ul className="setup-chat__log">
              {p.history.map((m, i) => <li key={i} className={`setup-chat__msg setup-chat__msg--${m.role}`}>{m.text}</li>)}
            </ul>
          )}
          {p.refining && <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.d.changing')}</p>}
          {p.refine_failed && !p.refining && (
            <p className="setup-ai">{p.refine_failed === 'unusable' ? t('setup.d.changeUnusable') : t('setup.d.changeFailed')}</p>
          )}
          <form className="setup-chat__form" onSubmit={e => {
            e.preventDefault()
            if (!message.trim()) return
            onRefine(message.trim())
            setMessage('')
          }}>
            <input value={message} onChange={e => setMessage(e.target.value)} disabled={!!p.refining}
              placeholder={t('setup.d.changePh')} aria-label={t('setup.d.changeLabel', { name: p.name })} />
            <button type="submit" className="btn btn-sm btn-primary" disabled={!!p.refining || !message.trim()}>
              {t('setup.d.send')}
            </button>
          </form>
        </div>
      )}
    </li>
  )
}
