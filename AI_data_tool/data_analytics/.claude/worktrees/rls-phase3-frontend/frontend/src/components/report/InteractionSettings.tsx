import { useEffect } from 'react'
import type { Widget } from '../../types/report'
import { useCrossFilter } from './CrossFilterContext'

interface Props { widget: Widget }

const MODES = [
  { label: 'Two-way ⇄',        broadcasts: true,  receives: true  },
  { label: 'Broadcast only →', broadcasts: true,  receives: false },
  { label: 'Receive only ←',   broadcasts: false, receives: true  },
  { label: 'Isolated —',        broadcasts: false, receives: false },
]

export default function InteractionSettings({ widget }: Props) {
  const { setInteraction, interactions } = useCrossFilter()
  const current = interactions[widget.id] ?? { broadcasts: true, receives: true }

  useEffect(() => {
    setInteraction(widget.id, { broadcasts: true, receives: true })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [widget.id])

  const activeIdx = MODES.findIndex(m => m.broadcasts === current.broadcasts && m.receives === current.receives)

  return (
    <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px' }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
        Interaction mode
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {MODES.map((m, i) => (
          <button key={i} onClick={() => setInteraction(widget.id, m)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '6px 9px',
              background: i === activeIdx ? 'rgba(108,143,255,.12)' : 'transparent',
              border: i === activeIdx ? '1px solid var(--accent)' : '1px solid var(--border)',
              borderRadius: 6, cursor: 'pointer', color: i === activeIdx ? 'var(--accent)' : 'var(--muted)',
              fontFamily: 'var(--sans)', fontSize: 12, textAlign: 'left', transition: 'all .15s',
            }}>
            {m.label}
          </button>
        ))}
      </div>
    </div>
  )
}
