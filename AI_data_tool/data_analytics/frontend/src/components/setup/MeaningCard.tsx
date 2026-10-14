/**
 * "How to read this database" (docs/meaning-map/PLAN.md).
 *
 * A count says nothing until it stands beside what it is counted against:
 * the biggest group has the most of everything. This card says, in plain
 * sentences, what the app measured on the database -- what is counted
 * against what, what became of a row, which numbers add up and which are
 * averaged -- because every later step reads its numbers this way. A person
 * who knows better says "Not right" and it is never used again; the kind of
 * each number can be changed under "Show details". Built once and kept.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { BookOpenCheck, ChevronDown, RefreshCw, Sparkles } from 'lucide-react'
import { useT, type MessageKey } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { useAlwaysShowDetails } from '../../lib/detailsPreference'
import { setupApi, type SetupMeaning } from '../../services/api'

const POLL_MS = 4000
const POLL_LIMIT = 45

export default function MeaningCard({ sourceId, canEdit }: { sourceId: number; canEdit: boolean }) {
  const t = useT()
  const { language } = useDirection()
  const [always] = useAlwaysShowDetails()
  const [open, setOpen] = useState<boolean | null>(null)
  const [data, setData] = useState<SetupMeaning | null>(null)
  const [ticks, setTicks] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const polls = useRef(0)
  const panelId = useId()
  const shown = open ?? always

  const load = useCallback(async () => {
    try { setData(await setupApi.meaning(sourceId, language)); setTicks(n => n + 1) }
    catch { /* optional: the step works without it */ }
  }, [sourceId, language])
  useEffect(() => { polls.current = 0; load() }, [load])

  const waiting = !!data && (data.pending || !data.built)
  useEffect(() => {
    if (!waiting || polls.current >= POLL_LIMIT) return
    const id = window.setTimeout(() => { polls.current += 1; load() }, POLL_MS)
    return () => window.clearTimeout(id)
  }, [waiting, ticks, load])

  async function edit(body: Parameters<typeof setupApi.editMeaning>[1], key: string) {
    setBusy(key)
    try { setData(await setupApi.editMeaning(sourceId, body, language)) }
    catch { toast.error(t('setup.m.editFailed')) } finally { setBusy(null) }
  }

  async function again() {
    polls.current = 0
    try { setData(await setupApi.refreshMeaning(sourceId, language)) } catch { toast.error(t('setup.m.editFailed')) }
  }

  if (!data) return null
  const facts = data.lines.filter(l => l.kind !== 'numbers')
  const numbers = data.lines.filter(l => l.kind === 'numbers')
  if (!waiting && data.lines.length === 0 && data.rejected.length === 0) return null

  return (
    <section className="card setup-card setup-meaning" aria-labelledby="setup-meaning">
      <div className="setup-overview__head">
        <h2 id="setup-meaning" className="setup-section__title">
          <BookOpenCheck size={15} aria-hidden="true" /> {t('setup.m.title')}
        </h2>
        {!waiting && canEdit && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={again} title={t('setup.m.againHint')}>
            <RefreshCw size={13} aria-hidden="true" /> {t('setup.m.again')}
          </button>
        )}
      </div>
      <p className="setup-section__sub">{t('setup.m.sub')}</p>
      <div aria-live="polite">
        {waiting && <p className="setup-ai setup-ai--pending"><Sparkles size={13} aria-hidden="true" /> {t('setup.m.building')}</p>}
        {!waiting && data.failed && <p className="setup-ai">{t('setup.m.failed')}</p>}
      </div>
      <ul className="setup-meaning__lines">
        {facts.map(l => (
          <li key={`${l.kind}:${l.subject}`}>
            <span>{l.text}</span>
            {canEdit && (
              <button type="button" className="btn btn-ghost btn-sm" disabled={!!busy}
                aria-label={`${t('setup.m.notRight')}: ${l.text}`}
                onClick={() => edit({ kind: l.kind, subject: l.subject, status: 'rejected' }, l.subject)}>
                {t('setup.m.notRight')}
              </button>
            )}
          </li>
        ))}
        {numbers.map(l => <li key={l.subject}><span>{l.text}</span></li>)}
      </ul>
      {(data.numbers.length > 0 || data.rejected.length > 0) && (
        <>
          <button type="button" className="plain-summary__toggle" aria-expanded={shown} aria-controls={panelId}
            onClick={() => setOpen(!shown)}>
            <ChevronDown size={14} aria-hidden="true"
              className={shown ? 'plain-summary__chevron plain-summary__chevron--open' : 'plain-summary__chevron'} />
            {shown ? t('plain.hideDetails') : t('plain.showDetails')}
          </button>
          {shown && (
            <div id={panelId} className="setup-meaning__details">
              {data.numbers.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.m.numbers')}</p>
                  <p className="setup-section__sub">{t('setup.m.numbersSub', { n: data.min_base })}</p>
                  <ul className="setup-meaning__numbers">
                    {data.numbers.filter(n => n.kind !== 'code').map(n => (
                      <li key={n.subject}>
                        <span><strong>{n.column.replace(/_/g, ' ')}</strong>{' '}
                          <span className="setup-section__sub">{n.table}{n.unit ? ` · ${n.unit}` : ''}</span></span>
                        <select value={n.kind} disabled={!canEdit || !!busy}
                          aria-label={t('setup.m.kindOf', { name: n.column })}
                          onChange={e => edit({ kind: 'number', subject: n.subject, number_kind: e.target.value }, n.subject)}>
                          {data.kinds.map(k => <option key={k} value={k}>{t(`setup.m.kind.${k}` as MessageKey)}</option>)}
                        </select>
                        <select value={n.direction} disabled={!canEdit || !!busy}
                          aria-label={t('setup.m.directionOf', { name: n.column })}
                          onChange={e => edit({ kind: 'number', subject: n.subject, direction: e.target.value }, n.subject)}>
                          <option value="higher_better">{t('setup.m.dir.better')}</option>
                          <option value="higher_worse">{t('setup.m.dir.worse')}</option>
                          <option value="neither">{t('setup.m.dir.neither')}</option>
                        </select>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {data.rejected.length > 0 && (
                <>
                  <p className="setup-split__title">{t('setup.m.rejected')}</p>
                  <ul className="setup-meaning__numbers">
                    {data.rejected.map(r => (
                      <li key={`${r.kind}:${r.subject}`}>
                        <span>{r.subject.replace('>', ' → ').replace(/_/g, ' ')}</span>
                        {canEdit && (
                          <button type="button" className="btn btn-sm" disabled={!!busy}
                            onClick={() => edit({ kind: r.kind, subject: r.subject, status: 'active' }, r.subject)}>
                            {t('setup.m.useAgain')}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}
