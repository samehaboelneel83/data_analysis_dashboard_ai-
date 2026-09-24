import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { metadataApi, type GlossaryTerm } from '../../services/api'
import LoadError from '../ui/LoadError'
import LoadingState from '../ui/LoadingState'

/**
 * What the business calls things.
 *
 * The three endpoints behind this panel shipped with the retrieval work and had
 * no caller at all until it existed. The consequence was specific and bad: the
 * agent's context loader reads `glossary_terms` on every question, the dashboard
 * designer's prompt now carries a BUSINESS TERMS block, and the table they both
 * read could only ever be empty, because nothing in the product could put a row
 * in it. A model asked for "GMV" had to guess which column that was, and guessed
 * quietly.
 *
 * Synonyms are the reason this is a table rather than a description field:
 * "GMV" and "إجمالي المبيعات" must resolve to the same metric, and matching is a
 * plain case/unicode-fold containment check, so an alias list is all it takes.
 *
 * Terms created here are scoped to THIS connection -- that is what the endpoint
 * does. Org-wide terms (`data_source_id: null`) still appear in the list,
 * marked, because they apply here too; they are not created from this screen.
 */
export interface GlossaryPanelProps {
  sourceId: number
  /** Only an org admin may write. A member still reads the vocabulary -- it is
   *  documentation, and hiding it would make the terms less useful, not safer. */
  canEdit: boolean
  /** Object names from the catalog, offered as the optional mapping target. */
  objectNames?: string[]
}

const input: React.CSSProperties = {
  fontSize: 12, padding: '5px 8px', background: 'var(--surface2)',
  border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text)',
  boxSizing: 'border-box', width: '100%',
}

export default function GlossaryPanel({ sourceId, canEdit, objectNames }: GlossaryPanelProps) {
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState({
    term: '', definition: '', synonyms: '', maps_to_object: '', maps_to_column: '',
  })

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setTerms(await metadataApi.glossary(sourceId))
    } catch (e) {
      // A persistent banner, not a toast: a failed load leaves nothing else on
      // the panel, and a message that fades leaves the reader with a blank box
      // and no way to retry.
      setLoadError(e)
    }
  }, [sourceId])

  useEffect(() => { void load() }, [load])

  const save = async () => {
    const term = draft.term.trim()
    if (!term) { toast.error('A term needs a name'); return }
    setBusy(true)
    try {
      await metadataApi.addTerm(sourceId, {
        term,
        definition: draft.definition.trim() || undefined,
        // Comma-separated in, list out. Every separator that is not a comma --
        // Arabic comma included -- is a character somebody may legitimately want
        // inside a term, so only the comma splits.
        synonyms: draft.synonyms.split(',').map(s => s.trim()).filter(Boolean),
        maps_to_object: draft.maps_to_object.trim() || undefined,
        maps_to_column: draft.maps_to_column.trim() || undefined,
      })
      setDraft({ term: '', definition: '', synonyms: '', maps_to_object: '', maps_to_column: '' })
      setAdding(false)
      await load()
      toast.success('Term added')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not add the term')
    } finally { setBusy(false) }
  }

  const remove = async (t: GlossaryTerm) => {
    setBusy(true)
    try {
      await metadataApi.deleteTerm(sourceId, t.id)
      await load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not delete the term')
    } finally { setBusy(false) }
  }

  if (loadError) return <LoadError what="the glossary" error={loadError} onRetry={() => void load()} />
  if (terms === null) return <LoadingState label="Loading the glossary" />

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>Business terms</h3>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
          What your organisation calls things. The agent and the dashboard
          designer both read these, so a term defined once is understood
          everywhere.
        </span>
        <span style={{ flex: 1 }} />
        {canEdit && !adding && (
          <button onClick={() => setAdding(true)} disabled={busy}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
              padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border)',
              background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer' }}>
            <Plus size={12} /> Add a term
          </button>
        )}
      </div>

      {adding && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 12,
          marginBottom: 12, display: 'grid', gap: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 8 }}>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Term
              <input style={input} value={draft.term} autoFocus
                placeholder="GMV"
                onChange={e => setDraft({ ...draft, term: e.target.value })} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              What it means
              <input style={input} value={draft.definition}
                placeholder="Gross merchandise value, before returns."
                onChange={e => setDraft({ ...draft, definition: e.target.value })} />
            </label>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Also called (comma separated)
              <input style={input} value={draft.synonyms}
                placeholder="إجمالي المبيعات, gross sales"
                onChange={e => setDraft({ ...draft, synonyms: e.target.value })} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Table (optional)
              <input style={input} value={draft.maps_to_object} list="glossary-objects"
                onChange={e => setDraft({ ...draft, maps_to_object: e.target.value })} />
              <datalist id="glossary-objects">
                {(objectNames ?? []).map(n => <option key={n} value={n} />)}
              </datalist>
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              Column (optional)
              <input style={input} value={draft.maps_to_column}
                onChange={e => setDraft({ ...draft, maps_to_column: e.target.value })} />
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => void save()} disabled={busy}
              style={{ fontSize: 12, padding: '5px 12px', borderRadius: 6, border: 'none',
                background: 'var(--accent)', color: 'var(--mc-accent-fg)', cursor: 'pointer' }}>
              {busy ? 'Saving…' : 'Save'}
            </button>
            <button onClick={() => setAdding(false)} disabled={busy}
              style={{ fontSize: 12, padding: '5px 12px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text)', cursor: 'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {terms.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
          No terms yet. {canEdit
            ? 'Add the words your team uses that this database does not spell out — an alias in another language counts.'
            : 'An administrator can add the words your team uses for this data.'}
        </p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>Term</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>Means</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>Also called</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>Maps to</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {terms.map(t => (
              <tr key={t.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>
                  {t.term}
                  {t.data_source_id === null && (
                    <span style={{ marginInlineStart: 6, fontSize: 10, fontWeight: 400,
                      color: 'var(--muted)' }}>
                      organisation-wide
                    </span>
                  )}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{t.definition || '—'}</td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>
                  {(t.synonyms ?? []).join(', ') || '—'}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>
                  {t.maps_to_column
                    ? `${t.maps_to_object ? `${t.maps_to_object}.` : ''}${t.maps_to_column}`
                    : (t.maps_to_object || '—')}
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'end' }}>
                  {/* An org-wide term is not this connection's to delete: it is
                      in use on every other source too, and the endpoint refuses
                      it. Offering the button anyway would be a dead control. */}
                  {canEdit && t.data_source_id !== null && (
                    <button aria-label={`Delete ${t.term}`} disabled={busy}
                      onClick={() => void remove(t)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer',
                        color: 'var(--muted)', padding: 2 }}>
                      <Trash2 size={13} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
