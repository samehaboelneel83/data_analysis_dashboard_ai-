import { useState, useEffect, useRef } from 'react'
import type { ReportPage, PageType } from '../../types/report'
import type { DatasetColumn } from '../../services/api'

interface Props {
  page:     ReportPage
  columns:  DatasetColumn[]
  onUpdate: (data: Partial<ReportPage>) => void
}

const PAGE_TYPES: { value: PageType; label: string; desc: string }[] = [
  { value: 'normal', label: 'Normal',  desc: 'Standard visible tab' },
  { value: 'hidden', label: 'Hidden',  desc: 'Tab hidden in view mode' },
  { value: 'popup',  label: 'Popup',   desc: 'Rendered as floating overlay' },
]

export default function PagePropertiesPanel({ page, columns, onUpdate }: Props) {
  const [name,          setName]          = useState(page.name)
  const [title,         setTitle]         = useState(page.title ?? '')
  const [pageType,      setPageType]      = useState<PageType>(page.page_type ?? 'normal')
  const [promptColumn,  setPromptColumn]  = useState(page.prompt_column ?? '')
  const [promptLabel,   setPromptLabel]   = useState(page.prompt_label ?? '')

  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = false
    setName(page.name)
    setTitle(page.title ?? '')
    setPageType(page.page_type ?? 'normal')
    setPromptColumn(page.prompt_column ?? '')
    setPromptLabel(page.prompt_label ?? '')
  }, [page.id])

  useEffect(() => {
    if (!mounted.current) { mounted.current = true; return }
    const timer = setTimeout(() => onUpdate({
      name:          name || page.name,
      title:         title || undefined,
      page_type:     pageType,
      prompt_column: promptColumn || undefined,
      prompt_label:  promptLabel || undefined,
    }), 500)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, title, pageType, promptColumn, promptLabel])

  const fld = (lbl: string, el: React.ReactNode) => (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: 'block', fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>{lbl}</label>
      {el}
    </div>
  )

  return (
    <div style={{ padding: '14px 14px 0', fontSize: 13 }}>
      <div style={{ fontWeight: 700, marginBottom: 14, fontSize: 13, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>
        Page Properties
      </div>

      {fld('Tab name', (
        <input value={name} onChange={e => setName(e.target.value)} style={{ width: '100%' }} placeholder="Page name" />
      ))}

      {fld('Display title', (
        <input value={title} onChange={e => setTitle(e.target.value)} style={{ width: '100%' }} placeholder="Shown as heading on page" />
      ))}

      {fld('Page type', (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {PAGE_TYPES.map(pt => (
            <label key={pt.value} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', padding: '7px 8px', borderRadius: 6, background: pageType === pt.value ? 'rgba(108,143,255,.12)' : 'transparent', border: `1px solid ${pageType === pt.value ? 'var(--accent)' : 'var(--border)'}`, transition: 'all .15s' }}>
              <input type="radio" name="page_type" value={pt.value} checked={pageType === pt.value} onChange={() => setPageType(pt.value)} style={{ marginTop: 2, accentColor: 'var(--accent)' }} />
              <div>
                <div style={{ fontWeight: 600, fontSize: 12, color: pageType === pt.value ? 'var(--accent)' : 'var(--text)' }}>{pt.label}</div>
                <div style={{ fontSize: 10, color: 'var(--muted)' }}>{pt.desc}</div>
              </div>
            </label>
          ))}
        </div>
      ))}

      <div style={{ borderTop: '1px solid var(--border)', margin: '16px 0' }} />

      <div style={{ fontWeight: 700, marginBottom: 10, fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
        Page Prompt
      </div>
      <p style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.5 }}>
        A prompt lets viewers filter all widgets by entering a value. Select the column to filter on.
      </p>

      {fld('Filter column', (
        <select value={promptColumn} onChange={e => setPromptColumn(e.target.value)} style={{ width: '100%' }}>
          <option value="">— no prompt —</option>
          {columns.map(c => <option key={c.name} value={c.name}>{c.name} ({c.dtype})</option>)}
        </select>
      ))}

      {promptColumn && fld('Prompt label', (
        <input value={promptLabel} onChange={e => setPromptLabel(e.target.value)} style={{ width: '100%' }} placeholder={`Filter by ${promptColumn}`} />
      ))}
    </div>
  )
}