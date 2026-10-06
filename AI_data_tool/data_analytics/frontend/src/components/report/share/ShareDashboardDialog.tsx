import { useEffect, useState } from 'react'
import { Building2, CalendarClock, Code2, Copy, KeyRound, Lock, ShieldCheck, Users, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { authzApi, reportGrantsApi, reportsApi, type ReportGrant } from '../../../services/api'
import { useModalDialog } from '../../ui/useModalDialog'
import { useT, type MessageKey } from '../../../i18n'
import { SchedulePanel } from '../../../pages/reportBuilder/SchedulePanel'
import { EmbedSection, GuestLinks } from './ShareSections'
import './share.css'

/**
 * Share a dashboard (redesign 7c): People, Embed and Schedule in one dialog,
 * for the builder's header and the Dashboards list alike.
 *
 * Everything here is an existing endpoint, with v1's rules:
 *  - people are named by EMAIL (sharing must not double as an org-directory
 *    listing), at view / edit / edit + data; only the author or an admin may
 *    change who has access, and re-sending a grant changes its level;
 *  - general access is the publish flag (Restricted = a private draft,
 *    Workspace = everyone in the organisation, view-only);
 *  - "anyone with the link" is v1's guest links (several, each URL shown
 *    once, 1–90 days, with the sharer's data permissions);
 *  - embedding is host-signed (EmbedSection), schedules are v1's panel.
 * Left out (no backend): a comment level, user suggestions, groups, pending
 * invitations, invitation emails, transfer of ownership (PLAN.md).
 */

export interface ShareTarget {
  id: number
  name: string
  created_by?: number | null
  is_mine?: boolean
  published?: boolean
}

type Tab = 'people' | 'embed' | 'schedule'
const COLORS = [1, 2, 3, 4, 5, 6]
const color = (s: string) => `var(--dl-series-${COLORS[[...s].reduce((n, c) => n + c.charCodeAt(0), 0) % COLORS.length]})`

export default function ShareDashboardDialog({ report, canEdit, isAdmin, pageId, initialTab = 'people', onClose, onPublishedChange, onAccessWhy, onAccessByRole }: {
  report: ShareTarget
  /** The viewer may edit this dashboard: guest links, embedding, schedules. */
  canEdit: boolean
  isAdmin: boolean
  /** The page the copied link should open on. */
  pageId?: number | null
  initialTab?: Tab
  onClose: () => void
  onPublishedChange?: (published: boolean) => void
  onAccessWhy?: () => void
  onAccessByRole?: () => void
}) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [tab, setTab] = useState<Tab>(canEdit ? initialTab : 'people')
  // Grants and publishing are the AUTHOR's controls (admins too), on an
  // authored dashboard only: a legacy one is outside that regime.
  const authored = report.created_by != null
  const manages = authored && (!!report.is_mine || isAdmin)

  const [grants, setGrants] = useState<ReportGrant[] | null>(null)
  const [email, setEmail] = useState('')
  const [level, setLevel] = useState<'view' | 'edit' | 'data'>('edit')
  const [busy, setBusy] = useState(false)
  const [published, setPublished] = useState(!!report.published)
  const [guestBlocked, setGuestBlocked] = useState<string | null>(null)

  useEffect(() => {
    if (!manages) return
    reportGrantsApi.list(report.id)
      .then(setGrants)
      .catch(() => { toast.error(t('dsh.sd.loadFailed')); setGrants([]) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.id, manages])
  // Whether a guest link is allowed here, and the server's reason if not (a
  // Restricted label, an export policy) -- greyed with the reason, never hidden.
  useEffect(() => {
    if (!canEdit) return
    Promise.resolve().then(() => authzApi.decisions([{ resource: 'report', id: report.id, action: 'share_link' }]))
      .then(ds => { const d = ds?.find(x => x.action === 'share_link'); setGuestBlocked(d && !d.allowed ? d.reason : null) })
      .catch(() => setGuestBlocked(null))
  }, [report.id, canEdit])

  const LEVEL: Record<'view' | 'edit' | 'data', MessageKey> = { view: 'dsh.sd.view', edit: 'dsh.sd.edit', data: 'dsh.sd.data' }
  const levelSelect = (value: 'view' | 'edit' | 'data', onChange: (v: 'view' | 'edit' | 'data') => void, label: string, small = false) => (
    <select className={`shx-sel${small ? ' sm' : ''}`} value={value} aria-label={label} onChange={e => onChange(e.target.value as 'view' | 'edit' | 'data')}>
      {(['view', 'edit', 'data'] as const).map(k => <option key={k} value={k}>{t(LEVEL[k])}</option>)}
    </select>
  )

  const invite = async () => {
    if (!email.trim()) return
    setBusy(true)
    try {
      const g = await reportGrantsApi.create(report.id, { email: email.trim(), level })
      setGrants(prev => [...(prev ?? []).filter(x => x.user_id !== g.user_id), g])
      setEmail('')
      toast.success(t('dsh.sd.shared', { email: g.email }))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('dsh.sd.failed'))
    } finally { setBusy(false) }
  }
  const changeLevel = async (g: ReportGrant, next: 'view' | 'edit' | 'data') => {
    try {
      // Re-sending a grant for the same person updates its level.
      const got = await reportGrantsApi.create(report.id, { email: g.email, level: next })
      setGrants(prev => (prev ?? []).map(x => x.id === g.id ? { ...x, ...got } : x))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('dsh.sd.failed'))
    }
  }
  const remove = async (g: ReportGrant) => {
    try {
      await reportGrantsApi.remove(report.id, g.id)
      setGrants(prev => (prev ?? []).filter(x => x.id !== g.id))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('dsh.sd.removeFailed'))
    }
  }
  const setAccess = async (next: boolean) => {
    if (next === published) return
    try {
      await reportsApi.setPublished(report.id, next)
      setPublished(next)
      onPublishedChange?.(next)
      toast.success(t(next ? 'dsh.toast.published' : 'dsh.toast.unpublished'))
    } catch (e) {
      // The publish gate answers with {message, findings}.
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof d === 'string' ? d : (d as { message?: string })?.message ?? t('dsh.toast.publishFailed'))
    }
  }
  const pageLink = () => {
    const url = new URL(`${window.location.origin}/reports/${report.id}`)
    if (pageId != null) url.searchParams.set('page', String(pageId))
    return url.toString()
  }
  const copyLink = () => navigator.clipboard.writeText(pageLink())
    .then(() => toast.success(t('dsh.toast.copied')))
    .catch(() => toast.error(t('dsh.toast.copyFailed')))

  const people = (
    <>
      {manages ? (<>
        <div className="shx-inv">
          <input className="shx-in" type="email" value={email} onChange={e => setEmail(e.target.value)} dir="ltr"
            placeholder="colleague@company.com" aria-label={t('dsh.sd.email')}
            onKeyDown={e => { if (e.key === 'Enter') void invite() }} />
          {levelSelect(level, setLevel, t('dsh.sd.level'))}
          <button type="button" className="btn btn-primary" onClick={() => void invite()} disabled={busy || !email.trim()}
            title={!email.trim() ? t('dsh.sd.needEmail') : undefined}>{t('shx.invite')}</button>
        </div>
        <p className="shx-note">{t('shx.emailOnly')}</p>

        <div className="shx-sec">{t('shx.withAccess')}</div>
        <div className="shx-ppl" data-testid="share-people">
          {report.is_mine && (
            <div className="shx-p">
              <span className="shx-av" style={{ background: 'var(--accent)' }} aria-hidden>{t('hm.you').slice(0, 1)}</span>
              <span className="tx"><b>{t('hm.you')}</b></span>
              <span className="shx-own">{t('shx.owner')}</span>
            </div>
          )}
          {grants === null && <p className="shx-note">{t('common.loading')}</p>}
          {grants?.length === 0 && <p className="shx-note">{t('dsh.sd.none')}</p>}
          {grants?.map(g => {
            const who = g.email.split('@')[0]
            return (
              <div key={g.id} className="shx-p">
                <span className="shx-av" style={{ background: color(g.email) }} aria-hidden>{[...who][0]}</span>
                <span className="tx"><b dir="auto">{who}</b><span dir="ltr">{g.email}</span></span>
                {levelSelect(g.level, v => void changeLevel(g, v), t('shx.levelFor', { email: g.email }), true)}
                <button type="button" className="shx-ib" onClick={() => void remove(g)} aria-label={t('dsh.sd.removeFor', { email: g.email })}
                  title={t('dsh.sd.remove')}><X size={15} aria-hidden /></button>
              </div>
            )
          })}
        </div>

        <div className="shx-sec">{t('shx.general')}</div>
        <div className="shx-acc" role="radiogroup" aria-label={t('shx.general')}>
          <button type="button" role="radio" aria-checked={!published} className="shx-opt" onClick={() => void setAccess(false)}>
            <span className="ic" aria-hidden><Lock size={16} /></span>
            <span className="tx"><b>{t('shx.restricted')}</b>{t('shx.restrictedSub')}</span>
          </button>
          <button type="button" role="radio" aria-checked={published} className="shx-opt" onClick={() => void setAccess(true)}>
            <span className="ic" aria-hidden><Building2 size={16} /></span>
            <span className="tx"><b>{t('shx.workspace')}</b>{t('shx.workspaceSub')}</span>
          </button>
        </div>
      </>) : (
        <div className="shx-info"><ShieldCheck size={15} aria-hidden /><span>{t(authored ? 'shx.notAuthor' : 'shx.legacy')}</span></div>
      )}

      {canEdit && (<>
        <div className="shx-sec">{t('shx.link')}</div>
        <div className="shx-link" style={{ marginTop: 0 }}>
          <div className="shx-url" dir="ltr"><span>{pageLink()}</span></div>
          <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} onClick={() => void copyLink()}>
            <Copy size={14} aria-hidden />{t('dsh.copyLink')}
          </button>
        </div>
        <p className="shx-note">{t('shx.linkNote')}</p>

        <div className="shx-sec">{t('shx.guest')}</div>
        <GuestLinks reportId={report.id} blockedReason={guestBlocked} />
      </>)}
    </>
  )

  const tabs: { k: Tab; icon: typeof Users; label: MessageKey }[] = [
    { k: 'people', icon: Users, label: 'shx.tab.people' },
    ...(canEdit ? [{ k: 'embed' as Tab, icon: Code2, label: 'shx.tab.embed' as MessageKey },
      { k: 'schedule' as Tab, icon: CalendarClock, label: 'shx.tab.schedule' as MessageKey }] : []),
  ]

  return (
    <div className="shx-scrim" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={ref} className="shx-dlg" role="dialog" aria-modal="true" aria-label={t('dsh.shareName', { name: report.name })}>
        <div className="shx-h">
          <div className="tt"><h2>{t('dsh.sd.title', { name: report.name })}</h2></div>
          <button type="button" className="shx-ib" onClick={onClose} aria-label={t('hm.close')} title={t('hm.close')}><X size={16} aria-hidden /></button>
        </div>
        {tabs.length > 1 && (
          <div className="shx-tabs" role="tablist">
            {tabs.map(x => (
              <button key={x.k} type="button" role="tab" className="shx-tab" aria-selected={tab === x.k} onClick={() => setTab(x.k)}>
                <x.icon size={15} aria-hidden />{t(x.label)}
              </button>
            ))}
          </div>
        )}
        <div className="shx-b" role={tabs.length > 1 ? 'tabpanel' : undefined}>
          {tab === 'people' && people}
          {tab === 'embed' && <EmbedSection reportId={report.id} />}
          {tab === 'schedule' && <div className="shx-sched"><SchedulePanel reportId={report.id} /></div>}
        </div>
        <div className="shx-f">
          {onAccessWhy && <button type="button" className="lk" onClick={onAccessWhy}><KeyRound size={14} aria-hidden />{t('shx.why')}</button>}
          {isAdmin && onAccessByRole && <button type="button" className="lk" onClick={onAccessByRole}><ShieldCheck size={14} aria-hidden />{t('shx.byRole')}</button>}
          <span className="shx-sp" />
          <button type="button" className="btn btn-primary" onClick={onClose}>{t('shx.done')}</button>
        </div>
      </div>
    </div>
  )
}
