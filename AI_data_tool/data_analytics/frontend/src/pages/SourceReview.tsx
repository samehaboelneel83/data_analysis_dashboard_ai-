import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { dataSourcesApi, type IndexAdvice } from '../services/api'
import toast from 'react-hot-toast'
import {
  metadataApi,
  type DriftVersion, type ReviewEntity, type ReviewQueue, type ReviewRelationship,
  type SyncRun,
} from '../services/api'
import JoinGraph from '../components/review/JoinGraph'
import SyncProgress from '../components/review/SyncProgress'
import SourceOverview from '../components/review/SourceOverview'
import GlossaryPanel from '../components/review/GlossaryPanel'
import { AuthContext } from '../contexts/AuthContext'
import SuggestFromSourceDialog from '../components/review/SuggestFromSourceDialog'
import LoadError from '../components/ui/LoadError'
import LoadingState from '../components/ui/LoadingState'
import { useT } from '../i18n'
import {
  RelationshipRow, ColumnReview, EntityReview, DriftPanel, SourceHealthPanel,
} from './sourceReview/ReviewPanels'

/**
 * Stage 7 — human confirmation.
 *
 * ARCHITECTURE.md sets the bar explicitly: "Target: a correct semantic model in
 * under ten minutes. If it takes a week of hand-authoring, you have rebuilt Cube
 * with extra steps."
 *
 * Ten minutes is a design constraint, not an aspiration, and it drives two
 * choices here:
 *
 *   * Everything at or above the high-confidence threshold is PRE-SELECTED, so
 *     the common case is one button rather than N decisions. Inference is right
 *     about those often enough that reviewing them one by one is wasted time.
 *
 *   * Every proposal shows its evidence inline rather than behind a click. A
 *     user who has to open something to judge it will instead approve without
 *     looking, which converts a review step into a rubber stamp.
 */
export default function SourceReview() {
  const { id } = useParams<{ id: string }>()
  const sourceId = Number(id)
  const tr = useT()

  const [queue, setQueue] = useState<ReviewQueue | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [entities, setEntities] = useState<ReviewEntity[]>([])
  const [run, setRun] = useState<SyncRun | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [syncing, setSyncing] = useState(false)
  const [tab, setTab] = useState<'graph' | 'columns' | 'entities' | 'glossary'
                                 | 'drift' | 'health'>('graph')
  // The connection-level dashboard proposal. Opened from the header rather
  // than a tab: it is an action taken ON this source, not another view of it.
  const [suggesting, setSuggesting] = useState(false)
  // Writing vocabulary is admin-gated the way the endpoint is; READING it is
  // not, because the glossary is documentation and hiding it helps nobody.
  // `useContext` rather than `useAuth()`: the hook THROWS outside a provider,
  // and this page is rendered without one in its own tests. Reports.tsx reads
  // the admin flag the same way for the same reason. A missing provider must
  // mean "not an admin", never a crashed page.
  const canEdit = !!useContext(AuthContext)?.user?.role?.is_org_admin
  // Schema drift history -- fetched on first open of its tab, not with the
  // page: most visits are about the review queue, and the endpoint had zero
  // callers until this tab existed.
  const [drift, setDrift] = useState<DriftVersion[] | null>(null)
  const [driftError, setDriftError] = useState<string | null>(null)
  // Index advice -- what the platform has watched itself filter on, against
  // the customer's own indexes. Fetched on first open of its tab, like drift:
  // it reads the customer's database, and the review page must not pay that
  // on every load.
  const [advice, setAdvice] = useState<IndexAdvice | null>(null)
  const [adviceError, setAdviceError] = useState<string | null>(null)
  useEffect(() => {
    if (tab !== 'health' || advice !== null) return
    dataSourcesApi.indexAdvice(sourceId)
      .then(setAdvice)
      .catch(() => setAdviceError(tr('pg.dataPages.sr.adviceError')))
  }, [tab, advice, sourceId])

  useEffect(() => {
    if (tab !== 'drift' || drift !== null) return
    metadataApi.drift(sourceId)
      .then(setDrift)
      .catch(() => setDriftError(tr('pg.dataPages.sr.driftError')))
  }, [tab, drift, sourceId])
  const [pollTimer, setPollTimer] = useState<number | null>(null)
  // One search term across both tabs. At 82 tables and 1,354 columns, finding
  // the thing you came for is the primary interaction, not a refinement.
  const [search, setSearch] = useState('')

  // Navigating away mid-sync must not leave a timer running against an
  // unmounted component.
  useEffect(() => () => { if (pollTimer) window.clearInterval(pollTimer) }, [pollTimer])

  // A failed initial load leaves nothing else on the page to show -- the
  // persistent banner below, not a toast that fades and leaves the user
  // staring at a blank page with no explanation or way to retry. Caught here
  // (rather than by callers) so every caller -- the mount effect and the
  // load() calls after each mutation -- gets the same behaviour for free.
  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const [q, latest, ent] = await Promise.all([
        metadataApi.review(sourceId),
        metadataApi.latestSync(sourceId).catch(() => null),
        // Entities are additive (Task R3); a source with none, or an older
        // backend that doesn't yet know the route, must not break the page.
        metadataApi.entities(sourceId).catch(() => []),
      ])
      setQueue(q)
      setRun(latest)
      setEntities(ent)
      // Pre-select the high-confidence proposals. This is what makes the target
      // reachable: the user confirms a batch and reviews only the rest.
      setSelected(new Set(
        q.relationships.filter(r => r.needs_review && r.evidence?.high_confidence)
          .map(r => r.id)
      ))
    } catch (err) {
      setLoadError(err)
    }
  }, [sourceId])

  useEffect(() => { load() }, [load])

  const term = search.trim().toLowerCase()

  const matchesRel = (r: ReviewRelationship) =>
    !term
    || r.from_dataset?.toLowerCase().includes(term)
    || r.to_dataset?.toLowerCase().includes(term)
    || r.from_column.toLowerCase().includes(term)
    || r.to_column.toLowerCase().includes(term)

  const pending = useMemo(
    () => (queue?.relationships ?? []).filter(r => r.needs_review && matchesRel(r)),
    [queue, term],
  )
  const settled = useMemo(
    () => (queue?.relationships ?? []).filter(r => !r.needs_review),
    [queue],
  )

  /** Columns grouped under their table, so 1,354 rows become 82 headings. */
  const columnsByTable = useMemo(() => {
    const grouped = new Map<string, ReviewQueue['columns']>()
    for (const column of queue?.columns ?? []) {
      if (term
          && !column.name.toLowerCase().includes(term)
          && !column.dataset.toLowerCase().includes(term)
          && !(column.description ?? '').toLowerCase().includes(term)) continue
      const bucket = grouped.get(column.dataset) ?? []
      bucket.push(column)
      grouped.set(column.dataset, bucket)
    }
    return grouped
  }, [queue, term])

  const columnsShown = useMemo(
    () => [...columnsByTable.values()].reduce((n, c) => n + c.length, 0),
    [columnsByTable],
  )

  const toggle = (relationshipId: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(relationshipId)) next.delete(relationshipId)
      else next.add(relationshipId)
      return next
    })
  }

  const pollUntilDone = useCallback((runId: number) => {
    // Cleared by whichever branch ends the run, so a finished sync never leaves
    // a timer polling a dead id.
    const timer = window.setInterval(async () => {
      try {
        const latest = await metadataApi.syncStatus(sourceId, runId)
        setRun(latest)
        if (latest.status !== 'running') {
          window.clearInterval(timer)
          setSyncing(false)
          await load()
          const failed = latest.stages.filter(st => st.status === 'failed').length
          if (latest.status === 'ok') toast.success(tr('pg.dataPages.sr.syncFinished'))
          else if (failed) toast.error(tr('pg.dataPages.sr.syncFailedStages', { n: failed }))
          else toast.error(tr('pg.dataPages.sr.syncStatus', { status: latest.status }))
        }
      } catch {
        window.clearInterval(timer)
        setSyncing(false)
        toast.error(tr('pg.dataPages.sr.lostSync'))
      }
    }, 1500)
    setPollTimer(timer)
  }, [sourceId, load, tr])

  // A sync started somewhere ELSE -- by creating the connection, which now sends
  // the user straight here -- must be followed like one started from this page.
  // Without this, arriving mid-sync showed a single frozen snapshot: the stages
  // never advanced, the queue never refilled, and the only way to see the result
  // was to reload a page that gave no hint it needed reloading.
  //
  // Guarded on `syncing` so it cannot race the timer `runSync` already owns, and
  // on `pollTimer` so a re-render does not start a second one.
  useEffect(() => {
    // `id` is optional on SyncRun because the never-run placeholder has none.
    // A run with no id cannot be polled, and pretending otherwise would poll
    // `undefined` and lose the sync rather than follow it.
    if (!run || run.status !== 'running' || run.id == null || syncing || pollTimer) return
    setSyncing(true)
    pollUntilDone(run.id)
  }, [run, syncing, pollTimer, pollUntilDone])

  /**
   * Start a sync and follow it.
   *
   * The request returns as soon as the run row exists, so the stages arrive by
   * polling rather than all at once when the whole thing finishes. On a real
   * source — sampling every table, then a per-table model call — that is the
   * difference between a button that says "Syncing…" for four minutes and a
   * list you can watch fill in.
   */
  const runSync = async () => {
    setSyncing(true)
    try {
      const started = await metadataApi.sync(sourceId)
      setRun({ ...started, stages: [] })
      pollUntilDone(started.sync_run_id)
    } catch (err: any) {
      setSyncing(false)
      // 409 means one is already in flight — a normal outcome, not a fault.
      toast.error(err?.response?.status === 409
        ? tr('pg.dataPages.sr.syncRunning')
        : tr('pg.dataPages.sr.syncStartFailed'))
    }
  }


  const confirmSelected = async () => {
    if (!selected.size) return
    await metadataApi.confirm(sourceId, { relationship_ids: [...selected] })
    toast.success(tr('pg.dataPages.sr.confirmedN', { n: selected.size }))
    await load()
  }

  const reject = async (relationshipId: number) => {
    await metadataApi.confirm(sourceId, { rejected_relationship_ids: [relationshipId] })
    await load()
  }

  const saveDescription = async (columnId: number, description: string) => {
    await metadataApi.confirm(sourceId, { column_updates: [{ id: columnId, description }] })
    toast.success(tr('pg.dataPages.sr.saved'))
    await load()
  }

  const saveEnumLabels = async (columnId: number, labels: Record<string, string>) => {
    await metadataApi.confirm(sourceId, { column_updates: [{ id: columnId, enum_labels: labels }] })
    toast.success(tr('pg.dataPages.sr.saved'))
    await load()
  }

  const saveEntity = async (entityId: number, fields: {
    business_name?: string; grain?: string; description?: string
  }) => {
    await metadataApi.confirmEntities(sourceId, { updates: [{ id: entityId, ...fields }] })
    toast.success(tr('pg.dataPages.sr.saved'))
    await load()
  }

  const confirmEntity = async (entityId: number) => {
    await metadataApi.confirmEntities(sourceId, { updates: [{ id: entityId, confirm: true }] })
    toast.success(tr('pg.dataPages.rev.confirmed'))
    await load()
  }

  if (!queue && loadError != null) {
    return (
      <div style={{ padding: 24 }}>
        <LoadError what="the review queue" title={tr('pg.dataPages.sr.loadError')} error={loadError} onRetry={load} />
      </div>
    )
  }
  if (!queue) return <div style={{ padding: 24 }}><LoadingState /></div>

  return (
    // Full width, like every other page: a 1200px cap left half of a wide
    // screen empty beside the join graph (reported 2026-09-28).
    <div style={{ padding: '24px 32px', width: '100%', boxSizing: 'border-box' }}>
      {/* Title+stats grouped on the start side, the action on the end side --
          matching the space-between header every other list page uses. The
          stats line reads as this page's subtitle (what the numbers below
          mean), so it belongs with the title, not stranded after the button. */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="dl-page-title" style={{ margin: 0, marginBottom: 4 }}>{tr('pg.dataPages.sr.title')}</h1>
          <span style={{ color: 'var(--muted)', fontSize: 13 }}>
            {tr('pg.dataPages.sr.stats', { tables: queue.datasets.length, columns: queue.columns.length, pending: pending.length, settled: settled.length })}
          </span>
        </div>
        <button type="button" className="btn btn-primary" onClick={runSync} disabled={syncing}>
          {syncing
            ? tr('pg.dataPages.sr.syncing', { n: run?.stages?.length ?? 0, total: 6 })
            : tr('pg.dataPages.sr.runSync')}
        </button>
      </header>

      <input
        className="input"
        type="search"
        aria-label={tr('pg.dataPages.sr.searchAria')}
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder={tr('pg.dataPages.sr.searchPlaceholder')}
        style={{ width: '100%', marginBottom: 16, boxSizing: 'border-box' }}
      />

      <SourceOverview
        source={queue.source}
        datasets={queue.datasets}
        busy={syncing}
        onToggleLlm={async (on) => {
          await metadataApi.settings(sourceId, { allow_llm_sampling: on })
          toast.success(on
            ? tr('pg.dataPages.sr.llmOn')
            : tr('pg.dataPages.sr.llmOff'))
          await load()
        }}
        onSaveDescription={async (text) => {
          await metadataApi.settings(sourceId, { description: text })
          toast.success(tr('pg.dataPages.sr.descSaved'))
          await load()
        }}
        onRetrySample={async (objectId) => {
          // Clears the flag only. Deliberately not a sync trigger: one object
          // is not worth a whole run, and someone clearing these usually
          // clears several before starting one.
          await metadataApi.confirm(sourceId, {
            object_updates: [{ id: objectId, retry_sample: true }],
          })
          toast.success(tr('pg.dataPages.sr.resample'))
          await load()
        }}
        onToggleCanonical={async (objectId, canonical) => {
          await metadataApi.confirm(sourceId, {
            object_updates: [{ id: objectId, is_canonical: canonical }],
          })
          toast.success(canonical
            ? tr('pg.dataPages.sr.canonicalOn')
            : tr('pg.dataPages.sr.canonicalOff'))
          await load()
        }}
      />

      <section className="card" style={{ marginBottom: 20, padding: 12,
        display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1 }}><SyncProgress run={run} /></div>
        {/* The step BEFORE a dataset exists: someone has connected a database,
            has no dataset, and does not know which of its tables to join. The
            backend has answered this since it shipped and nothing called it. */}
        <button type="button" className="btn btn-primary" onClick={() => setSuggesting(true)}
          style={{ whiteSpace: 'nowrap', alignSelf: 'flex-start' }}>
          {tr('pg.dataPages.sr.suggest')}
        </button>
      </section>

      {suggesting && (
        <SuggestFromSourceDialog sourceId={sourceId} sourceName={queue.source.name}
                                 synced={(queue.datasets ?? []).length > 0}
                                 onClose={() => setSuggesting(false)} />
      )}

      {/* A tab strip, the current tab marked as selected -- they were plain
          browser buttons, the current one shown only by being disabled. */}
      <div role="tablist" aria-label={tr('pg.dataPages.sr.tabsAria')} className="dl-review-tabs"
        style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap',
          borderBottom: '1px solid var(--border)' }}>
        {([
          ['graph', tr('pg.dataPages.sr.tabRelationships', { n: pending.length })],
          ['columns', tr('pg.dataPages.sr.tabColumns', { n: columnsShown })],
          ['entities', tr('pg.dataPages.sr.tabEntities', { n: entities.length })],
          ['glossary', tr('pg.dataPages.sr.tabGlossary')],
          ['drift', tr('pg.dataPages.sr.tabDrift')],
          ['health', tr('pg.dataPages.sr.tabHealth')],
        ] as const).map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key}
            className="btn btn-ghost btn-sm" onClick={() => setTab(key)}
            style={{ borderRadius: '6px 6px 0 0', marginBottom: -1,
              borderBottom: tab === key ? '2px solid var(--accent)' : '2px solid transparent',
              color: tab === key ? 'var(--accent)' : undefined, fontWeight: tab === key ? 600 : undefined }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'graph' ? (
        <>
          <JoinGraph queue={queue} selectedIds={selected} onToggle={toggle}
                     filter={search} />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '12px 0' }}>
            <button type="button" className="btn btn-primary" onClick={confirmSelected} disabled={!selected.size} title={!selected.size ? tr('pg.dataPages.sr.tickFirst') : undefined}>
              {tr('pg.dataPages.sr.confirmSelected', { n: selected.size })}
            </button>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              {tr('pg.dataPages.sr.preselected')}
            </span>
          </div>

          {pending.map(rel => (
            <RelationshipRow
              key={rel.id}
              rel={rel}
              checked={selected.has(rel.id)}
              onToggle={() => toggle(rel.id)}
              onReject={() => reject(rel.id)}
            />
          ))}
          {!pending.length && (
            <p style={{ color: '#16785a', fontSize: 14 }}>
              {tr('pg.dataPages.sr.nothingPending')}
            </p>
          )}
        </>
      ) : tab === 'columns' ? (
        <ColumnReview grouped={columnsByTable} total={columnsShown}
                      onSave={saveDescription} onSaveLabels={saveEnumLabels} />
      ) : tab === 'entities' ? (
        <EntityReview entities={entities} onSave={saveEntity} onConfirm={confirmEntity} />
      ) : tab === 'glossary' ? (
        <GlossaryPanel sourceId={sourceId} canEdit={canEdit}
                       objectNames={(queue.datasets ?? []).map(d => d.name)} />
      ) : tab === 'drift' ? (
        <DriftPanel drift={drift} error={driftError} />
      ) : (
        <SourceHealthPanel advice={advice} error={adviceError} />
      )}
    </div>
  )
}
