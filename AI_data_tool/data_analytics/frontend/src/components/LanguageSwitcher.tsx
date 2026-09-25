import { useEffect, useRef, useState } from 'react'
import { Check, Languages } from 'lucide-react'
import {
  LANGUAGE_DIRECTION, LANGUAGE_LABEL, useDirection, type Language,
} from '../contexts/DirectionContext'
import { useT } from '../i18n'
import { getDigits, setDigits } from '../lib/arabicFormats'

const LANGUAGES: Language[] = ['en', 'ar']

/**
 * Language picker for the top bar.
 *
 * Picking a language sets the reading direction with it (Arabic → RTL) and
 * swaps the chrome strings from `src/i18n`. The rail keeps its standalone
 * direction toggle for reading English content in an RTL layout, or vice versa.
 */
export default function LanguageSwitcher() {
  const { language, setLanguage } = useDirection()
  const t = useT()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div ref={rootRef} style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen(o => !o)}
        aria-label={t('lang.aria', { name: LANGUAGE_LABEL[language] })}
        aria-expanded={open} aria-haspopup="menu"
        title={t('lang.title', { name: LANGUAGE_LABEL[language] })}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'none',
          border: 'none', cursor: 'pointer', padding: '5px 7px', borderRadius: 8,
          color: open ? 'var(--accent)' : 'var(--muted)', fontFamily: 'var(--sans)' }}>
        <Languages size={17} strokeWidth={1.9} aria-hidden />
        {/* The current language in its own script: a reader scanning for Arabic
            finds العربية, not the string "AR". */}
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}>
          {language}
        </span>
      </button>

      {open && (
        <div role="menu" aria-label={t('lang.menu')}
          style={{ position: 'absolute', insetInlineEnd: 0, top: '115%', zIndex: 900,
            minWidth: 210, background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 10, boxShadow: '0 8px 24px rgb(15 23 42 / .12)', padding: 6 }}>
          {LANGUAGES.map(l => (
            <button key={l} type="button" role="menuitemradio" aria-checked={l === language}
              onClick={() => { setLanguage(l); setOpen(false) }}
              lang={l} dir={LANGUAGE_DIRECTION[l]}
              style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                background: l === language ? 'var(--accent-soft)' : 'none', border: 'none',
                cursor: 'pointer', textAlign: 'start', padding: '8px 10px', borderRadius: 7,
                fontSize: 13, color: l === language ? 'var(--accent)' : 'var(--text)',
                fontWeight: l === language ? 650 : 400, fontFamily: 'var(--sans)' }}>
              <span aria-hidden style={{ width: 14, display: 'inline-flex', flexShrink: 0 }}>
                {l === language && <Check size={13} />}
              </span>
              <span style={{ flex: 1 }}>{LANGUAGE_LABEL[l]}</span>
              <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase' }}>
                {LANGUAGE_DIRECTION[l]}
              </span>
            </button>
          ))}
          {/* Digits are a reader preference, separate from the language:
              the Gulf mostly reads 123, Egypt ١٢٣ (Phase 7.5). */}
          <div role="group" aria-label="Digits" style={{ display: 'flex', alignItems: 'center', gap: 6,
            margin: '6px 8px 0', borderTop: '1px solid var(--border)', paddingTop: 6, fontSize: 12 }}>
            <span style={{ color: 'var(--muted)', flex: 1 }}>{language === 'ar' ? 'الأرقام' : 'Digits'}</span>
            {(['latn', 'arab'] as const).map(d => (
              <button key={d} type="button" role="menuitemradio" aria-checked={getDigits() === d}
                title={d === 'arab' ? 'Arabic-Indic digits (reloads the page)' : 'Western digits (reloads the page)'}
                onClick={() => { if (getDigits() !== d) { setDigits(d); window.location.reload() } }}
                style={{ border: '1px solid var(--border)', borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
                  background: getDigits() === d ? 'var(--accent-soft)' : 'none',
                  color: getDigits() === d ? 'var(--accent)' : 'var(--text)', fontFamily: 'var(--sans)' }}>
                {d === 'arab' ? '١٢٣' : '123'}
              </button>
            ))}
          </div>
          <p style={{ fontSize: 10.5, color: 'var(--muted)', lineHeight: 1.45,
            margin: '6px 8px 2px', borderTop: '1px solid var(--border)', paddingTop: 6 }}>
            {t('lang.hint')}
          </p>
        </div>
      )}
    </div>
  )
}
