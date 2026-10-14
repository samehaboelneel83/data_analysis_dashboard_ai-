import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { allowAiApi, type DatasetAllowAi as State } from '../services/api'
import { useT } from '../i18n'

/**
 * "Allow AI" for one dataset -- the same switch a connection has, so an
 * uploaded file has one too. One answer for every AI feature (the server's
 * services/ai_policy.py): with it off nothing from the dataset reaches a
 * model, and each feature answers with what the platform computes by itself.
 * A dataset built from a connection follows the connection unless it says no.
 */
export default function DatasetAllowAi({ datasetId }: { datasetId: number }) {
  const [s, setS] = useState<State | null>(null)
  const t = useT()
  useEffect(() => {
    let live = true
    allowAiApi.get(datasetId).then(r => { if (live) setS(r) }).catch(() => { if (live) setS(null) })
    return () => { live = false }
  }, [datasetId])
  if (!s) return null
  const blocked = s.connection != null && !s.effective && s.own !== false
  const value = s.own === true ? 'on' : s.own === false ? 'off' : ''
  return (
    <span data-testid="dataset-allow-ai" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11 }}
      title={blocked ? t('allowAi.byConnection', { name: s.connection ?? '' }) : t('allowAi.title')}>
      <select aria-label={t('allowAi.aria')} value={value} style={{ fontSize: 11, padding: '2px 4px' }}
        onChange={async e => {
          const next = e.target.value === 'on' ? true : e.target.value === 'off' ? false : null
          try {
            const got = await allowAiApi.set(datasetId, next)
            setS(got)
            toast.success(got.effective ? t('allowAi.nowOn') : t('allowAi.nowOff'))
          } catch (err) {
            toast.error((err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('allowAi.failed'))
          }
        }}>
        <option value="">{s.connection != null ? t('allowAi.followConnection') : t('allowAi.follow')}</option>
        {s.connection == null && <option value="on">{t('allowAi.on')}</option>}
        <option value="off">{t('allowAi.off')}</option>
      </select>
      {!s.effective && s.own !== false && <b style={{ color: 'var(--muted)' }}>{t('allowAi.off')}</b>}
    </span>
  )
}
