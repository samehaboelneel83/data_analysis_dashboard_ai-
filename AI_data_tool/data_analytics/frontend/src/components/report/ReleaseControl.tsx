/**
 * E09: where an editor sees whether viewers have their changes yet, and
 * releases them.
 *
 * Viewers of a report with a release are served that release; the editor's
 * pages are the draft. So an editor needs to know, at a glance, whether what
 * they are looking at is what everyone else sees -- and one button to make it
 * so. A viewer sees nothing here: they are always looking at the release.
 */
import { useState } from 'react'
import toast from 'react-hot-toast'
import { reportsApi, describeMissing } from '../../services/api'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import type { Report } from '../../types/report'

function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '' : d.toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })
}

export default function ReleaseControl({ report, canEdit, revision, onReleased }: {
  report: Pick<Report, 'id' | 'published' | 'release' | 'unreleased_changes'>
  canEdit: boolean
  /** The revision the page last knows of: an edit that did not reload the
   *  report still moves it past the release's. */
  revision?: number | null
  /** Called after a release, so the page can re-read the report. */
  onReleased?: () => void
}) {
  const tr = useT()
  const { language } = useDirection()
  const [busy, setBusy] = useState(false)
  if (!canEdit) return null
  const release = report.release ?? null
  // A private draft with no release has nobody to release to.
  if (!release && !report.published) return null

  const date = when(release?.released_at, language === 'ar' ? 'ar' : 'en')
  const pending = !release || !!report.unreleased_changes
    || (revision != null && revision !== release.revision)
  const label = !release ? tr('release.live') : pending ? tr('release.unreleased') : tr('release.released')
  const title = !release ? tr('release.title.live')
    : pending ? tr('release.title.unreleased', { date }) : tr('release.title.released', { date })

  async function doRelease() {
    setBusy(true)
    try {
      const got = await reportsApi.release(report.id)
      toast.success(tr('release.done'))
      if (got?.missing?.length) toast(describeMissing(got.missing), { icon: '⚠' })
      onReleased?.()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : detail?.message ?? tr('release.failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span data-testid="release-control" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <span role="status" title={title} className={`dl-release-status${pending ? ' dl-release-status--pending' : ''}`}>
        {label}
      </span>
      {pending && (
        <button type="button" className="btn btn-primary btn-sm" disabled={busy} title={title} onClick={doRelease}>
          {release ? tr('release.button') : tr('release.first')}
        </button>
      )}
    </span>
  )
}
