import { useContext } from 'react'
import { AuthContext } from '../contexts/AuthContext'
import AboutMe from '../components/AboutMe'
import { useT } from '../i18n'

/**
 * My profile: who the product knows this person as (set by an administrator,
 * shown read-only) and the one thing they say about themselves -- which the
 * designers read when they tailor a dashboard to them (components/AboutMe).
 */
export default function Profile() {
  const t = useT()
  const user = useContext(AuthContext)?.user ?? null
  if (!user) return null
  const row = (label: string, value: string) => (
    <div style={{ display: 'flex', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ flex: '0 0 140px', color: 'var(--muted)', fontSize: 13 }}>{label}</span>
      <bdi style={{ fontSize: 13 }}>{value}</bdi>
    </div>
  )
  return (
    <div className="page" style={{ maxWidth: 720 }} data-testid="profile-page">
      <h1 style={{ fontSize: 20, margin: '0 0 4px' }}>{t('profile.title')}</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13, margin: '0 0 16px' }}>{t('profile.lead')}</p>
      <div className="card" style={{ padding: 16, marginBottom: 16 }}>
        {row(t('profile.email'), user.email)}
        {row(t('profile.role'), user.role?.name ?? '—')}
        {row(t('profile.org'), user.organization?.name ?? '—')}
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>{t('profile.setByAdmin')}</div>
      </div>
      <div className="card" style={{ padding: 16 }}>
        <AboutMe open where="profile" />
      </div>
    </div>
  )
}
