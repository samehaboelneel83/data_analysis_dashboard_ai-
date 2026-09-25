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
      .catch(() => setAdviceError('Could not load index advice'))
  }, [tab, advice, sourceId])

  useEffect(() => {
    if (tab !== 'drift' || drift !== null) return
    metadataApi.drift(sourceId)
      .then(setDrift)
      .catch(() => setDriftError('Could not load drift history'))
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
          if (latest.status === 'ok') toast.success('Sync finished')
          else if (failed) toast.error(`Sync finished with ${failed} failed stage(s)`)
          else toast.error(`Sync ${latest.status}`)
        }
      } catch {
        window.clearInterval(timer)
        setSyncing(false)
        toast.error('Lost track of the sync — reload to see where it got to')
      }
    }, 1500)
    setPollTimer(timer)
  }, [sourceId, load])

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
        ? 'A sync is already running for this source'
        : 'Could not start the sync')
    }
  }


  const confirmSelected = async () => {
    if (!selected.size) return
    await metadataApi.confirm(sourceId, { relationship_ids: [...selected] })
    toast.success(`Confirmed ${selected.size} relationship${selected.size === 1 ? '' : 's'}`)
    await load()
  }

  const reject = async (relationshipId: number) => {
    await metadataApi.confirm(sourceId, { rejected_relationship_ids: [relationshipId] })
    await load()
  }

  const saveDescription = async (columnId: number, description: string) => {
    await metadataApi.confirm(sourceId, { column_updates: [{ id: columnId, description }] })
    toast.success('Saved')
    await load()
  }

  const saveEnumLabels = async (columnId: number, labels: Record<string, string>) => {
    await metadataApi.confirm(sourceId, { column_updates: [{ id: columnId, enum_labels: labels }] })
    toast.success('Saved')
    await load()
  }

  const saveEntity = async (entityId: number, fields: {
    business_name?: string; grain?: string; description?: string
  }) => {
    await metadataApi.confirmEntities(sourceId, { updates: [{ id: entityId, ...fields }] })
    toast.success('Saved')
    await load()
  }

  const confirmEntity = async (entityId: number) => {
    await metadataApi.confirmEntities(sourceId, { updates: [{ id: entityId, confirm: true }] })
    toast.success('Confirmed')
    await load()
  }

  if (!queue && loadError != null) {
    return (
      <div style={{ padding: 24 }}>
        <LoadError what="the review queue" error={loadError} onRetry={load} />
      </div>
    )
  }
  if (!queue) return <div style={{ padding: 24 }}><LoadingState /></div>

  return (
    <div style={{ padding: 24, maxWidth: 1200 }}>
      {/* Title+stats grouped on the start side, the action on the end side --
          matching the space-between header every other list page uses. The
          stats line reads as this page's subtitle (what the numbers below
          mean), so it belongs with the title, not stranded after the button. */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 className="dl-page-title" style={{ margin: 0, marginBottom: 4 }}>Review data source</h1>
          <span style={{ color: '#64748b', fontSize: 13 }}>
            {queue.datasets.length} tables · {queue.columns.length} columns ·{' '}
            {pending.length} awaiting review · {settled.length} settled
          </span>
        </div>
        <button onClick={runSync} disabled={syncing}>
          {syncing
            ? `Syncing… ${run?.stages?.length ?? 0}/6`
            : 'Run sync'}
        </button>
      </header>

      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search tables, columns and descriptions…"
        style={{ width: '100%', padding: '8px 10px', marginBottom: 16,
                 fontSize: 13, border: '1px solid #cbd5e1', borderRadius: 4 }}
      />

      <SourceOverview
        source={queue.source}
        datasets={queue.datasets}
        busy={syncing}
        onToggleLlm={async (on) => {
          await metadataApi.settings(sourceId, { allow_llm_sampling: on })
          toast.success(on
            ? 'The model will describe this source on the next sync'
            : 'Model descriptions switched off for this source')
          await load()
        }}
        onSaveDescription={async (text) => {
          await metadataApi.settings(sourceId, { description: text })
          toast.success('Description saved')
          await load()
        }}
        onRetrySample={async (objectId) => {
          // Clears the flag only. Deliberately not a sync trigger: one object
          // is not worth a whole run, and someone clearing these usually
          // clears several before starting one.
          await metadataApi.confirm(sourceId, {
            object_updates: [{ id: objectId, retry_sample: true }],
          })
          toast.success('It will be sampled again on the next sync')
          await load()
        }}
        onToggleCanonical={async (objectId, canonical) => {
          await metadataApi.confirm(sourceId, {
            object_updates: [{ id: objectId, is_canonical: canonical }],
          })
          toast.success(canonical
            ? 'Marked as the source of truth for what it describes'
            : 'No longer marked canonical')
          await load()
        }}
      />

      <section style={{ marginBottom: 20, padding: 12, background: '#f8fafc',
        borderRadius: 6, display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ flex: 1 }}><SyncProgress run={run} /></div>
        {/* The step BEFORE a dataset exists: someone has connected a database,
            has no dataset, and does not know which of its tables to join. The
            backend has answered this since it shipped and nothing called it. */}
        <button onClick={() => setSuggesting(true)}
          style={{ fontSize: 12, padding: '6px 12px', borderRadius: 6, border: 'none',
            background: 'var(--accent, #2563eb)', color: 'var(--mc-accent-fg)', cursor: 'pointer',
            whiteSpace: 'nowrap' }}>
          Suggest a dashboard
        </button>
      </section>

      {suggesting && (
        <SuggestFromSourceDialog sourceId={sourceId} sourceName={queue.source.name}
                                 synced={(queue.datasets ?? []).length > 0}
                                 onClose={() => setSuggesting(false)} />
      )}

      <nav style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <button onClick={() => setTab('graph')} disabled={tab === 'graph'}>
          Relationships ({pending.length})
        </button>
        <button onClick={() => setTab('columns')} disabled={tab === 'columns'}>
          Columns ({columnsShown})
        </button>
        <button onClick={() => setTab('entities')} disabled={tab === 'entities'}>
          Entities ({entities.length})
        </button>
        <button onClick={() => setTab('glossary')} disabled={tab === 'glossary'}>
          Business terms
        </button>
        <button onClick={() => setTab('drift')} disabled={tab === 'drift'}>
          Schema drift
        </button>
        <button onClick={() => setTab('health')} disabled={tab === 'health'}>
          Source health
        </button>
      </nav>

      {tab === 'graph' ? (
        <>
          <JoinGraph queue={queue} selectedIds={selected} onToggle={toggle}
                     filter={search} />

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '12px 0' }}>
            <button onClick={confirmSelected} disabled={!selected.size} title={!selected.size ? 'Tick at least one suggestion first' : undefined}>
              Confirm {selected.size} selected
            </button>
            <span style={{ fontSize: 12, color: '#64748b' }}>
              High-confidence proposals are pre-selected.
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
              Nothing awaiting review. Every proposed relationship has been decided.
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
