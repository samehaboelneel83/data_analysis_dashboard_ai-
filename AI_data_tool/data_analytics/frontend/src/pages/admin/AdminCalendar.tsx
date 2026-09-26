import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useT } from '../../i18n'
import { useDirection } from '../../contexts/DirectionContext'
import { calendarSettingsApi } from '../../services/api'
import { fiscalLabel, monthName } from '../../lib/fiscal'
import LoadError from '../../components/ui/LoadError'
import LoadingState from '../../components/ui/LoadingState'

/**
 * The org's calendar (E10): the month its fiscal year starts in. Charts
 * grouped by fiscal year or quarter follow it unless a chart names its own,
 * so changing it here moves every such chart at once.
 */
export default function AdminCalendar() {
  const t = useT()
  const { language } = useDirection()
  const locale = language === 'ar' ? 'ar' : 'en'
  const [month, setMonth] = useState(1)
  const [saved, setSaved] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const load = () => {
    setLoading(true); setLoadError(null)
    calendarSettingsApi.get()
      .then(s => { setMonth(s.fiscal_year_start_month); setSaved(s.fiscal_year_start_month) })
      .catch(setLoadError)
      .finally(() => setLoading(false))
  }
  useEffect(load, [])

  const save = async () => {
    setSaving(true)
    try {
      const s = await calendarSettingsApi.set({ fiscal_year_start_month: month })
      setMonth(s.fiscal_year_start_month); setSaved(s.fiscal_year_start_month)
      toast.success(t('cal.saved'))
    } catch (e) {
      toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('cal.saveFailed'))
    } finally { setSaving(false) }
  }

  if (loading) return <LoadingState />
  if (loadError) return <LoadError what={t('cal.loadWhat')} error={loadError} onRetry={load} />

  // A worked example makes the naming concrete: the day the chosen year
  // starts, labelled as the charts will label it.
  const today = new Date()
  const example = new Date(Date.UTC(today.getUTCFullYear(), month - 1, 1))
  const exampleDate = new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(example)
  const quarter = fiscalLabel(example, 'fiscal_quarter', month).split('-Q')[1]
  return (
    <div style={{ maxWidth: 820 }}>
      <h1 className="dl-page-title" style={{ marginBottom: 4 }}>{t('nav.calendar')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, marginTop: 0 }}>{t('cal.lead')}</p>

      <section className="card" style={{ padding: 16, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, marginTop: 0 }}>{t('cal.fiscalTitle')}</h2>
        <label htmlFor="fiscal-start" style={{ display: 'block', fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
          {t('cal.startsIn')}
        </label>
        <select id="fiscal-start" value={month} onChange={e => setMonth(Number(e.target.value))}
          style={{ minWidth: 200 }}>
          {Array.from({ length: 12 }, (_, i) => i + 1).map(m => (
            <option key={m} value={m}>{monthName(m, locale)}</option>
          ))}
        </select>
        <p style={{ fontSize: 12.5, color: 'var(--muted)' }}>{t('cal.hint')}</p>
        <p data-testid="fiscal-example" dir="auto" style={{ fontSize: 13 }}>
          {t('cal.example', { date: exampleDate, year: fiscalLabel(example, 'fiscal_year', month), quarter })}
        </p>
        <button className="btn btn-primary btn-sm" disabled={saving || month === saved} onClick={() => void save()}>
          {saving ? t('cal.saving') : t('cal.save')}
        </button>
      </section>

      <section className="card" style={{ padding: 16, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, marginTop: 0 }}>{t('cal.hijriTitle')}</h2>
        <p style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 0 }}>{t('cal.hijriNote')}</p>
      </section>
    </div>
  )
}
