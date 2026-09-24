import { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { usePrompt } from '../ui/PromptDialog'
import { ThumbsUp, ThumbsDown, Copy, Download, Database } from 'lucide-react'
import { agentApi, dataSourcesApi } from '../../services/api'
import type { AgentAnswer, AgentMessage, AgentPresentation, AgentResult } from '../../services/api'
import Pending from './Pending'
import ResultView, { downloadCsv } from './ResultView'
import AnalysisResult, { isAnalysisResult } from './AnalysisResult'
import ChoiceOptions, { isChoices } from './ChoiceOptions'
import DashboardProposals, { type DashboardProposalsPresentation }
  from './DashboardProposals'
import { useT } from '../../i18n'

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
}

type MessageKind = 'answer' | 'clarify' | 'error'

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
    intent: result.intent ?? null,
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
    intent: run?.intent ?? null,
  }
}

/** `presentation` is a union carried on the run: a format hint for results, a
 *  set of dashboard proposals, or an analysis the agent ran instead of writing
 *  SQL. One narrow check per kind keeps the branch below readable. */
function isProposals(p: unknown): p is DashboardProposalsPresentation {
  return !!p && (p as { kind?: string }).kind === 'dashboard_proposals'
}

export default function ChatPane({ dataSourceId, datasetIds, conversationId, onConversationCreated }: ChatPaneProps) {
  const t = useT()
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
    } catch {
      setMessages(m => [...m, {
        id: nextId++, role: 'assistant', text: 'Could not reach the agent. Try again.', kind: 'error',
      }])
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

  const bubble: React.CSSProperties = { borderRadius: 10, padding: '8px 12px', fontSize: 13 }
  const linkBtn: React.CSSProperties = {
    background: 'none', border: 'none', padding: 0, color: 'var(--accent)',
    cursor: 'pointer', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 4,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: 12, display: 'flex',
                    flexDirection: 'column', gap: 10 }}>
        {loading && (
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>{t('common.loading')}</p>
        )}
        {loadError && (
          <p role="alert" style={{ fontSize: 13, color: 'var(--danger)', margin: 0 }}>{loadError}</p>
        )}
        {!loading && !loadError && messages.length === 0 && (
          <p style={{ fontSize: 13, color: 'var(--muted)', margin: 0 }}>
            {t('ask.empty')}
          </p>
        )}
        {messages.map(msg => (
          <div key={msg.id} style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: msg.results?.length ? '100%' : '85%',
            minWidth: msg.results?.length ? '60%' : undefined,
          }}>
            {msg.role === 'user' ? (
              <div style={{ ...bubble, background: 'var(--accent)', color: 'var(--mc-accent-fg)' }}>
                {msg.text}
              </div>
            ) : msg.kind === 'error' ? (
              <div style={{ ...bubble, background: '#fdecec', border: '1px solid #f0acac', color: '#a4231f' }}>
                <strong>Could not answer that.</strong>
                <div style={{ marginTop: 4 }}>{msg.text}</div>
              </div>
            ) : msg.kind === 'clarify' ? (
              <div style={{ ...bubble, background: '#fdf6e7', border: '1px solid #f0dfae', color: '#7a5a12' }}>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                              letterSpacing: '.04em', display: 'block', marginBottom: 4 }}>
                  Needs more detail
                </span>
                {msg.text}
                {isChoices(msg.presentation) && (
                  <ChoiceOptions presentation={msg.presentation} disabled={busy}
                    onChoose={option => void send(option)} />
                )}
              </div>
            ) : (
              <div style={{ ...bubble, background: 'var(--surface2)', color: 'var(--text)' }}>
                {msg.text}
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
                  <ResultView results={msg.results} presentation={msg.presentation} />
                )}
                {/* Where this answer came from (Part IV criterion 10). The
                    words above are the AI's; the numbers are the query's or
                    the test's -- a reader has to be able to tell which. */}
                <AnswerSource msg={msg} />
                {msg.runId != null && (
                  <div style={{ marginTop: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                      <button
                        aria-label="Good answer"
                        aria-pressed={feedbackByRun[msg.runId] === 'up'}
                        onClick={() => void rate(msg.runId!, 'up')}
                        style={{ ...linkBtn, color: 'var(--text)',
                                 opacity: feedbackByRun[msg.runId] === 'down' ? 0.4 : 1 }}
                      >
                        <ThumbsUp size={13} />
                      </button>
                      <button
                        aria-label="Bad answer"
                        aria-pressed={feedbackByRun[msg.runId] === 'down'}
                        onClick={() => void rate(msg.runId!, 'down')}
                        style={{ ...linkBtn, color: 'var(--text)',
                                 opacity: feedbackByRun[msg.runId] === 'up' ? 0.4 : 1 }}
                      >
                        <ThumbsDown size={13} />
                      </button>
                      {/* A greeting, an analysis and a set of dashboard
                          proposals are answers with no query behind them, so
                          "Show SQL" on one is a control that does nothing --
                          a defect this codebase has shipped before. Judged by
                          what the run WAS, not by whether SQL rode along with
                          it: a run stored before answers carried their SQL
                          has none here and still fetches it on click. */}
                      {!(msg.intent === 'chat' || isProposals(msg.presentation)
                         || isAnalysisResult(msg.presentation)) && (
                        <>
                          <button onClick={() => void toggleSql(msg)} style={linkBtn}>
                            {openRun.has(msg.runId) ? 'Hide SQL' : 'Show SQL'}
                          </button>
                          <button onClick={() => void copySql(msg)} style={linkBtn} aria-label="Copy SQL">
                            <Copy size={12} aria-hidden /> Copy SQL
                          </button>
                          {/* Connection scope only: a dataset-mode answer runs
                              over frames in DuckDB and has no source to import
                              from, so the control is absent rather than
                              present-and-failing. */}
                          {dataSourceId != null && (
                            <button onClick={() => void saveAsDataset(msg)}
                              style={linkBtn} aria-label="Save as dataset"
                              disabled={saving !== null}>
                              <Database size={12} aria-hidden />
                              {saving === msg.runId ? 'Saving…' : 'Save as dataset'}
                            </button>
                          )}
                        </>
                      )}
                      {msg.results && msg.results.some(r => r.total > 0) && (
                        <>
                          <button aria-label="Download CSV" style={linkBtn}
                            onClick={() => downloadCsv(msg.results!, `ask-ai-result-${msg.runId}.csv`)}>
                            <Download size={12} aria-hidden /> CSV
                          </button>
                          {/* Excel and PDF are built server-side from the
                              same stored snapshot the grid draws. */}
                          <button aria-label="Download Excel" style={linkBtn}
                            onClick={() => void downloadFile(msg.runId!, 'xlsx')}>
                            <Download size={12} aria-hidden /> Excel
                          </button>
                          <button aria-label="Download PDF" style={linkBtn}
                            onClick={() => void downloadFile(msg.runId!, 'pdf')}>
                            <Download size={12} aria-hidden /> PDF
                          </button>
                        </>
                      )}
                    </div>
                    {openRun.has(msg.runId) && (
                      <div style={{ marginTop: 6 }}>
                        {sqlLoading.has(msg.runId) ? (
                          <span style={{ fontSize: 12, color: 'var(--muted)' }}>Loading…</span>
                        ) : (
                          ((msg.sql && msg.sql.length ? msg.sql : sqlByRun[msg.runId]) ?? []).map((sql, i) => (
                            <pre key={i} style={{ margin: '0 0 4px', fontSize: 11, direction: 'ltr',
                                                   background: '#0f172a', color: '#e2e8f0',
                                                   padding: 8, borderRadius: 6, overflowX: 'auto' }}>
                              {sql}
                            </pre>
                          ))
                        )}
                        {msg.contextObjects && msg.contextObjects.length > 0 && (
                          <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                            Tables considered: {msg.contextObjects.join(', ')}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
            {/* Between Send and the answer. Without this the pane showed
                nothing at all -- see Pending.tsx for the measurements. */}
            {pending !== null && <Pending question={pending} />}
      </div>
      <div style={{ display: 'flex', gap: 8, padding: 12, borderTop: '1px solid var(--border)' }}>
        <input
          placeholder="Ask a question about this data…"
          value={input}
          disabled={busy}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') void send() }}
          style={{ flex: 1, padding: '8px 10px', fontSize: 13, border: '1px solid var(--border)',
                   borderRadius: 6, background: 'var(--surface)', color: 'var(--text)' }}
        />
        <button
          onClick={() => void send()}
          disabled={busy}
          style={{ padding: '8px 14px', fontSize: 13, borderRadius: 6, border: 'none',
                   background: busy ? 'var(--muted)' : 'var(--accent)', color: 'var(--mc-accent-fg)',
                   cursor: busy ? 'default' : 'pointer' }}
        >
          {busy ? 'Asking…' : 'Send'}
        </button>
      </div>
    </div>
  )
}

/** One line naming the engine behind an assistant answer, and its evidence. */
export function answerSource(msg: Pick<ChatMessage, 'intent' | 'results' | 'sql' | 'presentation'>): string {
  if (isProposals(msg.presentation)) {
    return 'Proposed by the AI model from this data; "Show SQL" on each shows the query it is built on'
  }
  if (isAnalysisResult(msg.presentation)) {
    return 'The AI chose the test; the result was computed on the data by the statistics engine (method and effect size above)'
  }
  const results = msg.results ?? []
  if (msg.intent === 'chat' || results.length === 0) {
    return 'AI reply: no data was queried for this'
  }
  if (results.every(r => (r as { source?: string }).source === 'catalog')) {
    return 'AI answer from the data catalog (what is in scope), not from a query on the rows'
  }
  const rows = results.reduce((n, r) => n + (Number(r.total) || 0), 0)
  const queries = Math.max(msg.sql?.length ?? 0, results.length)
  return `AI answer from ${queries} ${queries === 1 ? 'query' : 'queries'} on your data `
    + `(${rows.toLocaleString()} ${rows === 1 ? 'row' : 'rows'}); "Show SQL" shows exactly what ran`
}

function AnswerSource({ msg }: { msg: ChatMessage }) {
  if (msg.role !== 'assistant' || msg.kind === 'error' || msg.kind === 'clarify') return null
  return (
    <div data-testid="answer-source" style={{ marginTop: 6, fontSize: 10.5, color: 'var(--muted)' }}>
      <span aria-hidden>ⓘ </span>{answerSource(msg)}
    </div>
  )
}
