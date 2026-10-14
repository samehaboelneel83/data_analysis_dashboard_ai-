import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { metadataApi, type GlossaryTerm } from '../../services/api'
import LoadError from '../ui/LoadError'
import LoadingState from '../ui/LoadingState'
import { useT } from '../../i18n'

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
  const tr = useT()
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState({
    term: '', definition: '', synonyms: '', maps_to_object: '', maps_to_column: '',
    rule: '', always: false,
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
    if (!term) { toast.error(tr('pg.dataPages.gl.needsName')); return }
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
        rule: draft.rule.trim() || undefined,
        always: draft.always,
      })
      setDraft({ term: '', definition: '', synonyms: '', maps_to_object: '', maps_to_column: '', rule: '', always: false })
      setAdding(false)
      await load()
      toast.success(tr('pg.dataPages.gl.added'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? tr('pg.dataPages.gl.addFailed'))
    } finally { setBusy(false) }
  }

  const setAlways = async (t: GlossaryTerm, always: boolean) => {
    setBusy(true)
    try {
      await metadataApi.updateTerm(sourceId, t.id, { always })
      await load()
      toast.success(always ? tr('pg.dataPages.gl.nowAlways', { name: t.term }) : tr('pg.dataPages.gl.nowNamed', { name: t.term }))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? tr('pg.dataPages.gl.updateFailed'))
    } finally { setBusy(false) }
  }

  const editRule = async (t: GlossaryTerm, rule: string) => {
    if ((t.rule ?? '') === rule.trim()) return
    setBusy(true)
    try {
      await metadataApi.updateTerm(sourceId, t.id, { rule: rule.trim() || null })
      await load()
      toast.success(tr('pg.dataPages.gl.ruleSaved'))
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? tr('pg.dataPages.gl.ruleFailed'))
    } finally { setBusy(false) }
  }

  const remove = async (t: GlossaryTerm) => {
    setBusy(true)
    try {
      await metadataApi.deleteTerm(sourceId, t.id)
      await load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? tr('pg.dataPages.gl.deleteFailed'))
    } finally { setBusy(false) }
  }

  if (loadError) return <LoadError what="the glossary" title={tr('pg.dataPages.gl.loadError')} error={loadError} onRetry={() => void load()} />
  if (terms === null) return <LoadingState label={tr('pg.dataPages.gl.loading')} />

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>{tr('pg.dataPages.sr.tabGlossary')}</h3>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
          {tr('pg.dataPages.gl.intro')}
        </span>
        <span style={{ flex: 1 }} />
        {canEdit && !adding && (
          <button onClick={() => setAdding(true)} disabled={busy}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
              padding: '4px 10px', borderRadius: 6, border: '1px solid var(--border)',
              background: 'var(--surface)', color: 'var(--text)', cursor: 'pointer' }}>
            <Plus size={12} /> {tr('pg.dataPages.gl.add')}
          </button>
        )}
      </div>

      {adding && (
        <div style={{ border: '1px solid var(--border)', borderRadius: 6, padding: 12,
          marginBottom: 12, display: 'grid', gap: 8 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 8 }}>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('pg.dataPages.gl.term')}
              <input style={input} value={draft.term} autoFocus
                placeholder="GMV" // i18n-ok
                onChange={e => setDraft({ ...draft, term: e.target.value })} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('pg.dataPages.gl.whatItMeans')}
              <input style={input} value={draft.definition}
                placeholder={tr('pg.dataPages.gl.definitionPlaceholder')}
                onChange={e => setDraft({ ...draft, definition: e.target.value })} />
            </label>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('pg.dataPages.gl.alsoCalledLabel')}
              <input style={input} value={draft.synonyms}
                placeholder="إجمالي المبيعات, gross sales" // i18n-ok
                onChange={e => setDraft({ ...draft, synonyms: e.target.value })} />
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('pg.dataPages.gl.tableOptional')}
              <input style={input} value={draft.maps_to_object} list="glossary-objects"
                onChange={e => setDraft({ ...draft, maps_to_object: e.target.value })} />
              <datalist id="glossary-objects">
                {(objectNames ?? []).map(n => <option key={n} value={n} />)}
              </datalist>
            </label>
            <label style={{ fontSize: 11, color: 'var(--muted)' }}>
              {tr('pg.dataPages.gl.columnOptional')}
              <input style={input} value={draft.maps_to_column}
                onChange={e => setDraft({ ...draft, maps_to_column: e.target.value })} />
            </label>
          </div>
          <label style={{ fontSize: 11, color: 'var(--muted)' }}>
            {tr('pg.dataPages.gl.ruleLabel')}
            <input style={input} value={draft.rule} aria-label={tr('pg.dataPages.gl.rule')}
              placeholder="dept_emp.to_date = '9999-01-01'" // i18n-ok
              onChange={e => setDraft({ ...draft, rule: e.target.value })} />
          </label>
          <label style={{ fontSize: 11, color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={draft.always} aria-label={tr('pg.dataPages.gl.alwaysAria')}
              onChange={e => setDraft({ ...draft, always: e.target.checked })} />
            {tr('pg.dataPages.gl.alwaysLabel')}
            <span style={{ opacity: .8 }}>{tr('pg.dataPages.gl.alwaysExample')}</span>
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => void save()} disabled={busy}
              style={{ fontSize: 12, padding: '5px 12px', borderRadius: 6, border: 'none',
                background: 'var(--accent)', color: 'var(--mc-accent-fg)', cursor: 'pointer' }}>
              {busy ? tr('pg.dataPages.saving') : tr('pg.dataPages.rev.save')}
            </button>
            <button onClick={() => setAdding(false)} disabled={busy}
              style={{ fontSize: 12, padding: '5px 12px', borderRadius: 6,
                border: '1px solid var(--border)', background: 'var(--surface)',
                color: 'var(--text)', cursor: 'pointer' }}>
              {tr('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {terms.length === 0 ? (
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
          {canEdit ? tr('pg.dataPages.gl.emptyEditor') : tr('pg.dataPages.gl.emptyViewer')}
        </p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ textAlign: 'start', color: 'var(--muted)' }}>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{tr('pg.dataPages.gl.term')}</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{tr('pg.dataPages.gl.thMeans')}</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{tr('pg.dataPages.gl.thAlsoCalled')}</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{tr('pg.dataPages.gl.thMapsTo')}</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }}>{tr('pg.dataPages.gl.thRule')}</th>
              <th style={{ textAlign: 'start', padding: '4px 8px' }} title={tr('pg.dataPages.gl.thAlwaysTitle')}>{tr('pg.dataPages.gl.thAlways')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {terms.map(t => (
              <tr key={t.id} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', fontWeight: 600 }}>
                  {t.term}
                  {t.data_source_id === null && (
                    <span style={{ marginInlineStart: 6, fontSize: 11, fontWeight: 400,
                      color: 'var(--muted)' }}>
                      {tr('pg.dataPages.gl.orgWide')}
                    </span>
                  )}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{t.definition || '—'}</td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>
                  {(t.synonyms ?? []).join(tr('pg.dataPages.listSep')) || '—'}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>
                  {t.maps_to_column || t.maps_to_object
                    ? <bdi dir="ltr">{t.maps_to_column
                        ? `${t.maps_to_object ? `${t.maps_to_object}.` : ''}${t.maps_to_column}`
                        : t.maps_to_object}</bdi>
                    : '—'}
                </td>
                <td style={{ padding: '6px 8px', color: 'var(--muted)', minWidth: 160 }}>
                  {canEdit && t.data_source_id !== null ? (
                    <input key={`${t.id}:${t.rule ?? ''}`} defaultValue={t.rule ?? ''} aria-label={tr('pg.dataPages.gl.ruleFor', { name: t.term })}
                      placeholder="—" disabled={busy}
                      onBlur={e => void editRule(t, e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
                      style={{ ...input, fontFamily: 'var(--mono, monospace)', fontSize: 11 }} />
                  ) : (t.rule || '—')}
                </td>
                <td style={{ padding: '6px 8px' }}>
                  <input type="checkbox" checked={!!t.always} aria-label={tr('pg.dataPages.gl.alwaysFor', { name: t.term })}
                    disabled={!canEdit || busy || t.data_source_id === null || !t.rule}
                    title={!t.rule ? tr('pg.dataPages.gl.writeRuleFirst') : undefined}
                    onChange={e => void setAlways(t, e.target.checked)} />
                </td>
                <td style={{ padding: '6px 8px', textAlign: 'end' }}>
                  {/* An org-wide term is not this connection's to delete: it is
                      in use on every other source too, and the endpoint refuses
                      it. Offering the button anyway would be a dead control. */}
                  {canEdit && t.data_source_id !== null && (
                    <button aria-label={tr('pg.dataPages.gl.deleteFor', { name: t.term })} disabled={busy}
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
