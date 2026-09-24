import { useState } from 'react'
import { Pencil } from 'lucide-react'
import toast from 'react-hot-toast'
import { columnMetaApi, datasetsApi, type ColumnMeta, type Dataset } from '../../services/api'

/**
 * What a column IS, for every engine that reads it.
 *
 * `freetext` and `identifier` are the two that change what ANALYSES do, and
 * neither could be set through the API until now: the engine has read both
 * since it shipped while the only endpoint that writes them refused anything
 * outside {measure, category, geography}. A comments field detected as
 * `categorical` was charted as one bar per distinct comment; an id column was
 * summed into a total with no referent.
 */
const ROLES: { value: NonNullable<ColumnMeta['role']>; label: string; why: string }[] = [
  { value: 'measure',    label: 'Measure',    why: 'a number worth summing or averaging' },
  { value: 'category',   label: 'Category',   why: 'something to group or break down by' },
  { value: 'temporal',   label: 'Date/time',  why: 'can carry a trend or a forecast' },
  { value: 'geography',  label: 'Geography',  why: 'can be drawn on a map' },
  { value: 'freetext',   label: 'Free text',  why: 'prose - never a chart axis; topic analysis reads it' },
  { value: 'identifier', label: 'Identifier', why: 'counted, never summed' },
]

/**
 * What each column MEANS, and where that sentence lives.
 *
 * Every AI path in this product now reads these: the dashboard designer's prompt
 * carries them, the agent's context renders them, and the insights engine writes
 * its findings in their words. Until this panel there was nowhere in the product
 * to write one for a dataset — they could only be inferred by a sync, or typed
 * on the source review page by an admin who knew it existed.
 *
 * The important behaviour is the one the panel has to EXPLAIN, because it is not
 * what a person expects from an inline edit: a column that came from a connected
 * table is described on the SOURCE catalog, so the sentence is written once and
 * every dataset built from that table reads it. That is deliberate — copying the
 * text onto each dataset is what lets two datasets from one table disagree about
 * what `status` means — but a person who types into a box labelled with this
 * dataset's name deserves to be told their words travelled further than that.
 */
export interface ColumnMeaningPanelProps {
  dataset: Dataset
  /** Whether this viewer may author. The endpoint enforces it; hiding the
   *  controls keeps a reader from meeting a refusal they cannot act on. */
  canEdit: boolean
  /** Reload the dataset so the resolved descriptions come back fresh. */
  onSaved?: () => void
}

export default function ColumnMeaningPanel(
  { dataset, canEdit, onSaved }: ColumnMeaningPanelProps,
) {
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const described = dataset.column_descriptions ?? {}
  const labels = dataset.value_labels ?? {}
  const targets = dataset.column_targets ?? {}
  const ineligible = new Set(dataset.ineligible_columns ?? [])
  const meta = dataset.column_meta ?? {}

  /** Merge one column's change into the WHOLE map and send it back.
   *
   *  `PUT /column-meta` replaces the map wholesale - that is deliberate, and it
   *  is what makes a bulk edit one request - so a panel that sent only its own
   *  column would silently delete every role, format and label set anywhere
   *  else. The map arrives on the dataset payload, so merging is both possible
   *  and required. */
  const patchMeta = async (column: string, change: Partial<ColumnMeta>, note: string) => {
    setBusy(true)
    try {
      const next: Record<string, ColumnMeta> = { ...meta }
      next[column] = { ...(next[column] ?? {}), ...change }
      await columnMetaApi.set(dataset.id, next)
      toast.success(note)
      onSaved?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save')
    } finally { setBusy(false) }
  }

  const start = (name: string) => {
    setEditing(name)
    setDraft(described[name] ?? '')
  }

  const save = async (name: string) => {
    setBusy(true)
    try {
      const r = await datasetsApi.setColumnDescription(dataset.id, name, draft.trim())
      // Said plainly, because it is the surprising half: the sentence just
      // became the answer for every dataset built from that table.
      toast.success(r.shared
        ? `Saved. ${r.object}.${r.column} now reads this way in every dataset built from it.`
        : 'Saved for this dataset.')
      setEditing(null)
      onSaved?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'Could not save the description')
    } finally { setBusy(false) }
  }

  const input: React.CSSProperties = {
    width: '100%', fontSize: 12, padding: '5px 8px', boxSizing: 'border-box',
    background: 'var(--surface2)', border: '1px solid var(--border)',
    borderRadius: 4, color: 'var(--text)',
  }

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 14 }}>What the columns mean</h3>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>
          Read by the dashboard designer, the agent and the insights engine. A
          column that came from a connected table is described once, for every
          dataset built from it.
        </span>
      </div>

      {dataset.grain && (
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: '0 0 10px' }}>
          <strong style={{ color: 'var(--text)' }}>
            {dataset.business_name || dataset.name}
          </strong>{' — '}{dataset.grain}
        </p>
      )}

      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <tbody>
          {dataset.columns.map(c => {
            const values = labels[c.name]
            return (
              <tr key={c.name} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 8px', width: 200, verticalAlign: 'top' }}>
                  <div style={{ fontWeight: 600 }}>{c.name}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 11 }}>{c.dtype}</div>
                </td>
                <td style={{ padding: '6px 8px', verticalAlign: 'top' }}>
                  {editing === c.name ? (
                    <div style={{ display: 'flex', gap: 6 }}>
                      <input style={input} value={draft} autoFocus disabled={busy}
                        placeholder="What is this column for?"
                        onChange={e => setDraft(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') void save(c.name)
                          if (e.key === 'Escape') setEditing(null)
                        }} />
                      <button onClick={() => void save(c.name)} disabled={busy}
                        style={{ fontSize: 12, padding: '4px 10px', borderRadius: 6,
                          border: 'none', background: 'var(--accent, #2563eb)',
                          color: 'var(--mc-accent-fg)', cursor: 'pointer' }}>
                        {busy ? 'Saving…' : 'Save'}
                      </button>
                      <button onClick={() => setEditing(null)} disabled={busy}
                        style={{ fontSize: 12, padding: '4px 10px', borderRadius: 6,
                          border: '1px solid var(--border)', background: 'var(--surface)',
                          color: 'var(--text)', cursor: 'pointer' }}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <span style={{ color: described[c.name] ? 'var(--text)' : 'var(--muted)' }}>
                        {described[c.name] || 'Not described yet'}
                      </span>
                      {canEdit && (
                        <button aria-label={`Describe ${c.name}`} onClick={() => start(c.name)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--muted)', padding: '0 6px' }}>
                          <Pencil size={12} />
                        </button>
                      )}
                    </>
                  )}
                  {values && (
                    <div style={{ color: 'var(--muted)', fontSize: 11, marginTop: 2 }}>
                      {Object.entries(values).slice(0, 8)
                        .map(([raw, label]) => `${raw} = ${label}`).join(', ')}
                    </div>
                  )}

                  {canEdit && (
                    <div style={{ display: 'flex', gap: 14, alignItems: 'center',
                      marginTop: 6, flexWrap: 'wrap' }}>
                      <label style={{ fontSize: 11, color: 'var(--muted)',
                        display: 'flex', alignItems: 'center', gap: 4 }}>
                        Treat as
                        <select disabled={busy} value={meta[c.name]?.role ?? ''}
                          aria-label={`Role for ${c.name}`}
                          onChange={e => void patchMeta(
                            c.name,
                            { role: (e.target.value || undefined) as ColumnMeta['role'] },
                            e.target.value
                              ? `${c.name} is now a ${e.target.value}`
                              : `${c.name} goes back to what detection found`)}
                          style={{ fontSize: 11, padding: '2px 4px',
                            background: 'var(--surface2)', color: 'var(--text)',
                            border: '1px solid var(--border)', borderRadius: 4 }}>
                          <option value="">detected</option>
                          {ROLES.map(r => (
                            <option key={r.value} value={r.value} title={r.why}>
                              {r.label}
                            </option>
                          ))}
                        </select>
                      </label>

                      {/* An OUTCOME worth explaining. This is what lets the
                          "what drives X" analyses run without being told what X
                          is -- the alternative is guessing from flag-shaped
                          columns, which cannot know which question anybody has. */}
                      <label style={{ fontSize: 11, color: 'var(--muted)',
                        display: 'flex', alignItems: 'center', gap: 4 }}>
                        <input type="checkbox" disabled={busy}
                          aria-label={`Explain ${c.name}`}
                          checked={targets[c.name] !== undefined}
                          onChange={e => void patchMeta(
                            c.name,
                            { target_candidate_priority: e.target.checked ? 10 : undefined },
                            e.target.checked
                              ? `The analyses will look for what drives ${c.name}`
                              : `${c.name} is no longer treated as an outcome`)} />
                        Worth explaining
                        {targets[c.name] !== undefined && (
                          <span style={{ opacity: .7 }}>({targets[c.name]})</span>
                        )}
                      </label>

                      {/* Not the same as hiding it, and the tooltip has to say
                          so or the two controls read as duplicates. */}
                      <label style={{ fontSize: 11, color: 'var(--muted)',
                        display: 'flex', alignItems: 'center', gap: 4 }}
                        title="Still usable by anyone who asks for it. This only stops the platform offering charts of it unprompted.">
                        <input type="checkbox" disabled={busy}
                          aria-label={`Suggest ${c.name}`}
                          checked={!ineligible.has(c.name)}
                          onChange={e => void patchMeta(
                            c.name,
                            { eligible_for_suggestion: e.target.checked ? undefined : false },
                            e.target.checked
                              ? `${c.name} can be suggested again`
                              : `${c.name} will not be suggested - it stays usable`)} />
                        May be suggested
                      </label>
                    </div>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </section>
  )
}
