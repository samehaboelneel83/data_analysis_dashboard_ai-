import { useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../services/api'
import { useModalDialog } from './ui/useModalDialog'

/** "Use in Python" (Phase 7.6): the governed-frame snippet for this dataset.
 *  The key is never shown here -- it is created once under API keys. */
export default function NotebookSnippet({ datasetId, datasetName }: { datasetId: number; datasetName: string }) {
  const [open, setOpen] = useState(false)
  const base = String(api.defaults.baseURL ?? '').replace(/\/api\/v1\/?$/, '') || window.location.origin
  const code = `from datalytics_client import Datalytics   # clients/python in the repository

dl = Datalytics("${base}", api_key="dl_…")    # Settings → API keys; acts as you
df = dl.frame(${datasetId})                     # ${datasetName}: the rows you may see
summary = dl.query(${datasetId}, dimensions=[...], measures=[{"column": ..., "agg": "sum"}])`
  return (<>
    <button className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}
      title="Read this dataset from a notebook, under your own security">🐍 Use in Python</button>
    {open && <Dialog code={code} onClose={() => setOpen(false)} />}
  </>)
}

function Dialog({ code, onClose }: { code: string; onClose: () => void }) {
  const ref = useModalDialog<HTMLDivElement>(onClose)
  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.45)',
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label="Use in Python" onClick={e => e.stopPropagation()}
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius)',
          padding: 18, width: 'min(640px, calc(100vw - 32px))', display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <b>Use this dataset in Python</b>
          <button type="button" className="btn btn-sm" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--muted)', margin: 0 }}>
          A notebook gets exactly what your dashboards show: your row and column security, the dataset's prep,
          calculated columns and measures, its export policy and sensitivity label. Every call is audited.
        </p>
        <pre data-testid="notebook-code" dir="ltr" style={{ fontSize: 12, background: 'var(--surface2)', padding: 10,
          borderRadius: 6, overflow: 'auto', margin: 0 }}>{code}</pre>
        <button className="btn btn-sm" style={{ alignSelf: 'flex-start' }}
          onClick={() => navigator.clipboard.writeText(code).then(() => toast.success('Copied')).catch(() => toast.error('Could not copy'))}>
          Copy
        </button>
      </div>
    </div>
  )
}
