import { useEffect, useState } from 'react'
import { Bot, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { reportsApi, describeMissing, type MissingDependency } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { localDigits } from '../../lib/arabicFormats'
import './share/share.css'

/**
 * Version history for the open report (R2), restyled in redesign 7c.
 *
 * The revision counter always detected concurrent edits; this is the way
 * back. Every edit — from the GUI or the page copilot — leaves a restorable
 * content snapshot, listed newest first and grouped by day. Restore replaces
 * the report's pages and widgets with a chosen version's, and is itself
 * captured first, so it can be undone in turn.
 *
 * Deliberately narrow: it restores CONTENT (charts, layout, theme), never
 * identity (name, sharing, publish state) — the backend enforces that, and
 * the confirmation says so, because "go back to Tuesday" must not also
 * un-share the dashboard. Previewing or comparing a version, and naming one,
 * need a backend that returns version content (PLAN.md).
 */
export interface VersionHistoryPaneProps {
  reportId: number
  /** The report's current revision, to mark "current" in the list. */
  currentRevision: number | null
  /** Reload the builder after a restore lands. */
  onRestored: () => void | Promise<void>
}

interface VersionRow {
  id: number
  revision: number
  created_at: string | null
  created_by: string | null
  pages: number
  widgets: number
  via?: string | null
  note?: string | null
}

const COLORS = [1, 2, 3, 4, 5, 6]
const color = (s: string) => `var(--dl-series-${COLORS[[...s].reduce((n, c) => n + c.charCodeAt(0), 0) % COLORS.length]})`

function dayOf(iso: string | null): 'today' | 'yesterday' | 'earlier' {
  if (!iso) return 'earlier'
  const d = new Date(iso), now = new Date()
  const start = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((start(now) - start(d)) / 86400000)
  return diff <= 0 ? 'today' : diff === 1 ? 'yesterday' : 'earlier'
}
/** In the reader's language and on a 24-hour clock (QA2 V10: Arabic showed
 *  "01:01 PM" in English letters). Latin digits, as the app's numbers. */
function when(iso: string | null, group: string, lang: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const loc = lang === 'ar' ? 'ar-u-nu-latn' : 'en-GB'
  return group === 'earlier'
    ? d.toLocaleString(loc, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    : d.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
}

/** Saves this close together by one person are one action as far as a
 *  reader is concerned (QA2 N3): an automatic layout pass writes every
 *  widget separately, and the server snapshots each write. */
const BURST_MS = 10_000
function bursts(rows: VersionRow[]): VersionRow[][] {
  const out: VersionRow[][] = []
  for (const r of rows) {
    const g = out[out.length - 1]
    const prev = g?.[g.length - 1]
    const close = prev && prev.created_by === r.created_by && (prev.via ?? null) === (r.via ?? null)
      && prev.created_at && r.created_at
      && Math.abs(new Date(prev.created_at).getTime() - new Date(r.created_at).getTime()) <= BURST_MS
    if (close) g.push(r); else out.push([r])
  }
  return out
}

export default function VersionHistoryPane({ reportId, currentRevision, onRestored }: VersionHistoryPaneProps) {
  const t = useT()
  const { language } = useDirection()
  const confirm = useConfirm()
  const [rows, setRows] = useState<VersionRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [restoring, setRestoring] = useState<number | null>(null)
  const [selected, setSelected] = useState<number | null>(null)

  const load = () => {
    setError(null)
    reportsApi.versions(reportId)
      .then(setRows)
      .catch(() => setError(t('shx.vh.loadFailed')))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [reportId])

  const restore = async (v: VersionRow) => {
    // E09: what this version names that no longer exists is said BEFORE the
    // restore, not discovered as charts quietly drawing something else.
    let missing: MissingDependency[] = []
    try { missing = (await reportsApi.versionDependencies(reportId, v.id)).missing ?? [] } catch { /* the restore still says */ }
    const gap = missing.length ? `\n\n${t('shx.vh.missing', { what: describeMissing(missing) })}` : ''
    if (!await confirm({
      title: t('shx.vh.confirmTitle', { n: localDigits(String(v.revision)) }),
      body: t('shx.vh.confirmBody') + gap,
      confirmLabel: t('shx.vh.restore'),
      destructive: false,
    })) return
    setRestoring(v.id)
    try {
      const got = await reportsApi.restoreVersion(reportId, v.id)
      toast.success(t('shx.vh.restored', { n: localDigits(String(got.restored_revision)) }))
      if (got.missing?.length) toast(t('shx.vh.restoredMissing', { what: describeMissing(got.missing) }), { icon: '⚠' })
      await onRestored()
      setSelected(null)
      load()
    } catch {
      toast.error(t('shx.vh.failed'))
    } finally {
      setRestoring(null)
    }
  }

  let group = ''
  return (
    <div className="shx-vp">
      <div className="shx-vp-h"><h2>{t('shx.vh.title')}</h2></div>
      <div className="shx-vl">
        {error && <p role="alert" className="shx-err">{error}</p>}
        {rows && rows.length === 0 && <p className="shx-note">{t('shx.vh.empty')}</p>}
        {!rows && !error && <p className="shx-note">{t('common.loading')}</p>}
        {bursts(rows ?? []).map(members => {
          const v = members[0]
          const g = dayOf(v.created_at)
          const head = g !== group ? (group = g, <div key={`g-${g}`} className="shx-vg">{t(`shx.vh.${g}` as 'shx.vh.today')}</div>) : null
          if (members.length > 1) {
            // One entry for the burst; Restore goes to the state before it.
            const oldest = members[members.length - 1]
            const on = selected === v.id
            const who = v.created_by?.split('@')[0] ?? null
            return [head, (
              <div key={v.id} role="button" tabIndex={0} aria-pressed={on} aria-expanded={on} className="shx-v"
                onClick={e => { if (!(e.target as HTMLElement).closest('button')) setSelected(on ? null : v.id) }}
                onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); setSelected(on ? null : v.id) } }}>
                <span className="dt" aria-hidden />
                <div className="tx">
                  <div className="tm">
                    {t('shx.vh.burst', { n: localDigits(String(members.length)) })}
                    <span style={{ fontWeight: 400, color: 'var(--muted)' }}>· {when(v.created_at, g, language)}</span>
                  </div>
                  {who && (
                    <div className="by"><span className="shx-av" style={{ background: color(who) }} aria-hidden>{[...who][0]}</span><bdi>{who}</bdi></div>
                  )}
                  <div className="sm">{t('shx.vh.burstWhy')}</div>
                  {on && (<>
                    <ul className="shx-vb">
                      {members.map(m => (
                        <li key={m.id}>{t('shx.vh.revision', { n: localDigits(String(m.revision)) })}<span> · {when(m.created_at, g, language)}</span></li>
                      ))}
                    </ul>
                    <div className="shx-va">
                      <button type="button" className="btn btn-primary btn-sm" disabled={restoring != null}
                        aria-label={t('shx.vh.burstRestore')} onClick={() => void restore(oldest)}>
                        <RotateCcw size={13} aria-hidden />{restoring === oldest.id ? t('shx.vh.restoring') : t('shx.vh.burstRestore')}
                      </button>
                    </div>
                  </>)}
                </div>
              </div>
            )]
          }
          const isCurrent = currentRevision != null && v.revision === currentRevision
          const on = selected === v.id
          const who = v.created_by?.split('@')[0] ?? null
          return [head, (
            <div key={v.id} role="button" tabIndex={0} aria-pressed={on} className={`shx-v${isCurrent ? ' cur' : ''}`}
              onClick={e => { if (!(e.target as HTMLElement).closest('button')) setSelected(on ? null : v.id) }}
              onKeyDown={e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); setSelected(on ? null : v.id) } }}>
              <span className="dt" aria-hidden />
              <div className="tx">
                <div className="tm">
                  {t('shx.vh.revision', { n: localDigits(String(v.revision)) })}
                  <span style={{ fontWeight: 400, color: 'var(--muted)' }}>· {when(v.created_at, g, language)}</span>
                  {isCurrent && <span className="shx-cur">{t('shx.vh.current')}</span>}
                </div>
                {who && (
                  <div className="by"><span className="shx-av" style={{ background: color(who) }} aria-hidden>{[...who][0]}</span><bdi>{who}</bdi></div>
                )}
                {v.via === 'copilot' && (
                  <div data-testid="version-copilot" className="sm ai">
                    <Bot size={12} aria-hidden /> <span>{v.note ? <bdi>{v.note}</bdi> : t('shx.vh.copilot')}{v.created_by ? ` ${t('shx.vh.askedBy', { who: v.created_by })}` : ''}</span>
                  </div>
                )}
                <div className="sm">{t('shx.vh.counts', { p: localDigits(String(v.pages)), w: localDigits(String(v.widgets)) })}</div>
                {on && !isCurrent && (
                  <div className="shx-va">
                    <button type="button" className="btn btn-primary btn-sm" disabled={restoring != null}
                      aria-label={t('shx.vh.restoreAria', { n: localDigits(String(v.revision)) })} onClick={() => void restore(v)}>
                      <RotateCcw size={13} aria-hidden />{restoring === v.id ? t('shx.vh.restoring') : t('shx.vh.restore')}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )]
        })}
      </div>
    </div>
  )
}
