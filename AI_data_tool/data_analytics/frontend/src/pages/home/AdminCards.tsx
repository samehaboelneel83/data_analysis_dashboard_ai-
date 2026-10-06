import { useState } from 'react'
import { Activity, RefreshCw, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import { formatTimeAgo, useT } from '../../i18n'
import { localDigits } from '../../lib/arabicFormats'
import { datasetsApi, type RefreshRunRow } from '../../services/api'
import type { FeedItem, JobsDigest } from './feeds'
import { Empty, SecError, SecHead, Sk, fill } from './parts'

/**
 * The two cards in Home's side column (redesign 7a). Both read org-admin
 * endpoints, so Home renders them for org admins only and never calls the
 * endpoints for anyone else.
 */

const AVATAR = [1, 2, 3, 4, 5, 6]
const avatarColor = (name: string) =>
  `var(--dl-series-${AVATAR[[...name].reduce((n, c) => n + c.charCodeAt(0), 0) % AVATAR.length]})`

export function ActivityCard({ items, loading, error, onRetry }: {
  items: FeedItem[]; loading: boolean; error: boolean; onRetry: () => void
}) {
  const t = useT()
  let body: React.ReactNode
  if (loading) {
    body = <ol className="hm-feed">{[0, 1, 2, 3].map(i => (
      <li key={i}><Sk w="28px" h={28} r={50} style={{ flex: 'none' }} /><div style={{ flex: 1 }}><Sk w="90%" h={10} /><Sk w="40%" h={9} style={{ marginTop: 7 }} /></div></li>
    ))}</ol>
  } else if (error) {
    body = <SecError text={t('hm.err.activity')} onRetry={onRetry} />
  } else if (!items.length) {
    body = <Empty small icon={Activity} title={t('hm.act.empty')} text={t('hm.act.emptyText')} />
  } else {
    body = <ol className="hm-feed">{items.map(a => (
      <li key={a.id}>
        <span className="hm-pp" style={{ background: avatarColor(a.who) }} aria-hidden>{[...a.who][0]}</span>
        <div className="tx">
          {fill(t(a.key, { who: '{who}', name: '{name}' }), {
            who: <b>{a.mine ? t('hm.you') : <bdi>{a.who}</bdi>}</b>,
            name: <b><bdi>{a.name}</bdi></b>,
          })}
          <span className="tm">{formatTimeAgo(a.at, t)}</span>
        </div>
      </li>
    ))}</ol>
  }
  return (
    <section className="hm-card" aria-labelledby="hm-act" data-testid="home-activity">
      <SecHead id="hm-act" title={t('hm.act.title')} all={!loading && !error && items.length ? '/monitoring/activity' : undefined} />
      {body}
    </section>
  )
}

export function JobsCard({ digest, loading, error, onRetry }: {
  digest: JobsDigest | null; loading: boolean; error: boolean; onRetry: () => void
}) {
  const t = useT()
  const [retrying, setRetrying] = useState<number | null>(null)
  const retry = async (r: RefreshRunRow) => {
    setRetrying(r.id)
    try {
      await datasetsApi.queueRefresh(r.item_id, { mode: 'full' })
      toast.success(t('hm.jobs.queued', { name: r.name ?? '' }))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('hm.jobs.retryFailed'))
    } finally { setRetrying(null) }
  }
  const line = (r: RefreshRunRow) => {
    const ago = formatTimeAgo(r.started_at ?? undefined, t) ?? ''
    if (r.status === 'running') return t('hm.jobs.running', { ago })
    if (r.status === 'ok') return t('hm.jobs.ok', { ago })
    return r.error ? t('hm.jobs.failedWhy', { ago, why: r.error }) : t('hm.jobs.failed', { ago })
  }
  const tone = (r: RefreshRunRow) => r.status === 'ok' ? 'ok' : r.status === 'running' ? 'run' : 'err'

  let body: React.ReactNode
  if (loading) {
    body = <>
      <div className="hm-jc">{[0, 1, 2].map(i => <div key={i}><Sk w="40%" h={20} /><Sk w="70%" h={9} style={{ marginTop: 6 }} /></div>)}</div>
      {[0, 1].map(i => <div key={i} className="hm-job"><div className="tx"><Sk w="80%" h={10} /><Sk w="50%" h={9} style={{ marginTop: 6 }} /></div></div>)}
    </>
  } else if (error) {
    body = <SecError text={t('hm.err.jobs')} onRetry={onRetry} />
  } else if (!digest || !digest.total) {
    body = <Empty small icon={RefreshCw} title={t(digest?.any ? 'hm.jobs.empty' : 'hm.tile.noJobs')} text={t('hm.jobs.emptyText')} />
  } else {
    body = <>
      <p className="hm-jsub">{t('hm.jobs.window')}</p>
      <div className="hm-jc">
        {([['ok', digest.ok, 'hm.jobs.nOk'], ['run', digest.running, 'hm.jobs.nRunning'], ['err', digest.failed, 'hm.jobs.nFailed']] as const).map(([d, n, l]) => (
          <div key={d}><b>{localDigits(String(n))}</b><span><span className={`hm-dot ${d}`} aria-hidden />{t(l)}</span></div>
        ))}
      </div>
      {digest.shown.map(r => (
        <div key={r.id} className="hm-job">
          <span className={`hm-dot ${tone(r)}`} aria-hidden />
          <div className="tx"><b><bdi>{r.name ?? t('hm.jobs.deleted')}</bdi></b><small>{line(r)}</small></div>
          {(r.status === 'failed' || r.status === 'blocked') && r.kind === 'dataset' && r.name != null && (
            <button type="button" className="btn btn-ghost btn-sm" disabled={retrying === r.id} onClick={() => void retry(r)}>
              <RotateCcw size={13} aria-hidden />{t('hm.retry')}
            </button>
          )}
        </div>
      ))}
    </>
  }
  return (
    <section className="hm-card" aria-labelledby="hm-jobs" data-testid="home-jobs">
      <SecHead id="hm-jobs" title={t('hm.jobs.title')} all={!loading && !error && digest?.total ? '/monitoring/jobs' : undefined} />
      {body}
    </section>
  )
}
