import { X } from 'lucide-react'
import { useT, type MessageKey } from '../../i18n'
import { BORDERS, FONTS, tidyStyle, type DashboardStyle } from '../../lib/dashboardStyle'
import '../../pages/templates/templates.css'

const WEIGHTS = [300, 400, 500, 600, 700, 800] as const
const SHADOW_KEYS = ['none', 'soft', 'raised', 'strong'] as const

/**
 * The dashboard's look, for every page of it: light or dark, font, title,
 * card border, corners, shadow, backgrounds. Each control is one key of the
 * style (lib/dashboardStyle); an empty control means "as the app". A widget's
 * own appearance settings still win over all of this.
 */
export default function DashboardStylePanel({ style, onChange }: {
  style: DashboardStyle
  onChange: (next: DashboardStyle) => void
}) {
  const t = useT()
  const set = <K extends keyof DashboardStyle>(key: K, value: DashboardStyle[K] | undefined) =>
    onChange(tidyStyle({ ...style, [key]: value }))

  const select = (key: keyof DashboardStyle, label: MessageKey, options: { value: string; label: string }[], empty: MessageKey) => (
    <div>
      <label htmlFor={`ds-${key}`}>{t(label)}</label>
      <select id={`ds-${key}`} value={String(style[key] ?? '')}
        onChange={e => set(key, (e.target.value || undefined) as never)}>
        <option value="">{t(empty)}</option>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
  const number = (key: keyof DashboardStyle, label: MessageKey, min: number, max: number) => (
    <div>
      <label htmlFor={`ds-${key}`}>{t(label)} ({t('tpl.style.px')})</label>
      <input id={`ds-${key}`} type="number" min={min} max={max} value={(style[key] as number | undefined) ?? ''}
        onChange={e => {
          const v = e.target.value === '' ? undefined : Math.max(min, Math.min(max, Number(e.target.value)))
          set(key, (Number.isFinite(v as number) ? v : undefined) as never)
        }} />
    </div>
  )
  const color = (key: keyof DashboardStyle, label: MessageKey) => (
    <div>
      <label htmlFor={`ds-${key}`}>{t(label)}</label>
      <div className="color">
        <input id={`ds-${key}`} type="color" value={(style[key] as string | undefined) ?? '#ffffff'}
          onChange={e => set(key, e.target.value as never)} />
        <bdi style={{ fontSize: 11, color: 'var(--muted)' }}>{(style[key] as string | undefined) ?? '—'}</bdi>
        {style[key] != null && (
          <button type="button" onClick={() => set(key, undefined)} aria-label={t('tpl.style.clear', { what: t(label) })}
            title={t('tpl.style.clear', { what: t(label) })}><X size={12} aria-hidden /></button>
        )}
      </div>
    </div>
  )

  return (
    <div data-testid="dashboard-style">
      <div style={{ fontSize: 10.5, color: 'var(--muted)', marginBottom: 8 }}>{t('tpl.style.help')}</div>
      <div className="dl-style">
        {select('mode', 'tpl.style.mode', [
          { value: 'light', label: t('tpl.style.mode.light') }, { value: 'dark', label: t('tpl.style.mode.dark') }], 'tpl.style.mode.auto')}
        {select('font_family', 'tpl.style.font', FONTS.map(f => ({ value: f, label: t(`tpl.style.font.${f}`) })), 'tpl.style.font.default')}
        {number('font_size', 'tpl.style.fontSize', 10, 24)}
        {number('title_size', 'tpl.style.titleSize', 10, 32)}
        {select('title_weight', 'tpl.style.titleWeight', WEIGHTS.map(w => ({ value: String(w), label: t(`tpl.style.weight.${w}`) })), 'tpl.style.font.default')}
        {select('title_align', 'tpl.style.titleAlign', (['start', 'center', 'end'] as const).map(a => ({ value: a, label: t(`tpl.style.align.${a}`) })), 'tpl.style.font.default')}
        {color('title_color', 'tpl.style.titleColor')}
        {color('text_color', 'tpl.style.textColor')}
        {number('number_size', 'tpl.style.numberSize', 16, 72)}
        {color('accent', 'tpl.style.accent')}
        {color('page_background', 'tpl.style.pageBg')}
        {color('card_background', 'tpl.style.cardBg')}
        {select('border_style', 'tpl.style.border', BORDERS.map(b => ({ value: b, label: t(`tpl.style.border.${b}`) })), 'tpl.style.border.default')}
        {number('border_width', 'tpl.style.borderWidth', 0, 8)}
        {color('border_color', 'tpl.style.borderColor')}
        {number('radius', 'tpl.style.radius', 0, 32)}
        {select('shadow', 'tpl.style.shadow', SHADOW_KEYS.map(s => ({ value: s, label: t(`tpl.style.shadow.${s}`) })), 'tpl.style.shadow.default')}
        <div className="wide">
          <button type="button" className="btn btn-ghost btn-sm" disabled={Object.keys(style).length === 0} onClick={() => onChange({})}>
            {t('tpl.style.reset')}
          </button>
        </div>
      </div>
    </div>
  )
}
