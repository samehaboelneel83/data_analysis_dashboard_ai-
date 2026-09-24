/**
 * Page setup for the server PDF (MASTER_PLAN Phase 5 item 6): paper,
 * orientation, whether to include the contents page, and which pages.
 */
import { useState } from 'react'
import { useModalDialog } from '../ui/useModalDialog'

export interface PdfOptions { paper: 'A4' | 'A3' | 'Letter'; orientation: 'landscape' | 'portrait'; contents: boolean; pages: number[] }

export default function PdfOptionsDialog({ pages, onDownload, onClose }: {
  pages: { id: number; name: string }[]
  onDownload: (o: PdfOptions) => void
  onClose: () => void
}) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  const [o, setO] = useState<PdfOptions>({ paper: 'A4', orientation: 'landscape', contents: true, pages: pages.map(p => p.id) })
  const lbl: React.CSSProperties = { display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', margin: '8px 0 4px' }
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label="Download PDF" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 18,
          width: 'min(380px, calc(100vw - 32px))', fontSize: 13 }}>
        <b>Download PDF</b>
        <label style={lbl} htmlFor="pdf-paper">Paper</label>
        <select id="pdf-paper" value={o.paper} onChange={e => setO({ ...o, paper: e.target.value as PdfOptions['paper'] })} style={{ width: '100%' }}>
          <option value="A4">A4</option><option value="Letter">Letter</option><option value="A3">A3</option>
        </select>
        <div style={lbl}>Orientation</div>
        {(['landscape', 'portrait'] as const).map(v => (
          <label key={v} style={{ marginInlineEnd: 12 }}>
            <input type="radio" name="pdf-orientation" checked={o.orientation === v} onChange={() => setO({ ...o, orientation: v })} /> {v === 'landscape' ? 'Landscape' : 'Portrait'}
          </label>
        ))}
        <label style={{ display: 'block', marginTop: 8 }}>
          <input type="checkbox" checked={o.contents} onChange={e => setO({ ...o, contents: e.target.checked })} /> Contents page
        </label>
        {pages.length > 1 && (<>
          <div style={lbl}>Pages</div>
          {pages.map(p => (
            <label key={p.id} style={{ display: 'block' }}>
              <input type="checkbox" checked={o.pages.includes(p.id)}
                onChange={() => setO({ ...o, pages: o.pages.includes(p.id) ? o.pages.filter(x => x !== p.id) : [...o.pages, p.id] })} /> {p.name}
            </label>
          ))}
        </>)}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
          <button type="button" className="btn btn-sm" onClick={onClose}>Cancel</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={o.pages.length === 0}
            title={o.pages.length === 0 ? 'Choose at least one page' : undefined} onClick={() => onDownload(o)}>Download</button>
        </div>
      </div>
    </div>
  )
}
