import { Link, useLocation } from 'react-router-dom'
import { Compass } from 'lucide-react'
import EmptyState from '../components/ui/EmptyState'
import { useT } from '../i18n'

/** An address the app does not know. Rendered INSIDE the shell so the rail
 *  and header stay -- a blank page reads as a crash, not a wrong link. */
export default function NotFound() {
  const { pathname } = useLocation()
  const t = useT()
  return (
    <EmptyState icon={Compass} title={t('notFound.title')} titleAs="h1"
      description={t('notFound.body', { path: pathname })}
      action={<>
        <Link to="/" className="btn btn-primary">{t('nav.home')}</Link>
        <Link to="/datasets" className="btn btn-ghost">{t('nav.datasets')}</Link>
        <Link to="/reports" className="btn btn-ghost">{t('nav.dashboards')}</Link>
      </>} />
  )
}
