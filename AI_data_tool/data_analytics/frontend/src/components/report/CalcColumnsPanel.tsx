import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { columnsApi, calcColumnsApi, customFunctionsApi } from '../../services/api'
import type { CalcColumn, CalcColumnFormat, CustomFunction, DatasetColumn } from '../../services/api'
import CustomFunctionsPanel from './CustomFunctionsPanel'
import { useConfirm } from '../ui/ConfirmDialog'

import { funcCats, type FuncCat } from './calcColumns/catalog'
import { BuilderModal } from './calcColumns/BuilderModal'
import { useT } from '../../i18n'
// ── Props ─────────────────────────────────────────────────────────────────────

interface Props {
  datasetId: number
  columns: DatasetColumn[]
  onChanged: (cols: CalcColumn[]) => void
}

const BLANK = { name: '', expression: '', format: undefined as CalcColumnFormat | undefined }

// ── Main component ────────────────────────────────────────────────────────────

export default function CalcColumnsPanel({ datasetId, columns, onChanged }: Props) {
  const confirm = useConfirm()
  const tr = useT()
  const [calcCols, setCalcCols] = useState<CalcColumn[]>([])
  const [editing,  setEditing]  = useState<typeof BLANK | null>(null)  // null = modal closed
  const [customFunctions, setCustomFunctions] = useState<CustomFunction[]>([])

  useEffect(() => {
    calcColumnsApi.list(datasetId).then(cols => { setCalcCols(cols); onChanged(cols) })
  }, [datasetId])

  useEffect(() => {
    customFunctionsApi.list(datasetId).then(setCustomFunctions)
  }, [datasetId])

  const customCat: FuncCat | null = customFunctions.length === 0 ? null : {
    label: tr('pg.panelsA.calc.custom'), color: '#818cf8',
    items: customFunctions.map(fn => {
      const n = fn.params.length
      return {
        label: `${fn.name}(${fn.params.join(', ')})`,
        snippet: `${fn.name}(${', '.repeat(Math.max(n - 1, 0))})`,
        back: n === 0 ? 0 : 2 * n - 1,
        hint: fn.expression,
      }
    }),
  }

  const functionsCatalog = customCat ? [...funcCats(tr), customCat] : funcCats(tr)

  const openAdd  = ()                => setEditing({ ...BLANK })
  const openEdit = (col: CalcColumn) => setEditing({ name: col.name, expression: col.expression, format: col.format })

  const handleSaved = (updated: CalcColumn[]) => {
    setCalcCols(updated); onChanged(updated); setEditing(null)
  }

  const del = async (name: string) => {
    // Referenced by name, like a measure: widgets and other calculated columns
    // built on this one stop resolving, across every report.
    if (!await confirm({
      title: tr('pg.panelsA.calc.deleteTitle', { name }),
      body: tr('pg.panelsA.calc.deleteBody'),
    })) return
    let updated: CalcColumn[]
    try {
      updated = await calcColumnsApi.delete(datasetId, name)
    } catch (e: any) {
      // E05: something still names it, so the server refused with the list.
      // This used to reject unhandled -- the person confirmed and nothing happened.
      if (e?.response?.status !== 409) throw e
      if (!await confirm({
        title: tr('pg.panelsA.inUse', { name }),
        body: tr('pg.panelsA.inUseBody', { detail: String(e.response.data?.detail ?? '').replace(/ Delete anyway with \?force=true\./, '') }),
        confirmLabel: tr('pg.panelsA.deleteAnyway'), destructive: true,
      })) return
      updated = await calcColumnsApi.delete(datasetId, name, true)
    }
    setCalcCols(updated); onChanged(updated)
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
        <span style={{ fontSize: 11, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em' }}>
          {tr('calc.title')}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={openAdd} style={{ fontSize: 11, padding:'2px 7px' }}>
          {tr('pg.panelsA.calc.add')}
        </button>
      </div>

      {/* Duplicate a data item: the copy is a real calculated column referencing the
          original, so it can carry its own default aggregation and format -- SAS's
          standard way of getting two aggregations from one column. */}
      <div style={{ marginBottom: 8 }}>
        <label htmlFor="dup-col-select" style={{ display:'block', fontSize: 10.5, fontWeight:700, color:'var(--muted)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:3 }}>
          {tr('calc.dup')}
        </label>
        <select id="dup-col-select" value="" style={{ width:'100%', fontSize:11 }}
          onChange={async e => {
            const col = e.target.value
            if (!col) return
            e.target.value = ''
            try {
              await columnsApi.duplicate(datasetId, col)
              const cols = await calcColumnsApi.list(datasetId)
              setCalcCols(cols); onChanged(cols)
            } catch { /* the API rejected it; the list stays as it was */ }
          }}>
          <option value="">{tr('pg.panelsA.chooseColumn')}</option>
          {columns.filter(c => c.dtype !== 'calculated').map(c =>
            <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </div>

      {/* Existing columns list */}
      {calcCols.map(col => (
        <div key={col.name} style={{ display:'flex', alignItems:'center', gap:5, padding:'5px 7px',
          background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:5, marginBottom:4 }}>
          <span style={{ color:'var(--accent)', fontSize:11, flexShrink:0 }}>ƒx</span>
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ fontSize:12, fontWeight:600, color:'var(--text)' }}><bdi>{col.name}</bdi></div>
            <div style={{ fontSize: 11, color:'var(--muted)', overflow:'hidden', textOverflow:'ellipsis',
              whiteSpace:'nowrap', fontFamily:'var(--mono)' }}><bdi dir="ltr">{col.expression}</bdi></div>
          </div>
          <button style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:12, padding:'0 3px' }}
            title={tr('pg.panelsA.edit')} onClick={() => openEdit(col)}>✏</button>
          <button style={{ background:'none', border:'none', cursor:'pointer', color:'var(--muted)', fontSize:14, padding:'0 3px' }}
            title={tr('pg.panelsA.delete')} onClick={() => del(col.name)}>×</button>
        </div>
      ))}

      {calcCols.length === 0 && (
        <p style={{ fontSize:11, color:'var(--muted)', textAlign:'center', padding:'8px 0' }}>
          {tr('calc.none')}
        </p>
      )}

      <CustomFunctionsPanel datasetId={datasetId} onChanged={setCustomFunctions} />

      {/* Builder modal */}
      {editing !== null && createPortal(
        <BuilderModal
          initial={editing}
          datasetId={datasetId}
          columns={columns}
          calcCols={calcCols}
          functionsCatalog={functionsCatalog}
          onSave={handleSaved}
          onClose={() => setEditing(null)}
        />,
        document.body,
      )}
    </div>
  )
}

// ── Builder modal ─────────────────────────────────────────────────────────────

