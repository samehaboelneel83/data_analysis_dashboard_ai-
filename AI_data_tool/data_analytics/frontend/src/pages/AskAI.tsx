import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bot, Columns3, History } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import ChatPane from '../components/chat/ChatPane'
import { agentApi, analysisApi, datasetsApi, dataSourcesApi } from '../services/api'
import type { AgentConversation, Dataset, DatasetColumn } from '../services/api'
import { useT } from '../i18n'
import DataPicker, { type PickerItem } from './ask/DataPicker'
import HistoryPanel from './ask/HistoryPanel'
import ColumnPanel, { readColumnsFold } from './ask/ColumnPanel'
import DataChooser from './ask/DataChooser'
import Composer from '../components/chat/Composer'
import type { Analysis } from './datasetDetail/columnProfile'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { localDigits } from '../lib/arabicFormats'
import { sourceWords } from './datasetsList/classify'
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
 *  - A scope: the threads held about it (History) beside the chat, and the
 *    dataset's columns on the other side (redesign 4a): History | thread |
 *    Columns, edge to edge, the scope named in a bar over the thread.
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
  // Every thread, whatever it asks about: the no-scope page lists them all
  // and counts them per dataset for "Recently asked about" (4b).
  const [allConvs, setAllConvs] = useState<AgentConversation[]>([])
  // A thread picked before its scope was open: opened once the scope loads.
  const wanted = useRef<number | null>(null)
  const [profile, setProfile] = useState<Analysis>(null)
  // undefined = not decided yet (list still loading); null = a fresh thread.
  const [selected, setSelected] = useState<number | null | undefined>(undefined)
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null)
  const [folded, setFolded] = useState(readFold)
  const [drawer, setDrawer] = useState(false)
  const [colsFolded, setColsFolded] = useState(readColumnsFold)
  const [colsDrawer, setColsDrawer] = useState(false)
  const [insert, setInsert] = useState<{ text: string; seq: number } | null>(null)
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
    let alive = true
    setSelected(undefined)
    setEditing(null)
    setInsert(null)
    agentApi.listConversations()
      .then(all => {
        if (!alive) return
        setAllConvs([...all].sort((a, b) => b.id - a.id))
        if (!scopeKey) return
        const mine = all.filter(c => inScope(c, sourceId, datasetId)).sort((a, b) => b.id - a.id)
        setConversations(mine)
        const pick = mine.find(c => c.id === wanted.current)
        wanted.current = null
        setSelected(pick ? pick.id : mine.length ? mine[0].id : null)
      })
      .catch(() => { if (alive) { setConversations([]); setSelected(null) } })
    return () => { alive = false }
  }, [scopeKey, sourceId, datasetId])

  // The dataset's saved profile: value counts and ranges for the columns
  // panel and the clarification's column options. Read once, shared.
  useEffect(() => {
    setProfile(null)
    if (datasetId == null) return
    let alive = true
    Promise.resolve().then(() => analysisApi?.get?.(datasetId))
      .then(a => { if (alive && a) setProfile(a) }).catch(() => {})
    return () => { alive = false }
  }, [datasetId])

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
      setAllConvs(list => list.map(c => c.id === id ? { ...c, title: got.title } : c))
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
    setAllConvs(list => list.filter(x => x.id !== c.id))
    if (selected === c.id) setSelected(null)
  }

  const toggleFold = () => setFolded(f => {
    try { localStorage.setItem(FOLD_KEY, f ? '0' : '1') } catch { /* a convenience */ }
    return !f
  })

  const toggleCols = () => setColsFolded(f => {
    try { localStorage.setItem('datalytics.ask.columnsFolded', f ? '0' : '1') } catch { /* a convenience */ }
    return !f
  })

  const scoped = sourceId != null || datasetId != null
  const dataset = datasetId != null ? usableDatasets.find(d => d.id === datasetId) : undefined
  const scopeName = dataset?.name ?? (sourceId != null ? sourceItems.find(s => s.key === `s:${sourceId}`)?.name : undefined)
  const columnValues = useMemo(() => {
    const out: Record<string, number> = {}
    for (const [c, v] of Object.entries(profile?.categorical?.columns ?? {})) {
      if ((v as { n_unique?: number }).n_unique != null) out[c] = (v as { n_unique: number }).n_unique
    }
    return out
  }, [profile])
  // A thread's target, in words, for the no-scope history list.
  const targetName = (c: AgentConversation) => c.data_source_id != null
    ? sourceItems.find(s => s.key === `s:${c.data_source_id}`)?.name
    : usableDatasets.find(d => d.id === c.dataset_ids?.[0])?.name
  const openThread = (c: AgentConversation) => {
    wanted.current = c.id
    choose(c.data_source_id != null ? `s:${c.data_source_id}` : `d:${c.dataset_ids?.[0]}`)
  }
  // "Uploaded file · 3,612 rows · 9 columns", beside the picker.
  const scopeMeta = dataset ? [
    sourceWords(dataset, null, t),
    t('ask3.rowsCols', {
      rows: localDigits((dataset.row_count ?? 0).toLocaleString('en-US')),
      cols: localDigits(String(dataset.col_count ?? dataset.columns?.length ?? 0)),
    }),
  ].join(' · ') : ''
  const columns = datasetId != null ? columnsById[datasetId] : undefined
  const suggestions = useMemo(
    () => (sourceId != null ? connectionSuggestions(t) : datasetSuggestions(columns, t)),
    [sourceId, columns, t],
  )
  const noData = !loading && !error && items.length === 0

  const history = (list: AgentConversation[], unscoped: boolean) => (
    <HistoryPanel
      conversations={list} selected={unscoped ? undefined : selected}
      onSelect={id => {
        setDrawer(false)
        if (unscoped) { const c = list.find(x => x.id === id); if (c) openThread(c) } else setSelected(id)
      }}
      onNew={() => {
        setEditing(null); setDrawer(false)
        if (unscoped) document.getElementById('dl-choose-search')?.focus(); else setSelected(null)
      }}
      editing={editing} onEdit={setEditing} onSave={() => void saveTitle()}
      onCancelEdit={() => setEditing(null)} onDelete={c => void remove(c)}
      collapsed={folded} onToggleCollapsed={toggleFold}
      mobileOpen={drawer} onCloseMobile={() => setDrawer(false)}
      describe={unscoped ? targetName : undefined}
      emptyText={unscoped ? undefined : t('askh.firstEmpty')} />
  )

  if (!scoped) {
    // No scope yet (4b): the same three columns, the thread replaced by the
    // chooser and the composer locked until data is picked.
    return (
      <div className="dl-ask dl-ask--work dl-ask--choose">
        {history(allConvs, true)}
        <section className="dl-ask__main">
          <div className="dl-ask__bar">
            <button type="button" className="dl-ask__hist-btn" onClick={() => setDrawer(true)}
              aria-label={t('ask.hist.title')} aria-expanded={drawer}>
              <History size={16} aria-hidden /> <span>{t('ask.hist.title')}</span>
            </button>
            <span className="dl-ask__bar-hint">{t('nods.choose')}</span>
          </div>
          <div className="dl-ask__pane">
            <div className="dl-chat__scroll">
              {error && <div role="alert" className="dl-ask__error">{error}</div>}
              {noData ? (
                <EmptyState icon={Bot} title={t('ask.noData')}
                  action={<Link to="/upload" className="btn btn-primary">{t('ask.uploadDataset')}</Link>} />
              ) : loading ? (
                <p className="dl-chat__note">{t('common.loading')}</p>
              ) : !error && (
                <DataChooser datasets={clean.visible} sources={sourceItems} conversations={allConvs}
                  onChoose={choose} footer={<DatasetListFilter state={clean} />} />
              )}
            </div>
            <div className="dl-chat__composer">
              <Composer value="" onChange={() => {}} onSend={() => {}} locked lockedHint={t('nods.choose')} />
            </div>
          </div>
        </section>
        <aside className="dl-cols3 dl-cols3--idle" aria-label={t('ask3.columns')}>
          <p className="dl-cols3__idle">{t('nods.choose')}</p>
        </aside>
      </div>
    )
  }

  return (
    <div className={`dl-ask dl-ask--work${columns?.length ? ' dl-ask--cols' : ''}`}>
      {history(conversations, false)}

      <section className="dl-ask__main">
        <div className="dl-ask__bar">
          <button type="button" className="dl-ask__hist-btn" onClick={() => setDrawer(true)}
            aria-label={t('ask.hist.title')} aria-expanded={drawer}>
            <History size={16} aria-hidden /> <span>{t('ask.hist.title')}</span>
          </button>
          <div className="dl-ask__scope">
            <DataPicker items={items} value={scopeKey} onChoose={choose} size="compact" loading={loading} />
            {scopeMeta && <span className="dl-ask__scope-meta">{scopeMeta}</span>}
          </div>
          {columns && columns.length > 0 && (
            <button type="button" className="dl-ask__hist-btn dl-ask__cols-btn" onClick={() => setColsDrawer(true)}
              aria-expanded={colsDrawer}>
              <Columns3 size={16} aria-hidden /> <span>{t('ask3.columns')}</span>
            </button>
          )}
        </div>
        <div className="dl-ask__pane">
          {selected !== undefined && (
            sourceId != null
              ? <ChatPane key={scopeKey} dataSourceId={sourceId} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions} variant="page"
                  datasetName={scopeName} insertRequest={insert} />
              : <ChatPane key={scopeKey} datasetIds={[datasetId as number]} conversationId={selected}
                  onConversationCreated={created} suggestions={suggestions}
                  datasetColumns={columns?.map(c => c.name)} variant="page"
                  datasetName={scopeName} insertRequest={insert}
                  scopeRows={dataset?.row_count ?? null} columnValues={columnValues} />
          )}
        </div>
      </section>

      {datasetId != null && columns && columns.length > 0 && (
        <ColumnPanel profile={profile} columns={columns}
          onInsert={name => { setInsert(r => ({ text: name, seq: (r?.seq ?? 0) + 1 })); setColsDrawer(false) }}
          collapsed={colsFolded && !colsDrawer} onToggle={toggleCols}
          mobileOpen={colsDrawer} onCloseMobile={() => setColsDrawer(false)} />
      )}
    </div>
  )
}
