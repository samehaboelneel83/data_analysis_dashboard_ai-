import { useContext, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { AuthContext } from '../contexts/AuthContext'
import { authApi } from '../services/api'
import { useT } from '../i18n'

const MAX = 1000

/**
 * What a person says about themselves, kept on their profile and read by the
 * designers that tailor a dashboard to them (backend services/ai_context.py):
 * written once, it stands in whenever the "what are you trying to find out"
 * box is left empty, and travels beside it when it is not. Folded away until
 * opened; it says, when closed, whether one is saved.
 */
export default function AboutMe({ disabled, open, where = 'dialog' }: {
  disabled?: boolean
  /** Shown unfolded (the profile page). */
  open?: boolean
  /** Where it sits: the sentence about its effect names "the box above" only in the dialog. */
  where?: 'dialog' | 'profile' }) {
  const t = useT()
  const user = useContext(AuthContext)?.user ?? null
  const [saved, setSaved] = useState<string>(user?.about ?? '')
  const [text, setText] = useState<string>(user?.about ?? '')
  const [busy, setBusy] = useState(false)
  useEffect(() => { setSaved(user?.about ?? ''); setText(user?.about ?? '') }, [user?.about])

  const save = async () => {
    setBusy(true)
    try {
      const me = await authApi.updateMe({ about: text.trim() })
      setSaved(me.about ?? ''); setText(me.about ?? '')
      toast.success(t(me.about ? 'about.saved' : 'about.cleared'))
    } catch { toast.error(t('about.failed')) } finally { setBusy(false) }
  }

  return (
    <details data-testid="about-me" open={open} style={{ marginTop: open ? 0 : 10 }}>
      <summary style={{ cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
        {t('about.title')}{' '}
        <span style={{ fontWeight: 400, color: 'var(--muted)' }}>{t(saved ? 'about.has' : 'about.none')}</span>
      </summary>
      <label htmlFor="about-me-text" style={{ display: 'block', fontSize: 12, color: 'var(--muted)', margin: '6px 0 4px' }}>
        {t('about.help')}
      </label>
      <textarea id="about-me-text" rows={3} maxLength={MAX} value={text} dir="auto" disabled={disabled || busy}
        onChange={e => setText(e.target.value)} placeholder={t('about.placeholder')}
        style={{ width: '100%', resize: 'vertical' }} />
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={save}
          disabled={disabled || busy || text.trim() === saved.trim()}>{t('about.save')}</button>
        <span style={{ fontSize: 11, color: 'var(--muted)' }}>{t(where === 'profile' ? 'about.effectProfile' : 'about.effect')}</span>
      </div>
    </details>
  )
}
