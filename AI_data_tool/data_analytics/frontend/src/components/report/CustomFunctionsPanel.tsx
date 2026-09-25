import { useEffect, useState } from 'react'
import { customFunctionsApi } from '../../services/api'
import type { CustomFunction } from '../../services/api'
import { useConfirm } from '../ui/ConfirmDialog'
import { useT } from '../../i18n'

/**
 * Management surface for a dataset's custom calculated-column functions --
 * named, parameterized expression templates (services/custom_functions.py
 * on the backend). Kept separate from CalcColumnsPanel, which already
 * merges this panel's list into the expression palette it hands to
 * ExpressionBuilder.
 */
const BLANK = { name: '', params: '', expression: '' }

export default function CustomFunctionsPanel({ datasetId, onChanged }: {
  datasetId: number
  onChanged: (fns: CustomFunction[]) => void
}) {
  const confirm = useConfirm()
  const tr = useT()
  const [functions, setFunctions] = useState<CustomFunction[]>([])
  const [editing, setEditing] = useState<typeof BLANK | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sampleValues, setSampleValues] = useState<Record<string, string>>({})
  const [previewResult, setPreviewResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    customFunctionsApi.list(datasetId).then(fns => { setFunctions(fns); onChanged(fns) })
  }, [datasetId])

  const params = (editing?.params ?? '').split(',').map(p => p.trim()).filter(Boolean)

  const openAdd = () => { setEditing({ ...BLANK }); setError(null); setPreviewResult(null); setSampleValues({}) }
  const openEdit = (fn: CustomFunction) => {
    setEditing({ name: fn.name, params: fn.params.join(', '), expression: fn.expression })
    setError(null); setPreviewResult(null); setSampleValues({})
  }

  const save = async () => {
    if (!editing || !editing.name.trim() || !editing.expression.trim()) return
    setError(null)
    try {
      const updated = await customFunctionsApi.save(datasetId,
        { name: editing.name.trim(), params, expression: editing.expression.trim() })
      setFunctions(updated); onChanged(updated); setEditing(null)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Could not save this function')
    }
  }

  const del = async (name: string) => {
    if (!await confirm({
      title: `Delete the custom function "${name}"?`,
      body: 'Any calculated column calling it stops working. This cannot be undone.',
    })) return
    const updated = await customFunctionsApi.delete(datasetId, name)
    setFunctions(updated); onChanged(updated)
  }

  const test = async () => {
    if (!editing) return
    setTesting(true); setPreviewResult(null)
    try {
      // Coerce each sample value to a number where parseable: the backend
      // evaluates them arithmetically, and a real dataset column arriving
      // through pandas is already numeric -- a hand-typed '100' must behave
      // the same way here, or a perfectly valid numeric function fails its
      // own preview.
      const coerced = Object.fromEntries(Object.entries(sampleValues).map(([k, v]) => {
        const n = Number(v)
        return [k, v.trim() !== '' && !Number.isNaN(n) ? n : v]
      }))
      const r = await customFunctionsApi.preview(datasetId, params, editing.expression.trim(), coerced)
      setPreviewResult(r.ok ? String(r.result) : (r.error ?? 'Preview failed'))
    } catch (err: any) {
      setPreviewResult(err?.response?.data?.detail ?? 'Preview failed')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>
          {tr('fn.title')}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={openAdd}
          style={{ fontSize: 11, padding:'2px 7px' }}>
          {tr('fn.new')}
        </button>
      </div>

      {functions.map(fn => (
        <div key={fn.name} style={{ display:'flex', alignItems:'center', gap:5, padding:'5px 7px',
          background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, marginBottom:4 }}>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:600 }}>{`${fn.name}(${fn.params.join(', ')})`}</div>
            <div style={{ fontSize: 11, color:'var(--muted)', fontFamily:'var(--mono)' }}>{fn.expression}</div>
          </div>
          <button style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:12, padding:'0 3px' }}
            title="Edit" onClick={() => openEdit(fn)}>✏</button>
          <button title="Delete" onClick={() => del(fn.name)}
            style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:14 }}>×</button>
        </div>
      ))}

      {functions.length === 0 && (
        <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'8px 0' }}>
          {tr('fn.none')}
        </p>
      )}

      {editing !== null && (
        <div style={{ border:'1px solid var(--border)', borderRadius:7, padding:10, marginTop:8 }}>
          <label htmlFor="cf-name" style={{ display:'block', fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Function name</label>
          <input id="cf-name" value={editing.name} onChange={e => setEditing({ ...editing, name: e.target.value })}
            style={{ width:'100%', fontSize:12, marginBottom:6 }} />

          <label htmlFor="cf-params" style={{ display:'block', fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Parameters (comma-separated)</label>
          <input id="cf-params" value={editing.params} onChange={e => setEditing({ ...editing, params: e.target.value })}
            placeholder="revenue, cost" style={{ width:'100%', fontSize:12, marginBottom:6 }} />

          <label htmlFor="cf-expr" style={{ display:'block', fontSize: 11, color:'var(--muted)', marginBottom:3 }}>Expression</label>
          <textarea id="cf-expr" value={editing.expression} onChange={e => setEditing({ ...editing, expression: e.target.value })}
            style={{ width:'100%', fontSize:12, fontFamily:'var(--mono)', marginBottom:6 }} rows={2} />

          {params.map(p => (
            <div key={p} style={{ marginBottom: 4 }}>
              <label htmlFor={`cf-sample-${p}`} style={{ fontSize: 11, color:'var(--muted)' }}>Sample value for {p}</label>
              <input id={`cf-sample-${p}`} value={sampleValues[p] ?? ''}
                onChange={e => setSampleValues({ ...sampleValues, [p]: e.target.value })}
                style={{ width:'100%', fontSize:12 }} />
            </div>
          ))}

          {error && <p role="alert" style={{ fontSize:11, color:'var(--danger)' }}>{error}</p>}
          {previewResult !== null && <p style={{ fontSize:12 }}>{previewResult}</p>}

          <div style={{ display:'flex', gap:6, marginTop:6 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditing(null)} style={{ fontSize:11 }}>Cancel</button>
            <button className="btn btn-ghost btn-sm" onClick={test} disabled={testing || !editing.expression.trim()} title={!editing.expression.trim() ? 'Write the function body first' : undefined} style={{ fontSize:11 }}>
              {testing ? 'Testing…' : 'Test'}
            </button>
            <button className="btn btn-primary btn-sm" onClick={save} style={{ fontSize:11, marginInlineStart:'auto' }}>Save</button>
          </div>
        </div>
      )}
    </div>
  )
}
