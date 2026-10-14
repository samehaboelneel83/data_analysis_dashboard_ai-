import { useState } from 'react'
import type { ReviewQueue, ReviewSource } from '../../services/api'
import { useT } from '../../i18n'
import { withNode } from '../../i18n/pages/dataPages'

/**
 * What this database is, in plain language.
 *
 * This is the panel that answers the first question a person has after
 * connecting a source: *what is actually in here?* The per-column descriptions
 * elsewhere serve an agent composing a query; they do not answer that.
 *
 * Three states, and the empty ones matter as much as the filled one — a blank
 * panel with no explanation is how a feature gets written off as broken:
 *
 *   no description, model off   explain that it is off, and offer the switch
 *   no description, model on    say a sync will write one
 *   description present         show it, and say whether a human approved it
 */
export interface SourceOverviewProps {
  source: ReviewSource
  datasets: ReviewQueue['datasets']
  onToggleLlm: (on: boolean) => void
  onSaveDescription: (text: string) => void
  /** Clears one object's skip flag so the next sync tries it again. */
  onRetrySample: (objectId: number) => void
  /** Marks (or unmarks) an object as the source of truth for what it
   *  describes -- see agent/nodes/generate.py's canonical preference. */
  onToggleCanonical: (objectId: number, canonical: boolean) => void
  busy?: boolean
}

export default function SourceOverview({
  source, datasets, onToggleLlm, onSaveDescription, onRetrySample,
  onToggleCanonical, busy,
}: SourceOverviewProps) {
  const tr = useT()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(source.description ?? '')

  const described = datasets.filter(d => d.description)
  const describedTables = described.filter(d => d.kind !== 'view')
  const describedViews = described.filter(d => d.kind === 'view')
  const views = datasets.filter(d => d.kind === 'view').length
  const tables = datasets.length - views
  const deprecated = datasets.filter(d => d.is_deprecated).length
  // A table with no description was either empty or could not be sampled in
  // time. Both are worth surfacing: a blank entry with no explanation reads as
  // a bug rather than as a deliberate limit.
  const unsampled = datasets.length - described.length
  // Objects the last sync gave up on. Distinct from "not profiled": these were
  // not merely missed, they will be SKIPPED from now on until someone here
  // says otherwise.
  const skipped = datasets.filter(d => d.sample_timed_out_at)

  return (
    <section style={{
      border: '1px solid #e2e8f0', borderRadius: 6, padding: 16, marginBottom: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 10 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{source.name}</h2>
        <span style={{ fontSize: 12, color: '#64748b' }}>{source.type}</span>
        <span style={{ flex: 1 }} />
        <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={source.allow_llm_sampling}
            disabled={busy}
            onChange={e => onToggleLlm(e.target.checked)}
          />
          {tr('pg.dataPages.ov.allowLlm')}
        </label>
      </div>

      {editing ? (
        <div>
          <textarea
            value={draft}
            onChange={e => setDraft(e.target.value)}
            rows={4}
            style={{ width: '100%', padding: 8, fontSize: 13, fontFamily: 'inherit' }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button onClick={() => { onSaveDescription(draft); setEditing(false) }}>
              {tr('pg.dataPages.rev.save')}
            </button>
            <button onClick={() => { setDraft(source.description ?? ''); setEditing(false) }}>
              {tr('common.cancel')}
            </button>
          </div>
        </div>
      ) : source.description ? (
        <>
          <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.6 }}>
            {source.description}
          </p>
          <div style={{ fontSize: 12, color: '#64748b' }}>
            {source.description_source === 'confirmed'
              ? tr('pg.dataPages.ov.confirmedByPerson')
              : tr('pg.dataPages.ov.writtenByModel')}
            {' · '}
            <button
              onClick={() => { setDraft(source.description ?? ''); setEditing(true) }}
              style={{ background: 'none', border: 'none', padding: 0,
                       color: '#2d5ba8', cursor: 'pointer', fontSize: 12 }}
            >
              {tr('pg.dataPages.ov.edit')}
            </button>
          </div>
        </>
      ) : (
        <p style={{ margin: 0, fontSize: 13, color: '#64748b' }}>
          {source.allow_llm_sampling
            ? tr('pg.dataPages.ov.noDescModelOn')
            : tr('pg.dataPages.ov.noDescModelOff')}
          {' '}
          <button
            onClick={() => { setDraft(''); setEditing(true) }}
            style={{ background: 'none', border: 'none', padding: 0,
                     color: '#2d5ba8', cursor: 'pointer', fontSize: 13 }}
          >
            {tr('pg.dataPages.ov.writeYourself')}
          </button>
        </p>
      )}

      <div style={{ display: 'flex', gap: 18, marginTop: 12, fontSize: 12,
                    color: '#64748b', flexWrap: 'wrap' }}>
        <span>{withNode(tr('pg.dataPages.ov.statTables', { n: tables, b: '\u0001' }), <strong style={{ color: '#101822' }}>{tables}</strong>)}</span>
        <span>{withNode(tr('pg.dataPages.ov.statViews', { n: views, b: '\u0001' }), <strong style={{ color: '#101822' }}>{views}</strong>)}</span>
        <span>{withNode(tr('pg.dataPages.ov.statDescribed', { n: described.length, b: '\u0001' }), <strong style={{ color: '#101822' }}>{described.length}</strong>)}</span>
        {deprecated > 0 && (
          <span>{withNode(tr('pg.dataPages.ov.statAbandoned', { n: deprecated, b: '\u0001' }), <strong style={{ color: '#a86c15' }}>{deprecated}</strong>)}</span>
        )}
        {unsampled > 0 && (
          <span title={tr('pg.dataPages.ov.notProfiledTitle')}>
            {withNode(tr('pg.dataPages.ov.statNotProfiled', { n: unsampled, b: '\u0001' }), <strong style={{ color: '#a86c15' }}>{unsampled}</strong>)}
          </span>
        )}
      </div>

      {/* Tables and views listed apart, because they are different kinds of
          thing and get read for different reasons. A table is where data
          lives; a view is somebody's saved question about it. Mixing them
          leaves a reader unable to tell which is which without checking each
          name, and on this source there are more views than tables. */}
      <DescribedGroup
        title={tr('pg.dataPages.ov.tables')}
        items={describedTables}
        empty={tr('pg.dataPages.ov.noTableDescs')}
        onToggleCanonical={onToggleCanonical}
        busy={busy}
      />
      {skipped.length > 0 && (
        /* The visible half of the skip. Sampling gives each object a fixed time
           budget, and a handful of expensive views spend that whole budget on
           every sync without ever returning rows — so once an object hits the
           deadline it is left out of later runs.
           That is only acceptable while it stays SEEN and REVERSIBLE. A table
           that quietly stops being described, with nothing on the page to say
           why, is indistinguishable from a bug; and the person who can judge
           whether the view has since been fixed is the one reading this. */
        <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 6,
                      background: '#fdf6e7', border: '1px solid #f0dfae' }}>
          <p style={{ margin: 0, fontSize: 13, color: '#7a5a12' }}>
            {withNode(tr('pg.dataPages.ov.skipped', { n: skipped.length, b: '\u0001' }), <strong>{skipped.length}</strong>)}
          </p>
          <ul style={{ margin: '8px 0 0', paddingInlineStart: 18, fontSize: 13,
                       lineHeight: 1.8, maxHeight: 180, overflowY: 'auto' }}>
            {skipped.map(d => (
              <li key={d.id}>
                <strong>{d.name}</strong>{' '}
                <button
                  onClick={() => onRetrySample(d.id)}
                  disabled={busy}
                  style={{ background: 'none', border: 'none', padding: 0,
                           color: '#2d5ba8', cursor: busy ? 'default' : 'pointer',
                           fontSize: 13 }}
                >
                  {tr('pg.dataPages.ov.retrySample')}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <DescribedGroup
        title={tr('pg.dataPages.ov.views')}
        items={describedViews}
        empty={tr('pg.dataPages.ov.noViewDescs')}
        note={tr('pg.dataPages.ov.viewNote')}
        onToggleCanonical={onToggleCanonical}
        busy={busy}
      />
    </section>
  )
}


function DescribedGroup({ title, items, empty, note, onToggleCanonical, busy }: {
  title: string
  items: ReviewQueue['datasets']
  empty: string
  note?: string
  onToggleCanonical: (objectId: number, canonical: boolean) => void
  busy?: boolean
}) {
  const tr = useT()
  if (!items.length) return null
  return (
    <details style={{ marginTop: 10 }}>
      <summary style={{ fontSize: 13, cursor: 'pointer' }}>
        {tr('pg.dataPages.ov.groupSummary', { title, n: items.length })}
      </summary>
      {note && (
        <p style={{ fontSize: 12, color: '#64748b', margin: '6px 0 0' }}>{note}</p>
      )}
      {/* Scrollable rather than truncated: a wall of text is not read, but
          silently dropping entries would hide part of the database. */}
      <ul style={{ margin: '8px 0 0', paddingInlineStart: 18, fontSize: 13,
                   lineHeight: 1.55, maxHeight: 240, overflowY: 'auto' }}>
        {items.map(d => (
          <li key={d.id} style={{ marginBottom: 4 }}>
            <strong>{d.name}</strong>
            {d.description_source === 'schema' && (
              <span style={{ color: '#16785a', fontWeight: 400 }}> {tr('pg.dataPages.ov.fromSchema')}</span>
            )}
            {' '}— {d.description}
            {' '}
            {/* Admin-only in effect: the confirm endpoint this calls already
                requires org-admin, so a non-admin's click just 403s. Kept
                visible rather than hidden, since "why can't I see this" is
                worse than a rare failed click. */}
            <label style={{ fontSize: 11, color: '#64748b', cursor: busy ? 'default' : 'pointer' }}>
              <input
                type="checkbox"
                checked={!!d.is_canonical}
                disabled={busy}
                onChange={e => onToggleCanonical(d.id, e.target.checked)}
                style={{ marginInlineStart: 6, marginInlineEnd: 4, verticalAlign: 'middle' }}
              />
              {tr('pg.dataPages.ov.canonical')}
            </label>
          </li>
        ))}
      </ul>
    </details>
  )
}
