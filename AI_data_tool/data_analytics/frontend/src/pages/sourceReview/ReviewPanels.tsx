import EvidenceSummary from '../../components/review/EvidencePopover'
import { useDirection } from '../../contexts/DirectionContext'
import type { IndexAdvice } from '../../services/api'
import {
  type DriftVersion, type ReviewEntity, type ReviewQueue, type ReviewRelationship,
} from '../../services/api'
import { useState } from 'react'
import { useT } from '../../i18n'
import { dtypeName } from '../../lib/dtypeName'
import { withNode } from '../../i18n/pages/dataPages'

export function RelationshipRow({ rel, checked, onToggle, onReject }: {
  rel: ReviewRelationship
  checked: boolean
  onToggle: () => void
  onReject: () => void
}) {
  const tr = useT()
  return (
    <div style={{
      display: 'flex', gap: 12, alignItems: 'flex-start',
      padding: 12, borderBottom: '1px solid #e2e8f0',
    }}>
      <input type="checkbox" checked={checked} onChange={onToggle} style={{ marginTop: 3 }} />
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 600 }}>
          {rel.from_dataset}.{rel.from_column} → {rel.to_dataset}.{rel.to_column}
          <span style={{ marginInlineStart: 8, fontWeight: 400, color: '#64748b' }}>
            {Math.round(rel.confidence * 100)}% · {rel.cardinality ?? tr('pg.dataPages.rev.unknownCardinality')}
          </span>
        </div>
        <EvidenceSummary evidence={rel.evidence} />
      </div>
      <button onClick={onReject} title={tr('pg.dataPages.rev.rejectTitle')}>
        {tr('pg.dataPages.rev.reject')}
      </button>
    </div>
  )
}

export function ColumnReview({ grouped, total, onSave, onSaveLabels }: {
  grouped: Map<string, ReviewQueue['columns']>
  total: number
  onSave: (id: number, description: string) => void
  onSaveLabels: (id: number, labels: Record<string, string>) => void
}) {
  const tr = useT()
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  if (!total) {
    return <p style={{ fontSize: 13, color: '#64748b' }}>{tr('pg.dataPages.rev.noColumnsMatch')}</p>
  }

  return (
    <div>
      <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 10px' }}>
        {tr('pg.dataPages.rev.columnsIntro', { n: total, tables: grouped.size })}
      </p>
      {[...grouped.entries()].map(([table, columns]) => (
        <details key={table} style={{ marginBottom: 6, border: '1px solid #e2e8f0',
                                      borderRadius: 4, padding: '6px 10px' }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 600 }}>
            {table}{' '}
            <span style={{ fontWeight: 400, color: '#64748b' }}>
              ({tr('pg.dataPages.rev.columnCount', { n: columns.length })})
            </span>
          </summary>
          <table style={{ width: '100%', borderCollapse: 'collapse',
                          fontSize: 13, marginTop: 8 }}>
            <tbody>
              {columns.map(col => {
                const value = drafts[col.id] ?? col.description ?? ''
                return (
                  <tr key={col.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: 6, fontWeight: 600, width: 200 }}>{col.name}</td>
                    <td style={{ padding: 6, color: '#64748b', width: 110 }}>
                      {col.semantic_type ?? dtypeName(tr, col.dtype)}
                    </td>
                    <td style={{ padding: 6 }}>
                      <input
                        value={value}
                        onChange={e => setDrafts(d => ({ ...d, [col.id]: e.target.value }))}
                        placeholder={tr('pg.dataPages.rev.noDescription')}
                        style={{ width: '100%', padding: 4 }}
                      />
                      {col.description_source === 'schema' && (
                        <span style={{ fontSize: 11, color: '#16785a' }}>
                          {tr('pg.dataPages.rev.fromSchema')}
                        </span>
                      )}
                      {col.needs_review && (
                        <span style={{ fontSize: 11, color: '#a86c15' }}>
                          {tr('pg.dataPages.rev.generated')}
                        </span>
                      )}
                      <EnumLabels col={col} onSave={onSaveLabels} />
                    </td>
                    <td style={{ padding: 6, width: 70 }}>
                      <button
                        disabled={value === (col.description ?? '')} title={value === (col.description ?? '') ? tr('pg.dataPages.rev.nothingChanged') : undefined}
                        onClick={() => onSave(col.id, value)}
                      >
                        {tr('pg.dataPages.rev.save')}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  )
}

/** T2: what a coded column's values MEAN, e.g. `1 = new, 2 = paid`. Only
 *  rendered for columns that already carry `enum_labels` — a column with none
 *  gets no label UI at all, since there is nothing here yet to edit or show. */
export function EnumLabels({ col, onSave }: {
  col: ReviewQueue['columns'][number]
  onSave: (id: number, labels: Record<string, string>) => void
}) {
  const tr = useT()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Record<string, string>>(col.enum_labels ?? {})

  if (!col.enum_labels || !Object.keys(col.enum_labels).length) return null

  if (!editing) {
    return (
      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
        <span>{Object.entries(col.enum_labels).map(([v, l]) => `${v} = ${l}`).join(tr('pg.dataPages.listSep'))}</span>
        {col.enum_labels_source === 'confirmed' ? (
          <span style={{ color: '#16785a' }}> · {tr('pg.dataPages.rev.confirmed')}</span>
        ) : (
          <span style={{ color: '#a86c15' }}> · {tr('pg.dataPages.rev.notConfirmed')}</span>
        )}
        {' · '}
        <button
          onClick={() => { setDraft(col.enum_labels ?? {}); setEditing(true) }}
          style={{ background: 'none', border: 'none', padding: 0,
                   color: '#2d5ba8', cursor: 'pointer', fontSize: 11 }}
        >
          {tr('pg.dataPages.rev.editLabels')}
        </button>
      </div>
    )
  }

  return (
    <div style={{ marginTop: 4 }}>
      {Object.keys(draft).map(value => (
        <div key={value} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 2 }}>
          <span style={{ fontSize: 11, color: '#64748b', width: 40 }}>{value} =</span>
          <input
            value={draft[value]}
            onChange={e => setDraft(d => ({ ...d, [value]: e.target.value }))}
            style={{ fontSize: 11, padding: 2, flex: 1 }}
          />
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
        <button onClick={() => { onSave(col.id, draft); setEditing(false) }} style={{ fontSize: 11 }}>
          {tr('pg.dataPages.rev.save')}
        </button>
        <button onClick={() => setEditing(false)} style={{ fontSize: 11 }}>
          {tr('common.cancel')}
        </button>
      </div>
    </div>
  )
}

/** Task R3 / spec section 5 (E2): named business objects this source models,
 *  drafted by the sync's LLM pass ("inferred") and confirmed or edited by a
 *  human here -- same review pattern as ColumnReview's enum labels above:
 *  editing a field or clicking Confirm both promote the row to "confirmed",
 *  after which no later sync draft may overwrite it. */
export function EntityReview({ entities, onSave, onConfirm }: {
  entities: ReviewEntity[]
  onSave: (id: number, fields: { business_name?: string; grain?: string; description?: string }) => void
  onConfirm: (id: number) => void
}) {
  const tr = useT()
  if (!entities.length) {
    return (
      <p style={{ fontSize: 13, color: '#64748b' }}>
        {tr('pg.dataPages.rev.noEntities')}
      </p>
    )
  }

  return (
    <div>
      <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 10px' }}>
        {tr('pg.dataPages.rev.entitiesIntro', { n: entities.length })}
      </p>
      {entities.map(entity => (
        <EntityRow key={entity.id} entity={entity} onSave={onSave} onConfirm={onConfirm} />
      ))}
    </div>
  )
}

export function EntityRow({ entity, onSave, onConfirm }: {
  entity: ReviewEntity
  onSave: (id: number, fields: { business_name?: string; grain?: string; description?: string }) => void
  onConfirm: (id: number) => void
}) {
  const tr = useT()
  const [businessName, setBusinessName] = useState(entity.business_name ?? '')
  const [grain, setGrain] = useState(entity.grain ?? '')
  const [description, setDescription] = useState(entity.description ?? '')

  const dirty = businessName !== (entity.business_name ?? '')
    || grain !== (entity.grain ?? '')
    || description !== (entity.description ?? '')

  return (
    <div style={{ border: '1px solid #e2e8f0', borderRadius: 4, padding: 10, marginBottom: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <strong style={{ fontSize: 13 }}>{entity.name}</strong>
        {entity.primary_object && (
          <span style={{ fontSize: 11, color: '#64748b' }}>[{entity.primary_object}]</span>
        )}
        {entity.source === 'confirmed' ? (
          <span style={{ fontSize: 11, color: '#16785a' }}>{tr('pg.dataPages.rev.confirmed')}</span>
        ) : (
          <span style={{ fontSize: 11, color: '#a86c15' }}>{tr('pg.dataPages.rev.notConfirmed')}</span>
        )}
      </div>
      <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>
        {tr('pg.dataPages.rev.businessName')}
        <input value={businessName} onChange={e => setBusinessName(e.target.value)}
               placeholder={tr('pg.dataPages.rev.noBusinessName')} style={{ width: '100%', padding: 4, marginTop: 2 }} />
      </label>
      <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 4 }}>
        {tr('pg.dataPages.rev.grain')}
        <input value={grain} onChange={e => setGrain(e.target.value)}
               placeholder={tr('pg.dataPages.rev.grainPlaceholder')} style={{ width: '100%', padding: 4, marginTop: 2 }} />
      </label>
      <label style={{ display: 'block', fontSize: 11, color: '#64748b', marginBottom: 6 }}>
        {tr('pg.dataPages.rev.description')}
        <input value={description} onChange={e => setDescription(e.target.value)}
               placeholder={tr('pg.dataPages.rev.noDescription')} style={{ width: '100%', padding: 4, marginTop: 2 }} />
      </label>
      <div style={{ display: 'flex', gap: 6 }}>
        <button
          disabled={!dirty} title={!dirty ? tr('pg.dataPages.rev.nothingChanged') : undefined}
          onClick={() => onSave(entity.id, {
            business_name: businessName, grain, description,
          })}
        >
          {tr('pg.dataPages.rev.save')}
        </button>
        <button disabled={entity.source === 'confirmed'} title={entity.source === 'confirmed' ? tr('pg.dataPages.rev.alreadyConfirmed') : undefined} onClick={() => onConfirm(entity.id)}>
          {tr('pg.dataPages.rev.confirm')}
        </button>
      </div>
    </div>
  )
}

/** Schema drift history: one card per fingerprint change the metadata sync
 *  recorded (`SchemaVersion` rows). The data has been collected since Layer 1
 *  shipped; this panel is its first reader. Read-only -- fixing drift means
 *  running a sync and re-reviewing, both of which live above. */
export function DriftPanel({ drift, error }: { drift: DriftVersion[] | null; error: string | null }) {
  const { language } = useDirection()
  const tr = useT()
  if (error) return <p role="alert" style={{ fontSize: 13, color: '#b3261e' }}>{error}</p>
  if (drift === null) return <p style={{ fontSize: 13, color: '#64748b' }}>{tr('pg.dataPages.rev.loadingDrift')}</p>
  if (drift.length === 0) {
    return (
      <p style={{ fontSize: 13, color: '#64748b' }}>
        {tr('pg.dataPages.rev.noDrift')}
      </p>
    )
  }
  const changeList = (label: string, color: string, rows: { table: string; name: string }[]) =>
    rows.length > 0 && (
      <div style={{ fontSize: 12, marginTop: 4 }}>
        <span style={{ color, fontWeight: 600 }}>{tr('pg.dataPages.rev.changeLabel', { label })}</span>{' '}
        <bdi dir="ltr">{rows.map(r => `${r.table}.${r.name}`).join(', ')}</bdi>
      </div>
    )
  return (
    <div>
      <p style={{ fontSize: 12, color: '#64748b', margin: '0 0 10px' }}>
        {tr('pg.dataPages.rev.driftIntro')}
      </p>
      {drift.map(v => (
        <div key={v.id} style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: '10px 12px', marginBottom: 8 }}>
          <div style={{ fontSize: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ fontWeight: 600 }}>{new Date(v.detected_at).toLocaleString(language, { dateStyle: 'medium', timeStyle: 'short' })}</span>
            {v.is_baseline && (
              <span style={{ fontSize: 11, fontWeight: 700, color: '#2d5ba8', background: '#e5edfb',
                borderRadius: 99, padding: '2px 8px', textTransform: 'uppercase', letterSpacing: '.04em' }}>
                {tr('pg.dataPages.rev.baseline')}
              </span>
            )}
            <span style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 11 }}>{v.fingerprint.slice(0, 12)}</span>
          </div>
          {!v.is_baseline && v.added.length === 0 && v.removed.length === 0 && v.changed.length === 0 && (
            <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{tr('pg.dataPages.rev.noDifferences')}</div>
          )}
          {changeList(tr('pg.dataPages.rev.added'), '#16785a', v.added)}
          {changeList(tr('pg.dataPages.rev.removed'), '#b3261e', v.removed)}
          {changeList(tr('pg.dataPages.rev.changed'), '#a86c15', v.changed)}
          {changeList(tr('pg.dataPages.rev.orphaned'), '#a86c15', v.orphaned_annotations)}
        </div>
      ))}
    </div>
  )
}

/** Index advice: which columns this source is filtered on, and which of those
 *  have no index. Recommendations only -- the statement is for the customer's
 *  DBA to paste; nothing here creates an index anywhere.
 *
 *  Grouped columns are deliberately absent. Measured 2026-09-12 at 10M rows: an
 *  index on the FILTERED column cut a governed query by a quarter; one on the
 *  grouped column changed nothing, because a full aggregation scans either way.
 *  A panel that said "index what you group by" would be confidently wrong. */
export function SourceHealthPanel({ advice, error }: { advice: IndexAdvice | null; error: string | null }) {
  const tr = useT()
  if (error) return <p style={{ color: '#b91c1c', fontSize: 13 }}>{error}</p>
  if (!advice) return <p style={{ fontSize: 13, color: '#64748b' }}>{tr('pg.dataPages.rev.readingHistory')}</p>
  const muted: React.CSSProperties = { fontSize: 12, color: '#64748b' }
  return (
    <div>
      <p style={muted}>
        {tr('pg.dataPages.rev.adviceIntro', { runs: advice.runs_considered, days: advice.observed_days, min: advice.min_runs })}
        {advice.index_check === 'unavailable' && (
          <> {withNode(tr('pg.dataPages.rev.idxUnavailable', { b: '\u0001' }), <strong>{tr('pg.dataPages.rev.idxUnavailableBold')}</strong>)}</>
        )}
        {advice.index_check === 'unsupported' && (
          <> {withNode(tr('pg.dataPages.rev.idxUnsupported', { b: '\u0001' }), <strong>{tr('pg.dataPages.rev.idxUnsupportedBold')}</strong>)}</>
        )}
      </p>
      {advice.tables.length === 0 ? (
        <p style={{ fontSize: 13 }}>
          {tr('pg.dataPages.rev.noAdvice')}
        </p>
      ) : advice.tables.map(t => (
        <div key={t.table} style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 14, margin: '0 0 6px' }}><code>{t.table}</code></h3>
          <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
            <thead><tr style={{ textAlign: 'left', color: '#64748b' }}>
              <th style={{ padding: '4px 8px' }}>{tr('pg.dataPages.rev.thColumn')}</th>
              <th style={{ padding: '4px 8px' }}>{tr('pg.dataPages.rev.thRuns')}</th>
              <th style={{ padding: '4px 8px' }}>{tr('pg.dataPages.rev.thAvg')}</th>
              <th style={{ padding: '4px 8px' }}>{tr('pg.dataPages.rev.thIndex')}</th>
            </tr></thead>
            <tbody>
              {t.columns.map(c => (
                <tr key={c.column} style={{ borderTop: '1px solid #e2e8f0' }}>
                  <td style={{ padding: '6px 8px' }}><code>{c.column}</code></td>
                  <td style={{ padding: '6px 8px' }}>{tr('pg.dataPages.rev.runsCell', { n: c.runs })}</td>
                  <td style={{ padding: '6px 8px' }}>{tr('pg.dataPages.rev.msCell', { n: c.avg_ms })}</td>
                  <td style={{ padding: '6px 8px' }}>
                    {c.indexed === null ? (
                      <span style={{ color: '#b45309' }}>{tr('pg.dataPages.rev.hotUnchecked')}</span>
                    ) : c.indexed ? (
                      <span style={{ color: '#15803d' }}>{tr('pg.dataPages.rev.alreadyIndexed')}</span>
                    ) : (
                      <>
                        <span style={{ color: '#b45309' }}>{tr('pg.dataPages.rev.recommended')}</span>
                        {c.statement && (
                          <div><code dir="ltr" style={{ fontSize: 12, userSelect: 'all' }}>{c.statement}</code></div>
                        )}
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
