import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { usePrompt } from '../ui/PromptDialog'
import { AlertTriangle, Code2, Copy, Database, Download, RotateCcw, Sparkles, ThumbsDown, ThumbsUp, User } from 'lucide-react'
import { agentApi, dataSourcesApi } from '../../services/api'
import type { AgentAnswer, AgentMessage, AgentPresentation, AgentResult, AnswerEvidence } from '../../services/api'
import Pending from './Pending'
import ResultView, { downloadCsv, focusFor, type EvidenceFocus } from './ResultView'
import AnalysisResult, { isAnalysisResult } from './AnalysisResult'
import ChoiceOptions, { isChoices } from './ChoiceOptions'
import DashboardProposals, { type DashboardProposalsPresentation }
  from './DashboardProposals'
import { useT, translate, type TranslateFn } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { majorityDir } from '../../lib/autoDir'
import { renderTextWithLinks } from '../../lib/inlineMarkup'
import { aiLimitMessage } from '../../lib/aiLimit'
import Composer from './Composer'
import AnswerText from './AnswerText'
import AddToDashboard from './AddToDashboard'
import SaveAsRule, { looksLikeDefinition } from './SaveAsRule'
import { answerToWidget, type WidgetDraft } from './answerWidget'
import '../../pages/ask/ask.css'

/**
 * Ask the data a question in plain language.
 *
 * Who owns the conversation depends on how the pane is mounted:
 *
 * - `conversationId` given as a NUMBER: the page owns the thread. The pane
 *   loads its stored messages -- answers, clarifications, failures, and the
 *   result grids behind the answers -- and continues it.
 * - `conversationId` given as NULL: the page wants a fresh thread. The pane
 *   creates one on the first send and reports it via `onConversationCreated`,
 *   so the page's list can show it.
 * - `conversationId` OMITTED (the report-builder mount): the pane resumes
 *   the newest conversation targeting the same data, and now LOADS its
 *   messages on open -- it always appended to that thread silently, which
 *   made every visit look like a blank slate over a growing history. With
 *   no matching thread, one is created on the first send.
 *
 * Three answer shapes come back from the same endpoint and must never be
 * blurred together: `ok` is an answer, `needs_clarification` is a question
 * back (rendered as a question, not dressed up as an answer), and `failed`
 * is an honest error -- never presented as if it were a result. An answer
 * now carries its rows: the grid is drawn from them, the SQL is shown from
 * them, and "as a bar chart" re-draws them without another query.
 */
export interface ChatPaneProps {
  dataSourceId?: number
  datasetIds?: number[]
  conversationId?: number | null
  onConversationCreated?: (conv: { id: number; title: string }) => void
  /** Starter questions shown on an empty thread, and offered again as
   *  rephrasings when a question fails. Optional: the builder mount has none. */
  suggestions?: string[]
  /** The dataset's column names, when the pane asks about ONE dataset --
   *  what "Add to dashboard" maps an answer back onto. */
  datasetColumns?: string[]
  /** Mounted inside a dashboard: "Add to this page" puts the answer straight
   *  onto the page being edited, instead of asking which dashboard. */
  onAddToPage?: (draft: WidgetDraft, title: string) => unknown
}

type MessageKind = 'answer' | 'clarify' | 'error' | 'limit'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  text: string
  kind?: MessageKind
  runId?: number
  results?: AgentResult[]
  sql?: string[]
  presentation?: AgentPresentation | null
  contextObjects?: string[] | null
  /** The run's intent, kept for one reason: `chat` is a reply with no query
   *  behind it, and the SQL controls must not be offered on one. */
  intent?: string | null
  /** The answer's numbers, traced to the rows by the server (E11). */
  evidence?: AnswerEvidence | null
}

/** Same target as this pane's: same data source id, or the same set of
 * dataset ids compared order-insensitively. */
function matchesTarget(
  conv: { data_source_id: number | null; dataset_ids: number[] | null },
  dataSourceId: number | undefined,
  datasetIds: number[] | undefined,
): boolean {
  if (dataSourceId != null) return conv.data_source_id === dataSourceId
  const wanted = [...(datasetIds ?? [])].sort((a, b) => a - b)
  const got = [...(conv.dataset_ids ?? [])].sort((a, b) => a - b)
  return wanted.length > 0 && wanted.length === got.length &&
    wanted.every((id, i) => id === got[i])
}

let nextId = 1

function kindOf(status: AgentAnswer['status'] | undefined): MessageKind {
  return status === 'ok' ? 'answer' : status === 'needs_clarification' ? 'clarify' : status === 'failed' ? 'error' : 'answer'
}

function fromAnswer(result: AgentAnswer): ChatMessage {
  const kind = kindOf(result.status)
  return {
    id: nextId++, role: 'assistant', kind, runId: result.run_id,
    text: kind === 'error' ? (result.error ?? 'Something went wrong.') : (result.answer ?? ''),
    results: result.results ?? [], sql: result.sql ?? [],
    presentation: result.presentation ?? null, contextObjects: result.context_objects ?? null,
    intent: result.intent ?? null, evidence: result.evidence ?? null,
  }
}

function fromStored(m: AgentMessage): ChatMessage {
  if (m.role === 'user') return { id: nextId++, role: 'user', text: m.content }
  const run = m.run
  const kind = kindOf(run?.status)
  return {
    id: nextId++, role: 'assistant', kind, runId: run?.id,
    text: kind === 'error' ? (run?.error ?? m.content) : m.content,
    results: run?.results ?? [], sql: run?.sql ?? [],
    presentation: run?.presentation ?? null, contextObjects: run?.context_objects ?? null,
    intent: run?.intent ?? null, evidence: run?.evidence ?? null,
  }
}

/** `presentation` is a union carried on the run: a format hint for results, a
 *  set of dashboard proposals, or an analysis the agent ran instead of writing
 *  SQL. One narrow check per kind keeps the branch below readable. */
function isProposals(p: unknown): p is DashboardProposalsPresentation {
  return !!p && (p as { kind?: string }).kind === 'dashboard_proposals'
}

export default function ChatPane({ dataSourceId, datasetIds, conversationId, onConversationCreated,
  suggestions, datasetColumns, onAddToPage }: ChatPaneProps) {
  const t = useT()
  const { direction } = useDirection()
  // Model and server text: markup rendered, laid out by its majority script.
  const modelText = (text: string) => renderTextWithLinks(text, { httpsOnly: true })
  const owned = conversationId !== undefined
  const [convId, setConvId] = useState<number | null>(conversationId ?? null)
  // What the pane itself created or last loaded -- so a parent echoing the
  // id we just reported does not trigger a reload of the thread we hold.
  // Starts null so a thread given at mount IS loaded.
  const knownId = useRef<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  /** The question currently in flight, so the pending bubble can name the
   *  work. "Designing dashboards · 2m 14s" reads very differently from a
   *  greyed-out button when the wait is four minutes long. */
  const [pending, setPending] = useState<string | null>(null)
  // Cache of fetched SQL per run id, for runs stored before the answer
  // carried its SQL -- "Show SQL" fetches once per message, not per click.
  const [sqlByRun, setSqlByRun] = useState<Record<number, string[]>>({})
  const [openRun, setOpenRun] = useState<Set<number>>(new Set())
  const [sqlLoading, setSqlLoading] = useState<Set<number>>(new Set())
  // What the user already clicked, per run -- so a 👍/👎 shows as pressed
  // and a second click on the same one still upserts (the backend already
  // handles the dedupe; this just keeps the button state honest).
  // The number of an answer whose source the reader asked to see (E11).
  const [evidenceFocus, setEvidenceFocus] = useState<{ msg: number; at: EvidenceFocus } | null>(null)
  const [feedbackByRun, setFeedbackByRun] = useState<Record<number, 'up' | 'down'>>({})

  // Legacy mount: resume the newest matching thread WITH its history. The
  // ref stops a slow load from clobbering a conversation the user has
  // already started typing into; a failed load costs only the preload --
  // send() resolves the conversation for itself.
  const interacted = useRef(false)
  useEffect(() => {
    if (owned) return
    let alive = true
    agentApi.listConversations()
      .then(async existing => {
        if (!alive || interacted.current) return
        const match = existing.find(c => matchesTarget(c, dataSourceId, datasetIds))
        if (!match) return
        setConvId(match.id)
        const stored = await agentApi.messages(match.id)
        if (alive && !interacted.current) setMessages(stored.map(fromStored))
      })
      .catch(() => {})
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Stale loads are discarded by SEQUENCE, not by an unmount flag: under
  // React StrictMode (dev) every effect runs twice, and an unmount-flag
  // guard here left the pane on "Loading conversation…" forever -- the
  // first run's cleanup disowned its own response, and the second run
  // early-returned because knownId already matched. Seen live, in the
  // browser; jsdom tests only caught it once one rendered under StrictMode.
  const loadSeq = useRef(0)
  useEffect(() => {
    if (!owned) return
    if (conversationId === knownId.current) return
    knownId.current = conversationId ?? null
    setConvId(conversationId ?? null)
    setMessages([])
    setLoadError(null)
    if (conversationId == null) { setLoading(false); return }
    const seq = ++loadSeq.current
    setLoading(true)
    agentApi.messages(conversationId)
      .then(stored => { if (seq === loadSeq.current) setMessages(stored.map(fromStored)) })
      .catch(() => { if (seq === loadSeq.current) setLoadError('Could not load this conversation.') })
      .finally(() => { if (seq === loadSeq.current) setLoading(false) })
  }, [owned, conversationId])

  const target = dataSourceId != null ? { dataSourceId } : { datasetIds }

  // Keep the newest turn in view as questions and answers arrive.
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end', behavior: 'smooth' })
  }, [messages.length, pending])

  /** `choice` is an option the agent offered and the person clicked. It is
   *  sent exactly as typed would be -- same endpoint, same history, same
   *  resolver -- so a button is never a second way of asking. */
  const send = async (choice?: string) => {
    const question = (choice ?? input).trim()
    if (!question || busy) return
    interacted.current = true
    if (choice === undefined) setInput('')
    setBusy(true)
    setPending(question)
    setMessages(m => [...m, { id: nextId++, role: 'user', text: question }])

    try {
      let cid = convId
      if (cid == null) {
        if (owned) {
          const conv = await agentApi.createConversation(target)
          cid = conv.id
          knownId.current = cid
          setConvId(cid)
          // The server retitles a default-titled thread from its first
          // question during /ask; report that title now so the page's list
          // does not show "New conversation" until the next reload.
          onConversationCreated?.({
            id: conv.id,
            title: conv.title === 'New conversation' ? question.slice(0, 80) : conv.title,
          })
        } else {
          const existing = await agentApi.listConversations()
          const match = existing.find(c => matchesTarget(c, dataSourceId, datasetIds))
          cid = match ? match.id : (await agentApi.createConversation(target)).id
          setConvId(cid)
        }
      }
      const result = await agentApi.ask(cid, question)
      setMessages(m => [...m, fromAnswer(result)])
    } catch (e) {
      // A limit is not a failure to answer: no "rephrase" advice, and the
      // reason in the open rather than under Technical details (E11).
      const limit = aiLimitMessage(e, t)
      setMessages(m => [...m, limit
        ? { id: nextId++, role: 'assistant', kind: 'limit', text: limit }
        : { id: nextId++, role: 'assistant', kind: 'error', text: 'Could not reach the agent. Try again.' }])
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const rate = async (runId: number, rating: 'up' | 'down') => {
    setFeedbackByRun(m => ({ ...m, [runId]: rating })) // optimistic
    try {
      if (convId != null) await agentApi.feedback(convId, { runId, rating })
    } catch {
      // The click already reflects intent; a failed write just means it
      // wasn't persisted -- not worth interrupting the chat over.
    }
  }

  /** The SQL behind a message: carried on the answer when the server sent
   *  it, fetched once otherwise (runs stored before answers carried SQL). */
  /** The run currently being saved as a dataset, so its button can say so
   *  and cannot be pressed twice. */
  const [saving, setSaving] = useState<number | null>(null)
  const prompt = usePrompt()

  const sqlFor = async (msg: ChatMessage): Promise<string[]> => {
    if (msg.sql && msg.sql.length) return msg.sql
    if (msg.runId == null) return []
    if (sqlByRun[msg.runId]) return sqlByRun[msg.runId]
    setSqlLoading(s => new Set(s).add(msg.runId!))
    try {
      const detail = await agentApi.runDetail(msg.runId)
      const sql = detail.steps.map(s => s.sql).filter((s): s is string => !!s)
      setSqlByRun(m => ({ ...m, [msg.runId!]: sql }))
      return sql
    } finally {
      setSqlLoading(s => { const next = new Set(s); next.delete(msg.runId!); return next })
    }
  }

  const toggleSql = async (msg: ChatMessage) => {
    const runId = msg.runId!
    if (openRun.has(runId)) {
      setOpenRun(s => { const next = new Set(s); next.delete(runId); return next })
      return
    }
    setOpenRun(s => new Set(s).add(runId))
    await sqlFor(msg)
  }

  const downloadFile = async (runId: number, format: 'xlsx' | 'pdf') => {
    try {
      await agentApi.downloadRunFile(runId, format)
    } catch {
      toast.error('Could not download the file')
    }
  }

  /** Keep this answer as a dataset.
   *
   *  The chat could read anything and create nothing: a person who asked "show
   *  me last quarter by region", got it, and wanted to build on it had to copy
   *  the SQL out and re-run it on the Connections page by hand.
   *
   *  Composed from calls the person already has permission to make -- the same
   *  `import` the AI dashboard proposals use -- so the agent keeps its property
   *  of never creating anything on its own; a person pressed a button.
   *
   *  Connection scope only: a dataset-mode answer runs over frames in DuckDB
   *  with no source to import FROM, so the button is not offered there rather
   *  than being offered and failing.
   */
  const saveAsDataset = async (msg: ChatMessage) => {
    if (dataSourceId == null) return
    const sql = await sqlFor(msg)
    if (!sql.length) { toast.error('There is no query behind this answer'); return }
    // The LAST step: a multi-step run's earlier queries are intermediate
    // working, and the final one is the answer the person is looking at.
    const statement = sql[sql.length - 1]
    const name = await prompt({
      title: 'Name this dataset', label: 'Dataset name',
      defaultValue: 'Ask AI result', confirmLabel: 'Save dataset',
    })
    if (name === null) return
    const trimmed = name.trim()
    if (!trimmed) { toast.error('A dataset needs a name'); return }

    setSaving(msg.runId ?? -1)
    try {
      // Before creating: is there already one that covers this? Advisory, and a
      // failure here must not cost the person their dataset -- so it is asked
      // for, not required.
      try {
        const cols = (msg.results?.[0]?.columns ?? []) as string[]
        if (cols.length) {
          const { matches } = await dataSourcesApi.similarDatasets(dataSourceId, {
            columns: cols, query: statement,
          })
          if (matches.length) {
            const go = window.confirm(
              `You may already have this: ${matches[0].name} covers `
              + `${Math.round(matches[0].coverage * 100)}% of these columns.\n\n`
              + 'Create a new dataset anyway?')
            if (!go) return
          }
        }
      } catch { /* the save stands on its own */ }

      const ds = await dataSourcesApi.import(
        dataSourceId, trimmed, undefined, statement, 'import')
      toast.success(`Saved as "${ds.name}"`)
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save this as a dataset')
    } finally { setSaving(null) }
  }

  const copySql = async (msg: ChatMessage) => {
    const sql = await sqlFor(msg)
    if (!sql.length) { toast.error('No SQL to copy'); return }
    try {
      await navigator.clipboard.writeText(sql.join('\n\n'))
      toast.success('SQL copied')
    } catch {
      toast.error('Could not copy')
    }
  }

  const copyAnswer = async (msg: ChatMessage) => {
    try {
      await navigator.clipboard.writeText(msg.text)
      toast.success(t('ask.answerCopied'))
    } catch {
      toast.error('Could not copy')
    }
  }

  // Pair each question with the reply that follows it: one card per turn.
  const turns: { key: number; question?: ChatMessage; answer?: ChatMessage }[] = []
  for (const m of messages) {
    if (m.role === 'user') turns.push({ key: m.id, question: m })
    else {
      const last = turns[turns.length - 1]
      if (last && last.question && !last.answer) last.answer = m
      else turns.push({ key: m.id, answer: m })
    }
  }
  const pendingTurn = pending !== null ? turns[turns.length - 1] : null
  const rephrase = (suggestions ?? []).slice(0, 3)

  return (
    <div className="dl-chat">
      <div className="dl-chat__scroll">
        {loading && <p className="dl-chat__note">{t('common.loading')}</p>}
        {loadError && <p role="alert" className="dl-chat__note dl-chat__note--error">{loadError}</p>}
        {!loading && !loadError && messages.length === 0 && (
          suggestions && suggestions.length > 0 ? (
            <div className="dl-chat__start">
              <p className="dl-chat__start-title">{t('ask.tryOne')}</p>
              <div className="dl-chips" role="group" aria-label={t('ask.suggested')}>
                {suggestions.map(s => (
                  <button key={s} type="button" className="dl-chip" disabled={busy}
                    onClick={() => void send(s)}>
                    <Sparkles size={13} aria-hidden /> {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="dl-chat__note">{t('ask.empty')}</p>
          )
        )}

        {turns.map(turn => {
          const msg = turn.answer
          const isPending = turn === pendingTurn && !msg
          return (
            <article key={turn.key} className={`dl-turn${msg?.kind === 'error' ? ' dl-turn--error' : ''}`}
              aria-label={turn.question?.text}>
              {turn.question && (
                <header className="dl-turn__q">
                  <span className="dl-turn__avatar" aria-hidden><User size={14} /></span>
                  <p className="dl-turn__q-text" dir="auto">{turn.question.text}</p>
                </header>
              )}
              {turn.question && dataSourceId != null && looksLikeDefinition(turn.question.text) && (
                <div className="dl-turn__rule" style={{ display: 'flex', justifyContent: 'flex-end', paddingInlineEnd: 34 }}>
                  <SaveAsRule sourceId={dataSourceId} text={turn.question.text} />
                </div>
              )}
              {isPending && <Pending question={turn.question?.text ?? ''} />}
              {msg && (
                <div className="dl-turn__a">
                  <span className="dl-turn__avatar dl-turn__avatar--ai" aria-hidden><Sparkles size={14} /></span>
                  <div className="dl-turn__body">
                    {msg.kind === 'limit' ? (
                      <div className="dl-answer-error" role="status" data-testid="ai-limit">
                        <p className="dl-answer-error__title">
                          <AlertTriangle size={16} aria-hidden /> {t('ai.limit.title')}
                        </p>
                        <p className="dl-answer-error__hint" dir={majorityDir(msg.text, direction)}>{modelText(msg.text)}</p>
                      </div>
                    ) : msg.kind === 'error' ? (
                      <div className="dl-answer-error">
                        <p className="dl-answer-error__title">
                          <AlertTriangle size={16} aria-hidden /> {t('ask.err.title')}
                        </p>
                        <p className="dl-answer-error__hint">{t('ask.err.hint')}</p>
                        {rephrase.length > 0 && (
                          <div className="dl-chips dl-chips--small" role="group" aria-label={t('ask.err.tryInstead')}>
                            {rephrase.map(s => (
                              <button key={s} type="button" className="dl-chip" disabled={busy}
                                onClick={() => void send(s)}>{s}</button>
                            ))}
                          </div>
                        )}
                        <details className="dl-answer-error__details">
                          <summary>{t('ask.err.details')}</summary>
                          <div dir="ltr" className="dl-answer-error__raw">{modelText(msg.text)}</div>
                        </details>
                        {turn.question && (
                          <div className="dl-actions">
                            <button type="button" className="dl-act" disabled={busy}
                              onClick={() => void send(turn.question!.text)}>
                              <RotateCcw size={14} aria-hidden /> {t('ask.retry')}
                            </button>
                          </div>
                        )}
                      </div>
                    ) : msg.kind === 'clarify' ? (
                      <div className="dl-answer-clarify">
                        <span className="dl-answer-clarify__tag">{t('ask.needsDetail')}</span>
                        <p dir={majorityDir(msg.text, direction)}>{modelText(msg.text)}</p>
                        {isChoices(msg.presentation) && (
                          <ChoiceOptions presentation={msg.presentation} disabled={busy}
                            onChoose={option => void send(option)} />
                        )}
                      </div>
                    ) : (
                      <>
                        <AnswerText text={msg.text} evidence={msg.evidence}
                          onShow={msg.results?.length ? c => setEvidenceFocus(f => {
                            const at = focusFor(c, f?.at)
                            return at ? { msg: msg.id, at } : f
                          }) : undefined} />
                        {/* A dashboard proposal has no rows to show -- it rides the same
                            `presentation` channel, so it is dispatched by kind here rather
                            than pushed through ResultView, which exists to draw results. */}
                        {isProposals(msg.presentation) ? (
                          <DashboardProposals presentation={msg.presentation} />
                        ) : isAnalysisResult(msg.presentation) ? (
                          /* The agent answered with a statistic rather than SQL, so
                             there are no rows -- same channel, dispatched by kind. */
                          <AnalysisResult presentation={msg.presentation} />
                        ) : msg.results && msg.results.length > 0 && (
                          <ResultView results={msg.results} presentation={msg.presentation}
                            focus={evidenceFocus?.msg === msg.id ? evidenceFocus.at : null} />
                        )}
                        {/* Where this answer came from (Part IV criterion 10). The
                            words above are the AI's; the numbers are the query's or
                            the test's -- a reader has to be able to tell which. */}
                        <AnswerSource msg={msg} />
                        {msg.runId != null && (
                          <AnswerActions msg={msg} question={turn.question?.text} />
                        )}
                      </>
                    )}
                  </div>
                </div>
              )}
            </article>
          )
        })}
        <div ref={endRef} />
      </div>
      <div className="dl-chat__composer">
        <Composer value={input} onChange={setInput} onSend={() => void send()} busy={busy} />
      </div>
    </div>
  )

  function AnswerActions({ msg, question }: { msg: ChatMessage; question?: string }) {
    const runId = msg.runId!
    const sqlable = !(msg.intent === 'chat' || isProposals(msg.presentation)
      || isAnalysisResult(msg.presentation))
    const draft = datasetColumns && (datasetIds?.length === 1 || (onAddToPage && datasetIds?.length))
      ? answerToWidget(msg.results?.[0], msg.sql ?? sqlByRun[runId], datasetColumns,
          msg.presentation?.x, msg.presentation?.y)
      : null
    const answerTitle = question ?? msg.text.slice(0, 80)
    return (
      <div className="dl-actions-wrap">
        <div className="dl-actions">
          {draft && onAddToPage && (
            <button type="button" className="dl-act" data-testid="add-to-page"
              onClick={() => void onAddToPage(draft, answerTitle)}>
              <Sparkles size={14} aria-hidden /> <span className="dl-act__text">{t('ask.addToPage')}</span>
            </button>
          )}
          {draft && !onAddToPage && datasetIds && (
            <AddToDashboard datasetId={datasetIds[0]} draft={draft} title={answerTitle} />
          )}
          <button type="button" className="dl-act" onClick={() => void copyAnswer(msg)} aria-label={t('ask.copyAnswer')}>
            <Copy size={14} aria-hidden /> <span className="dl-act__text">{t('ask.copy')}</span>
          </button>
          {question && (
            <button type="button" className="dl-act" disabled={busy} onClick={() => void send(question)}>
              <RotateCcw size={14} aria-hidden /> <span className="dl-act__text">{t('ask.retry')}</span>
            </button>
          )}
          <span className="dl-actions__sep" aria-hidden />
          {/* A greeting, an analysis and a set of dashboard
              proposals are answers with no query behind them, so
              "Show SQL" on one is a control that does nothing --
              a defect this codebase has shipped before. Judged by
              what the run WAS, not by whether SQL rode along with
              it: a run stored before answers carried their SQL
              has none here and still fetches it on click. */}
          {sqlable && (
            <>
              <button type="button" className="dl-act" aria-expanded={openRun.has(runId)}
                onClick={() => void toggleSql(msg)}>
                <Code2 size={14} aria-hidden /> {openRun.has(runId) ? t('ask.hideSql') : t('ask.showSql')}
              </button>
              <button type="button" className="dl-act" onClick={() => void copySql(msg)} aria-label="Copy SQL">
                <Copy size={14} aria-hidden /> <span className="dl-act__text">{t('ask.copySql')}</span>
              </button>
              {/* Connection scope only: a dataset-mode answer runs
                  over frames in DuckDB and has no source to import
                  from, so the control is absent rather than
                  present-and-failing. */}
              {dataSourceId != null && (
                <button type="button" className="dl-act" onClick={() => void saveAsDataset(msg)}
                  aria-label="Save as dataset" disabled={saving !== null}>
                  <Database size={14} aria-hidden />
                  {saving === runId ? 'Saving…' : t('ask.saveDataset')}
                </button>
              )}
            </>
          )}
          {msg.results && msg.results.some(r => r.total > 0) && (
            <>
              <button type="button" aria-label="Download CSV" className="dl-act"
                onClick={() => downloadCsv(msg.results!, `ask-ai-result-${runId}.csv`)}>
                <Download size={14} aria-hidden /> CSV
              </button>
              {/* Excel and PDF are built server-side from the
                  same stored snapshot the grid draws. */}
              <button type="button" aria-label="Download Excel" className="dl-act"
                onClick={() => void downloadFile(runId, 'xlsx')}>
                <Download size={14} aria-hidden /> Excel
              </button>
              <button type="button" aria-label="Download PDF" className="dl-act"
                onClick={() => void downloadFile(runId, 'pdf')}>
                <Download size={14} aria-hidden /> PDF
              </button>
            </>
          )}
          <span className="dl-actions__grow" />
          <button type="button" className="dl-act dl-act--icon"
            aria-label="Good answer" title={t('ask.good')}
            aria-pressed={feedbackByRun[runId] === 'up'}
            onClick={() => void rate(runId, 'up')}>
            <ThumbsUp size={14} aria-hidden />
          </button>
          <button type="button" className="dl-act dl-act--icon"
            aria-label="Bad answer" title={t('ask.bad')}
            aria-pressed={feedbackByRun[runId] === 'down'}
            onClick={() => void rate(runId, 'down')}>
            <ThumbsDown size={14} aria-hidden />
          </button>
        </div>
        {openRun.has(runId) && (
          <div className="dl-sql">
            {sqlLoading.has(runId) ? (
              <span className="dl-chat__note">{t('common.loading')}</span>
            ) : (
              ((msg.sql && msg.sql.length ? msg.sql : sqlByRun[runId]) ?? []).map((sql, i) => (
                <pre key={i} dir="ltr" className="dl-sql__code">{sql}</pre>
              ))
            )}
            {msg.contextObjects && msg.contextObjects.length > 0 && (
              <div className="dl-sql__tables">
                Tables considered: {msg.contextObjects.join(', ')}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }
}

/** One line naming the engine behind an assistant answer, and its evidence.
 *  In the reader's language (HR re-test 2026-10-01: English under an Arabic
 *  answer); English when no translator is passed. */
export function answerSource(msg: Pick<ChatMessage, 'intent' | 'results' | 'sql' | 'presentation'>,
                             t: TranslateFn = (k, v) => translate('en', k, v)): string {
  if (isProposals(msg.presentation)) return t('ask.src.proposals')
  if (isAnalysisResult(msg.presentation)) return t('ask.src.analysis')
  const results = msg.results ?? []
  if (msg.intent === 'chat' || results.length === 0) return t('ask.src.chat')
  if (results.every(r => (r as { source?: string }).source === 'catalog')) return t('ask.src.catalog')
  const rows = results.reduce((n, r) => n + (Number(r.total) || 0), 0)
  const queries = Math.max(msg.sql?.length ?? 0, results.length)
  return t('ask.src.query', { q: queries, rows: rows.toLocaleString() })
}

function AnswerSource({ msg }: { msg: ChatMessage }) {
  const t = useT()
  if (msg.role !== 'assistant' || msg.kind === 'error' || msg.kind === 'clarify' || msg.kind === 'limit') return null
  return (
    <div data-testid="answer-source" style={{ marginTop: 6, fontSize: 10.5, color: 'var(--muted)' }}>
      <span aria-hidden>ⓘ </span>{answerSource(msg, t)}
    </div>
  )
}
