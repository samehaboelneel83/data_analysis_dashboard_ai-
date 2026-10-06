import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BarChart3, Bot, Code2, History, MessageSquareText, Sparkles } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import ChatPane from '../components/chat/ChatPane'
import { agentApi, datasetsApi, dataSourcesApi } from '../services/api'
import type { AgentConversation, Dataset, DatasetColumn } from '../services/api'
import { useT } from '../i18n'
import AskIllustration from './ask/AskIllustration'
import DataPicker, { type PickerItem } from './ask/DataPicker'
import HistoryPanel from './ask/HistoryPanel'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { connectionSuggestions, datasetSuggestions } from './ask/suggestions'
import './ask/ask.css'
import DatasetListFilter, { useCleanDatasets } from '../components/dataset/DatasetListFilter'
import { isCertified } from '../lib/cleanDatasets'

/**
 * The agent's own page. Two states:
 *
 *  - No scope yet: a hero that says what this page does, Step 1 (a searchable
 *    picker of datasets and live connections) and Step 2 (the question box,
 *    shown but locked, so the order of things is obvious at a glance).
 *  - A scope: the threads held about it (History) beside the chat.
 *
 * The scope is in the URL (`/ask?dataset=32`, `/ask?source=3`) so a question
 * about a specific dataset can be LINKED to -- DatasetDetail's "Ask about
 * this data" points here.
 *
 * The page owns the conversation list. It shows the user's threads for the
 * current scope, newest first, opens the newest by default, and hands the
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
  const clean = useCleanDatasets(usableDatasets)
  const items: PickerItem[] = useMemo(() => [
    ...clean.visible.map(d => ({
      key: `d:${d.id}`, kind: 'dataset' as const, name: isCertified(d) ? `✓ ${d.name}` : d.name,
      rows: d.row_count ?? null, cols: d.col_count ?? null, updated: d.updated_at ?? null,
    })),
    ...sourceItems,
  ], [clean.visible, sourceItems])
  const [columnsById, setColumnsById] = useState<Record<number, DatasetColumn[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [conversations, setConversations] = useState<AgentConversation[]>([])
  // undefined = not decided yet (list still loading); null = a fresh thread.
  const [selected, setSelected] = useState<number | null | undefined>(undefined)
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null)
  const [folded, setFolded] = useState(readFold)
  const [drawer, setDrawer] = useState(false)
  const confirm = useConfirm()

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
      .then(d => { if (alive && d?.columns) setColumnsById(m => ({ ...m, [datasetId]: d.columns })) })
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
        setSelected(mine.length ? mine[0].id : null)
      })
      .catch(() => { if (alive) { setConversations([]); setSelected(null) } })
    return () => { alive = false }
  }, [scopeKey, sourceId, datasetId])

  const choose = (value: string) => {
    // "d:32" or "s:3" -- one picker, two scope kinds, because the question
    // "what am I asking about?" has one answer, not two fields.
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

  const scoped = sourceId != null || datasetId != null
  const columns = datasetId != null ? columnsById[datasetId] : undefined
  const suggestions = useMemo(
    () => (sourceId != null ? connectionSuggestions(t) : datasetSuggestions(columns, t)),
    [sourceId, columns, t],
  )
  const noData = !loading && !error && items.length === 0

  if (!scoped) {
    return (
      <div className="dl-ask dl-ask--hero">
        {error && <div role="alert" className="dl-ask__error">{error}</div>}
        {noData ? (
          <EmptyState icon={Bot} title={t('ask.noData')}
            action={<Link to="/upload" className="btn btn-primary">{t('ask.uploadDataset')}</Link>} />
        ) : (
          // Text and picker on one side, the picture on the other: the
          // picker's list opens into the empty space under the text column, so
          // it never lands on the illustration (it used to sit under the
          // picture and flip up over it).
          <section className="dl-ask__hero" aria-labelledby="dl-ask-title">
            <div className="dl-ask__copy">
              <span className="dl-ask__eyebrow"><Sparkles size={14} aria-hidden /> {t('ask.hero.eyebrow')}</span>
              <h1 id="dl-ask-title" className="dl-ask__title">{t('ask.hero.title')}</h1>
              <p className="dl-ask__sub">{t('ask.hero.sub')}</p>
              <ul className="dl-ask__points">
                <li><MessageSquareText size={16} aria-hidden /> {t('ask.hero.point1')}</li>
                <li><BarChart3 size={16} aria-hidden /> {t('ask.hero.point2')}</li>
                <li><Code2 size={16} aria-hidden /> {t('ask.hero.point3')}</li>
              </ul>
              {/* One step only: the question box appears once data is chosen
                  (the scoped view below). */}
              <div className="dl-ask__step">
                <span className="dl-ask__step-label">{t('ask.step1')}</span>
                <DataPicker items={items} value="" onChoose={choose} size="hero" loading={loading} />
                <div style={{ marginTop: 8 }}><DatasetListFilter state={clean} /></div>
              </div>
            </div>
            <div className="dl-ask__art-wrap" aria-hidden>
              <AskIllustration className="dl-ask__art" />
            </div>
          </section>
        )}
      </div>
    )
  }

  return (
    <div className="dl-ask dl-ask--work">
      <HistoryPanel
        conversations={conversations} selected={selected}
        onSelect={id => { setSelected(id); setDrawer(false) }}
        onNew={() => { setSelected(null); setEditing(null); setDrawer(false) }}
        editing={editing} onEdit={setEditing} onSave={() => void saveTitle()}
        onCancelEdit={() => setEditing(null)} onDelete={c => void remove(c)}
        collapsed={folded} onToggleCollapsed={toggleFold}
        mobileOpen={drawer} onCloseMobile={() => setDrawer(false)} />

      <section className="dl-ask__main">
        <div className="dl-ask__bar">
          <button type="button" className="dl-ask__hist-btn" onClick={() => setDrawer(true)}
            aria-label={t('ask.hist.title')} aria-expanded={drawer}>
            <History size={16} aria-hidden /> <span>{t('ask.hist.title')}</span>
          </button>
          <DataPicker items={items} value={scopeKey} onChoose={choose} size="compact" loading={loading} />
        </div>
        <div className="dl-ask__pane">
          {selected !== undefined && (
            sourceId != null
              ? <ChatPane key={scopeKey} dataSourceId={sourceId} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions} />
              : <ChatPane key={scopeKey} datasetIds={[datasetId as number]} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions}
                  datasetColumns={columns?.map(c => c.name)} />
          )}
        </div>
      </section>
    </div>
  )
}
