import { useEffect, useRef, useState } from 'react'
import { Check, FileText, X } from 'lucide-react'
import type { OpenReport } from '../../lib/openReports'
import { useT } from '../../i18n'

/**
 * "Opened reports (3)" in the report header, as SAS VA keeps it: one button,
 * a list of the reports open in this tab (the current one ticked), a close
 * control on each, and "Close all reports". It replaces the row of tabs that
 * took a whole strip of the page from one report at a time.
 */
export default function OpenReportsMenu({ reports, currentId, onOpen, onClose, onCloseAll }: {
  reports: OpenReport[]
  currentId: number
  onOpen: (id: number) => void
  onClose: (id: number) => void
  onCloseAll: () => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])
  if (reports.length < 2) return null
  const label = t('openReports.button', { n: reports.length })
  return (
    <div ref={ref} style={{ position: 'relative' }} data-testid="open-reports">
      <button type="button" className="btn btn-ghost btn-sm" aria-haspopup="menu" aria-expanded={open}
        onClick={() => setOpen(o => !o)} style={{ color: 'var(--accent)', fontWeight: 600 }}>
        {label}
      </button>
      {open && (
        <div role="menu" aria-label={label} className="dl-menu"
          style={{ position: 'absolute', insetInlineEnd: 0, top: '110%', zIndex: 700, minWidth: 240, padding: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 700, padding: '6px 10px 4px' }}>{t('openReports.title')}</div>
          {reports.map(r => {
            const current = r.id === currentId
            return (
              <div key={r.id} style={{ display: 'flex', alignItems: 'center' }}>
                <button type="button" role="menuitemradio" aria-checked={current}
                  onClick={() => { setOpen(false); if (!current) onOpen(r.id) }}
                  className="dl-menu__item" style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                  <span style={{ inlineSize: 14, flex: 'none' }}>{current && <Check size={13} aria-hidden />}</span>
                  <FileText size={13} aria-hidden style={{ flex: 'none' }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.name}</span>
                </button>
                <button type="button" aria-label={t('openReports.close', { name: r.name })}
                  title={t('openReports.closeHint')} onClick={() => onClose(r.id)}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: '4px 8px' }}>
                  <X size={12} aria-hidden />
                </button>
              </div>
            )
          })}
          <div role="separator" style={{ height: 1, background: 'var(--border)', margin: '4px 2px' }} />
          <button type="button" role="menuitem" className="dl-menu__item" onClick={() => { setOpen(false); onCloseAll() }}>
            {t('openReports.closeAll')}
          </button>
        </div>
      )}
    </div>
  )
}
