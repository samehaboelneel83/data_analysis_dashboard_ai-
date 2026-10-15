import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useT } from '../../i18n'
import { reviewApi } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'

/**
 * F-09 (long-term option): the organisation's "Ask for approval before
 * publishing" switch, on Admin -> Settings with the organisation's other
 * settings. It used to sit in one dashboard's Share -> Publishing tab, where a
 * click there changed every dashboard in the organisation. Changing it is still
 * asked about first, naming the organisation-wide effect.
 */
export default function OrgApprovalSetting({ headingLevel = 3 }: { headingLevel?: 2 | 3 }) {
  const t = useT()
  const confirm = useConfirm()
  const [on, setOn] = useState<boolean | null>(null)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let live = true
    reviewApi.settings()
      .then(s => { if (live) setOn(!!s.require_approval) })
      .catch(() => { if (live) setFailed(true) })
    return () => { live = false }
  }, [])

  const change = async (next: boolean) => {
    if (!(await confirm({ title: t(next ? 'pub.review.confirmOn' : 'pub.review.confirmOff'), body: t('pub.review.confirmBodyOrg'),
      confirmLabel: t(next ? 'pub.review.turnOn' : 'pub.review.turnOff'), destructive: false, focusCancel: true }))) return
    setBusy(true)
    try {
      const saved = await reviewApi.setApproval(next)
      setOn(!!saved.require_approval)
      toast.success(t('pub.saved'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('pub.review.saveFailed'))
    } finally { setBusy(false) }
  }

  const H = headingLevel === 2 ? 'h2' : 'h3'
  return (
    <div className="card" style={{ padding: 16, marginTop: 12 }} data-testid="org-approval-setting">
      <H style={{ fontSize: 14, marginTop: 0 }}>{t('pub.review')}</H>
      {failed ? <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: 0 }}>{t('pub.review.loadFailed')}</p> : (
        <label style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer' }}>
          <input type="checkbox" checked={!!on} disabled={on === null || busy}
            onChange={e => void change(e.target.checked)} />
          <span style={{ fontSize: 13 }}>{t('pub.review.switch')}<br />
            <small style={{ color: 'var(--muted)' }}>{t('pub.review.switchHelp')}</small></span>
        </label>
      )}
    </div>
  )
}
