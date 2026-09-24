import { BarChart3, Download, Share2, Sparkles, Trash2 } from 'lucide-react'
import { IconLabel } from 'datalytics-frontend'

// IconLabel exists to keep the mark and the word tinting together, so every
// cell shows it inside something that has its own text colour.

export function InButtons() {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <button className="btn btn-primary"><IconLabel icon={Sparkles}>Ask AI</IconLabel></button>
      <button className="btn"><IconLabel icon={Download}>Export</IconLabel></button>
      <button className="btn btn-ghost"><IconLabel icon={Share2}>Share</IconLabel></button>
      <button className="btn btn-danger"><IconLabel icon={Trash2}>Delete</IconLabel></button>
    </div>
  )
}

export function InMenu() {
  return (
    <div className="card" style={{ padding: 8, width: 200 }}>
      {[
        { icon: BarChart3, label: 'Open report' },
        { icon: Share2, label: 'Share…' },
        { icon: Download, label: 'Export as PPTX' },
      ].map(({ icon, label }) => (
        <div key={label} style={{ padding: '7px 10px', fontSize: 13, cursor: 'pointer' }}>
          <IconLabel icon={icon}>{label}</IconLabel>
        </div>
      ))}
    </div>
  )
}

export function Sizes() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'flex-start' }}>
      <IconLabel icon={BarChart3} size={13}>Default, 13px</IconLabel>
      <span style={{ fontSize: 15 }}><IconLabel icon={BarChart3} size={16}>Larger, 16px</IconLabel></span>
      <span style={{ fontSize: 11 }}><IconLabel icon={BarChart3} size={11}>Dense, 11px</IconLabel></span>
    </div>
  )
}
