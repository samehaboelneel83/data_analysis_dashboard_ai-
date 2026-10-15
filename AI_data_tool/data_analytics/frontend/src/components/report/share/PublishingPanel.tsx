import { useEffect, useState } from 'react'
import { Archive, ArchiveRestore, History, UserRoundCog } from 'lucide-react'
import toast from 'react-hot-toast'
import { publishingApi, reviewApi, type Publication, type ReleaseSummary } from '../../../services/api'
import { useConfirm } from '../../ui/ConfirmDialog'
import { useT, type MessageKey } from '../../../i18n'
import { formatDate } from '../../../lib/dateFormat'
import { localDigits } from '../../../lib/arabicFormats'
import type { ShareTarget } from './ShareDashboardDialog'

/**
 * Publishing, for a dashboard's owner (and administrators): where it stands,
 * the details readers find it by, approval when the organisation asks for it,
 * the versions readers were shown (and going back to one), archiving, and
 * handing it over.
 *
 * Nothing here is the rule itself: every action is decided again by the
 * server, which answers with the reason when it refuses.
 */

const failure = (e: unknown, fallback: string) => {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === 'string' ? d : (d as { message?: string })?.message ?? fallback
}
const REASON: Record<string, MessageKey> = {
  publish: 'pub.reason.publish', release: 'pub.reason.release', rollback: 'pub.reason.rollback', first_edit: 'pub.reason.edit',
}

export default function PublishingPanel({ report, isAdmin, onStateChange }: {
  report: ShareTarget
  isAdmin: boolean
  onStateChange?: (state: Publication['state']) => void
}) {
  const t = useT()
  const confirm = useConfirm()
  const [pub, setPub] = useState<Publication | null>(null)
  const [failed, setFailed] = useState(false)
  const [releases, setReleases] = useState<ReleaseSummary[] | null>(null)
  const [category, setCategory] = useState('')
  const [tags, setTags] = useState('')
  const [note, setNote] = useState('')
  const [newOwner, setNewOwner] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => {
    publishingApi.get(report.id)
      .then(p => { setPub(p); setCategory(p.category ?? ''); setTags(p.tags.join(', ')); setFailed(false) })
      .catch(() => setFailed(true))
    publishingApi.releases(report.id).then(setReleases).catch(() => setReleases([]))
  }
  useEffect(load, [report.id])  // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (work: () => Promise<unknown>, done: string) => {
    setBusy(true)
    try { await work(); toast.success(done); load() }
    catch (e) { toast.error(failure(e, t('pub.failed'))) }
    finally { setBusy(false) }
  }

  if (failed) return <div className="shx-info"><span>{t('pub.loadFailed')}</span><button type="button" className="shx-lk" style={{ marginTop: 0 }} onClick={load}>{t('pub.retry')}</button></div>
  if (!pub) return <p className="shx-note">{t('common.loading')}</p>

  const n = (v: number) => localDigits(String(v))
  const archived = pub.state === 'archived'
  const review = pub.review
  const reviewState = review.state !== 'none' && !review.current ? 'none' : review.state
  const saveDetails = () => run(
    () => publishingApi.set(report.id, { category: category.trim() || null, tags: tags.split(/[,،]/).map(x => x.trim()).filter(Boolean) }),
    t('pub.saved'))
  const archive = async () => {
    const d = pub.depends ?? { shares: 0, links: 0, schedules: 0 }
    if (!(await confirm({ title: t('pub.archive.confirm', { name: report.name }),
      body: t('pub.archive.body', { shares: n(d.shares), links: n(d.links), schedules: n(d.schedules) }), confirmLabel: t('pub.archive') }))) return
    await run(() => publishingApi.archive(report.id), t('pub.archive.done'))
    onStateChange?.('archived')
  }
  // F-09: this switch is the ORGANISATION's, not this dashboard's -- asked first, saying so.
  const setApproval = async (on: boolean) => {
    if (!(await confirm({ title: t(on ? 'pub.review.confirmOn' : 'pub.review.confirmOff'), body: t('pub.review.confirmBody'),
      confirmLabel: t(on ? 'pub.review.turnOn' : 'pub.review.turnOff'), destructive: false, focusCancel: true }))) return
    await run(() => reviewApi.setApproval(on), t('pub.saved'))
  }
  const restore = async () => {
    // F-04: the server restores as a draft; tell the builder what it answered.
    const out: { state?: Publication['state'] } = {}
    await run(async () => { out.state = (await publishingApi.restore(report.id))?.state as Publication['state'] }, t('pub.restore.done'))
    if (out.state) onStateChange?.(out.state)
  }
  const goBack = async (r: ReleaseSummary) => {
    if (!(await confirm({ title: t('pub.versions.confirm', { n: n(r.revision) }), body: t('pub.versions.confirmBody'),
      confirmLabel: t('pub.versions.back'), destructive: false, focusCancel: true }))) return
    await run(() => publishingApi.rollback(report.id, r.id), t('pub.versions.done', { n: n(r.revision) }))
  }
  const handOver = async () => {
    const email = newOwner.trim()
    if (!email) return
    if (!(await confirm({ title: t('pub.owner.confirm', { name: report.name, email }), body: t('pub.owner.confirmBody'),
      confirmLabel: t('pub.owner.move'), destructive: false, focusCancel: true }))) return
    await run(async () => { await publishingApi.transfer(report.id, email); setNewOwner('') }, t('pub.owner.done', { email }))
  }

  return (
    <div data-testid="publishing-panel">
      <div className="shx-sec">{t('pub.state')}</div>
      <div className="shx-st">
        <span className="shx-pill" data-state={pub.state}>{t(`pub.state.${pub.state}` as MessageKey)}</span>
        <div className="tx">
          <p>{t(`pub.state.${pub.state}Sub` as MessageKey)}</p>
          {pub.state === 'published' && pub.published_at && (
            <p>{t('pub.publishedBy', { who: pub.published_by ?? pub.owner ?? '', date: formatDate(pub.published_at, 'date') })}</p>
          )}
          {pub.release && !archived && <p>{t('pub.version', { n: n(pub.release.revision) })}</p>}
          {pub.unreleased_changes && !archived && <p>{t('pub.unreleased')}</p>}
        </div>
      </div>
      <div className="shx-acts">
        {archived
          ? <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void restore()}><ArchiveRestore size={14} aria-hidden />{t('pub.restore')}</button>
          : <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} disabled={busy} onClick={() => void archive()}><Archive size={14} aria-hidden />{t('pub.archive')}</button>}
      </div>

      {(review.required || isAdmin) && !archived && <div className="shx-sec">{t('pub.review')}</div>}
      {isAdmin && !archived && (
        <label className="shx-ck" data-testid="approval-switch">
          <input type="checkbox" checked={review.required} disabled={busy}
            onChange={e => void setApproval(e.target.checked)} />
          <span>{t('pub.review.switch')}<br /><small style={{ color: 'var(--muted)' }}>{t('pub.review.switchHelp')}</small></span>
        </label>
      )}
      {review.required && !archived && (<>
        <div className="shx-st" style={{ marginTop: isAdmin ? 10 : 0 }}>
          <span className="shx-pill" data-state={reviewState}>{t(`pub.review.${reviewState}` as MessageKey, { who: (reviewState === 'requested' ? review.requested_by : review.decided_by) ?? '' })}</span>
        </div>
        <p className="shx-note">{review.state !== 'none' && !review.current ? t('pub.review.stale') : t('pub.review.needed')}</p>
        {review.note && review.current && <p className="shx-note" dir="auto">{review.note}</p>}
        <label className="shx-fld" style={{ marginTop: 10 }}><span>{t('pub.review.note')}</span>
          <input className="shx-in" value={note} maxLength={300} onChange={e => setNote(e.target.value)} dir="auto" />
        </label>
        <div className="shx-acts">
          {reviewState !== 'requested' && reviewState !== 'approved' && (
            <button type="button" className="btn btn-primary" disabled={busy}
              onClick={() => void run(async () => { await publishingApi.requestReview(report.id, note.trim() || undefined); setNote('') }, t('pub.review.asked'))}>{t('pub.review.ask')}</button>
          )}
          {isAdmin && reviewState === 'requested' && (<>
            <button type="button" className="btn btn-primary" disabled={busy}
              onClick={() => void run(async () => { await publishingApi.decideReview(report.id, true, note.trim() || undefined); setNote('') }, t('pub.review.approve'))}>{t('pub.review.approve')}</button>
            <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} disabled={busy}
              onClick={() => void run(async () => { await publishingApi.decideReview(report.id, false, note.trim() || undefined); setNote('') }, t('pub.review.reject'))}>{t('pub.review.reject')}</button>
          </>)}
        </div>
      </>)}

      <div className="shx-sec">{t('pub.details')}</div>
      <label className="shx-fld"><span>{t('pub.category')}</span>
        <input className="shx-in" value={category} maxLength={60} onChange={e => setCategory(e.target.value)} placeholder={t('pub.categoryPh')} dir="auto" />
      </label>
      <label className="shx-fld" style={{ marginTop: 10 }}><span>{t('pub.tags')}</span>
        <input className="shx-in" value={tags} onChange={e => setTags(e.target.value)} placeholder={t('pub.tagsPh')} dir="auto" />
      </label>
      <div className="shx-acts">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void saveDetails()}>{t('pub.save')}</button>
      </div>
      <label className="shx-ck" style={{ marginTop: 14 }}>
        <input type="checkbox" checked={pub.viewers_may_export} disabled={busy}
          onChange={e => void run(() => publishingApi.set(report.id, { viewers_may_export: e.target.checked }), t('pub.saved'))} />
        <span>{t('pub.readersDownload')}<br /><small style={{ color: 'var(--muted)' }}>{t('pub.readersDownloadHelp')}</small></span>
      </label>

      <div className="shx-sec"><History size={13} aria-hidden style={{ verticalAlign: -2, marginInlineEnd: 6 }} />{t('pub.versions')}</div>
      {releases?.length === 0 && <p className="shx-note">{t('pub.versions.none')}</p>}
      {!!releases?.length && (
        <ul className="shx-list" style={{ marginTop: 0 }} data-testid="publishing-versions">
          {releases.slice(0, 12).map(r => {
            const current = pub.release?.id === r.id
            return (
              <li key={r.id}>
                <span className="tx"><b>{t('pub.versions.row', { n: n(r.revision) })}</b>
                  <span>{[t(REASON[r.reason] ?? 'pub.reason.release'), r.released_at ? formatDate(r.released_at, 'date') : null].filter(Boolean).join(' · ')}</span>
                </span>
                {current ? <span className="shx-own">{t('pub.versions.current')}</span>
                  : <button type="button" className="btn btn-ghost" style={{ height: 30 }} disabled={busy || archived} onClick={() => void goBack(r)}>{t('pub.versions.back')}</button>}
              </li>
            )
          })}
        </ul>
      )}

      <div className="shx-sec"><UserRoundCog size={13} aria-hidden style={{ verticalAlign: -2, marginInlineEnd: 6 }} />{t('pub.owner')}</div>
      {pub.owner && <p className="shx-note" style={{ marginTop: 0 }}>{t('pub.owner.now', { who: pub.owner })}</p>}
      <div className="shx-inv" style={{ marginTop: 8 }}>
        <input className="shx-in" type="email" dir="ltr" value={newOwner} onChange={e => setNewOwner(e.target.value)}
          placeholder="name@example.com" /* i18n-ok: an address */ aria-label={t('pub.owner.email')} />
        <button type="button" className="btn btn-ghost" style={{ border: '1px solid var(--mc-border-strong)' }} disabled={busy || !newOwner.trim()} onClick={() => void handOver()}>{t('pub.owner.move')}</button>
      </div>
    </div>
  )
}
