import { Link, useLocation } from 'react-router-dom'
import { Compass } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import { useT } from '../i18n'
import { useDirection } from '../contexts/DirectionContext'

/** An address the app does not know. Rendered INSIDE the shell so the rail
 *  and header stay -- a blank page reads as a crash, not a wrong link. */
export default function NotFound() {
  const { pathname } = useLocation()
  const t = useT()
  // QA5 R3: a path reads left to right inside an Arabic sentence ("/activity",
  // not "activity/"): isolated LTR (LRI…PDI). English unchanged.
  const { rtl } = useDirection()
  const path = rtl ? `\u2066${pathname}\u2069` : pathname
  return (
    <EmptyState icon={Compass} title={t('notFound.title')} titleAs="h1"
      description={t('notFound.body', { path })}
      action={<>
        <Link to="/" className="btn btn-primary">{t('nav.home')}</Link>
        <Link to="/datasets" className="btn btn-ghost">{t('nav.datasets')}</Link>
        <Link to="/reports" className="btn btn-ghost">{t('nav.dashboards')}</Link>
      </>} />
  )
}
