import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import ChatPane from '../components/chat/ChatPane'
import { agentApi, datasetsApi, dataSourcesApi } from '../services/api'
import type { AgentConversation } from '../services/api'
import { useT } from '../i18n'

/**
 * The agent's own page: a scope picker (which dataset, or which live
 * connection, to ask about), the threads already held about that scope, and
 * the pane.
 *
 * The scope is in the URL (`/ask?dataset=32`, `/ask?source=3`) so a question
 * about a specific dataset can be LINKED to -- DatasetDetail's "Ask about
 * this data" points here.
 *
 * The page owns the conversation list. It shows the user's threads for the
 * current scope, newest first, opens the newest by default, and hands the
 * chosen id to the pane (`conversationId`); "New chat" hands it null and the
 * pane reports back the thread its first question creates. Before this the
 * pane silently resumed the newest server thread and could not show it, so
 * every visit looked like a blank slate over a growing history.
 */

function inScope(c: AgentConversation, sourceId: number | null, datasetId: number | null): boolean {
  if (sourceId != null) return c.data_source_id === sourceId
  if (datasetId != null) return c.data_source_id == null && (c.dataset_ids ?? []).length === 1 && c.dataset_ids![0] === datasetId
  return false
}

function when(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export default function AskAI() {
  const t = useT()
  const [params, setParams] = useSearchParams()
  const [datasets, setDatasets] = useState<{ id: number; name: string }[]>([])
  const [sources, setSources] = useState<{ id: number; name: string }[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [conversations, setConversations] = useState<AgentConversation[]>([])
  // undefined = not decided yet (list still loading); null = a fresh thread.
  const [selected, setSelected] = useState<number | null | undefined>(undefined)
  const [editing, setEditing] = useState<{ id: number; title: string } | null>(null)

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
        // DirectQuery datasets keep their rows in the connection, so the
        // agent's dataset mode -- which answers out of a file frame -- has
        // nothing to read and the API refuses them with a 400. The connection
        // is the live-data path and is already listed below, so leaving these
        // out removes a dead choice rather than a capability.
        setDatasets(ds.filter(d => d.mode !== 'directquery' && d.filename)
                      .map(d => ({ id: d.id, name: d.name })))
        setSources(srcs.map(s => ({ id: s.id, name: s.name })))
      })
      // A failed dataset list must not read as "no data yet" -- an error
      // dressed as an empty state is the defect, not a degradation.
      .catch((e: any) => setError(e?.response?.data?.detail ?? 'Failed to load your data'))
      .finally(() => setLoading(false))
  }, [])

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
    // value is "d:32" or "s:3" or "" -- one select, two scope kinds, because
    // the question "what am I asking about?" has one answer, not two fields.
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
    if (!window.confirm(`Delete "${c.title}"? Its messages go with it.`)) return
    try {
      await agentApi.remove(c.id)
    } catch {
      return
    }
    setConversations(list => list.filter(x => x.id !== c.id))
    if (selected === c.id) setSelected(null)
  }

  const current = scopeKey
  const scoped = sourceId != null || datasetId != null

  const iconBtn: React.CSSProperties = {
    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)',
    padding: 2, display: 'inline-flex', borderRadius: 4,
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200, display: 'flex', flexDirection: 'column',
      height: '100%', boxSizing: 'border-box' }}>
      <h1 style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>{t('nav.askAi')}</h1>
      <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
        {t('ask.subtitle')}
      </p>

      <div style={{ marginBottom: 12 }}>
        <select value={current} onChange={e => choose(e.target.value)} aria-label={t('ask.scope')}
          style={{ fontSize: 12, padding: '6px 8px', background: 'var(--surface2)',
            border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text)', minWidth: 260 }}>
          <option value="">{t('ask.choose')}</option>
          {datasets.length > 0 && (
            <optgroup label={t('nav.datasets')}>
              {datasets.map(d => <option key={`d${d.id}`} value={`d:${d.id}`}>{d.name}</option>)}
            </optgroup>
          )}
          {sources.length > 0 && (
            <optgroup label={t('ask.liveConnections')}>
              {sources.map(s => <option key={`s${s.id}`} value={`s:${s.id}`}>{s.name}</option>)}
            </optgroup>
          )}
        </select>
      </div>

      {error && (
        <div role="alert" className="card" style={{ padding: 16, color: 'var(--negative, #e2606c)' }}>{error}</div>
      )}

      {!scoped && !loading && !error && (
        <div className="card" style={{ padding: '40px 24px', textAlign: 'center', color: 'var(--muted)' }}>
          {datasets.length === 0 && sources.length === 0
            ? 'No data yet — upload a dataset or add a connection first.'
            : 'Pick a dataset or connection above to start asking.'}
        </div>
      )}

      {scoped && (
        <div style={{ flex: 1, minHeight: 0, display: 'flex', gap: 16 }}>
          <aside style={{ width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column',
            gap: 8, minHeight: 0 }}>
            <button onClick={() => { setSelected(null); setEditing(null) }}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12.5, fontWeight: 600,
                padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border)',
                background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer' }}>
              <Plus size={14} aria-hidden /> New chat
            </button>
            <ul aria-label="Conversations" style={{ listStyle: 'none', margin: 0, padding: 0,
              overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
              {conversations.length === 0 && (
                <li style={{ fontSize: 12, color: 'var(--muted)', padding: '6px 8px' }}>
                  No conversations yet.
                </li>
              )}
              {conversations.map(c => (
                <li key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 4,
                  padding: '4px 6px', borderRadius: 6,
                  background: selected === c.id ? 'var(--accent-soft)' : 'transparent' }}>
                  {editing?.id === c.id ? (
                    <input aria-label="Title" autoFocus value={editing.title}
                      onChange={e => setEditing({ id: c.id, title: e.target.value })}
                      onKeyDown={e => {
                        if (e.key === 'Enter') void saveTitle()
                        if (e.key === 'Escape') setEditing(null)
                      }}
                      onBlur={() => void saveTitle()}
                      style={{ flex: 1, minWidth: 0, fontSize: 12.5, padding: '4px 6px',
                        border: '1px solid var(--accent)', borderRadius: 4,
                        background: 'var(--surface)', color: 'var(--text)' }} />
                  ) : (
                    <button onClick={() => setSelected(c.id)} title={c.title}
                      style={{ flex: 1, minWidth: 0, textAlign: 'start', background: 'none',
                        border: 'none', cursor: 'pointer', padding: '4px 4px', fontSize: 12.5,
                        color: selected === c.id ? 'var(--accent)' : 'var(--text)',
                        fontWeight: selected === c.id ? 600 : 400, display: 'flex',
                        flexDirection: 'column', gap: 1, overflow: 'hidden' }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', width: '100%' }}>
                        {c.title}
                      </span>
                      {when(c.created_at) && (
                        <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>{when(c.created_at)}</span>
                      )}
                    </button>
                  )}
                  <button aria-label={`Rename ${c.title}`} title="Rename" style={iconBtn}
                    onClick={() => setEditing({ id: c.id, title: c.title })}>
                    <Pencil size={13} aria-hidden />
                  </button>
                  <button aria-label={`Delete ${c.title}`} title="Delete" style={iconBtn}
                    onClick={() => void remove(c)}>
                    <Trash2 size={13} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <div style={{ flex: 1, minWidth: 0, minHeight: 0, display: 'flex', flexDirection: 'column',
            border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)' }}>
            {selected !== undefined && (
              sourceId != null
                ? <ChatPane key={scopeKey} dataSourceId={sourceId} conversationId={selected}
                    onConversationCreated={created} />
                : <ChatPane key={scopeKey} datasetIds={[datasetId as number]} conversationId={selected}
                    onConversationCreated={created} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
