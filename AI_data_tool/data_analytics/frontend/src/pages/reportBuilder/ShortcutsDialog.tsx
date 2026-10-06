import { X } from 'lucide-react'
import { useModalDialog } from '../../components/ui/useModalDialog'
import { useT, type MessageKey } from '../../i18n'

/** The builder's shortcuts, as the prototype's sheet: Canvas and Report. Only
 *  keys the builder binds are listed (v1's set, plus Ctrl+D, Ctrl + / − and
 *  Ctrl+/ from the prototype, bound in 7e5). */
const GROUPS: [MessageKey, [MessageKey, string[]][]][] = [
  ['bd.keys.canvas', [
    ['bd.keys.select', ['Shift', 'Click']],
    ['bd.keys.move', ['↑', '↓', '←', '→']],
    ['bd.keys.resize', ['Shift', '↑ ↓ ← →']],
    ['bd.keys.duplicate', ['Ctrl', 'D']],
    ['bd.keys.delete', ['Del']],
    ['bd.keys.deselect', ['Esc']],
  ]],
  ['bd.keys.report', [
    ['bd.keys.undo', ['Ctrl', 'Z']],
    ['bd.keys.redo', ['Ctrl', 'Y']],
    ['bd.keys.zoom', ['Ctrl', '+ / −']],
    ['bd.keys.ask', ['Ctrl', '/']],
    ['bd.keys.jump', ['Ctrl', 'K']],
    ['bd.keys.sheet', ['?']],
  ]],
]

export default function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const t = useT()
  const ref = useModalDialog<HTMLDivElement>(onClose)
  return (
    <div className="dl-bd-scrim" onClick={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="dl-bd-keys-t" className="dl-bd-keys" onClick={e => e.stopPropagation()}>
        <div className="hd">
          <h2 id="dl-bd-keys-t">{t('bd.keys.title')}</h2>
          <button type="button" className="dl-bd-ib" onClick={onClose} aria-label={t('bd.keys.close')} title={t('bd.keys.close')}><X size={16} aria-hidden /></button>
        </div>
        {GROUPS.map(([g, rows]) => (
          <section key={g}>
            <h3 className="dl-bd-gh">{t(g)}</h3>
            <dl>
              {rows.map(([label, keys]) => (
                <div key={label}>
                  <dt>{t(label)}</dt>
                  <dd dir="ltr">{keys.map(k => <kbd key={k}>{k}</kbd>)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </div>
  )
}
