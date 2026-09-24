import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { translationsApi } from '../../services/api'
import type { Report, Widget } from '../../types/report'

/**
 * Localisation authoring: pick a locale, translate widget titles (and text
 * widgets' content). The authored strings stay the single source of truth;
 * translations are VIEW-time overrides selected by the viewer's browser
 * locale, exactly SAS's model.
 */
export default function TranslationsPane({ report, onSaved }: {
  report: Report
  onSaved?: () => void
}) {
  const [all, setAll] = useState<Record<string, Record<string, string>>>({})
  const [locale, setLocale] = useState('')
  const [draft, setDraft] = useState<Record<string, string>>({})

  useEffect(() => {
    translationsApi.list(report.id).then(setAll).catch(() => setAll({}))
  }, [report.id])

  const pick = (loc: string) => {
    setLocale(loc)
    setDraft(all[loc] ?? {})
  }

  const save = async () => {
    if (!locale) return
    try {
      const saved = await translationsApi.save(report.id, locale, draft)
      setAll(p => {
        const next = { ...p }
        if (Object.keys(saved).length) next[locale] = saved
        else delete next[locale]
        return next
      })
      toast.success(Object.keys(saved).length ? `Saved ${locale} translations` : `Removed ${locale}`)
      onSaved?.()
    } catch { toast.error('Could not save translations') }
  }

  const widgets: { w: Widget; page: string }[] = report.pages.flatMap(p =>
    (p.widgets ?? []).map(w => ({ w, page: p.name })))
  const titled = widgets.filter(x => x.w.title || x.w.widget_type === 'text')

  return (
    <div style={{ padding: 12, overflowY: 'auto', height: '100%' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
        Translations
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
        Viewers whose browser locale matches see these instead of the authored text. Blank entries fall back.
      </p>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
        <input aria-label="Locale" value={locale} onChange={e => pick(e.target.value.trim())}
          placeholder="locale, e.g. ar or fr" style={{ fontSize: 12, width: 110 }} />
        {Object.keys(all).map(loc => (
          <button key={loc} className="btn" style={{ fontSize: 10 }} onClick={() => pick(loc)}>{loc}</button>
        ))}
      </div>

      {locale && (
        <>
          {titled.map(({ w, page }) => (
            <div key={w.id} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>
                {page} · {w.title || w.widget_type}
              </div>
              {w.title && (
                <input aria-label={`Translation of ${w.title}`} value={draft[`w${w.id}`] ?? ''}
                  placeholder={w.title}
                  onChange={e => setDraft(p => ({ ...p, [`w${w.id}`]: e.target.value }))}
                  style={{ fontSize: 12, width: '100%' }} />
              )}
              {w.widget_type === 'text' && (
                <textarea aria-label={`Translation of text ${w.id}`} rows={2}
                  value={draft[`c${w.id}`] ?? ''}
                  placeholder={String((w.config as { content?: string })?.content ?? '')}
                  onChange={e => setDraft(p => ({ ...p, [`c${w.id}`]: e.target.value }))}
                  style={{ fontSize: 12, width: '100%', marginTop: 4 }} />
              )}
            </div>
          ))}
          <button className="btn btn-primary" style={{ fontSize: 11 }} onClick={() => void save()}>
            Save {locale}
          </button>
        </>
      )}
    </div>
  )
}
