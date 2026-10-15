import { useEffect, useState } from 'react'
import { Building2, CalendarClock, Code2, Copy, KeyRound, Lock, Network, Send, ShieldCheck, SlidersHorizontal, Users, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { authzApi, publishingApi, reportGrantsApi, reportsApi, workspaceApi, type GrantBody, type ListedRecords, type ReportGrant, type WorkspaceShareOptions } from '../../../services/api'
import { useModalDialog } from '../../ui/useModalDialog'
import { useConfirm } from '../../ui/ConfirmDialog'
import { useT, type MessageKey } from '../../../i18n'
import { formatDate } from '../../../lib/dateFormat'
import PublishingPanel from './PublishingPanel'
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
 *    change who has access. A share may also name a ROLE or a TEAM (asked
 *    about first, since it reaches many people), may end on a date, and says
 *    separately whether its holder may download and may share it on;
 *  - general access is the publish flag (Restricted = a private draft,
 *    Workspace = everyone in the organisation, view-only);
 *  - "anyone with the link" is v1's guest links (several, each URL shown
 *    once, 1–90 days, with the sharer's data permissions);
 *  - embedding is host-signed (EmbedSection), schedules are v1's panel.
 *  - Publishing (the owner's tab): state, details, approval, the versions
 *    readers were shown, archiving and handing over (PublishingPanel).
 * Every control here is a convenience: the server decides each action again.
 * Left out (no backend): a comment level, user suggestions, pending
 * invitations, invitation emails (docs/publishing/PLAN.md).
 */

export interface ShareTarget {
  id: number
  name: string
  created_by?: number | null
  is_mine?: boolean
  published?: boolean
}

type Tab = 'people' | 'publishing' | 'embed' | 'schedule'
type Kind = 'user' | 'role' | 'team'
const failure = (e: unknown, fallback: string) => {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : fallback
}
/** A day picked in a date field, as the end of that day. */
const endOfDay = (day: string) => new Date(`${day}T23:59:59`).toISOString()
const COLORS = [1, 2, 3, 4, 5, 6]
/** How many charts that list single records are named; the rest are counted. */
const LISTED_SHOWN = 5
const color = (s: string) => `var(--dl-series-${COLORS[[...s].reduce((n, c) => n + c.charCodeAt(0), 0) % COLORS.length]})`

export default function ShareDashboardDialog({ report, canEdit, isAdmin, pageId, initialTab = 'people', onClose, onPublishedChange, onReleased, onAccessWhy, onAccessByRole }: {
  report: ShareTarget
  /** The viewer may edit this dashboard: guest links, embedding, schedules. */
  canEdit: boolean
  isAdmin: boolean
  /** The page the copied link should open on. */
  pageId?: number | null
  initialTab?: Tab
  onClose: () => void
  onPublishedChange?: (published: boolean) => void
  /** Changes were released from the Publishing tab (F-10). */
  onReleased?: () => void
  onAccessWhy?: () => void
  onAccessByRole?: () => void
}) {
  const t = useT()
  const confirm = useConfirm()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [tab, setTab] = useState<Tab>(canEdit ? initialTab : 'people')
  // Grants and publishing are the AUTHOR's controls (admins too), on an
  // authored dashboard only: a legacy one is outside that regime.
  const authored = report.created_by != null
  const manages = authored && (!!report.is_mine || isAdmin)

  const [grants, setGrants] = useState<ReportGrant[] | null>(null)
  const [email, setEmail] = useState('')
  // Least privilege (F-06): a new share starts at Can view; more is a choice.
  const [level, setLevel] = useState<'view' | 'edit' | 'data'>('view')
  const [busy, setBusy] = useState(false)
  const [kind, setKind] = useState<Kind>('user')
  const [options, setOptions] = useState<WorkspaceShareOptions | null>(null)
  const [groupId, setGroupId] = useState('')
  const [more, setMore] = useState(false)
  const [until, setUntil] = useState('')
  const [mayDownload, setMayDownload] = useState(true)
  const [mayShare, setMayShare] = useState(false)
  const [message, setMessage] = useState('')
  const [openRow, setOpenRow] = useState<number | null>(null)
  const [published, setPublished] = useState(!!report.published)
  // Charts that show single records (a bar per person, account or item): said
  // before anything is shared, never blocking -- the column may name an order.
  const [listed, setListed] = useState<ListedRecords[]>([])
  useEffect(() => {
    Promise.resolve().then(() => reportsApi.listedRecords(report.id)).then(items => setListed(items ?? [])).catch(() => setListed([]))
  }, [report.id])
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

  // Roles and teams are asked for only when someone chooses to share with one.
  useEffect(() => {
    if (kind === 'user' || options) return
    workspaceApi.shareOptions().then(setOptions).catch(() => setOptions({ roles: [], org_units: [] }))
  }, [kind, options])
  const groups = kind === 'role' ? (options?.roles ?? []).map(r => ({ id: r.id, name: r.name }))
    : (options?.org_units ?? []).map(u => ({ id: u.id, name: u.level_name ? `${u.name} (${u.level_name})` : u.name }))
  const nameOf = (g: ReportGrant) => g.name ?? g.email
  const ready = kind === 'user' ? !!email.trim() : !!groupId

  const invite = async () => {
    if (!ready) return
    const group = groups.find(x => String(x.id) === groupId)
    // A role or a team is many people at once, so it is asked about first.
    if (kind !== 'user' && !(await confirm({
      title: t('pub.sh.confirmGroup', { name: group?.name ?? '' }), body: t('pub.sh.confirmGroupBody'),
      confirmLabel: t('pub.sh.share'), destructive: false }))) return
    const body: GrantBody = { level }
    if (kind === 'user') body.email = email.trim()
    else if (kind === 'role') body.role_id = Number(groupId)
    else body.org_unit_id = Number(groupId)
    // Only what was changed from the usual is sent.
    if (until) body.expires_at = endOfDay(until)
    if (!mayDownload) body.can_export = false
    if (mayShare && kind === 'user' && level === 'view') body.can_share = true
    if (message.trim()) body.message = message.trim()
    setBusy(true)
    try {
      const g = await reportGrantsApi.create(report.id, body)
      setGrants(prev => [...(prev ?? []).filter(x => x.id !== g.id && (g.user_id == null || x.user_id !== g.user_id)), g])
      setEmail(''); setGroupId(''); setMessage(''); setUntil(''); setMayDownload(true); setMayShare(false); setLevel('view')
      toast.success(kind === 'user' ? t('dsh.sd.shared', { email: g.email }) : t('pub.sh.sharedWith', { name: nameOf(g) }))
    } catch (e) {
      toast.error(failure(e, t('dsh.sd.failed')))
    } finally { setBusy(false) }
  }
  /** Change one share in place: its level, its end date, what it allows. */
  const change = async (g: ReportGrant, body: Parameters<typeof publishingApi.changeGrant>[2]) => {
    try {
      const got = await publishingApi.changeGrant(report.id, g.id, body)
      setGrants(prev => (prev ?? []).map(x => x.id === g.id ? { ...x, ...got } : x))
    } catch (e) {
      toast.error(failure(e, t('dsh.sd.failed')))
    }
  }
  const remove = async (g: ReportGrant) => {
    if (!(await confirm({ title: t('pub.sh.confirmRemove', { name: nameOf(g) }), body: t('pub.sh.confirmRemoveBody'),
      confirmLabel: t('pub.sh.remove') }))) return
    try {
      await reportGrantsApi.remove(report.id, g.id)
      setGrants(prev => (prev ?? []).filter(x => x.id !== g.id))
    } catch (e) {
      toast.error(failure(e, t('dsh.sd.removeFailed')))
    }
  }
  const setAccess = async (next: boolean) => {
    if (next === published) return
    // F-08: the whole organisation at once, either way -- asked first, like a
    // role or a team share. Cancel leaves the choice as it was.
    if (!(await confirm(next
      ? { title: t('pub.sh.confirmPublish', { name: report.name }), body: t('pub.sh.confirmPublishBody'),
          confirmLabel: t('pub.sh.publish'), destructive: false }
      : { title: t('pub.sh.confirmUnpublish', { name: report.name }), body: t('pub.sh.confirmUnpublishBody'),
          confirmLabel: t('pub.sh.unpublish') }))) return
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
        <div className="shx-seg" role="group" aria-label={t('pub.sh.kind')} style={{ marginBottom: 10 }}>
          {(['user', 'role', 'team'] as const).map(k => (
            <button key={k} type="button" aria-pressed={kind === k} onClick={() => { setKind(k); setGroupId(''); setLevel('view') /* every new share starts at view */ }}>
              {t(k === 'user' ? 'pub.sh.person' : k === 'role' ? 'pub.sh.role' : 'pub.sh.team')}
            </button>
          ))}
        </div>
        <div className="shx-inv">
          {kind === 'user' ? (
            <input className="shx-in" type="email" value={email} onChange={e => setEmail(e.target.value)} dir="ltr"
              placeholder="name@example.com" /* i18n-ok: an address */ aria-label={t('dsh.sd.email')}
              onKeyDown={e => { if (e.key === 'Enter') void invite() }} />
          ) : (
            <select className="shx-sel" style={{ flex: 1, minWidth: 0 }} value={groupId} onChange={e => setGroupId(e.target.value)}
              aria-label={t(kind === 'role' ? 'pub.sh.chooseRole' : 'pub.sh.chooseTeam')}>
              <option value="">{t(kind === 'role' ? 'pub.sh.chooseRole' : 'pub.sh.chooseTeam')}</option>
              {groups.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          )}
          {levelSelect(level, setLevel, t('dsh.sd.level'))}
          <button type="button" className="btn btn-primary" onClick={() => void invite()} disabled={busy || !ready}
            title={kind === 'user' && !ready ? t('dsh.sd.needEmail') : undefined}>{t(kind === 'user' ? 'shx.invite' : 'pub.sh.share')}</button>
        </div>
        <p className="shx-note">{t(kind === 'user' ? 'shx.emailOnly' : 'pub.sh.rules')}</p>
        <button type="button" className="shx-lk" aria-expanded={more} onClick={() => setMore(v => !v)}>
          <SlidersHorizontal size={14} aria-hidden />{t('pub.sh.more')}
        </button>
        {more && (
          <div className="shx-more">
            <label className="shx-fld"><span>{t('pub.sh.until')}</span>
              <input className="shx-in" type="date" value={until} onChange={e => setUntil(e.target.value)} />
              <small>{t('pub.sh.untilHelp')}</small>
            </label>
            <label className="shx-ck"><input type="checkbox" checked={mayDownload} onChange={e => setMayDownload(e.target.checked)} />{t('pub.sh.mayDownload')}</label>
            {kind === 'user' && level === 'view' && (
              <label className="shx-ck"><input type="checkbox" checked={mayShare} onChange={e => setMayShare(e.target.checked)} />{t('pub.sh.mayShare')}</label>
            )}
            <label className="shx-fld"><span>{t('pub.sh.message')}</span>
              <input className="shx-in" value={message} maxLength={300} onChange={e => setMessage(e.target.value)} placeholder={t('pub.sh.messagePh')} dir="auto" />
            </label>
          </div>
        )}

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
            const group = g.kind === 'role' || g.kind === 'team'
            const name = nameOf(g)
            const who = group ? name : g.email.split('@')[0]
            const day = g.expires_at ? formatDate(g.expires_at, 'date') : null
            const notes = [
              ...(day ? [t(g.expired ? 'pub.sh.ended' : 'pub.sh.ends', { date: day })] : []),
              ...(g.can_export === false ? [t('pub.sh.noDownload')] : []),
              ...(g.can_share ? [t('pub.sh.sharesOn')] : []),
            ]
            return (
              <div key={g.id} data-expired={g.expired ? 'true' : undefined}>
                <div className="shx-p">
                  <span className="shx-av" style={{ background: color(name) }} aria-hidden>
                    {g.kind === 'role' ? <ShieldCheck size={15} /> : g.kind === 'team' ? <Network size={15} /> : [...who][0]}
                  </span>
                  <span className="tx"><b dir="auto">{who}</b>
                    {group ? <span>{t(g.kind === 'role' ? 'pub.sh.tag.role' : 'pub.sh.tag.team')}</span> : <span dir="ltr">{g.email}</span>}
                    {notes.length > 0 && <span className={g.expired ? 'shx-late' : undefined}>{notes.join(' · ')}</span>}
                  </span>
                  {levelSelect(g.level, v => void change(g, { level: v }), group ? t('pub.sh.levelFor', { name }) : t('shx.levelFor', { email: g.email }), true)}
                  <button type="button" className="shx-ib" aria-expanded={openRow === g.id} onClick={() => setOpenRow(openRow === g.id ? null : g.id)}
                    aria-label={t('pub.sh.optionsFor', { name })} title={t('pub.sh.more')}><SlidersHorizontal size={15} aria-hidden /></button>
                  <button type="button" className="shx-ib" onClick={() => void remove(g)}
                    aria-label={group ? t('pub.sh.removeFor', { name }) : t('dsh.sd.removeFor', { email: g.email })}
                    title={t('dsh.sd.remove')}><X size={15} aria-hidden /></button>
                </div>
                {openRow === g.id && (
                  <div className="shx-more">
                    <label className="shx-fld"><span>{t('pub.sh.until')}</span>
                      <input className="shx-in" type="date" value={g.expires_at ? g.expires_at.slice(0, 10) : ''}
                        onChange={e => void change(g, e.target.value ? { expires_at: endOfDay(e.target.value) } : { clear_expiry: true })} />
                      <small>{t('pub.sh.untilHelp')}</small>
                    </label>
                    <label className="shx-ck"><input type="checkbox" checked={g.can_export !== false}
                      onChange={e => void change(g, { can_export: e.target.checked })} />{t('pub.sh.mayDownload')}</label>
                    {g.kind !== 'role' && g.kind !== 'team' && g.level === 'view' && (
                      <label className="shx-ck"><input type="checkbox" checked={!!g.can_share}
                        onChange={e => void change(g, { can_share: e.target.checked })} />{t('pub.sh.mayShare')}</label>
                    )}
                  </div>
                )}
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
    ...(manages ? [{ k: 'publishing' as Tab, icon: Send, label: 'pub.tab' as MessageKey }] : []),
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
          {listed.length > 0 && (
            <div className="shx-listed" role="note" data-testid="share-listed-records">
              <ShieldCheck size={14} aria-hidden="true" />
              <div>
                <p>{t('dsh.sd.listedLead', { n: listed.length })}</p>
                <ul>
                  {listed.slice(0, LISTED_SHOWN).map(l => (
                    <li key={`${l.widget_id}-${l.column}`}>
                      {t(l.kind === 'identifier' ? 'dsh.sd.listedById' : 'dsh.sd.listedByPersonal',
                        { title: l.title || t('dsh.sd.listedUntitled'), column: l.column })}
                    </li>
                  ))}
                  {listed.length > LISTED_SHOWN && <li>{t('dsh.sd.listedMore', { n: listed.length - LISTED_SHOWN })}</li>}
                </ul>
              </div>
            </div>
          )}
          {tab === 'people' && people}
          {tab === 'publishing' && <PublishingPanel report={report} isAdmin={isAdmin} onReleased={onReleased}
            onStateChange={s => { setPublished(s === 'published'); onPublishedChange?.(s === 'published') }} />}
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
