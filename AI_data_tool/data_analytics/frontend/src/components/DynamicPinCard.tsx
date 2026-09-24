import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { findingKey, insightsApi, narrateApi } from '../services/api'
import type { PinnedTileInfo } from '../services/api'

/**
 * A Dynamic Pin: one insight finding, pinned to the home dashboard.
 *
 *     Insight Engine → Evidence Boundary → LLM Narrator → this card.
 *
 * Everything on it is LIVE and per-viewer. The card holds only a reference
 * (`dataset_id` + `finding_key`); on mount it re-evaluates through the same
 * secured insights endpoint the dataset page uses — same RLS, same column
 * mask — and selects its finding by the identity `apply_novelty` uses. N cards
 * over one dataset share one request (`insightsApi.runShared`).
 *
 * The badge renders from the finding's structured `figures`, never by parsing
 * its sentence. The sentence is TEMPLATE-FIRST: the finding's own
 * deterministic title shows immediately, and a guarded LLM rewrite (digit
 * guard + breaker, server-side) swaps in only if it arrives — the card never
 * blocks on the model and badge/prose can never disagree.
 *
 * A finding no longer detected says exactly that. Dormant, not deleted: the
 * data may change back, and a pin is the user's to remove.
 */

interface Finding {
  kind: string; score: number; title: string; detail: string
  columns: string[]
  figures?: Record<string, number | string>
  p_adjusted?: number
  significant?: boolean | null
  novelty?: 'new' | 'changed' | 'unchanged'
}

function Badge({ figures }: { figures?: Record<string, number | string> }) {
  if (!figures) return null
  if (typeof figures.delta_pct === 'number') {
    const up = figures.direction !== 'down'
    return (
      <span data-testid="pin-badge" style={{
        fontSize: 18, fontWeight: 700, fontVariantNumeric: 'tabular-nums',
        color: up ? 'var(--success, #3fb950)' : 'var(--danger)' }}>
        {up ? '📈' : '📉'} {figures.delta_pct > 0 ? '+' : ''}{figures.delta_pct}%
      </span>
    )
  }
  if (typeof figures.share_pct === 'number') {
    return (
      <span data-testid="pin-badge" style={{ fontSize: 18, fontWeight: 700,
        fontVariantNumeric: 'tabular-nums', color: 'var(--accent)' }}>
        {figures.share_pct}%
      </span>
    )
  }
  if (typeof figures.r === 'number') {
    return (
      <span data-testid="pin-badge" style={{ fontSize: 18, fontWeight: 700,
        fontVariantNumeric: 'tabular-nums', color: 'var(--accent)' }}>
        r = {figures.r.toFixed(2)}
      </span>
    )
  }
  return null
}

export default function DynamicPinCard({ tile, refreshNonce }: {
  tile: PinnedTileInfo
  refreshNonce?: number
}) {
  const [finding, setFinding] = useState<Finding | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'gone' | 'error'>('loading')
  const [polished, setPolished] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setState('loading')
    setPolished(null)
    if (tile.dataset_id == null || !tile.finding_key) { setState('gone'); return }
    insightsApi.runShared(tile.dataset_id)
      .then(res => {
        if (!alive) return
        const hit = (res.findings as Finding[])
          .find(f => findingKey(f) === tile.finding_key) ?? null
        setFinding(hit)
        setState(hit ? 'ready' : 'gone')
        if (hit) {
          // Background polish; the template sentence is already on screen.
          // Null answer = keep the template, never an error.
          void narrateApi.one(hit as unknown as Record<string, unknown>)
            .then(sentence => { if (alive && sentence) setPolished(sentence) })
            .catch(() => {})
        }
      })
      .catch(() => { if (alive) setState('error') })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tile.dataset_id, tile.finding_key, refreshNonce])

  if (state === 'loading') {
    return <p style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>Evaluating…</p>
  }
  if (state === 'error') {
    return (
      <p role="alert" style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>
        Could not evaluate this finding right now.
      </p>
    )
  }
  if (state === 'gone' || !finding) {
    return (
      <p data-testid="pin-dormant" style={{ color: 'var(--muted)', fontSize: 12, margin: 0 }}>
        Not currently detected — the data may have changed. The pin stays until
        you remove it.
      </p>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <Badge figures={finding.figures} />
        {(finding.novelty === 'new' || finding.novelty === 'changed') && (
          <span style={{ background: 'var(--accent)', color: 'var(--surface)',
            borderRadius: 3, padding: '0 5px', fontSize: 9, fontWeight: 700 }}>
            {finding.novelty === 'new' ? 'NEW' : 'CHANGED'}
          </span>
        )}
        {finding.significant === true && (
          <span title={finding.p_adjusted != null
              ? `adjusted p = ${finding.p_adjusted}` : 'statistically significant'}
            style={{ fontSize: 9, color: 'var(--muted)', border: '1px solid var(--border)',
              borderRadius: 3, padding: '0 4px' }}>
            significant
          </span>
        )}
      </div>
      {/* Template-first: the deterministic sentence renders immediately; the
          guarded LLM rewrite replaces it only when it arrives. */}
      <p style={{ fontSize: 13, margin: 0, lineHeight: 1.45 }}>
        {polished ?? finding.title}
      </p>
      <div style={{ fontSize: 10, color: 'var(--muted)' }}>
        <Link to={`/datasets/${tile.dataset_id}`}
          style={{ color: 'var(--muted)' }}>
          {tile.dataset_name}
        </Link>
        {' · '}{finding.columns.join(', ')}
      </div>
    </div>
  )
}
