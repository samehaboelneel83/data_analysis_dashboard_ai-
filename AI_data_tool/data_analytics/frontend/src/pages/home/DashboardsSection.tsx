import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowDownUp, Download, ExternalLink, LayoutDashboard, LayoutGrid, Link2, List, Pencil, Plus, Share2, Trash2,
} from 'lucide-react'
import toast from 'react-hot-toast'
import ActionMenu, { type ActionMenuItem } from '../../components/ActionMenu'
import { useConfirm } from '../../components/ui/ConfirmDialog'
import { usePrompt } from '../../components/ui/PromptDialog'
import { formatTimeAgo, useT } from '../../i18n'
import { reportsApi } from '../../services/api'
import type { Report } from '../../types/report'
import { ShareDialog } from '../reports/listParts'
import { Empty, SecHead, Sk } from './parts'
import Thumb, { firstPageWidgets } from './Thumb'

/**
 * Home's Dashboards section (redesign 7a): the six most recent, as cards or a
 * table, with the list page's own actions behind the same permission rules.
 * Left out, because the backend has no data for them: favourites, owner
 * names, "Shared with me" and Duplicate (PLAN.md, Backend follow-ups).
 */

const SHOWN = 6
const PREF = 'home.dashboards'

type Filter = 'all' | 'mine'
type Sort = 'recent' | 'name'
type View = 'grid' | 'list'

function readPref(): { filter: Filter; sort: Sort; view: View } {
  try {
    const p = JSON.parse(localStorage.getItem(PREF) ?? '{}')
    return { filter: p.filter === 'mine' ? 'mine' : 'all', sort: p.sort === 'name' ? 'name' : 'recent', view: p.view === 'list' ? 'list' : 'grid' }
  } catch { return { filter: 'all', sort: 'recent', view: 'grid' } }
}

const errText = (e: unknown, fallback: string) =>
  (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail as string | undefined ?? fallback

export default function DashboardsSection({ reports, isAdmin, loading, onRename, onDelete, onOpen }: {
  reports: Report[]
  isAdmin: boolean
  loading: boolean
  onRename: (id: number, name: string) => void
  onDelete: (id: number) => void
  onOpen: () => void
}) {
  const t = useT()
  const confirm = useConfirm()
  const prompt = usePrompt()
  const [pref, setPref] = useState(readPref)
  const [sharing, setSharing] = useState<Report | null>(null)
  const set = (p: Partial<typeof pref>) => setPref(prev => {
    const next = { ...prev, ...p }
    try { localStorage.setItem(PREF, JSON.stringify(next)) } catch { /* a convenience */ }
    return next
  })

  const shown = useMemo(() => {
    const xs = reports.filter(r => pref.filter === 'all' || r.is_mine)
    const sorted = [...xs].sort(pref.sort === 'name'
      ? (a, b) => a.name.localeCompare(b.name)
      : (a, b) => new Date(b.updated_at ?? 0).getTime() - new Date(a.updated_at ?? 0).getTime())
    return sorted.slice(0, SHOWN)
  }, [reports, pref.filter, pref.sort])

  // Draft / Published as the list page reads them: a legacy (unowned) report
  // is neither, and the folder that may publish a draft is not visible here.
  const badge = (r: Report) => r.created_by == null ? null
    : r.published ? <span className="hm-bd pub">{t('hm.badge.published')}</span>
    : <span className="hm-bd draft" title={t('home.draftTitle')}>{t('hm.badge.draft')}</span>
  const meta = (r: Report) => r.my_capability === 'view' ? t('home.viewOnly')
    : formatTimeAgo(r.updated_at, t) && t('home.modified', { when: formatTimeAgo(r.updated_at, t)! })

  const canEdit = (r: Report) => (r.my_capability ?? 'view') !== 'view'
  const canShare = (r: Report) => r.created_by != null && (!!r.is_mine || isAdmin)

  const rename = async (r: Report) => {
    const name = (await prompt({ title: t('hm.dash.renameTitle'), defaultValue: r.name, confirmLabel: t('hm.dash.rename') }))?.trim()
    if (!name || name === r.name) return
    try {
      await reportsApi.update(r.id, { name })
      onRename(r.id, name)
      toast.success(t('hm.dash.renamed'))
    } catch (e) { toast.error(errText(e, t('hm.dash.renameFailed'))) }
  }
  const remove = async (r: Report) => {
    if (!await confirm({ title: t('hm.dash.deleteTitle', { name: r.name }), body: t('hm.dash.deleteBody'),
      confirmLabel: t('hm.dash.delete') })) return
    try {
      await reportsApi.delete(r.id)
      onDelete(r.id)
      toast.success(t('hm.dash.deleted'))
    } catch (e) { toast.error(errText(e, t('hm.dash.deleteFailed'))) }
  }
  const copyLink = async (r: Report) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/reports/${r.id}`)
      toast.success(t('hm.dash.copied'))
    } catch { toast.error(t('hm.dash.copyFailed')) }
  }
  const exportPdf = (r: Report) => {
    // The server applies the export policy; a refusal comes back as its reason.
    reportsApi.downloadPdf(r.id, r.name)
      .then(() => toast.success(t('hm.dash.pdfDone')))
      .catch(e => toast.error(errText(e, t('hm.dash.pdfFailed'))))
  }
  const menu = (r: Report): ActionMenuItem[] => [
    ...(canEdit(r) ? [{ key: 'rename', label: t('hm.dash.rename'), icon: <Pencil size={14} />, onSelect: () => void rename(r) }] : []),
    { key: 'link', label: t('hm.dash.copyLink'), icon: <Link2 size={14} />, onSelect: () => void copyLink(r) },
    { key: 'pdf', label: t('hm.dash.exportPdf'), icon: <Download size={14} />, onSelect: () => exportPdf(r) },
    ...(canEdit(r) ? [{ key: 'delete', label: t('hm.dash.delete'), icon: <Trash2 size={14} />, danger: true, onSelect: () => void remove(r) }] : []),
  ]
  const more = (r: Report, cls: string) => (
    <ActionMenu items={menu(r)} label={t('hm.dash.more', { name: r.name })} portal align="end" triggerClassName={cls} />
  )
  const shareBtn = (r: Report) => canShare(r) && (
    <button type="button" className="hm-ib" onClick={() => setSharing(r)}
      aria-label={t('hm.dash.shareName', { name: r.name })} title={t('hm.dash.share')}><Share2 size={15} aria-hidden /></button>
  )
  const openLink = (r: Report, className: string, children: React.ReactNode, testId?: string) => (
    <Link className={className} to={`/reports/${r.id}`} title={r.name} data-testid={testId}
      onClick={e => { if (e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) onOpen() }}>{children}</Link>
  )

  const head = <SecHead id="hm-dash" title={t('nav.dashboards')} count={loading ? undefined : reports.length}
    all={!loading && reports.length ? '/reports' : undefined} />

  let body: React.ReactNode
  if (loading) {
    body = <div className="hm-dg">{[0, 1, 2, 3, 4, 5].map(i => (
      <div key={i} className="hm-dc"><span className="sk" style={{ aspectRatio: '16/9', borderRadius: '13px 13px 0 0' }} />
        <div className="hm-db"><Sk w="80%" h={12} /><Sk w="55%" h={10} style={{ marginTop: 12 }} /></div></div>
    ))}</div>
  } else if (!reports.length) {
    body = <Empty icon={LayoutDashboard} title={t('hm.dash.empty')} text={t('hm.dash.emptyText')}
      actions={<Link className="btn btn-primary btn-sm" to="/reports?new=1"><Plus size={14} aria-hidden />{t('hm.qa.newDash')}</Link>} />
  } else {
    const tools = (
      <div className="hm-tools">
        <div className="hm-seg" role="group" aria-label={t('hm.dash.filter')}>
          {(['all', 'mine'] as Filter[]).map(k => (
            <button key={k} type="button" aria-pressed={pref.filter === k} onClick={() => set({ filter: k })}>
              {t(k === 'all' ? 'hm.dash.all' : 'hm.dash.mine')}
            </button>
          ))}
        </div>
        <span className="hm-sp" />
        <ActionMenu label={t('hm.dash.sortBy', { sort: t(pref.sort === 'recent' ? 'hm.dash.recent' : 'hm.dash.name') })}
          align="end" trigger={<><ArrowDownUp size={14} aria-hidden />{t(pref.sort === 'recent' ? 'hm.dash.recent' : 'hm.dash.name')}</>}
          items={[
            { key: 'recent', label: t('hm.dash.recent'), onSelect: () => set({ sort: 'recent' }) },
            { key: 'name', label: t('hm.dash.nameAz'), onSelect: () => set({ sort: 'name' }) },
          ]} />
        <div className="hm-seg ic" role="group" aria-label={t('hm.dash.view')}>
          <button type="button" aria-pressed={pref.view === 'grid'} onClick={() => set({ view: 'grid' })}
            aria-label={t('hm.dash.grid')} title={t('hm.dash.grid')}><LayoutGrid size={15} aria-hidden /></button>
          <button type="button" aria-pressed={pref.view === 'list'} onClick={() => set({ view: 'list' })}
            aria-label={t('hm.dash.list')} title={t('hm.dash.list')}><List size={15} aria-hidden /></button>
        </div>
      </div>
    )
    const items = !shown.length
      ? <Empty small icon={LayoutDashboard} title={t('hm.dash.noneMine')} text={t('hm.dash.noneMineText')} />
      : pref.view === 'grid' ? (
        <div className="hm-dg" data-testid="home-dashboards">
          {shown.map(r => (
            <article key={r.id} className="hm-dc">
              <div className="hm-th-w">
                <Thumb widgets={firstPageWidgets(r)} />
                <div className="hm-ov">
                  {openLink(r, 'btn btn-primary btn-sm', <><ExternalLink size={14} aria-hidden />{t('hm.dash.open')}</>)}
                  <span className="hm-sp" />
                  {shareBtn(r)}
                  {more(r, 'hm-ib')}
                </div>
              </div>
              <div className="hm-db">
                {openLink(r, 'hm-link hm-dn', <bdi>{r.name}</bdi>, `home-dash-${r.id}`)}
                <div className="hm-dm"><span>{meta(r)}</span><span className="hm-sp" />{badge(r)}</div>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="hm-tbw" data-testid="home-dashboards">
          <table className="hm-tb">
            <thead><tr>
              <th>{t('hm.col.name')}</th><th>{t('hm.col.status')}</th><th>{t('hm.col.modified')}</th>
              <th style={{ width: '1%' }}><span className="dl-sr-only">{t('hm.col.actions')}</span></th>
            </tr></thead>
            <tbody>{shown.map(r => (
              <tr key={r.id}>
                <td><div className="hm-nm"><span className="hm-src s-der" aria-hidden><LayoutDashboard size={17} /></span>
                  {openLink(r, 'hm-rl', <bdi>{r.name}</bdi>, `home-dash-${r.id}`)}</div></td>
                <td>{badge(r)}</td>
                <td className="nw">{meta(r)}</td>
                <td><div className="hm-ra">{shareBtn(r)}{more(r, 'hm-ib')}</div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )
    body = <>{tools}{items}</>
  }
  return (
    <section className="hm-sec" aria-labelledby="hm-dash">
      {head}{body}
      {sharing && <ShareDialog report={sharing} onClose={() => setSharing(null)} />}
    </section>
  )
}
