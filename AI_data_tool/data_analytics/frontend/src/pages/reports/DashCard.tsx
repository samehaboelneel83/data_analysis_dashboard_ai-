import { Link } from 'react-router-dom'
import { ArrowUpRight, Database, Eye, Folder, FolderOpen, Share2, Sparkles } from 'lucide-react'
import ActionMenu, { type ActionMenuItem } from '../../components/ActionMenu'
import { formatTimeAgo, useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import type { ReportSummary } from '../../services/api'
import Thumb, { firstPageWidgets } from '../home/Thumb'
import { pageCount, provenance, showsDataset, statusOf } from './model'

/**
 * One dashboard, as a card (grid) or a row (list), for the Dashboards page
 * (redesign 7b). The page decides what this viewer may do; this only draws it.
 * No star, owner avatar, view count or Duplicate: the backend has no data for
 * them (PLAN.md, Backend follow-ups).
 */

export interface DashProps {
  r: ReportSummary
  datasetName?: string
  folderName?: string | null
  canEdit: boolean
  canShare: boolean
  selected: boolean
  selectMode: boolean
  draggable: boolean
  dragging: boolean
  menu: ActionMenuItem[]
  onToggle: () => void
  onShare: () => void
  onOpen: () => void
  onDragStart: () => void
  onDragEnd: () => void
}

/** Only a plain left-click opens here; modified clicks open a new tab. */
const plain = (e: React.MouseEvent) => !(e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey)

export function Badge({ r }: { r: ReportSummary }) {
  const t = useT()
  if (provenance(r).suggested) return <span className="dsh-bdg ai" title={t('dsh.suggestedTitle')}><Sparkles size={12} aria-hidden />{t('dsh.badge.ai')}</span>
  const s = statusOf(r)
  if (!s) return null
  return s === 'pub'
    ? <span className="dsh-bdg pub" title={t('dsh.publishedTitle')}><i />{t('dsh.badge.published')}</span>
    : <span className="dsh-bdg draft" title={t('home.draftTitle')}><i />{t('dsh.badge.draft')}</span>
}

function Blurb({ r, className }: { r: ReportSummary; className: string }) {
  const t = useT()
  const { blurb } = provenance(r)
  if (blurb) return <p className={className} title={blurb}>{blurb}</p>
  const n = pageCount(r)
  return <p className={`${className} none`}>{t(n === 1 ? 'dsh.onePage' : 'dsh.pages', { n: localDigits(String(n)) })}</p>
}

export function DashCard(p: DashProps) {
  const t = useT()
  const { r } = p
  const when = formatTimeAgo(r.updated_at, t)
  const sug = provenance(r).suggested
  return (
    <article className={`dsh-card${sug ? ' sug' : ''}`} data-testid={`dash-card-${r.id}`}
      data-selected={p.selected || undefined} data-dragging={p.dragging || undefined}
      draggable={p.draggable && !p.selectMode}
      onDragStart={e => { e.dataTransfer?.setData('text/plain', String(r.id)); p.onDragStart() }}
      onDragEnd={p.onDragEnd}
      onClick={e => {
        // In select mode the whole card is the checkbox.
        if (!p.selectMode || !p.canEdit) return
        if ((e.target as HTMLElement).closest('input, button')) return
        e.preventDefault()
        p.onToggle()
      }}>
      <div className="dsh-th">
        <Thumb widgets={firstPageWidgets(r)} />
        {p.canEdit && (
          <input type="checkbox" className="dsh-ck" checked={p.selected} onChange={p.onToggle}
            aria-label={t('bulk.selectRow', { name: r.name })} />
        )}
        {!p.canEdit && <span className="dsh-vo"><Eye size={12} aria-hidden />{t('dsh.viewOnly')}</span>}
        <div className="dsh-ov">
          <Link className="btn btn-primary" to={`/reports/${r.id}`} tabIndex={-1} aria-hidden="true"
            onClick={e => { if (p.selectMode) e.preventDefault(); else if (plain(e)) p.onOpen() }}>{t('dsh.open')}</Link>
          <span className="dsh-sp" />
          {p.canShare && (
            <button type="button" className="dsh-ibx" onClick={p.onShare}
              aria-label={t('dsh.shareName', { name: r.name })} title={t('dsh.share')}><Share2 size={16} aria-hidden /></button>
          )}
          <ActionMenu items={p.menu} label={t('dsh.moreFor', { name: r.name })} portal align="end" triggerClassName="dsh-ibx" />
        </div>
      </div>
      <div className="dsh-bd">
        <h3 className="dsh-nm">
          <Link to={`/reports/${r.id}`} title={r.name}
            onClick={e => { if (p.selectMode) e.preventDefault(); else if (plain(e)) p.onOpen() }}><bdi>{r.name}</bdi></Link>
        </h3>
        <Blurb r={r} className="dsh-desc" />
        <div className="dsh-mt">
          <Badge r={r} />
          <span className="dsh-sp" />
          {when && <span className="tm">{t('dsh.modified', { when })}</span>}
          {showsDataset(r, p.datasetName) && (
            <span className="dsh-ch" title={p.datasetName}><Database size={12} aria-hidden /><span><bdi>{p.datasetName}</bdi></span></span>
          )}
        </div>
      </div>
    </article>
  )
}

export function DashRow(p: DashProps) {
  const t = useT()
  const { r } = p
  const folder = p.folderName ?? t('dsh.notInFolder')
  const folderIcon = p.folderName ? <Folder size={14} aria-hidden /> : <FolderOpen size={14} aria-hidden />
  return (
    <tr data-testid={`dash-row-${r.id}`} data-selected={p.selected || undefined}
      draggable={p.draggable && !p.selectMode}
      onDragStart={e => { e.dataTransfer?.setData('text/plain', String(r.id)); p.onDragStart() }}
      onDragEnd={p.onDragEnd}>
      <td className="c-ck">
        {p.canEdit && <input type="checkbox" className="dsh-ck" checked={p.selected} onChange={p.onToggle}
          aria-label={t('bulk.selectRow', { name: r.name })} />}
      </td>
      <td className="c-nm">
        <div className="dsh-nmc">
          <span className="dsh-mth"><Thumb widgets={firstPageWidgets(r)} /></span>
          <span className="tx">
            {/* dir="auto": a clipped English name in an Arabic table keeps its
                start and loses its end, not the other way round. */}
            <Link to={`/reports/${r.id}`} title={r.name} dir="auto"
              onClick={e => { if (p.selectMode) e.preventDefault(); else if (plain(e)) p.onOpen() }}>{r.name}</Link>
            <Blurb r={r} className="d" />
            {/* Shown only on a narrow table, where the folder column gives way. */}
            <span className="fdi">{folderIcon}<span dir="auto">{folder}</span><span className="sti"><Badge r={r} /></span></span>
          </span>
        </div>
      </td>
      <td className="c-fd">
        {/* dir="auto" on the span that clips: text loses its end, whatever the page direction. */}
        <span className="fd" title={folder}>{folderIcon}<span dir="auto">{folder}</span></span>
      </td>
      <td className="c-ds">{p.datasetName
        ? <span className="dsh-ch" style={{ flex: 'none' }} title={p.datasetName}><Database size={12} aria-hidden /><span dir="auto">{p.datasetName}</span></span>
        : null}</td>
      <td className="c-st">
        <Badge r={r} />
        {!p.canEdit && <span className="dsh-bdg draft" style={{ marginInlineStart: 6 }} title={t('dsh.viewOnly')}>
          <Eye size={12} aria-label={t('dsh.viewOnly')} /></span>}
      </td>
      <td className="nw" style={{ color: 'var(--muted)' }}>{formatTimeAgo(r.updated_at, t)}</td>
      <td className="c-act">
        <span className="dsh-ra">
          <Link className="dsh-ibx q" to={`/reports/${r.id}`} tabIndex={-1} aria-hidden="true"
            onClick={e => { if (plain(e)) p.onOpen() }} title={t('dsh.open')}><ArrowUpRight size={16} className="flip" /></Link>
          {p.canShare && (
            <button type="button" className="dsh-ibx q" onClick={p.onShare}
              aria-label={t('dsh.shareName', { name: r.name })} title={t('dsh.share')}><Share2 size={16} aria-hidden /></button>
          )}
          <ActionMenu items={p.menu} label={t('dsh.moreFor', { name: r.name })} portal align="end" triggerClassName="dsh-ibx" />
        </span>
      </td>
    </tr>
  )
}
