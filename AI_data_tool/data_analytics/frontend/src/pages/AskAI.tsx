import { useContext, useEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BarChart3, Bot, Code2, History, MessageSquareText, Sparkles } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import ChatPane from '../components/chat/ChatPane'
import Composer from '../components/chat/Composer'
import { agentApi, allowAiApi, analysisApi, datasetsApi, dataSourcesApi } from '../services/api'
import type { AgentConversation, Dataset, DatasetColumn } from '../services/api'
import { useT } from '../i18n'
import AskHero from './ask/AskHero'
import SuggestionGrid from './ask/SuggestionGrid'
import DataPicker, { useItemMeta, type PickerItem } from './ask/DataPicker'
import HistoryPanel from './ask/HistoryPanel'
import { signalRobot } from './ask/robotMood'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { connectionSuggestionCards, datasetSuggestionCards, nearUniqueLabels, type ColumnClasses } from './ask/suggestions'
import './ask/ask.css'
import './ask/askLayout.css'
import './ask/askCards.css'
import { AuthContext } from '../contexts/AuthContext'
import { cleanDatasets, isCertified } from '../lib/cleanDatasets'
import { localDigits } from '../lib/arabicFormats'

/**
 * The agent's own page (step 10 design). Two states:
 *
 *  - No scope yet: a centred hero -- the picture, "Ask your data anything",
 *    Step 1 (a searchable picker of datasets and live connections) -- and the
 *    question box at the foot, shown but locked, so the order is obvious.
 *  - A scope: an "Asking about" row, the chat column (880px, centred) and the
 *    threads held about it (History) on the inline end. A new thread opens on
 *    "What would you like to know?" and Step 2's suggestion cards, built from
 *    the dataset's own columns. Below 1180px History is an overlay.
 *
 * The scope is in the URL (`/ask?dataset=32`, `/ask?source=3`) so a question
 * about a specific dataset can be LINKED to -- DatasetDetail's "Ask about
 * this data" points here.
 *
 * `?q=` carries a question from Home. It is read once, taken out of the URL
 * (a reload must not bring it back), shown in the hero while no data is
 * chosen, and put in the question box of the first chat that opens -- never
 * sent on the person's behalf.
 *
 * The page owns the conversation list. It shows the user's threads for the
 * current scope, newest first, opens a new thread by default (the design's
 * "dataset picked" state; the threads are one click away), and hands the
 * chosen id to the pane (`conversationId`); "New chat" hands it null and the
 * pane reports back the thread its first question creates.
 */

function inScope(c: AgentConversation, sourceId: number | null, datasetId: number | null): boolean {
  if (sourceId != null) return c.data_source_id === sourceId
  if (datasetId != null) return c.data_source_id == null && (c.dataset_ids ?? []).length === 1 && c.dataset_ids![0] === datasetId
  return false
}

const FOLD_KEY = 'datalytics.ask.historyFolded'
const readFold = () => { try { return localStorage.getItem(FOLD_KEY) === '1' } catch { return false } }

export default function AskAI() {
  const t = useT()
  const [params, setParams] = useSearchParams()
  const [usableDatasets, setUsableDatasets] = useState<Dataset[]>([])
  const [sourceItems, setSourceItems] = useState<PickerItem[]>([])
  // 4.7: certified first, test-looking leftovers out of sight -- in the
  // picker a newcomer sees first.
  // Two toggles in the chooser's tools row: only mine, and the test-looking
  // ones. This page's own (not the shared All / Certified / Mine choice other
  // pickers remember), so nothing here is filtered by a control it lacks.
  const userId = useContext(AuthContext)?.user?.id ?? null
  const [mineOnly, setMineOnly] = useState(false)
  const [showTest, setShowTest] = useState(false)
  const clean = useMemo(() => {
    const got = cleanDatasets(usableDatasets, mineOnly ? 'mine' : 'all', userId, showTest)
    // "Mine" with nothing of mine would be an empty chooser: show all instead.
    const shown = got.visible.length === 0 && mineOnly ? cleanDatasets(usableDatasets, 'all', userId, showTest) : got
    return { ...shown, testCount: cleanDatasets(usableDatasets, mineOnly ? 'mine' : 'all', userId, false).hiddenTest }
  }, [usableDatasets, mineOnly, userId, showTest])
  // The dataset the URL is about is always listed, even one hidden as
  // test-looking: a link (Home's Ask AI, a starter) can open it, and the
  // picker must then name it rather than say "Choose a dataset" (QA B2).
  const linkedId = params.get('dataset') ? Number(params.get('dataset')) : null
  const items: PickerItem[] = useMemo(() => {
    const linked = linkedId != null && !clean.visible.some(d => d.id === linkedId)
      ? usableDatasets.filter(d => d.id === linkedId) : []
    return [
      ...[...linked, ...clean.visible].map(d => ({
        key: `d:${d.id}`, kind: 'dataset' as const, name: isCertified(d) ? `✓ ${d.name}` : d.name,
        rows: d.row_count ?? null, cols: d.col_count ?? null, updated: d.updated_at ?? null,
        mode: d.mode === 'directquery' ? 'directquery' as const : 'import' as const,
      })),
      ...sourceItems,
    ]
  }, [clean.visible, sourceItems, usableDatasets, linkedId])
  const [columnsById, setColumnsById] = useState<Record<number, DatasetColumn[]>>({})
  const [classesById, setClassesById] = useState<Record<number, ColumnClasses>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [conversations, setConversations] = useState<AgentConversation[]>([])
  // undefined = not decided yet (list still loading); null = a fresh thread.
  const [selected, setSelected] = useState<number | null | undefined>(undefined)
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null)
  const [folded, setFolded] = useState(readFold)
  const [drawer, setDrawer] = useState(false)
  const confirm = useConfirm()

  // Home's question, read once and dropped from the URL (see the docstring).
  const [pendingQ, setPendingQ] = useState(() => (params.get('q') ?? '').trim().slice(0, 2000))
  useEffect(() => {
    if (!params.has('q')) return
    const next = new URLSearchParams(params)
    next.delete('q')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const datasetId = params.get('dataset') ? Number(params.get('dataset')) : null
  const sourceId = params.get('source') ? Number(params.get('source')) : null
  const scopeKey = sourceId != null ? `s:${sourceId}` : datasetId != null ? `d:${datasetId}` : ''

  useEffect(() => {
    Promise.all([
      datasetsApi.list(),
      // Non-admins may lack connection access; the dataset scope still works.
      dataSourcesApi.list().catch(() => []),
    ])
      .then(([ds, srcs]) => {
        // Live (DirectQuery) datasets are asked through their own SQL now, so
        // "Current workforce" is answered from Current workforce rather than
        // from the raw tables of its connection (HR evaluation, blocker 3).
        const usable = ds.filter(d => d.filename || (d.mode === 'directquery' && d.data_source_id != null))
        setUsableDatasets(usable)
        setSourceItems(srcs.map(s => ({
          key: `s:${s.id}`, kind: 'source' as const, name: s.name,
          sourceType: s.type ?? null, updated: s.created_at ?? null,
        })))
        const cols: Record<number, DatasetColumn[]> = {}
        for (const d of usable) if (Array.isArray(d.columns) && d.columns.length) cols[d.id] = d.columns
        setColumnsById(cols)
        // AD-11: the list already carries each dataset's stored classes; the
        // per-dataset read below is skipped when columns are known, so without
        // this the suggestions never saw a "level" or a "code".
        const classes: Record<number, ColumnClasses> = {}
        for (const d of usable) if (d.column_meta) classes[d.id] = d.column_meta as ColumnClasses
        setClassesById(m => ({ ...classes, ...m }))
      })
      // A failed dataset list must not read as "no data yet" -- an error
      // dressed as an empty state is the defect, not a degradation.
      .catch((e: any) => setError(e?.response?.data?.detail ?? t('ask.loadFailed')))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // The list may carry columns; when it doesn't, one read of the dataset does.
  useEffect(() => {
    if (datasetId == null || columnsById[datasetId] || typeof datasetsApi.get !== 'function') return
    let alive = true
    datasetsApi.get(datasetId)
      .then(d => {
        if (!alive || !d?.columns) return
        setColumnsById(m => ({ ...m, [datasetId]: d.columns }))
        if (d.column_meta) setClassesById(m => ({ ...m, [datasetId]: d.column_meta as ColumnClasses }))
      })
      .catch(() => { /* suggestions fall back to generic ones */ })
    return () => { alive = false }
  }, [datasetId, columnsById])

  // The threads for this scope, newest first; the newest opens by default.
  useEffect(() => {
    if (!scopeKey) return
    let alive = true
    setSelected(undefined)
    setEditing(null)
    agentApi.listConversations()
      .then(all => {
        if (!alive) return
        const mine = all.filter(c => inScope(c, sourceId, datasetId)).sort((a, b) => b.id - a.id)
        setConversations(mine)
        setSelected(null)
      })
      .catch(() => { if (alive) { setConversations([]); setSelected(null) } })
    return () => { alive = false }
  }, [scopeKey, sourceId, datasetId])

  const choose = (value: string) => {
    // "d:32" or "s:3" -- one picker, two scope kinds, because the question
    // "what am I asking about?" has one answer, not two fields.
    signalRobot(value ? 'chosen' : 'rest')
    if (!value) { setParams({}, { replace: true }); return }
    const [kind, id] = value.split(':')
    setParams(kind === 's' ? { source: id } : { dataset: id }, { replace: true })
  }

  const created = (conv: { id: number; title: string }) => {
    setConversations(list => [{
      id: conv.id, title: conv.title, data_source_id: sourceId,
      dataset_ids: datasetId != null ? [datasetId] : null,
      created_at: new Date().toISOString(),
    }, ...list])
    setSelected(conv.id)
  }

  // Enter and blur both save; the ref makes the second arrival a no-op
  // instead of a second PATCH.
  const editRef = useRef(editing)
  editRef.current = editing
  const saveTitle = async () => {
    const e = editRef.current
    if (!e) return
    editRef.current = null
    const title = e.title.trim()
    const id = e.id
    setEditing(null)
    if (!title) return
    try {
      const got = await agentApi.rename(id, title)
      setConversations(list => list.map(c => c.id === id ? { ...c, title: got.title } : c))
    } catch {
      // The old title stands; nothing to undo.
    }
  }

  const remove = async (c: AgentConversation) => {
    if (!(await confirm({ title: t('ask3.deleteTitle'), body: t('ask3.deleteBody', { title: c.title }),
      confirmLabel: t('ask3.delete') }))) return
    try {
      await agentApi.remove(c.id)
    } catch {
      return
    }
    setConversations(list => list.filter(x => x.id !== c.id))
    if (selected === c.id) setSelected(null)
  }

  const toggleFold = () => setFolded(f => {
    try { localStorage.setItem(FOLD_KEY, f ? '0' : '1') } catch { /* a convenience */ }
    return !f
  })

  // The empty page's question box is locked, so there the robot's "typing"
  // is the data chooser's search box: while it has focus or text.
  const searchBox = (e: FocusEvent<HTMLDivElement> | FormEvent<HTMLDivElement>) => {
    const box = e.target
    if (!(box instanceof HTMLInputElement) || box.type === 'checkbox' || box.type === 'radio') return
    if (e.type === 'input') signalRobot('key')
    signalRobot((e.type !== 'blur' && document.activeElement === box) || box.value ? 'compose-on' : 'compose-off')
  }

  // AD-10: the dataset's "Allow AI" answer, read up front so the person learns
  // before asking -- not from the first answer -- that only the built-in
  // analyses will answer. The suggestions stay: the no-AI path answers them.
  const [aiOff, setAiOff] = useState(false)
  useEffect(() => {
    setAiOff(false)
    if (datasetId == null) return
    let live = true
    Promise.resolve().then(() => allowAiApi.get(datasetId))
      .then(r => { if (live) setAiOff(r?.effective === false) })
      .catch(() => {})
    return () => { live = false }
  }, [datasetId])

  const scoped = sourceId != null || datasetId != null
  // The pane copies the question into its box when it mounts; after that it is
  // the pane's, so a later scope change does not put it back.
  const paneOpen = scoped && selected !== undefined
  useEffect(() => { if (paneOpen && pendingQ) setPendingQ('') }, [paneOpen, pendingQ])
  const columns = datasetId != null ? columnsById[datasetId] : undefined
  // AD-11 step 3: which labels have a value per row, from the stored profile
  // (one cached read; the server withholds it from a reader under a row or
  // column rule, and then nothing is skipped).
  const [perRow, setPerRow] = useState<{ id: number; cols: Set<string> } | null>(null)
  useEffect(() => {
    if (datasetId == null || typeof analysisApi?.get !== 'function') return
    let alive = true
    Promise.resolve().then(() => analysisApi.get(datasetId))
      .then(p => { if (alive) setPerRow({ id: datasetId, cols: nearUniqueLabels(p) }) })
      .catch(() => { /* no profile: nothing skipped */ })
    return () => { alive = false }
  }, [datasetId])
  const skip = perRow && perRow.id === datasetId ? perRow.cols : undefined
  const cards = useMemo(
    () => (sourceId != null ? connectionSuggestionCards(t)
      : datasetSuggestionCards(columns, t, datasetId != null ? classesById[datasetId] : undefined, skip)),
    [sourceId, columns, t, datasetId, classesById, skip],
  )
  const suggestions = useMemo(() => cards.map(c => c.text), [cards])
  const itemMeta = useItemMeta()
  // "… based on the columns in **Demo — Sales**.": the name bold and isolated
  // inside the translated sentence (one template per language, not glued).
  const rich = (key: 'ask2.picked.sub' | 'ask2.picked.subSource', name: string) => {
    const [before, after = ''] = t(key, { name: '\uE000' }).split('\uE000')
    return <>{before}<bdi><b>{name}</b></bdi>{after}</>
  }
  const scopeItem = items.find(i => i.key === scopeKey)
  // History beside the chat on a wide screen (unless folded away), an overlay
  // below 1180px; the "History" button in the context row opens it either way.
  const showHistory = () => {
    if (window.matchMedia?.('(max-width: 1179px)').matches) setDrawer(true)
    else if (folded) toggleFold()
  }
  const noData = !loading && !error && items.length === 0
  const nSets = items.filter(i => i.kind === 'dataset').length
  const heroCounts = [
    nSets ? t('ask2.pick.datasets', { n: localDigits(String(nSets)) }) : '',
    items.length - nSets ? t('ask2.pick.connections', { n: localDigits(String(items.length - nSets)) }) : '',
  ].filter(Boolean)

  if (!scoped) {
    return (
      <div className="dl-ask dl-ask--v2 dl-ask--empty">
        <div className="dl-ask__chat">
          <div className="dl-ask__scroll">
            <div className="dl-ask__col">
              {error && <div role="alert" className="dl-ask__error">{error}</div>}
              {noData ? (
                <EmptyState icon={Bot} title={t('ask.noData')}
                  action={<Link to="/upload" className="btn btn-primary">{t('ask.uploadDataset')}</Link>} />
              ) : (
                // Owner's change to Part A: two columns. The data chooser,
                // always open, on the inline start; the picture, the headline
                // and the subtitle on the inline end. The page does not
                // scroll: the chooser's list scrolls in its own column.
                <div className="dl-ask__split">
                  <div className="dl-ask__chooser" onFocus={searchBox} onBlur={searchBox} onInput={searchBox}
                    onPointerEnter={() => signalRobot('look-on')} onPointerLeave={() => signalRobot('look-off')}>
                    {pendingQ && (
                      <p className="dl-ask__pending" data-testid="ask-pending-q">
                        {t('ask2.pendingQ')} <q dir="auto">{pendingQ}</q>
                      </p>
                    )}
                    <DataPicker items={items} value="" onChoose={choose} size="inline" loading={loading}
                      tools={{
                        mine: clean.mine > 0 ? { on: mineOnly, set: setMineOnly } : undefined,
                        test: clean.testCount > 0 ? { on: showTest, set: setShowTest, n: clean.testCount } : undefined,
                      }} />
                  </div>
                  <AskHero id="dl-ask-title" title={t('ask2.hero.title')} sub={t('ask2.hero.sub')}
                    eyebrow={<><Sparkles size={13} aria-hidden /> {[t('ask2.hero.eyebrow'), ...heroCounts].join(' · ')}</>}
                    facts={[
                      { icon: MessageSquareText, text: t('ask2.hero.fact1') },
                      { icon: BarChart3, text: t('ask2.hero.fact2') },
                      { icon: Code2, text: t('ask2.hero.fact3') },
                    ]} />
                </div>
              )}
            </div>
          </div>
          {!noData && (
            <div className="dl-ask__foot">
              <div className="dl-ask__col">
                <Composer value="" onChange={() => {}} onSend={() => {}} locked lockedHint={t('ask2.composer.chooseFirst')}
                  page={{ pill: t('ask2.composer.lock') }} />
                <p className="dl-ask__disc">{t('ask2.disclaimer')}</p>
              </div>
            </div>
          )}
        </div>
        {/* History is here before any data is chosen too, saying what it will
            hold; folded away it is gone, as on the chat. */}
        {!noData && (
          <HistoryPanel conversations={[]} selected={undefined} scope="none"
            onSelect={() => {}} onNew={() => {}} editing={null} onEdit={() => {}} onSave={() => {}}
            onCancelEdit={() => {}} onDelete={() => {}}
            collapsed={folded} onToggleCollapsed={toggleFold} mobileOpen={false} onCloseMobile={() => {}} />
        )}
      </div>
    )
  }

  const histHidden = folded || drawer
  return (
    <div className="dl-ask dl-ask--v2 dl-ask--work">
      <section className="dl-ask__chat">
        <div className="dl-ask__ctx">
          <span className="dl-ask__ctx-label">{t('ask2.ctx.asking')}</span>
          <DataPicker items={items} value={scopeKey} onChoose={choose} size="compact" loading={loading} />
          {scopeItem && <span className="dl-ask__ctx-meta">{itemMeta(scopeItem)}</span>}
          <span className="dl-ask__ctx-grow" />
          <button type="button" className={`btn btn-ghost btn-sm dl-ask__hist-btn${histHidden ? '' : ' dl-ask__hist-btn--wide-hidden'}`}
            onClick={showHistory} aria-label={t('ask2.hist.show')} aria-expanded={drawer}>
            <History size={15} aria-hidden /> {t('ask2.hist.button')}
          </button>
        </div>
        <div className="dl-ask__pane">
          {aiOff && (
            <p role="status" data-testid="ask-ai-off" className="dl-chat__note">{t('ask2.aiOff')}</p>
          )}
          {selected !== undefined && (() => {
            const startView = (ask: (q: string) => void, busy: boolean, reason?: string) => (
              <AskHero id="dl-ask-picked" small title={t('ask2.picked.title')}
                sub={rich(sourceId != null ? 'ask2.picked.subSource' : 'ask2.picked.sub', scopeItem?.name ?? '')}
                step={2} stepLabel={t('ask2.step2')}>
                <SuggestionGrid cards={cards} onAsk={ask} disabled={busy} disabledReason={reason} />
              </AskHero>
            )
            return sourceId != null
              ? <ChatPane key={scopeKey} dataSourceId={sourceId} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions} initialInput={pendingQ} startView={startView} onActivity={signalRobot}
                  card={{ scopeName: scopeItem?.name ?? '' }} />
              : <ChatPane key={scopeKey} datasetIds={[datasetId as number]} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions}
                  datasetColumns={columns?.map(c => c.name)} initialInput={pendingQ} startView={startView} onActivity={signalRobot}
                  card={{ scopeName: scopeItem?.name ?? '' }} />
          })()}
        </div>
      </section>

      <HistoryPanel
        conversations={conversations} selected={selected}
        onSelect={id => { setSelected(id); setDrawer(false) }}
        onNew={() => { setSelected(null); setEditing(null); setDrawer(false) }}
        editing={editing} onEdit={setEditing} onSave={() => void saveTitle()}
        onCancelEdit={() => setEditing(null)} onDelete={c => void remove(c)}
        collapsed={folded} onToggleCollapsed={toggleFold} scope={sourceId != null ? 'source' : 'dataset'}
        mobileOpen={drawer} onCloseMobile={() => setDrawer(false)} />
    </div>
  )
}
